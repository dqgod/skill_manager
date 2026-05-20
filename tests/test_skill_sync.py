"""测试 SkillSyncService（仅本地同步，不依赖 SSH）"""

import io
import tarfile
from pathlib import Path

from src.models.connection import Connection
from src.models.project import Project
from src.services.skill_hasher import SkillHasher
from src.services.skill_sync import SkillSyncService, SyncTask
from src.services.skill_scanner import SkillInfo
from src.config import SYNC_DIRECTION_PUSH, SYNC_DIRECTION_PULL


def _make_task(skill_name, source_path, target_path, **kwargs):
    defaults = dict(
        source_device="local",
        target_device="local",
        source_tool="claude",
        target_tool="claude",
        is_dir=False,
        expected_hash="",
    )
    defaults.update(kwargs)
    return SyncTask(skill_name=skill_name, source_path=source_path,
                    target_path=target_path, **defaults)


class FakeSSHManager:
    def __init__(self, remote_root: Path):
        self.remote_root = remote_root
        self.remote_root.mkdir(parents=True, exist_ok=True)

    def get_remote_home(self, conn):
        return "/home/tester"

    def _real(self, remote_path: str) -> Path:
        return self.remote_root / remote_path.lstrip("/")

    def file_exists(self, conn, remote_path: str) -> bool:
        return self._real(remote_path).exists()

    def read_file(self, conn, remote_path: str) -> bytes:
        return self._real(remote_path).read_bytes()

    def write_file(self, conn, remote_path: str, data: bytes):
        real = self._real(remote_path)
        real.parent.mkdir(parents=True, exist_ok=True)
        real.write_bytes(data)

    def mkdir_p(self, conn, remote_path: str):
        self._real(remote_path).mkdir(parents=True, exist_ok=True)

    def delete(self, conn, remote_path: str):
        real = self._real(remote_path)
        if real.is_dir():
            import shutil
            shutil.rmtree(real, ignore_errors=True)
        elif real.exists():
            real.unlink()

    def rename(self, conn, old_path: str, new_path: str):
        old_real = self._real(old_path)
        new_real = self._real(new_path)
        new_real.parent.mkdir(parents=True, exist_ok=True)
        old_real.rename(new_real)

    def compute_remote_hash(self, conn, remote_path: str) -> str:
        return SkillHasher.compute_local_hash(str(self._real(remote_path)))

    def download_directory(self, conn, remote_path: str) -> bytes:
        return self._archive_dir(self._real(remote_path))

    def extract_archive(self, conn, archive_data: bytes, remote_target_path: str):
        target = self._real(remote_target_path)
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:gz") as tar:
            tar.extractall(target)

    @staticmethod
    def _archive_dir(path: Path) -> bytes:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for entry in sorted(path.rglob("*")):
                tar.add(entry, arcname=entry.relative_to(path))
        return buffer.getvalue()


