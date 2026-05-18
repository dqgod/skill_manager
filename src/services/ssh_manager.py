"""SSH 连接管理器：连接池、sftp、远程哈希计算 (F5)"""

import stat
import time
from dataclasses import dataclass
from typing import Optional

import paramiko

from src.models.connection import Connection
from src.services.crypto_service import CryptoService
from src.utils.logger import get_logger

logger = get_logger(__name__)


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
            except Exception:
                pass

    def close_all(self):
        for cid in list(self._clients.keys()):
            self.close(cid)

    # ---- Remote Filesystem ----

    def list_dir(self, conn: Connection, remote_path: str) -> list[RemoteFileInfo]:
        """List directory contents via SFTP. Returns empty list if path missing."""
        client = self.get_client(conn)
        try:
            sftp = client.open_sftp()
            try:
                attrs = sftp.listdir_attr(remote_path)
            except FileNotFoundError:
                return []
            results = []
            for a in attrs:
                results.append(RemoteFileInfo(
                    name=a.filename,
                    path=f"{remote_path}/{a.filename}",
                    is_dir=stat.S_ISDIR(a.st_mode),
                    size=a.st_size if not stat.S_ISDIR(a.st_mode) else 0,
                    modified_at=a.st_mtime,
                ))
            return results
        except Exception as e:
            logger.warning(f"list_dir failed for {remote_path}: {e}")
            return []

    def compute_remote_hash(self, conn: Connection, remote_path: str) -> str:
        """Compute deterministic SHA-256 hash of a remote file or directory."""
        client = self.get_client(conn)
        try:
            # try file first
            stdin, stdout, stderr = client.exec_command(
                f'sha256sum "{remote_path}" 2>/dev/null | cut -d" " -f1',
                timeout=30,
            )
            result = stdout.read().decode().strip()
            if result:
                return result

            # directory: hash all files sorted
            cmd = (
                f'cd "{remote_path}" 2>/dev/null && '
                f'find . -type f -print0 2>/dev/null | sort -z | '
                f'xargs -0 sha256sum 2>/dev/null | sha256sum | cut -d" " -f1'
            )
            stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
            result = stdout.read().decode().strip()
            return result if result else ""
        except Exception as e:
            logger.warning(f"compute_remote_hash failed for {remote_path}: {e}")
            return ""

    def file_exists(self, conn: Connection, remote_path: str) -> bool:
        client = self.get_client(conn)
        try:
            sftp = client.open_sftp()
            sftp.stat(remote_path)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def read_file(self, conn: Connection, remote_path: str) -> bytes:
        client = self.get_client(conn)
        sftp = client.open_sftp()
        with sftp.file(remote_path, "rb") as f:
            return f.read()

    def write_file(self, conn: Connection, remote_path: str, data: bytes):
        client = self.get_client(conn)
        sftp = client.open_sftp()
        with sftp.file(remote_path, "wb") as f:
            f.write(data)

    def mkdir_p(self, conn: Connection, remote_path: str):
        client = self.get_client(conn)
        client.exec_command(f'mkdir -p "{remote_path}"', timeout=10)

    def delete(self, conn: Connection, remote_path: str):
        client = self.get_client(conn)
        client.exec_command(f'rm -rf "{remote_path}"', timeout=10)

    def rename(self, conn: Connection, old_path: str, new_path: str):
        client = self.get_client(conn)
        sftp = client.open_sftp()
        sftp.rename(old_path, new_path)

    # ---- Internal ----

    def _connect(self, conn: Connection, timeout: int = 30) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_kwargs = {
            "hostname": conn.host,
            "port": conn.port,
            "username": conn.username,
            "timeout": timeout,
            "banner_timeout": timeout,
            "compress": True,
        }
        if conn.auth_type == "key":
            if conn.key_path:
                connect_kwargs["key_filename"] = conn.key_path
        elif conn.auth_type == "password":
            if conn.password_enc:
                connect_kwargs["password"] = self._crypto.decrypt(conn.password_enc)
        client.connect(**connect_kwargs)
        logger.info(f"SSH connected to {conn.host}:{conn.port}")
        return client

    @staticmethod
    def _is_alive(client: paramiko.SSHClient) -> bool:
        transport = client.get_transport()
        return transport is not None and transport.is_active()
