"""测试 ProjectService"""

import pytest
from pathlib import Path

from src.services.project_service import ProjectService
from src.models.project import Project, ProjectModel


class TestProjectService:
    def test_register_success(self, tmp_path):
        proj_dir = tmp_path / "my-project"
        proj_dir.mkdir()
        proj = ProjectService.register(
            name="测试项目", local_path=str(proj_dir),
            tools=["codex"]
        )
        assert proj.name == "测试项目"
        assert proj.tools == "codex"
        loaded = ProjectModel.get(proj.id)
        assert loaded is not None

    def test_register_empty_name_raises(self, tmp_path):
        proj_dir = tmp_path / "p"
        proj_dir.mkdir()
        with pytest.raises(ValueError, match="项目名称不能为空"):
            ProjectService.register(name="  ", local_path=str(proj_dir))

    def test_register_nonexistent_path_raises(self, tmp_path):
        with pytest.raises(ValueError, match="项目路径不存在"):
            ProjectService.register(
                name="ghost", local_path=str(tmp_path / "nope")
            )

    def test_register_duplicate_path_raises(self, tmp_path):
        proj_dir = tmp_path / "p"
        proj_dir.mkdir()
        ProjectService.register(name="first", local_path=str(proj_dir))
        with pytest.raises(ValueError, match="已注册为项目"):
            ProjectService.register(name="second", local_path=str(proj_dir))

    def test_auto_detect(self, tmp_path):
        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()
        (proj_dir / ".claude" / "skills").mkdir(parents=True)

        proj = Project(
            name="test", local_path=str(proj_dir),
            tools="codex,claude"
        )
        detected = ProjectService.auto_detect_skill_dirs(proj)
        assert detected["claude"] is True
        assert detected["codex"] is False

    def test_ensure_skill_dirs(self, tmp_path):
        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()
        proj = Project(
            name="test", local_path=str(proj_dir),
            tools="codex,claude"
        )
        ProjectService.ensure_skill_dirs(proj)
        assert (proj_dir / ".claude" / "skills").is_dir()
        assert (proj_dir / ".codex" / "skills").is_dir()

    def test_update(self, tmp_path):
        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()
        proj = ProjectService.register(name="old", local_path=str(proj_dir))
        ProjectService.update(proj, name="new-name")
        loaded = ProjectModel.get(proj.id)
        assert loaded.name == "new-name"

    def test_delete(self, tmp_path):
        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()
        proj = ProjectService.register(name="to-del", local_path=str(proj_dir))
        ProjectService.delete(proj.id)
        assert ProjectModel.get(proj.id) is None
