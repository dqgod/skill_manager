"""Skill 哈希计算与对比去重 (F3)"""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.models.connection import Connection
from src.services.skill_scanner import SkillInfo
from src.services.ssh_manager import SSHManager
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DiffResult:
    synced: list[SkillInfo] = field(default_factory=list)
    local_only: list[SkillInfo] = field(default_factory=list)
    remote_only: list[SkillInfo] = field(default_factory=list)
    conflict: list[tuple[SkillInfo, SkillInfo]] = field(default_factory=list)

    @property
    def has_differences(self) -> bool:
        return bool(self.local_only or self.remote_only or self.conflict)

    @property
    def total(self) -> int:
        return len(self.synced) + len(self.local_only) + len(self.remote_only) + len(self.conflict)


class SkillHasher:
    """Compute SHA-256 hashes and compare skill sets."""

    def __init__(self, ssh_manager: Optional[SSHManager] = None):
        self._ssh = ssh_manager

    # ---- Hashing ----

    @staticmethod
    def compute_local_hash(fs_path: str) -> str:
        """SHA-256 of file or directory. Directory hash is deterministic
        across machines: sorted concatenation of all file hashes."""
        p = Path(fs_path)
        if not p.exists():
            return ""
        if p.is_file():
            return SkillHasher._hash_file(p)
        return SkillHasher._hash_directory(p)

    def compute_remote_hash(self, conn, remote_path: str) -> str:
        """Compute hash on remote machine via SSH."""
        if self._ssh is None:
            return ""
        return self._ssh.compute_remote_hash(conn, remote_path)

    # ---- Comparison ----

    def compare(self, local: list[SkillInfo],
                remote: list[SkillInfo],
                remote_connection: Optional[Connection] = None) -> DiffResult:
        """Compare two skill lists and classify each skill."""
        result = DiffResult()

        # index by key
        local_by_key: dict[str, SkillInfo] = {}
        for s in local:
            k = s.key
            if k not in local_by_key:
                local_by_key[k] = s

        remote_by_key: dict[str, SkillInfo] = {}
        for s in remote:
            k = s.key
            if k not in remote_by_key:
                remote_by_key[k] = s

        all_keys = set(local_by_key.keys()) | set(remote_by_key.keys())

        for key in sorted(all_keys):
            l = local_by_key.get(key)
            r = remote_by_key.get(key)

            if l and r:
                # both exist — compute hashes if not already done
                if l.hash is None:
                    l.hash = self.compute_local_hash(l.path)
                if r.hash is None:
                    if r.device_type == "remote" and self._ssh:
                        r.hash = self.compute_remote_hash(remote_connection, r.path)
                    else:
                        # this is a local skill stored in remote list (unlikely)
                        r.hash = self.compute_local_hash(r.path)

                if l.hash == r.hash:
                    result.synced.append(l)
                else:
                    result.conflict.append((l, r))
            elif l and not r:
                result.local_only.append(l)
            elif r and not l:
                result.remote_only.append(r)

        logger.debug(
            "Comparison: %d synced, %d local-only, %d remote-only, %d conflict",
            len(result.synced), len(result.local_only),
            len(result.remote_only), len(result.conflict),
        )
        return result

    def classify_skills(self, local: list[SkillInfo],
                        remote: list[SkillInfo],
                        remote_connection: Optional[Connection] = None) -> list[SkillInfo]:
        """Tag each local skill with sync status and return tagged list."""
        if not remote:
            for s in local:
                s.hash = s.hash or "untagged"
            return local

        diff = self.compare(local, remote, remote_connection=remote_connection)

        synced_names = {(s.name, s.tool) for s in diff.synced}
        local_names = {(s.name, s.tool) for s in diff.local_only}
        conflict_names = {(s[0].name, s[0].tool) for s in diff.conflict}

        all_skills = list(local)
        for s in all_skills:
            key = (s.name, s.tool)
            if key in synced_names:
                s.hash = "synced"
            elif key in conflict_names:
                s.hash = "conflict"
            elif key in local_names:
                s.hash = "local-only"
            else:
                s.hash = "unknown"

        return all_skills

    def classify_remote_skills(self, local: list[SkillInfo],
                               remote: list[SkillInfo],
                               remote_connection: Optional[Connection] = None) -> list[SkillInfo]:
        """Tag each remote skill with sync status."""
        if not local:
            for s in remote:
                s.hash = "untagged"
            return remote

        diff = self.compare(local, remote, remote_connection=remote_connection)

        synced_names = {(s.name, s.tool) for s in diff.synced}
        remote_names = {(s.name, s.tool) for s in diff.remote_only}
        conflict_names = {(s[1].name, s[1].tool) for s in diff.conflict}

        all_skills = list(remote)
        for s in all_skills:
            key = (s.name, s.tool)
            if key in synced_names:
                s.hash = "synced"
            elif key in conflict_names:
                s.hash = "conflict"
            elif key in remote_names:
                s.hash = "remote-only"
            else:
                s.hash = "unknown"

        return all_skills

    # ---- Internal ----

    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _hash_directory(path: Path) -> str:
        """Deterministic directory hash based on relative paths and file hashes."""
        files = sorted(f for f in path.rglob("*") if f.is_file())
        if not files:
            return hashlib.sha256(b"").hexdigest()
        combined = hashlib.sha256()
        for f in files:
            rel = f.relative_to(path).as_posix()
            combined.update(f"{SkillHasher._hash_file(f)}  ./{rel}\n".encode())
        return combined.hexdigest()
