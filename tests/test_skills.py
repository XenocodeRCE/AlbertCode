"""Tests du support SKILL.md."""

from pathlib import Path

from albert_code.skills import SkillRegistry


def test_skill_registry_loads_skill_md(tmp_path: Path):
    root = tmp_path / ".albert-code" / "skills" / "python-lint"
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(
        "# Python Linting\n\nUse this skill to fix lint and formatting issues.",
        encoding="utf-8",
    )

    reg = SkillRegistry(default_root=tmp_path / "skills", include_home_paths=False)
    n = reg.reload(tmp_path)

    assert n == 1
    skills = reg.list()
    assert skills[0].name == "python-lint"
    assert "lint" in skills[0].summary.lower()


def test_skill_registry_selects_relevant_skill(tmp_path: Path):
    s1 = tmp_path / ".albert-code" / "skills" / "pytest-fixes"
    s1.mkdir(parents=True)
    (s1 / "SKILL.md").write_text(
        "# Pytest Fixes\n\nFix failing tests and assertions.",
        encoding="utf-8",
    )

    s2 = tmp_path / ".albert-code" / "skills" / "css-theme"
    s2.mkdir(parents=True)
    (s2 / "SKILL.md").write_text(
        "# CSS Theme\n\nDesign and tweak UI colors.",
        encoding="utf-8",
    )

    reg = SkillRegistry(default_root=tmp_path / "skills", include_home_paths=False)
    reg.reload(tmp_path)

    selected = reg.select_for_prompt("please fix failing tests in pytest")
    names = [s.name for s in selected]
    assert "pytest-fixes" in names


def test_skill_registry_can_be_disabled(tmp_path: Path):
    s1 = tmp_path / ".albert-code" / "skills" / "ops"
    s1.mkdir(parents=True)
    (s1 / "SKILL.md").write_text("# Ops\n\nDeploy and operate.", encoding="utf-8")

    reg = SkillRegistry(default_root=tmp_path / "skills", include_home_paths=False)
    reg.reload(tmp_path)
    reg.enabled = False

    selected = reg.select_for_prompt("deploy this service")
    assert selected == []


def test_skill_registry_creates_default_root(tmp_path: Path):
    root = tmp_path / "skills-root"
    assert not root.exists()

    reg = SkillRegistry(default_root=root)

    assert reg.default_root == root
    assert root.exists()
    assert root.is_dir()


def test_skill_registry_install_from_direct_skill_md_url(tmp_path: Path, monkeypatch):
    class FakeResponse:
        def __init__(self, status_code: int, text: str, url: str, headers: dict[str, str] | None = None):
            self.status_code = status_code
            self.text = text
            self.url = url
            self.headers = headers or {}

    def fake_get(url: str, timeout: float, follow_redirects: bool):
        return FakeResponse(
            200,
            "# Explain Like Socrates\n\nAsk guiding questions before giving the answer.",
            "https://example.test/skills/explain-like-socrates/SKILL.md",
            {"Content-Type": "text/markdown"},
        )

    monkeypatch.setattr("albert_code.skills.httpx.get", fake_get)

    reg = SkillRegistry(default_root=tmp_path / "skills")
    ok, msg, target = reg.install_from_url("https://example.test/some-skill")

    assert ok is True
    assert target is not None
    assert (target / "SKILL.md").is_file()
    assert "installe" in msg.lower()


def test_skill_registry_install_from_owner_repo(tmp_path: Path, monkeypatch):
    class FakeResponse:
        def __init__(self, status_code: int, text: str, url: str, headers: dict[str, str] | None = None):
            self.status_code = status_code
            self.text = text
            self.url = url
            self.headers = headers or {}

    def fake_get(url: str, timeout: float, follow_redirects: bool):
        if "raw.githubusercontent.com" in url and url.endswith("/SKILL.md"):
            return FakeResponse(
                200,
                "# Repo Skill\n\nDo the thing.",
                url,
                {"Content-Type": "text/markdown"},
            )
        return FakeResponse(404, "not found", url)

    monkeypatch.setattr("albert_code.skills.httpx.get", fake_get)

    reg = SkillRegistry(default_root=tmp_path / "skills")
    ok, msg, target = reg.install_from_url("owner/repo")

    assert ok is True
    assert "installe" in msg.lower()
    assert target is not None
    assert (target / "SKILL.md").is_file()


def test_skill_registry_install_from_skillsmp_html_fallback_to_github(tmp_path: Path, monkeypatch):
    class FakeResponse:
        def __init__(self, status_code: int, text: str, url: str, headers: dict[str, str] | None = None):
            self.status_code = status_code
            self.text = text
            self.url = url
            self.headers = headers or {}

    def fake_get(url: str, timeout: float, follow_redirects: bool):
        if "skillsmp.com" in url:
            html = (
                "<html><body>"
                "<p>Install: npx skills add sickn33/antigravity-awesome-skills</p>"
                "</body></html>"
            )
            return FakeResponse(200, html, url, {"Content-Type": "text/html"})

        if "raw.githubusercontent.com/sickn33/antigravity-awesome-skills" in url and url.endswith("/SKILL.md"):
            return FakeResponse(
                200,
                "# Explain Like Socrates\n\nUse guiding questions.",
                url,
                {"Content-Type": "text/markdown"},
            )

        return FakeResponse(404, "not found", url)

    monkeypatch.setattr("albert_code.skills.httpx.get", fake_get)

    reg = SkillRegistry(default_root=tmp_path / "skills")
    ok, msg, target = reg.install_from_url(
        "https://skillsmp.com/fr/skills/sickn33-antigravity-awesome-skills-plugins-antigravity-awesome-skills-claude-skills-explain-like-socrates-skill-md"
    )

    assert ok is True
    assert "installe" in msg.lower()
    assert target is not None
    assert (target / "SKILL.md").is_file()


