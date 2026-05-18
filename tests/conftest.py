"""测试 fixtures：临时 DB 和临时目录"""

import tempfile
import shutil
from pathlib import Path

import pytest

import src.models.db as db_module


@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
    """每个测试使用独立的临时数据库。"""
    tmpdir = Path(tempfile.mkdtemp())

    # monkeypatch the imported references in db.py directly
    monkeypatch.setattr(db_module, "APP_DATA_DIR", tmpdir, raising=False)
    monkeypatch.setattr(db_module, "DB_FILENAME", "test.db", raising=False)

    # force-clear thread-local to prevent connection reuse
    db_module._local.__dict__.clear()

    db_module.init_db()
    yield
    db_module.close_db()
    db_module._local.__dict__.clear()
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def skill_fixtures_dir(tmp_path):
    """创建测试用 skill 目录结构。"""
    global_dir = tmp_path / "global"
    proj_dir = tmp_path / "project"

    # global skills
    (global_dir / ".claude" / "skills" / "my-skill").mkdir(parents=True)
    (global_dir / ".claude" / "skills" / "my-skill" / "README.md").write_text(
        "# My Skill\nA test skill."
    )
    (global_dir / ".codex" / "skills" / "other-skill.md").parent.mkdir(
        parents=True, exist_ok=True
    )
    (global_dir / ".codex" / "skills" / "other-skill.md").write_text(
        "# Other Skill\nAnother test."
    )

    # project skills
    (proj_dir / ".claude" / "skills" / "proj-skill").mkdir(parents=True)
    (proj_dir / ".claude" / "skills" / "proj-skill" / "main.py").write_text(
        "print('hello')"
    )

    return {"global": global_dir, "project": proj_dir}
