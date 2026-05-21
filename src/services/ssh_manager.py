"""SSH 连接管理器：连接池、sftp、远程哈希计算 (F5)"""

import hashlib
import os
import shlex
import socket
import stat
import time
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional

import paramiko

from src.models.connection import Connection
from src.services.crypto_service import CryptoService
from src.utils.logger import get_logger

logger = get_logger(__name__)
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


@dataclass
class RemoteFileInfo:
    name: str
    path: str
    is_dir: bool
    size: int
    modified_at: float  # Unix timestamp


class SSHManager:
    """Manage SSH connections with lazy connect and idle timeout."""

    IDLE_TIMEOUT = 300  # seconds

    def __init__(self, crypto: Optional[CryptoService] = None):
        self._crypto = crypto or CryptoService()
        self._clients: dict[str, paramiko.SSHClient] = {}
        self._last_used: dict[str, float] = {}

    # ---- Connection Lifecycle ----

    def get_client(self, conn: Connection) -> paramiko.SSHClient:
        client = self._clients.get(conn.id)
        if client is None:
            client = self._connect(conn)
            self._clients[conn.id] = client
        elif not self._is_alive(client):
            client = self._connect(conn)
            self._clients[conn.id] = client
        self._last_used[conn.id] = time.time()
        return client

    def test(self, conn: Connection) -> tuple[bool, str]:
        """Test connection. Returns (success, error_message)."""
        try:
            client = self._connect(conn, timeout=10)
            _, stdout, _ = client.exec_command("echo ok", timeout=5)
            result = stdout.read().decode().strip()
            if result == "ok":
                return True, ""
            return False, f"unexpected response: {result}"
        except paramiko.AuthenticationException:
            return False, "认证失败：用户名或密码/密钥错误"
        except paramiko.SSHException as e:
            return False, f"SSH 连接错误：{e}"
        except socket.timeout:
            return False, f"连接超时：无法在 10 秒内连接到 {conn.host}:{conn.port}"
        except OSError as e:
            if "timed out" in str(e).lower() or "timeout" in str(e).lower():
                return False, f"连接超时：无法在 10 秒内连接到 {conn.host}:{conn.port}"
            return False, f"网络错误：{e}"
        except Exception as e:
            return False, f"连接失败：{e}"

    def close(self, conn_id: str):
        client = self._clients.pop(conn_id, None)
        if client:
            try:
                client.close()
                logger.info("SSH disconnected: %s", conn_id)
            except Exception as e:
                logger.warning("SSH close error for %s: %s", conn_id, e)

    def close_all(self):
        for cid in list(self._clients.keys()):
            self.close(cid)

    def cleanup_idle(self):
        """Close connections idle longer than IDLE_TIMEOUT seconds."""
        now = time.time()
        for conn_id in list(self._last_used.keys()):
            last = self._last_used.get(conn_id, 0)
            if now - last > self.IDLE_TIMEOUT:
                logger.info(
                    "Closing idle connection %s (idle for %.0fs)",
                    conn_id, now - last,
                )
                self.close(conn_id)

    # ---- Remote Filesystem ----

    def list_dir(self, conn: Connection, remote_path: str) -> list[RemoteFileInfo]:
        """List directory contents via SFTP. Returns empty list if path missing."""
        client = self.get_client(conn)
        try:
            sftp = client.open_sftp()
            try:
                attrs = sftp.listdir_attr(remote_path)
            except FileNotFoundError:
                logger.info("Remote path does not exist: %s", remote_path)
                return []
            try:
                results = []
                for a in attrs:
                    results.append(RemoteFileInfo(
                        name=a.filename,
                        path=f"{remote_path}/{a.filename}",
                        is_dir=stat.S_ISDIR(a.st_mode),
                        size=a.st_size if not stat.S_ISDIR(a.st_mode) else 0,
                        modified_at=a.st_mtime,
                    ))
                logger.debug("list_dir %s: %d entries", remote_path, len(results))
                return results
            finally:
                sftp.close()
        except Exception as e:
            logger.warning("list_dir failed for %s: %s", remote_path, e)
            return []

    def compute_remote_hash(self, conn: Connection, remote_path: str) -> str:
        """Compute deterministic SHA-256 hash of a remote file or directory.

        For directories, must mirror SkillHasher._hash_directory:
          - LC_ALL=C sort (raw byte order)
          - skip files matching SKILL_IGNORE_* sets
        """
        try:
            quoted = shlex.quote(remote_path)
            find_filters = self._build_find_filters()
            cmd = (
                f"if [ -f {quoted} ]; then "
                f"sha256sum {quoted} | cut -d' ' -f1; "
                f"elif [ -d {quoted} ]; then "
                f"cd {quoted} && "
                f"if find . -type f {find_filters} -print -quit | grep -q .; then "
                f"LC_ALL=C find . -type f {find_filters} -print0 | LC_ALL=C sort -z | "
                f"xargs -0 sha256sum | sha256sum | cut -d' ' -f1; "
                f"else printf '{EMPTY_SHA256}'; fi; "
                f"else printf ''; fi"
            )
            result = self._run_command(conn, cmd, timeout=30).strip()
            return result
        except Exception as e:
            logger.warning(f"compute_remote_hash failed for {remote_path}: {e}")
            return ""

    @staticmethod
    def _build_find_filters() -> str:
        """Return `find` predicates that exclude SKILL_IGNORE_* entries.

        Shape:  ! -name '.DS_Store' ! -name '*.swp' ... ! -path '*/.git/*' ...
        """
        from src.config import (
            SKILL_IGNORE_DIRS,
            SKILL_IGNORE_FILE_GLOBS,
            SKILL_IGNORE_FILES,
        )
        parts: list[str] = []
        for name in sorted(SKILL_IGNORE_FILES):
            parts.append(f"! -name {shlex.quote(name)}")
        for pat in SKILL_IGNORE_FILE_GLOBS:
            parts.append(f"! -name {shlex.quote(pat)}")
        for d in sorted(SKILL_IGNORE_DIRS):
            parts.append(f"! -path {shlex.quote(f'*/{d}/*')}")
        return " ".join(parts)

    def compute_remote_hashes(self, conn: Connection,
                              remote_paths: list[str]) -> dict[str, str]:
        """Hash many remote paths in a single SSH round-trip.

        Returns {remote_path: sha256_hex_or_empty}. A failed entry maps to "".

        Why batched: previous behaviour issued N SSH `exec_command`s for N
        skills; on internal links that's ~80ms × N. One round-trip drops total
        cost to ~one round-trip.
        """
        if not remote_paths:
            return {}
        find_filters = self._build_find_filters()
        # Ship the list of paths through base64 so spaces / unicode survive.
        import base64
        encoded = base64.b64encode(
            "\n".join(remote_paths).encode("utf-8")
        ).decode("ascii")
        empty_hash = EMPTY_SHA256
        cmd = (
            f"echo {shlex.quote(encoded)} | base64 -d | "
            f"while IFS= read -r p; do "
            f"  if [ -f \"$p\" ]; then "
            f"    h=$(sha256sum \"$p\" | cut -d' ' -f1); "
            f"  elif [ -d \"$p\" ]; then "
            f"    if (cd \"$p\" && find . -type f {find_filters} -print -quit | grep -q .); then "
            f"      h=$(cd \"$p\" && LC_ALL=C find . -type f {find_filters} -print0 | "
            f"          LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1); "
            f"    else h={empty_hash}; fi; "
            f"  else h=''; fi; "
            f"  printf '%s\\t%s\\n' \"$h\" \"$p\"; "
            f"done"
        )
        results: dict[str, str] = {p: "" for p in remote_paths}
        try:
            output = self._run_command(conn, cmd, timeout=120)
        except Exception as e:
            logger.warning("compute_remote_hashes batch failed: %s", e)
            return results
        for line in output.splitlines():
            if "\t" not in line:
                continue
            h, p = line.split("\t", 1)
            if p in results:
                results[p] = h.strip()
        return results

    def scan_skills_global(self, conn: Connection, remote_home: str,
                           tools: list[str]) -> dict[str, list[dict]]:
        """List all skill directories for the given tools in a single SSH call.

        Returns {tool: [{name, path, mtime, size}, ...]}.

        Why: replaces N×listdir+per-skill SKILL.md stat with one `find`.
        """
        bases = []
        tool_to_base = {}
        for t in tools:
            base = f"{remote_home}/.{t}/skills"
            bases.append(base)
            tool_to_base[t] = base
        if not bases:
            return {t: [] for t in tools}
        # find each base dir's */SKILL.md, print "<base>|<skill_name>|<mtime>|<size>"
        # using mtime of the skill *directory* (parent of SKILL.md).
        quoted_bases = " ".join(shlex.quote(b) for b in bases)
        cmd = (
            f"for base in {quoted_bases}; do "
            f"  if [ -d \"$base\" ]; then "
            f"    for d in \"$base\"/*/; do "
            f"      [ -d \"$d\" ] || continue; "
            f"      [ -f \"$d/SKILL.md\" ] || continue; "
            f"      name=$(basename \"$d\"); "
            f"      mtime=$(stat -c %Y \"$d\" 2>/dev/null || stat -f %m \"$d\"); "
            f"      size=$(stat -c %s \"$d\" 2>/dev/null || stat -f %z \"$d\"); "
            f"      printf '%s|%s|%s|%s\\n' \"$base\" \"$name\" \"$mtime\" \"$size\"; "
            f"    done; "
            f"  fi; "
            f"done"
        )
        out: dict[str, list[dict]] = {t: [] for t in tools}
        try:
            output = self._run_command(conn, cmd, timeout=30)
        except Exception as e:
            logger.warning("scan_skills_global batch failed: %s", e)
            return out
        # invert tool_to_base for parsing
        base_to_tool = {v: k for k, v in tool_to_base.items()}
        for line in output.splitlines():
            parts = line.split("|", 3)
            if len(parts) != 4:
                continue
            base, name, mtime, size = parts
            tool = base_to_tool.get(base)
            if tool is None:
                continue
            try:
                mtime_f = float(mtime)
            except ValueError:
                mtime_f = 0.0
            try:
                size_i = int(size)
            except ValueError:
                size_i = 0
            out[tool].append({
                "name": name,
                "path": f"{base}/{name}",
                "mtime": mtime_f,
                "size": size_i,
            })
        return out

    def file_exists(self, conn: Connection, remote_path: str) -> bool:
        client = self.get_client(conn)
        try:
            sftp = client.open_sftp()
            try:
                sftp.stat(remote_path)
                return True
            finally:
                sftp.close()
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def read_file(self, conn: Connection, remote_path: str) -> bytes:
        client = self.get_client(conn)
        sftp = client.open_sftp()
        try:
            with sftp.file(remote_path, "rb") as f:
                return f.read()
        finally:
            sftp.close()

    def write_file(self, conn: Connection, remote_path: str, data: bytes):
        client = self.get_client(conn)
        sftp = client.open_sftp()
        try:
            with sftp.file(remote_path, "wb") as f:
                f.write(data)
        finally:
            sftp.close()

    def mkdir_p(self, conn: Connection, remote_path: str):
        self._run_command(
            conn,
            f'mkdir -p {shlex.quote(remote_path)}',
            timeout=10,
        )

    def delete(self, conn: Connection, remote_path: str):
        self._run_command(
            conn,
            f'rm -rf {shlex.quote(remote_path)}',
            timeout=10,
        )

    def get_remote_home(self, conn: Connection) -> str:
        """Resolve the remote user's home directory via SSH."""
        client = self.get_client(conn)
        stdin, stdout, stderr = client.exec_command("echo $HOME", timeout=5)
        home = stdout.read().decode().strip()
        logger.debug("Remote home for %s@%s: %s", conn.username, conn.host, home)
        return home

    def rename(self, conn: Connection, old_path: str, new_path: str):
        client = self.get_client(conn)
        sftp = client.open_sftp()
        try:
            sftp.rename(old_path, new_path)
        finally:
            sftp.close()

    def download_directory(self, conn: Connection, remote_path: str) -> bytes:
        """Return a .tar.gz archive containing the directory contents."""
        quoted = shlex.quote(remote_path)
        cmd = (
            f"if [ -d {quoted} ]; then "
            f"tar -C {quoted} -czf - .; "
            f"else printf ''; fi"
        )
        return self._run_command(conn, cmd, timeout=60, binary=True)

    def extract_archive(self, conn: Connection, archive_data: bytes,
                        remote_target_path: str):
        """Extract a .tar.gz archive into remote_target_path."""
        target = PurePosixPath(remote_target_path)
        parent = str(target.parent)
        archive_name = f".skill-sync-{uuid.uuid4().hex[:8]}.tar.gz"
        remote_archive = str(target.parent / archive_name)
        self.mkdir_p(conn, parent)
        self.write_file(conn, remote_archive, archive_data)
        try:
            cmd = (
                f"mkdir -p {shlex.quote(remote_target_path)} && "
                f"tar -xzf {shlex.quote(remote_archive)} "
                f"-C {shlex.quote(remote_target_path)}"
            )
            self._run_command(conn, cmd, timeout=60)
        finally:
            try:
                self.delete(conn, remote_archive)
            except Exception:
                logger.warning("Failed to cleanup remote archive: %s", remote_archive)

    # ---- Internal ----

    def _connect(self, conn: Connection, timeout: int = 30) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Resolve SSH config (Host alias / ProxyJump / IdentityFile / User / Port ...)
        cfg = self._load_ssh_config_for(conn.host)
        host = cfg.get("hostname", conn.host)
        username = conn.username or cfg.get("user") or os.getenv("USER", "")
        try:
            port = int(cfg.get("port", conn.port))
        except (TypeError, ValueError):
            port = conn.port

        connect_kwargs = {
            "hostname": host,
            "port": port,
            "username": username,
            "timeout": timeout,
            "banner_timeout": timeout,
            "auth_timeout": timeout,
            "compress": True,
            "allow_agent": True,
            "look_for_keys": True,
        }

        # GSSAPI / Kerberos auth (e.g. internal corp networks).
        # Strategy:
        #   1) If paramiko has built-in GSS support (paramiko.ssh_gss), enable
        #      it via gss_* kwargs — same path as command-line OpenSSH.
        #   2) Otherwise, if a system `ssh` is available, fall back to
        #      `ssh -W host:port` as a transport ProxyCommand and let OpenSSH
        #      handle auth.
        gss_enabled_native = False
        if self._gssapi_available():
            try:
                import importlib
                importlib.import_module("paramiko.ssh_gss")
                connect_kwargs["gss_auth"] = True
                connect_kwargs["gss_kex"] = True
                connect_kwargs["gss_deleg_creds"] = True
                connect_kwargs["gss_host"] = host
                # Do NOT canonicalize via DNS — KDC may only have a ticket for
                # the literal hostname/IP (e.g. host/10.x.x.x@REALM).
                connect_kwargs["gss_trust_dns"] = False
                gss_enabled_native = True
            except Exception:
                pass
            if not gss_enabled_native and self._has_system_ssh():
                try:
                    connect_kwargs["sock"] = self._spawn_ssh_proxy(
                        host, port, username, timeout=timeout,
                    )
                    connect_kwargs["allow_agent"] = False
                    connect_kwargs["look_for_keys"] = False
                    logger.info("Using system ssh as transport proxy for %s@%s",
                                username, host)
                except Exception as e:
                    logger.warning("Failed to spawn ssh proxy: %s", e)

        # ProxyJump / ProxyCommand support from ~/.ssh/config
        sock = self._build_proxy_sock(cfg, timeout=timeout)
        if sock is not None:
            connect_kwargs["sock"] = sock

        if conn.auth_type == "key":
            if conn.key_path:
                connect_kwargs["key_filename"] = conn.key_path
            elif cfg.get("identityfile"):
                connect_kwargs["key_filename"] = cfg["identityfile"]
            else:
                # Mimic OpenSSH: try every default key that actually exists on disk.
                default_keys = self._discover_default_keys()
                if default_keys:
                    connect_kwargs["key_filename"] = default_keys
        elif conn.auth_type == "password":
            if conn.password_enc:
                connect_kwargs["password"] = self._crypto.decrypt(conn.password_enc)
            connect_kwargs["look_for_keys"] = False
            connect_kwargs["allow_agent"] = False

        try:
            client.connect(**connect_kwargs)
        except paramiko.AuthenticationException:
            raise
        logger.info(
            "SSH connected to %s@%s:%s (alias=%s)",
            username, host, port, conn.host,
        )
        return client

    @staticmethod
    def _has_system_ssh() -> bool:
        import shutil
        return shutil.which("ssh") is not None

    @staticmethod
    def _spawn_ssh_proxy(host: str, port: int, username: str, timeout: int):
        """Spawn `ssh -W host:port` and wrap its stdio as a paramiko sock.

        Why: paramiko 5.0 macOS wheels lack GSSAPI; system OpenSSH has it
        and is already configured to log in. We let it perform a *netcat-mode*
        connection (-W) and use it as the transport pipe.
        """
        import shlex as _sh
        cmd = (
            f"ssh -o ConnectTimeout={timeout} "
            f"-o ServerAliveInterval=15 "
            f"-o BatchMode=yes "
            f"-W {_sh.quote(host)}:{port} "
            f"-p {port} "
            f"{_sh.quote(username)}@{_sh.quote(host)}"
        )
        return paramiko.ProxyCommand(cmd)

    @staticmethod
    def _gssapi_available() -> bool:
        """Check if GSSAPI (Kerberos) authentication is usable on this machine."""
        try:
            import gssapi  # noqa: F401
        except Exception:
            return False
        # Need a usable Kerberos credential (ticket) to actually authenticate.
        try:
            import gssapi as _g
            creds = _g.Credentials(usage="initiate")
            # If lifetime is 0 or raises, we have no valid ticket.
            return bool(creds.lifetime and creds.lifetime > 0)
        except Exception:
            return False

    @staticmethod
    def _discover_default_keys() -> list[str]:
        """Return existing default private keys in ~/.ssh, in OpenSSH's order."""
        ssh_dir = Path.home() / ".ssh"
        names = [
            "id_ed25519", "id_ed25519_sk",
            "id_ecdsa", "id_ecdsa_sk",
            "id_rsa",
            "id_xmss", "id_dsa",
        ]
        found = []
        for n in names:
            p = ssh_dir / n
            if p.is_file():
                found.append(str(p))
        return found

    @staticmethod
    def _load_ssh_config_for(host_alias: str) -> dict:
        """Read ~/.ssh/config and return the resolved entry for host_alias."""
        cfg_path = Path.home() / ".ssh" / "config"
        if not cfg_path.is_file():
            return {}
        try:
            ssh_cfg = paramiko.SSHConfig()
            with open(cfg_path, "r", encoding="utf-8") as fh:
                ssh_cfg.parse(fh)
            return ssh_cfg.lookup(host_alias) or {}
        except Exception as e:
            logger.warning("parse ssh config failed: %s", e)
            return {}

    @staticmethod
    def _build_proxy_sock(cfg: dict, timeout: int):
        """Honor ProxyJump / ProxyCommand from ssh_config when present."""
        proxy_cmd = cfg.get("proxycommand")
        proxy_jump = cfg.get("proxyjump")
        if proxy_jump and not proxy_cmd:
            proxy_cmd = f"ssh -W %h:%p {proxy_jump}"
        if not proxy_cmd:
            return None
        try:
            host = cfg.get("hostname", "")
            port = str(cfg.get("port", "22"))
            cmd = (proxy_cmd
                   .replace("%h", host)
                   .replace("%p", port)
                   .replace("%r", cfg.get("user", "")))
            logger.info("Using SSH proxy command: %s", cmd)
            return paramiko.ProxyCommand(cmd)
        except Exception as e:
            logger.warning("build proxy sock failed: %s", e)
            return None

    @staticmethod
    def _is_alive(client: paramiko.SSHClient) -> bool:
        transport = client.get_transport()
        return transport is not None and transport.is_active()

    def _run_command(self, conn: Connection, command: str, *,
                     timeout: int = 30, binary: bool = False):
        client = self.get_client(conn)
        _, stdout, stderr = client.exec_command(command, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read()
        err = stderr.read()
        if exit_code != 0:
            raise RuntimeError(
                f"remote command failed (rc={exit_code}): "
                f"{err.decode(errors='replace').strip() or command}"
            )
        if binary:
            return out
        return out.decode().strip()
