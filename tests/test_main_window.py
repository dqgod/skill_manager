"""测试 MainWindow 的无 UI 业务方法"""

from types import SimpleNamespace

import src.ui.main_window as main_window_module
from src.models.project import Project
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
    )

    MainWindow._on_project_changed(fake)

    assert fake._sidebar.removed == ["old-project"]
    assert fake._sidebar.added == [("new-project", "new-project")]
    assert fake._toast.messages == [("项目列表已更新", True)]


def test_on_sync_progress_advances_on_failed_and_skipped():
    dialog = SyncDialogStub()
    fake = SimpleNamespace(_sync_dialog=dialog)

    MainWindow._on_sync_progress(fake, 1, 3, "skill-a", "failed")
    MainWindow._on_sync_progress(fake, 2, 3, "skill-b", "skipped")

    assert dialog.updated == [("skill-a", "failed"), ("skill-b", "skipped")]
    assert dialog.progress == [2, 3]
