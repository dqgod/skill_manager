"""测试 SSHManager 的资源释放和命令等待"""

from src.models.connection import Connection
from src.services.ssh_manager import SSHManager


class FakeRemoteFile:
    def __init__(self, data: bytes):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._data

    def write(self, data: bytes):
        self._data = data


class FakeSFTP:
    def __init__(self, data: bytes = b""):
        self.closed = False
        self._data = data

    def file(self, path: str, mode: str):
        return FakeRemoteFile(self._data)

    def close(self):
        self.closed = True


class FakeChannel:
    def __init__(self):
        self.wait_called = False

    def recv_exit_status(self):
        self.wait_called = True
        return 0


class FakeStream:
    def __init__(self, data: bytes = b""):
        self._data = data
        self.channel = FakeChannel()

    def read(self):
        return self._data


class FakeClient:
    def __init__(self, sftp: FakeSFTP):
        self.sftp = sftp
        self.commands = []
        self.stdout = FakeStream()
        self.stderr = FakeStream()

    def open_sftp(self):
        return self.sftp

    def exec_command(self, command: str, timeout: int = 30):
        self.commands.append((command, timeout))
        return None, self.stdout, self.stderr


def test_read_file_closes_sftp(monkeypatch):
    sftp = FakeSFTP(b"hello")
    client = FakeClient(sftp)
    mgr = SSHManager()
    conn = Connection(name="srv", host="127.0.0.1")
    monkeypatch.setattr(mgr, "get_client", lambda _: client)

    assert mgr.read_file(conn, "/tmp/file.txt") == b"hello"
    assert sftp.closed is True


def test_mkdir_p_waits_for_command_exit(monkeypatch):
    sftp = FakeSFTP()
    client = FakeClient(sftp)
    mgr = SSHManager()
    conn = Connection(name="srv", host="127.0.0.1")
    monkeypatch.setattr(mgr, "get_client", lambda _: client)

    mgr.mkdir_p(conn, "/tmp/skill-dir")

    assert client.commands == [("mkdir -p /tmp/skill-dir", 10)]
    assert client.stdout.channel.wait_called is True