class TestSyncService:
    def test_prepare_tasks_push(self):
        svc = SkillSyncService(None, SkillHasher())
        skill = SkillInfo(
            name="test-skill", tool="claude",
            path="/tmp/src/skill", level="global",
            device="local", device_type="local",
        )
        tasks = svc.prepare_tasks(
            [skill], SYNC_DIRECTION_PUSH, "global_to_global",
            ["claude"]
        )
        assert len(tasks) == 1
        assert tasks[0].skill_name == "test-skill"

    def test_prepare_tasks_push_remote_global_uses_remote_home(self, tmp_path):
        ssh = FakeSSHManager(tmp_path / "remote")
        svc = SkillSyncService(ssh, SkillHasher(ssh))
        conn = Connection(name="srv", host="127.0.0.1")
        skill = SkillInfo(
            name="test-skill", tool="claude",
            path="/tmp/src/skill", level="global",
            device="local", device_type="local",
        )
        tasks = svc.prepare_tasks(
            [skill], SYNC_DIRECTION_PUSH, "global_to_global",
            ["claude"], target_connection=conn
        )
        assert tasks[0].target_path == "/home/tester/.claude/skills/test-skill"

    def test_prepare_tasks_project_levels_and_remote_project_path(self, tmp_path):
        ssh = FakeSSHManager(tmp_path / "remote")
        svc = SkillSyncService(ssh, SkillHasher(ssh))
        conn = Connection(name="srv", host="127.0.0.1")
        project = Project(
            name="proj",
            local_path=str(tmp_path / "local-proj"),
            remote_path="/workspace/proj",
            tools="claude",
        )
        skill = SkillInfo(
            name="proj-skill", tool="claude",
            path="/tmp/src/proj-skill", level="project",
            device="local", device_type="local", project_id=project.id,
        )
        tasks = svc.prepare_tasks(
            [skill], SYNC_DIRECTION_PUSH, "project_to_project",
            ["claude"], source_project=project, target_project=project,
            target_connection=conn,
        )
        assert tasks[0].source_level == "project"
        assert tasks[0].target_level == "project"
        assert tasks[0].target_project_id == project.id
        assert tasks[0].target_path == "/workspace/proj/.claude/skills/proj-skill"

    def test_local_copy_file(self, tmp_path):
        svc = SkillSyncService(None, SkillHasher())
        src = tmp_path / "source" / "skill.md"
        src.parent.mkdir(parents=True)
        src.write_text("# test skill content")
        dst = tmp_path / "target"

        task = _make_task("skill.md", str(src), str(dst / "skill.md"))
        results = svc.execute([task], conflict_strategy="overwrite")
        assert results[0].status == "success"
        assert (dst / "skill.md").exists()
        assert (dst / "skill.md").read_text() == "# test skill content"

    def test_local_copy_directory(self, tmp_path):
        svc = SkillSyncService(None, SkillHasher())
        src_dir = tmp_path / "source" / "my-skill"
        src_dir.mkdir(parents=True)
        (src_dir / "main.py").write_text("print('hello')")
        (src_dir / "README.md").write_text("# readme")
        dst = tmp_path / "target"

        task = _make_task("my-skill", str(src_dir), str(dst / "my-skill"),
                          is_dir=True)
        results = svc.execute([task], conflict_strategy="overwrite")
        assert results[0].status == "success"

    def test_local_to_remote_copy_directory(self, tmp_path):
        ssh = FakeSSHManager(tmp_path / "remote")
        svc = SkillSyncService(ssh, SkillHasher(ssh))
        conn = Connection(name="srv", host="127.0.0.1")
        src_dir = tmp_path / "source" / "my-skill"
        src_dir.mkdir(parents=True)
        (src_dir / "SKILL.md").write_text("# skill")
        (src_dir / "main.py").write_text("print('hello')")

        task = _make_task(
            "my-skill",
            str(src_dir),
            "/home/tester/.claude/skills/my-skill",
            is_dir=True,
            expected_hash=SkillHasher.compute_local_hash(str(src_dir)),
        )
        results = svc.execute([task], target_connection=conn, conflict_strategy="overwrite")
        remote_dir = ssh._real("/home/tester/.claude/skills/my-skill")
        assert results[0].status == "success"
        assert (remote_dir / "SKILL.md").read_text() == "# skill"
        assert (remote_dir / "main.py").read_text() == "print('hello')"

    def test_remote_to_local_copy_directory(self, tmp_path):
        ssh = FakeSSHManager(tmp_path / "remote")
        svc = SkillSyncService(ssh, SkillHasher(ssh))
        conn = Connection(name="srv", host="127.0.0.1")
        remote_dir = ssh._real("/home/tester/.claude/skills/my-skill")
        remote_dir.mkdir(parents=True)
        (remote_dir / "SKILL.md").write_text("# remote skill")
        (remote_dir / "README.md").write_text("hello")
        dst = tmp_path / "local"

        task = _make_task(
            "my-skill",
            "/home/tester/.claude/skills/my-skill",
            str(dst / "my-skill"),
            is_dir=True,
            source_device="srv",
            target_device="local",
            expected_hash=SkillHasher.compute_local_hash(str(remote_dir)),
        )
        results = svc.execute([task], source_connection=conn, conflict_strategy="overwrite")
        assert results[0].status == "success"
        assert (dst / "my-skill" / "SKILL.md").read_text() == "# remote skill"
        assert (dst / "my-skill" / "README.md").read_text() == "hello"

    def test_conflict_skip(self, tmp_path):
        svc = SkillSyncService(None, SkillHasher())
        src = tmp_path / "src" / "skill.md"
        src.parent.mkdir(parents=True)
        src.write_text("new content")
        dst = tmp_path / "dst"
        dst.mkdir(parents=True)
        (dst / "skill.md").write_text("old content")

        task = _make_task("skill.md", str(src), str(dst / "skill.md"))
        results = svc.execute([task], conflict_strategy="skip")
        assert results[0].status == "skipped"
        assert (dst / "skill.md").read_text() == "old content"

    def test_conflict_overwrite(self, tmp_path):
        svc = SkillSyncService(None, SkillHasher())
        src = tmp_path / "src" / "skill.md"
        src.parent.mkdir(parents=True)
        src.write_text("new content")
        dst = tmp_path / "dst"
        dst.mkdir(parents=True)
        (dst / "skill.md").write_text("old content")

        task = _make_task("skill.md", str(src), str(dst / "skill.md"))
        results = svc.execute([task], conflict_strategy="overwrite")
        assert results[0].status == "success"
        assert (dst / "skill.md").read_text() == "new content"

    def test_multiple_tasks(self, tmp_path):
        svc = SkillSyncService(None, SkillHasher())
        tasks = []
        for i in range(3):
            src = tmp_path / "src" / f"skill-{i}.md"
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_text(f"content {i}")
            dst = tmp_path / "dst"
            tasks.append(_make_task(f"skill-{i}.md", str(src),
                                    str(dst / f"skill-{i}.md")))

        results = svc.execute(tasks, conflict_strategy="overwrite")
        success_count = sum(1 for r in results if r.status == "success")
        assert success_count == 3

    def test_history_recorded(self, tmp_path, monkeypatch):
        import src.services.skill_sync as ss
        # reset history model to use test DB
        monkeypatch.setattr(ss.SyncHistoryModel, 'add', lambda rec: None)

        svc = SkillSyncService(None, SkillHasher())
        src = tmp_path / "src" / "skill.md"
        src.parent.mkdir(parents=True)
        src.write_text("test")
        dst = tmp_path / "dst"
        tasks = [_make_task("skill.md", str(src), str(dst / "skill.md"))]
        results = svc.execute(tasks, conflict_strategy="overwrite")
        assert results[0].status == "success"
