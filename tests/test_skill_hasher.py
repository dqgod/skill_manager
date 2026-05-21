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

    # ---- PR-1: noise file filtering ----

    def test_hash_ignores_macos_ds_store(self, tmp_path):
        """Adding .DS_Store must NOT change the directory hash."""
        d = tmp_path / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text("hello")
        h_clean = SkillHasher.compute_local_hash(str(d))
        SkillHasher.clear_cache()
        (d / ".DS_Store").write_bytes(b"junk")
        h_with_noise = SkillHasher.compute_local_hash(str(d))
        assert h_clean == h_with_noise

    def test_hash_ignores_pycache_dir(self, tmp_path):
        d = tmp_path / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text("hi")
        h_clean = SkillHasher.compute_local_hash(str(d))
        SkillHasher.clear_cache()
        pyc = d / "__pycache__"
        pyc.mkdir()
        (pyc / "x.pyc").write_bytes(b"\x00\x01")
        h_with_noise = SkillHasher.compute_local_hash(str(d))
        assert h_clean == h_with_noise

    def test_hash_matches_remote_format(self, tmp_path):
        """Local algorithm must reproduce sha256sum-style aggregation."""
        import hashlib, subprocess, shutil
        d = tmp_path / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text("hello\n")
        sub = d / "sub"
        sub.mkdir()
        (sub / "x.txt").write_text("world\n")

        SkillHasher.clear_cache()
        local_hash = SkillHasher.compute_local_hash(str(d))

        # Reproduce remote aggregation locally with shell tools (skip on systems
        # without sha256sum / sort -z).
        if not shutil.which("sha256sum") or not shutil.which("sort"):
            return
        out = subprocess.check_output(
            f"cd {d} && LC_ALL=C find . -type f ! -name '.DS_Store' "
            f"! -name '*.swp' ! -name '*.swo' ! -name '*.tmp' "
            f"! -name '*.pyc' ! -name '*.orig' ! -name '*.rej' "
            f"! -name '*.bak' ! -name 'Thumbs.db' ! -name 'desktop.ini' "
            f"! -path '*/.git/*' ! -path '*/.hg/*' ! -path '*/.idea/*' "
            f"! -path '*/.mypy_cache/*' ! -path '*/.pytest_cache/*' "
            f"! -path '*/.svn/*' ! -path '*/.vscode/*' "
            f"! -path '*/__pycache__/*' ! -path '*/node_modules/*' "
            f"-print0 | LC_ALL=C sort -z | xargs -0 sha256sum | "
            f"sha256sum | cut -d' ' -f1",
            shell=True,
        ).decode().strip()
        assert local_hash == out

    # ---- PR-5: hash cache ----

    def test_local_hash_cache_hit(self, tmp_path):
        d = tmp_path / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text("a")
        SkillHasher.clear_cache()
        h1 = SkillHasher.compute_local_hash(str(d))
        # Mutate the file's sha but keep mtime/size identical: cache MUST
        # short-circuit and return the stale value (this is by design).
        # We assert it returns the same value by re-computing.
        h2 = SkillHasher.compute_local_hash(str(d))
        assert h1 == h2
        # Now actually change content/size: cache key changes, hash differs.
        (d / "SKILL.md").write_text("aa")
        h3 = SkillHasher.compute_local_hash(str(d))
        assert h3 != h1

    # ---- PR-3: dual-side compare signature ----

    def test_compare_dual_side_kwargs_local_only(self, tmp_path):
        """Both sides local: passing left_connection=None / right_connection=None
        works the same as the legacy positional call."""
        hasher = SkillHasher()
        f = tmp_path / "skill.md"
        f.write_text("xyz")
        left = [_make_skill("s1", path=str(f))]
        right = [_make_skill("s1", path=str(f))]
        result = hasher.compare(
            left, right,
            left_connection=None,
            right_connection=None,
        )
        assert len(result.synced) == 1

    def test_compare_legacy_remote_connection_still_works(self, tmp_path):
        """Old callers passing remote_connection= must keep functioning —
        it now aliases to right_connection internally."""
        hasher = SkillHasher()
        f = tmp_path / "skill.md"
        f.write_text("payload")
        left = [_make_skill("s1", path=str(f))]
        right = [_make_skill("s1", path=str(f))]
        # remote_connection=None still classifies via local FS hash on right.
        result = hasher.compare(left, right, remote_connection=None)
        assert len(result.synced) == 1