def test_skill_registry_install_from_owner_repo_uses_github_tree_fallback(tmp_path: Path, monkeypatch):
    class FakeResponse:
        def __init__(self, status_code: int, text: str, url: str, headers: dict[str, str] | None = None, json_data=None):
            self.status_code = status_code
            self.text = text
            self.url = url
            self.headers = headers or {}
            self._json_data = json_data

        def json(self):
            if self._json_data is not None:
                return self._json_data
            raise ValueError("no json")

    def fake_get(url: str, timeout: float, follow_redirects: bool):
        # Les URL candidates directes échouent -> fallback GitHub tree nécessaire
        if "raw.githubusercontent.com/owner/repo" in url and "git/trees" not in url:
            if url.endswith("plugins/antigravity-awesome-skills/claude-skills/explain-like-socrates/SKILL.md"):
                return FakeResponse(
                    200,
                    "# Explain Like Socrates\n\nGuide by questions.",
                    url,
                    {"Content-Type": "text/markdown"},
                )
            return FakeResponse(404, "not found", url)

        if "api.github.com/repos/owner/repo/git/trees/main?recursive=1" in url:
            return FakeResponse(
                200,
                "",
                url,
                {"Content-Type": "application/json"},
                json_data={
                    "tree": [
                        {"path": "README.md"},
                        {"path": "plugins/antigravity-awesome-skills/claude-skills/explain-like-socrates/SKILL.md"},
                    ]
                },
            )

        if "api.github.com/repos/owner/repo/git/trees/master?recursive=1" in url:
            return FakeResponse(404, "", url, {"Content-Type": "application/json"}, json_data={})

        return FakeResponse(404, "not found", url)

    monkeypatch.setattr("albert_code.skills.httpx.get", fake_get)

    reg = SkillRegistry(default_root=tmp_path / "skills")
    ok, msg, target = reg.install_from_url("owner/repo")

    assert ok is True
    assert "installe" in msg.lower()
    assert target is not None
    assert (target / "SKILL.md").is_file()


def test_extract_title_summary_skips_yaml_frontmatter(tmp_path: Path):
    s1 = tmp_path / ".albert-code" / "skills" / "with-frontmatter"
    s1.mkdir(parents=True)
    (s1 / "SKILL.md").write_text(
        "---\nname: test\n---\n\n# Explain Like Socrates\n\nGuide with questions.",
        encoding="utf-8",
    )

    reg = SkillRegistry(default_root=tmp_path / "skills", include_home_paths=False)
    reg.reload(tmp_path)
    skills = reg.list()

    assert skills
    assert skills[0].title == "Explain Like Socrates"
    assert skills[0].summary == "Guide with questions."


def test_install_from_skillsmp_url_prefers_hint_path(tmp_path: Path, monkeypatch):
    class FakeResponse:
        def __init__(self, status_code: int, text: str, url: str, headers: dict[str, str] | None = None, json_data=None):
            self.status_code = status_code
            self.text = text
            self.url = url
            self.headers = headers or {}
            self._json_data = json_data

        def json(self):
            if self._json_data is not None:
                return self._json_data
            raise ValueError("no json")

    def fake_get(url: str, timeout: float, follow_redirects: bool):
        if "skillsmp.com" in url:
            html = "<html><body><p>Install: npx skills add owner/repo</p></body></html>"
            return FakeResponse(200, html, url, {"Content-Type": "text/html"})

        if "api.github.com/repos/owner/repo/git/trees/main?recursive=1" in url:
            return FakeResponse(
                200,
                "",
                url,
                {"Content-Type": "application/json"},
                json_data={
                    "tree": [
                        {"path": "skills/general/SKILL.md"},
                        {"path": "plugins/repo/claude-skills/explain-like-socrates/SKILL.md"},
                    ]
                },
            )

        if "raw.githubusercontent.com/owner/repo/main/plugins/repo/claude-skills/explain-like-socrates/SKILL.md" in url:
            return FakeResponse(200, "# Explain Like Socrates\n\nAsk questions first.", url, {"Content-Type": "text/markdown"})

        if "raw.githubusercontent.com/owner/repo/main/skills/general/SKILL.md" in url:
            return FakeResponse(200, "# General\n\nGeneric instructions.", url, {"Content-Type": "text/markdown"})

        return FakeResponse(404, "not found", url)

    monkeypatch.setattr("albert_code.skills.httpx.get", fake_get)

    reg = SkillRegistry(default_root=tmp_path / "skills", include_home_paths=False)
    ok, _msg, target = reg.install_from_url(
        "https://skillsmp.com/fr/skills/owner-repo-plugins-repo-claude-skills-explain-like-socrates-skill-md"
    )

    assert ok is True
    assert target is not None
    content = (target / "SKILL.md").read_text(encoding="utf-8")
    assert "Explain Like Socrates" in content
