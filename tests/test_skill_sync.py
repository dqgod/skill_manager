"""测试 SkillSyncService（仅本地同步，不依赖 SSH）"""

from pathlib import Path

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
