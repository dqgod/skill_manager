"""Skill 哈希计算与对比去重 (F3)"""

import fnmatch
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from src.config import (
    SKILL_IGNORE_DIRS,
    SKILL_IGNORE_FILE_GLOBS,
    SKILL_IGNORE_FILES,
)
from src.models.connection import Connection
from src.services.skill_scanner import SkillInfo
from src.services.ssh_manager import SSHManager
from src.utils.logger import get_logger

logger = get_logger(__name__)


def should_ignore_file(rel_path: str) -> bool:
    """Return True if the relative path should be excluded from hash/archive.

    rel_path uses POSIX separators ('/').
    """
    # any path component is an ignored directory?
    parts = [p for p in rel_path.split("/") if p]
    if not parts:
        return True
    for part in parts[:-1]:
        if part in SKILL_IGNORE_DIRS:
            return True
    name = parts[-1]
    if name in SKILL_IGNORE_FILES:
        return True
    for pat in SKILL_IGNORE_FILE_GLOBS:
        if fnmatch.fnmatch(name, pat):
            return True
    return False


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

    # Process-wide local hash cache: { (abs_path, mtime_ns_aggregate, size_total) -> sha }
    # We use the directory's recursive (mtime, size) tuple as the cache key —
    # if anything inside changed, the tuple changes and we recompute.
    _local_cache: dict[tuple, str] = {}
    _CACHE_LIMIT = 4096

    def __init__(self, ssh_manager: Optional[SSHManager] = None):
        self._ssh = ssh_manager

    # ---- Hashing ----

    @staticmethod
    def compute_local_hash(fs_path: str) -> str:
        """SHA-256 of file or directory. Directory hash is deterministic
        across machines: sorted concatenation of all file hashes.

        Repeated calls with an unchanged tree are O(stat) thanks to a small
        in-memory (mtime, size) cache.
        """
        p = Path(fs_path)
        if not p.exists():
            return ""
        if p.is_file():
            try:
                st = p.stat()
                key = (str(p.resolve()), st.st_mtime_ns, st.st_size)
            except OSError:
                key = None
            if key and key in SkillHasher._local_cache:
                return SkillHasher._local_cache[key]
            h = SkillHasher._hash_file(p)
            if key:
                SkillHasher._cache_put(key, h)
            return h
        # Directory: build a fingerprint from (rel_path, mtime_ns, size) tuples
        # of all eligible files.
        try:
            sig = SkillHasher._dir_signature(p)
        except OSError:
            sig = None
        if sig and sig in SkillHasher._local_cache:
            return SkillHasher._local_cache[sig]
        h = SkillHasher._hash_directory(p)
        if sig:
            SkillHasher._cache_put(sig, h)
        return h

    @staticmethod
    def _cache_put(key: tuple, value: str) -> None:
        # Naive bounded cache: drop an arbitrary entry once full.
        if len(SkillHasher._local_cache) >= SkillHasher._CACHE_LIMIT:
            try:
                SkillHasher._local_cache.pop(next(iter(SkillHasher._local_cache)))
            except StopIteration:
                pass
        SkillHasher._local_cache[key] = value

    @staticmethod
    def _dir_signature(path: Path) -> tuple:
        """Return a hashable fingerprint of a directory's tree.

        Cheap (`stat` only) yet specific enough to use as a cache key.
        """
        rel_entries: list[tuple] = []
        for f in path.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(path).as_posix()
            if should_ignore_file(rel):
                continue
            try:
                st = f.stat()
            except OSError:
                continue
            rel_entries.append((rel, st.st_mtime_ns, st.st_size))
        rel_entries.sort()
        return ("dir", str(path.resolve()), tuple(rel_entries))

    @classmethod
    def clear_cache(cls) -> None:
        cls._local_cache.clear()

    def compute_remote_hash(self, conn, remote_path: str) -> str:
        """Compute hash on remote machine via SSH."""
        if self._ssh is None:
            return ""
        return self._ssh.compute_remote_hash(conn, remote_path)

    # ---- Comparison ----

    def compare(self, local: list[SkillInfo],
                remote: list[SkillInfo],
                remote_connection: Optional[Connection] = None,
                *,
                left_connection: Optional[Connection] = None,
                right_connection: Optional[Connection] = None) -> DiffResult:
        """Compare two skill lists and classify each skill.

        New dual-source model: ``local`` / ``remote`` parameter names are
        kept for backward compatibility, but they really mean "left" and
        "right" — either side may now be a remote source. Hashing on each
        side is dispatched based on whether a connection was supplied for
        that side.

        Connection-resolution rules (in priority order):
          - left side  → ``left_connection`` if given else None (= local FS)
          - right side → ``right_connection`` if given else
                          ``remote_connection`` (legacy alias) else None
        """
        result = DiffResult()

        # Resolve per-side connections (legacy API back-compat).
        left_conn = left_connection
        right_conn = right_connection if right_connection is not None else remote_connection

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

        # ---- Bulk-hash phase ----------------------------------------------
        # Hash skills that appear on *both* sides — those are the only ones
        # whose hashes we actually need for the synced/conflict decision.
        intersect_keys = [k for k in all_keys
                          if k in local_by_key and k in remote_by_key]

        # Helper: gather paths-needing-hash for one side, then bulk-hash.
        def _ensure_side_hashed(by_key: dict, conn: Optional[Connection]) -> None:
            if not intersect_keys:
                return
            if conn is None:
                # Local FS side — compute_local_hash uses the on-disk cache.
                for k in intersect_keys:
                    s = by_key[k]
                    if s.hash is None or len(s.hash) != 64:
                        s.hash = self.compute_local_hash(s.path)
                return
            # Remote side — one bulk SSH call, fall back per-skill on error.
            need: list[str] = []
            for k in intersect_keys:
                s = by_key[k]
                if s.hash is None or len(s.hash) != 64:
                    need.append(s.path)
            if not need or self._ssh is None:
                return
            try:
                bulk = self._ssh.compute_remote_hashes(conn, need)
            except Exception as e:
                logger.warning("bulk remote hash failed, falling back: %s", e)
                bulk = {}
            for k in intersect_keys:
                s = by_key[k]
                if s.hash is None or len(s.hash) != 64:
                    h = bulk.get(s.path, "")
                    if not h:
                        h = self._ssh.compute_remote_hash(conn, s.path)
                    s.hash = h

        _ensure_side_hashed(local_by_key, left_conn)
        _ensure_side_hashed(remote_by_key, right_conn)

        # ---- Classification ----------------------------------------------
        for key in sorted(all_keys):
            l = local_by_key.get(key)
            r = remote_by_key.get(key)

            if l and r:
                # Final fallback: ensure both sides have a hash before deciding.
                if l.hash is None or len(l.hash) != 64:
                    if left_conn and self._ssh:
                        l.hash = self.compute_remote_hash(left_conn, l.path)
                    else:
                        l.hash = self.compute_local_hash(l.path)
                if r.hash is None or len(r.hash) != 64:
                    if right_conn and self._ssh:
                        r.hash = self.compute_remote_hash(right_conn, r.path)
                    else:
                        r.hash = self.compute_local_hash(r.path)

                if l.hash and l.hash == r.hash:
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
        """Deterministic directory hash based on relative paths and file hashes.

        Mirrors the remote command:
          (cd <dir> && find . -type f ... | sort -z |
           xargs -0 sha256sum | sha256sum)

        We must:
          - skip noise files (.DS_Store, *.swp, __pycache__, .git ...) so the
            two sides don't disagree just because one carries OS/editor litter;
          - sort by raw bytes (LC_ALL=C) so non-ASCII filenames produce the
            same order on macOS, Linux, and the remote shell;
          - emit "<hex>  ./<rel>\n" exactly like sha256sum does, including
            the leading "./" prefix that `find .` adds.
        """
        files: list[Path] = []
        for f in path.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(path).as_posix()
            if should_ignore_file(rel):
                continue
            files.append(f)
        if not files:
            return hashlib.sha256(b"").hexdigest()
        # raw-bytes sort = LC_ALL=C sort
        files.sort(key=lambda p: p.relative_to(path).as_posix().encode("utf-8"))
        combined = hashlib.sha256()
        for f in files:
            rel = f.relative_to(path).as_posix()
            combined.update(f"{SkillHasher._hash_file(f)}  ./{rel}\n".encode("utf-8"))
        return combined.hexdigest()
