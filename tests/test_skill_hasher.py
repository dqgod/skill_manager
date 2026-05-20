"""测试 SkillHasher 哈希计算和对比去重"""

from src.services.skill_hasher import SkillHasher, DiffResult
from src.services.skill_scanner import SkillInfo


def _make_skill(name: str, tool: str = "claude", path: str = "/tmp/test",
                device_type: str = "local", device: str = "local") -> SkillInfo:
    return SkillInfo(
        name=name, tool=tool, path=path, level="global",
        device=device, device_type=device_type,
    )


class TestSkillHasher:
    def test_compute_local_hash_file(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("hello world")
        h = SkillHasher.compute_local_hash(str(f))
        assert len(h) == 64
        assert h == SkillHasher.compute_local_hash(str(f))  # deterministic

    def test_compute_local_hash_directory(self, tmp_path):
        d = tmp_path / "skill"
        d.mkdir()
        (d / "a.txt").write_text("aaa")
        (d / "b.txt").write_text("bbb")
        h = SkillHasher.compute_local_hash(str(d))
        assert len(h) == 64
        # deterministic
        assert h == SkillHasher.compute_local_hash(str(d))

    def test_compute_local_hash_directory_changes_with_filename(self, tmp_path):
        left = tmp_path / "left"
        right = tmp_path / "right"
        left.mkdir()
        right.mkdir()
        (left / "a.txt").write_text("same")
        (right / "b.txt").write_text("same")

        assert SkillHasher.compute_local_hash(str(left)) != SkillHasher.compute_local_hash(str(right))

    def test_compute_local_hash_nonexistent(self, tmp_path):
        h = SkillHasher.compute_local_hash(str(tmp_path / "nope"))
        assert h == ""

    def test_compare_synced(self):
        hasher = SkillHasher()
        local = [_make_skill("s1", path=__file__)]
        remote = [_make_skill("s1", path=__file__)]
        result = hasher.compare(local, remote)
        assert len(result.synced) == 1
        assert len(result.local_only) == 0
        assert len(result.remote_only) == 0
        assert len(result.conflict) == 0

    def test_compare_local_only(self):
        hasher = SkillHasher()
        local = [_make_skill("s1")]
        result = hasher.compare(local, [])
        assert len(result.local_only) == 1

    def test_compare_remote_only(self):
        hasher = SkillHasher()
        remote = [_make_skill("s1", device_type="remote", device="srv")]
        result = hasher.compare([], remote)
        assert len(result.remote_only) == 1

    def test_compare_conflict(self, tmp_path):
        hasher = SkillHasher()
        f1 = tmp_path / "a.txt"
        f1.write_text("content A")
        f2 = tmp_path / "b.txt"
        f2.write_text("content B")

        local = [_make_skill("s1", path=str(f1))]
        remote = [_make_skill("s1", path=str(f2))]
        result = hasher.compare(local, remote)
        assert len(result.conflict) == 1

    def test_compare_by_name_and_tool(self):
        """Same name, different tool — different keys."""
        hasher = SkillHasher()
        local = [_make_skill("s1", tool="claude", path=__file__)]
        remote = [_make_skill("s1", tool="codex", path=__file__)]
        result = hasher.compare(local, remote)
        assert len(result.local_only) == 1
        assert len(result.remote_only) == 1

    def test_classify_skills(self, tmp_path):
        hasher = SkillHasher()
        same = tmp_path / "same.txt"
        same.write_text("same")
        diff_l = tmp_path / "diff_l.txt"
        diff_l.write_text("local content")
        diff_r = tmp_path / "diff_r.txt"
        diff_r.write_text("remote content")

        local = [
            _make_skill("synced", path=str(same)),
            _make_skill("conflict", path=str(diff_l)),
            _make_skill("only-local", path=str(diff_l)),
        ]
        remote = [
            _make_skill("synced", path=str(same)),
            _make_skill("conflict", path=str(diff_r)),
        ]
        tagged = hasher.classify_skills(local, remote)
        statuses = {s.name: s.hash for s in tagged}
        assert statuses["synced"] == "synced"
        assert statuses["conflict"] == "conflict"
        assert statuses["only-local"] == "local-only"

    def test_classify_remote_skills(self, tmp_path):
        hasher = SkillHasher()
        same = tmp_path / "same.txt"
        same.write_text("same")

        local = [_make_skill("shared", path=str(same))]
        remote = [
            _make_skill("shared", path=str(same)),
            _make_skill("remote-only", path=str(same), device_type="remote", device="srv"),
        ]
        tagged = hasher.classify_remote_skills(local, remote)
        statuses = {s.name: s.hash for s in tagged}
        assert statuses["shared"] == "synced"
        assert statuses["remote-only"] == "remote-only"

    def test_diff_result_properties(self):
        diff = DiffResult(
            synced=[_make_skill("a")],
            local_only=[_make_skill("b")],
            remote_only=[_make_skill("c")],
            conflict=[(_make_skill("d"), _make_skill("d"))],
        )
        assert diff.has_differences is True
        assert diff.total == 4
