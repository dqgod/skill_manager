"""测试 MainWindow 的无 UI 业务方法"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import src.ui.main_window as main_window_module
from src.models.project import Project
from src.services.skill_scanner import SkillInfo
from src.ui.main_window import MainWindow


class SidebarStub:
    def __init__(self):
        self._nav_items = {"global": object(), "old-project": object()}
        self.removed = []
        self.added = []

    def remove_project_nav(self, project_id: str):
        self.removed.append(project_id)
        self._nav_items.pop(project_id, None)

    def add_project_nav(self, project_id: str, name: str):
        self.added.append((project_id, name))
        self._nav_items[project_id] = object()


class ToastStub:
    def __init__(self):
        self.messages = []

    def show_message(self, message: str, success: bool = True):
        self.messages.append((message, success))


class SyncDialogStub:
    def __init__(self):
        self.updated = []
        self.progress = []

    def update_item(self, name: str, status: str):
        self.updated.append((name, status))

    def set_progress(self, value: int):
        self.progress.append(value)


def test_on_project_changed_removes_stale_nav(monkeypatch, tmp_path):
    projects = [
        Project(name="new-project", local_path=str(tmp_path / "proj"), id="new-project")
    ]
    monkeypatch.setattr(main_window_module.ProjectModel, "get_all", lambda: projects)

    fake = SimpleNamespace(
        _sidebar=SidebarStub(),
        _toast=ToastStub(),
        _projects=[],
        _push_source_options=MagicMock(),
    )

    MainWindow._on_project_changed(fake)

    assert fake._sidebar.removed == ["old-project"]
    assert fake._sidebar.added == [("new-project", "new-project")]
    assert fake._toast.messages == [("项目列表已更新", True)]
    fake._push_source_options.assert_called_once()


def test_on_sync_progress_advances_on_failed_and_skipped():
    dialog = SyncDialogStub()
    fake = SimpleNamespace(_sync_dialog=dialog)

    MainWindow._on_sync_progress(fake, 1, 3, "skill-a", "failed")
    MainWindow._on_sync_progress(fake, 2, 3, "skill-b", "skipped")

    assert dialog.updated == [("skill-a", "failed"), ("skill-b", "skipped")]
    assert dialog.progress == [2, 3]


# ---- Hash-compare master switch + status chip ----


def _mk_skill(name: str, tool: str = "codex", device_type: str = "local") -> SkillInfo:
    return SkillInfo(
        name=name, tool=tool, path=f"/tmp/{name}",
        level="global", device="local", device_type=device_type,
    )


class _PanelsStub:
    def __init__(self):
        self.left_panel = MagicMock()
        self.right_panel = MagicMock()
        # Backward-compat aliases (production code also exposes these).
        self.local_panel = self.left_panel
        self.remote_panel = self.right_panel


def _build_toggle_fake(enabled_initial: bool, has_skills: bool = True):
    """Construct a SimpleNamespace mimicking just enough of MainWindow."""
    settings = MagicMock()
    settings.setValue = MagicMock()
    panels = _PanelsStub()
    lefts = [_mk_skill("a"), _mk_skill("b")] if has_skills else []
    rights = [_mk_skill("a", device_type="remote")] if has_skills else []
    fake = SimpleNamespace(
        _hash_compare_enabled=enabled_initial,
        _settings=settings,
        _left_skills=lefts,
        _right_skills=rights,
        # Legacy aliases retained so older tests can still inspect them.
        _local_skills=lefts,
        _remote_skills=rights,
        _panels=panels,
        _left_source=MagicMock(is_remote=False),
        _right_source=MagicMock(is_remote=True),
        _resolve_connection=MagicMock(return_value=None),
        _hasher=MagicMock(),
        _set_status_chip=MagicMock(),
        _finalize_worker=MagicMock(),
        statusBar=MagicMock(return_value=MagicMock()),
    )
    fake._auto_compare = MagicMock(side_effect=lambda: MainWindow._auto_compare(fake))
    return fake


def test_hash_compare_toggle_off_marks_off_and_skips_compare():
    fake = _build_toggle_fake(enabled_initial=True)
    # Patch _auto_compare to assert it's NOT called when toggling OFF.
    fake._auto_compare = MagicMock()

    MainWindow._on_hash_compare_toggled(fake, False)

    assert fake._hash_compare_enabled is False
    assert all(s.hash == "off" for s in fake._left_skills)
    assert all(s.hash == "off" for s in fake._right_skills)
    fake._settings.setValue.assert_called_with(
        "ui/hash_compare_enabled", False
    )
    fake._auto_compare.assert_not_called()


def test_hash_compare_toggle_on_triggers_compare():
    fake = _build_toggle_fake(enabled_initial=False)
    # Stub _auto_compare so we don't actually spin a thread.
    fake._auto_compare = MagicMock()

    MainWindow._on_hash_compare_toggled(fake, True)

    assert fake._hash_compare_enabled is True
    fake._settings.setValue.assert_called_with(
        "ui/hash_compare_enabled", True
    )
    fake._auto_compare.assert_called_once()


def test_auto_compare_short_circuits_when_disabled():
    fake = _build_toggle_fake(enabled_initial=False)
    fake._compare_worker = None
    fake._hasher = MagicMock()
    # Calling _auto_compare directly should NOT touch the hasher when off.
    MainWindow._auto_compare(fake)
    fake._hasher.compare.assert_not_called()
    assert all(s.hash == "off" for s in fake._left_skills)
    assert all(s.hash == "off" for s in fake._right_skills)
    fake._set_status_chip.assert_called()
