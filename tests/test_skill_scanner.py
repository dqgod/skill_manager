"""测试 SkillScanner 本地扫描"""

from pathlib import Path

from src.services.skill_scanner import SkillScanner, SkillInfo
from src.models.project import Project


class TestSkillScanner:
    def test_scan_directory_with_file_skill(self, tmp_path):
        # Bare files are not skills — only directories with SKILL.md are
        skills_dir = tmp_path / ".claude" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "my-skill.md").write_text("# My Skill")

        scanner = SkillScanner()
        result = scanner._scan_directory(
            skills_dir, tool="claude", level="global", device="local"
        )
        assert len(result) == 0  # bare .md file is not a valid skill

    def test_scan_directory_with_dir_skill(self, tmp_path):
        skills_dir = tmp_path / ".claude" / "skills"
        skills_dir.mkdir(parents=True)
        skill_dir = skills_dir / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# skill definition")
        (skill_dir / "README.md").write_text("# readme")
        (skill_dir / "main.py").write_text("print('hi')")

        scanner = SkillScanner()
        result = scanner._scan_directory(
            skills_dir, tool="claude", level="global", device="local"
        )
        assert len(result) == 1
        assert result[0].name == "my-skill"
        assert result[0].is_dir is True
        assert result[0].size > 0

    def test_scan_empty_directory(self, tmp_path):
        skills_dir = tmp_path / ".claude" / "skills"
        skills_dir.mkdir(parents=True)

        scanner = SkillScanner()
        result = scanner._scan_directory(
            skills_dir, tool="claude", level="global", device="local"
        )
        assert len(result) == 0

    def test_scan_nonexistent_directory(self, tmp_path):
        scanner = SkillScanner()
        result = scanner._scan_directory(
            tmp_path / "nonexistent", tool="claude",
            level="global", device="local"
        )
        assert len(result) == 0

    def test_skill_info_key(self):
        s = SkillInfo(
            name="test", tool="claude", path="/tmp/test",
            level="global", device="local", device_type="local",
        )
        assert s.key == "test|claude"

    def test_scan_local_global_uses_patched_paths(self, monkeypatch, tmp_path):
        claude_dir = tmp_path / ".claude" / "skills"
        claude_dir.mkdir(parents=True)
        cs = claude_dir / "claude-skill"
        cs.mkdir()
        (cs / "SKILL.md").write_text("# claude skill")

        codex_dir = tmp_path / ".codex" / "skills"
        codex_dir.mkdir(parents=True)
        cx = codex_dir / "codex-skill"
        cx.mkdir()
        (cx / "SKILL.md").write_text("# codex skill")

        # patch the reference in skill_scanner module namespace
        import src.services.skill_scanner as ss
        monkeypatch.setattr(ss, "GLOBAL_SKILL_PATHS", {
            "claude": claude_dir,
            "codex": codex_dir,
            "cc-switch": tmp_path / "nonexistent",
        })

        scanner = SkillScanner()
        results = scanner.scan_local_global(["claude", "codex"])
        names = sorted([r.name for r in results])
        assert "claude-skill" in names
        assert "codex-skill" in names

    def test_scan_local_project(self, tmp_path):
        proj_dir = tmp_path / "my-project"
        proj_dir.mkdir()
        skills_dir = proj_dir / ".claude" / "skills"
        skills_dir.mkdir(parents=True)
        ps = skills_dir / "proj-skill"
        ps.mkdir()
        (ps / "SKILL.md").write_text("# project skill")

        proj = Project(
            name="test-proj", local_path=str(proj_dir),
            tools="claude"
        )

        scanner = SkillScanner()
        results = scanner.scan_local_project(proj)
        assert len(results) == 1
        assert results[0].name == "proj-skill"
        assert results[0].level == "project"
        assert results[0].project_name == "test-proj"

    def test_scan_local_project_nonexistent_path(self):
        proj = Project(
            name="ghost", local_path="/nonexistent/path",
        )
        scanner = SkillScanner()
        results = scanner.scan_local_project(proj)
        assert len(results) == 0

    def test_format_size(self):
        from src.ui.skill_item_row import SkillItemRow
        assert SkillItemRow._format_size(0) == "0B"
        assert SkillItemRow._format_size(500) == "500B"
        assert SkillItemRow._format_size(1500) == "1KB"
        assert SkillItemRow._format_size(2_000_000) == "1.9MB"
