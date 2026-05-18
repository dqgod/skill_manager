from src.models.connection import Connection, ConnectionModel
from src.models.project import Project, ProjectModel
from src.models.sync_history import SyncRecord, SyncHistoryModel


class TestConnectionModel:
    def test_save_and_get(self):
        conn = Connection(name="test-server", host="192.168.1.1", username="root")
        ConnectionModel.save(conn)
        loaded = ConnectionModel.get(conn.id)
        assert loaded is not None
        assert loaded.name == "test-server"
        assert loaded.host == "192.168.1.1"
        assert loaded.port == 22

    def test_get_all(self):
        ConnectionModel.save(Connection(name="s1", host="10.0.0.1"))
        ConnectionModel.save(Connection(name="s2", host="10.0.0.2"))
        all_conns = ConnectionModel.get_all()
        assert len(all_conns) == 2

    def test_delete(self):
        conn = Connection(name="to-delete", host="10.0.0.3")
        ConnectionModel.save(conn)
        ConnectionModel.delete(conn.id)
        assert ConnectionModel.get(conn.id) is None

    def test_get_by_name(self):
        ConnectionModel.save(Connection(name="unique-srv", host="10.0.0.4"))
        found = ConnectionModel.get_by_name("unique-srv")
        assert found is not None
        assert found.host == "10.0.0.4"
        assert ConnectionModel.get_by_name("no-exist") is None

    def test_update(self):
        conn = Connection(name="old-name", host="10.0.0.5")
        ConnectionModel.save(conn)
        conn.name = "new-name"
        ConnectionModel.save(conn)
        loaded = ConnectionModel.get(conn.id)
        assert loaded.name == "new-name"

    def test_password_enc_stored(self):
        conn = Connection(
            name="pw-server", host="10.0.0.6",
            auth_type="password", password_enc=b"\x00\x01\x02"
        )
        ConnectionModel.save(conn)
        loaded = ConnectionModel.get(conn.id)
        assert loaded.password_enc == b"\x00\x01\x02"


class TestProjectModel:
    def test_save_and_get(self):
        proj = Project(name="my-project", local_path="/home/user/proj")
        ProjectModel.save(proj)
        loaded = ProjectModel.get(proj.id)
        assert loaded.name == "my-project"
        assert loaded.local_path == "/home/user/proj"

    def test_tool_list(self):
        proj = Project(name="p", local_path="/tmp/p", tools="codex,claude")
        assert proj.tool_list() == ["codex", "claude"]

    def test_get_all(self):
        ProjectModel.save(Project(name="p1", local_path="/tmp/p1"))
        ProjectModel.save(Project(name="p2", local_path="/tmp/p2"))
        assert len(ProjectModel.get_all()) == 2

    def test_delete(self):
        proj = Project(name="del", local_path="/tmp/del")
        ProjectModel.save(proj)
        ProjectModel.delete(proj.id)
        assert ProjectModel.get(proj.id) is None

    def test_get_by_local_path(self):
        ProjectModel.save(Project(name="p", local_path="/unique/path"))
        found = ProjectModel.get_by_local_path("/unique/path")
        assert found is not None
        assert found.name == "p"

    def test_duplicate_path_raises(self):
        ProjectModel.save(Project(name="p1", local_path="/dup/path"))
        try:
            ProjectModel.save(Project(name="p2", local_path="/dup/path"))
            assert False, "should have raised"
        except Exception:
            pass


class TestSyncHistoryModel:
    def test_add_and_query(self):
        rec = SyncRecord(
            direction="push",
            source_device="local", source_level="global", source_tool="claude",
            target_device="remote", target_level="global", target_tool="claude",
            skill_name="test-skill", status="success",
        )
        SyncHistoryModel.add(rec)
        results = SyncHistoryModel.query(limit=10)
        assert len(results) == 1
        assert results[0].skill_name == "test-skill"

    def test_add_bulk(self):
        records = [
            SyncRecord(
                direction="push", source_device="local", source_level="global",
                source_tool="claude", target_device="remote", target_level="global",
                target_tool="claude", skill_name=f"skill-{i}", status="success",
            )
            for i in range(3)
        ]
        SyncHistoryModel.add_bulk(records)
        assert len(SyncHistoryModel.query(limit=10)) == 3

    def test_query_by_project(self):
        rec = SyncRecord(
            direction="push", source_device="local", source_level="project",
            source_project_id="proj-1", source_tool="claude",
            target_device="remote", target_level="project",
            target_project_id="proj-1", target_tool="claude",
            skill_name="proj-skill", status="success",
        )
        SyncHistoryModel.add(rec)
        results = SyncHistoryModel.query(project_id="proj-1")
        assert len(results) == 1

    def test_query_by_device(self):
        rec = SyncRecord(
            direction="push", source_device="dev-A", source_level="global",
            source_tool="claude", target_device="dev-B", target_level="global",
            target_tool="claude", skill_name="s", status="failed", detail="timeout",
        )
        SyncHistoryModel.add(rec)
        results = SyncHistoryModel.query(device="dev-A")
        assert len(results) == 1
        assert results[0].detail == "timeout"
