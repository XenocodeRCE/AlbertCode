"""
Support SKILL.md (standard Agent Skills).

- Découverte locale de skills dans des dossiers standards.
- Chargement des métadonnées depuis SKILL.md.
- Sélection heuristique des skills pertinents selon le prompt utilisateur.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx


@dataclass
class Skill:
    name: str
    title: str
    path: Path
    skill_file: Path
    summary: str
    content: str
    keywords: set[str] = field(default_factory=set)


def _tokenize(text: str) -> set[str]:
    return {
        w.lower()
        for w in re.findall(r"[a-zA-Z0-9_-]+", text)
        if len(w) >= 3
    }


def _extract_title_and_summary(content: str, fallback: str) -> tuple[str, str]:
    title = fallback
    summary = ""
    lines = content.splitlines()
    i = 0

    # Ignore un éventuel frontmatter YAML (--- ... ---)
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            i += 1
        if i < len(lines) and lines[i].strip() == "---":
            i += 1

    for line in lines[i:]:
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            title = s.lstrip("#").strip() or fallback
            continue
        if not s.startswith("```"):
            summary = s
            break
    return title, summary


def _skill_dirs_from_cwd(cwd: Path, include_home_paths: bool = True) -> list[Path]:
    """Construit la liste des emplacements standards de skills."""
    home_resolved = Path.home().resolve()
    candidates: list[Path] = []
    if include_home_paths:
        home = home_resolved
        candidates.extend([
            home / ".albert-code" / "skills",
            home / ".claude" / "skills",
            home / ".codex" / "skills",
        ])

    current = cwd.resolve()
    while True:
        if not include_home_paths and current == home_resolved:
            break

        candidates.extend([
            current / ".albert-code" / "skills",
            current / ".claude" / "skills",
            current / ".codex" / "skills",
        ])
        parent = current.parent
        if parent == current:
            break
        current = parent

    unique: list[Path] = []
    seen: set[str] = set()
    for p in candidates:
        key = str(p)
        if key not in seen:
            unique.append(p)
            seen.add(key)
    return unique


class SkillRegistry:
    def __init__(self, default_root: Path | None = None, include_home_paths: bool = True) -> None:
        self.skills: list[Skill] = []
        self.enabled: bool = True
        self.max_active_skills: int = 3
        self.default_root: Path = default_root or (Path.home() / ".albert-code" / "skills")
        self.include_home_paths = include_home_paths
        self._ensure_default_root()

    def _ensure_default_root(self) -> None:
        try:
            self.default_root.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Non bloquant: l'agent continue même si ce dossier ne peut pas être créé.
            pass

    @staticmethod
    def _sanitize_skill_name(raw: str) -> str:
        name = re.sub(r"[^a-zA-Z0-9._-]+", "-", raw.strip()).strip("-._").lower()
        return name or "skill"

    @staticmethod
    def _extract_skill_md_link(html: str, page_url: str) -> str | None:
        for m in re.finditer(r'href=["\']([^"\']*SKILL\.md[^"\']*)["\']', html, re.IGNORECASE):
            href = m.group(1)
            return urljoin(page_url, href)
        return None

    @staticmethod
    def _extract_github_repo(text: str) -> str | None:
        patterns = [
            r"npx\s+skills\s+add\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",
            r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1)
        return None

    @staticmethod
    def _extract_skill_hint_from_url(url: str) -> str:
        parsed = urlparse(url)
        slug = parsed.path.rstrip("/").split("/")[-1] if parsed.path else ""
        slug = slug.lower()
        slug = re.sub(r"-skill-md$", "", slug)
        # ex: ...-explain-like-socrates -> explain-like-socrates
        if "-" in slug:
            tail = "-".join(slug.split("-")[-4:])
            # garder la version longue si elle ressemble à un nom de skill
            if len(tail) >= 8:
                slug = tail
        slug = re.sub(r"[^a-z0-9._-]+", "-", slug).strip("-._")
        return slug

    def _fetch_first_valid(self, urls: list[str]) -> str:
        for u in urls:
            try:
                r = httpx.get(u, timeout=20.0, follow_redirects=True)
            except Exception:
                continue
            if r.status_code != 200:
                continue
            content = r.text or ""
            if self._looks_like_skill_markdown(content):
                return content
        return ""

    def _candidate_raw_urls(self, owner_repo: str, skill_hint: str = "") -> list[str]:
        owner_repo = owner_repo.strip().strip("/")
        repo_name = owner_repo.split("/")[-1]
        branches = ["main", "master"]
        candidates: list[str] = []

        skill_parts = [skill_hint] if skill_hint else []
        for branch in branches:
            base = f"https://raw.githubusercontent.com/{owner_repo}/{branch}"
            for hint in skill_parts:
                candidates.extend([
                    f"{base}/plugins/{repo_name}/claude-skills/{hint}/SKILL.md",
                    f"{base}/claude-skills/{hint}/SKILL.md",
                    f"{base}/skills/{hint}/SKILL.md",
                ])
            candidates.extend([
                f"{base}/SKILL.md",
                f"{base}/skills/SKILL.md",
                f"{base}/claude-skills/SKILL.md",
            ])
        return candidates

    def _github_find_skill_paths(self, owner_repo: str, branch: str, skill_hint: str = "") -> list[str]:
        """Retourne des chemins SKILL.md trouvés via l'API GitHub tree recursive."""
        api = f"https://api.github.com/repos/{owner_repo}/git/trees/{branch}?recursive=1"
        try:
            resp = httpx.get(api, timeout=20.0, follow_redirects=True)
        except Exception:
            return []
        if resp.status_code != 200:
            return []

        try:
            data = resp.json()
        except Exception:
            return []

        items = data.get("tree", [])
        paths: list[str] = []
        for it in items:
            path = str(it.get("path", ""))
            if path.lower().endswith("/skill.md") or path.lower() == "skill.md":
                paths.append(path)

        hint = skill_hint.lower().strip()

        def _rank(p: str) -> tuple[int, int, str]:
            low = p.lower()
            score = 0
            if "claude-skills" in low:
                score += 5
            if "skills" in low:
                score += 3
            if "/plugins/" in low:
                score += 2
            if hint and hint in low:
                score += 20
            return (-score, len(p), p)

        paths.sort(key=_rank)
        return paths

    @staticmethod
    def _looks_like_skill_markdown(content: str) -> bool:
        if "SKILL" in content[:200].upper() and "#" in content[:400]:
            return True
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()][:8]
        return any(ln.startswith("#") for ln in lines)

    def _derive_name_from_url(self, url: str) -> str:
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        if not parts:
            return "skill"
        last = parts[-1]
        if last.lower() == "skill.md" and len(parts) >= 2:
            last = parts[-2]
        return self._sanitize_skill_name(last)

    def install_from_url(self, url: str, skill_name: str | None = None) -> tuple[bool, str, Path | None]:
        """
        Installe un skill depuis une URL directe SKILL.md ou une page qui y référence.
        Retourne (ok, message, dossier_skill).
        """
        self._ensure_default_root()

        source = url.strip()
        if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", source):
            effective_hint = (skill_name or "").strip().lower()
            skill_md = self._fetch_first_valid(self._candidate_raw_urls(source, skill_hint=effective_hint))
            if not skill_md:
                # Fallback robuste: scanner l'arbre GitHub pour trouver un SKILL.md
                for branch in ("main", "master"):
                    paths = self._github_find_skill_paths(source, branch, skill_hint=effective_hint)
                    if not paths:
                        continue
                    urls = [
                        f"https://raw.githubusercontent.com/{source}/{branch}/{p}"
                        for p in paths[:20]
                    ]
                    skill_md = self._fetch_first_valid(urls)
                    if skill_md:
                        break
            if not skill_md:
                return False, "Repo detecte mais aucun SKILL.md exploitable trouve.", None
            final_url = f"https://github.com/{source}"
        else:
            try:
                resp = httpx.get(source, timeout=20.0, follow_redirects=True)
            except Exception as exc:
                return False, f"Telechargement impossible: {exc}", None

            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code} lors du telechargement", None

            body = resp.text or ""
            content_type = resp.headers.get("Content-Type", "")
            final_url = str(resp.url)

            skill_md = ""
            if final_url.lower().endswith("skill.md") or "markdown" in content_type.lower():
                skill_md = body
            elif self._looks_like_skill_markdown(body):
                skill_md = body
            else:
                link = self._extract_skill_md_link(body, final_url)
                if link:
                    try:
                        md_resp = httpx.get(link, timeout=20.0, follow_redirects=True)
                    except Exception as exc:
                        return False, f"Lien SKILL.md detecte mais telechargement echoue: {exc}", None
                    if md_resp.status_code == 200:
                        skill_md = md_resp.text or ""

                if not skill_md:
                    owner_repo = self._extract_github_repo(body)
                    if owner_repo:
                        hint = skill_name or self._extract_skill_hint_from_url(final_url)
                        skill_md = self._fetch_first_valid(self._candidate_raw_urls(owner_repo, skill_hint=hint))
                        if not skill_md:
                            for branch in ("main", "master"):
                                paths = self._github_find_skill_paths(owner_repo, branch, skill_hint=hint)
                                if not paths:
                                    continue
                                urls = [
                                    f"https://raw.githubusercontent.com/{owner_repo}/{branch}/{p}"
                                    for p in paths[:20]
                                ]
                                skill_md = self._fetch_first_valid(urls)
                                if skill_md:
                                    break

                if not skill_md:
                    return (
                        False,
                        "Aucun lien SKILL.md detecte. Essayez une URL raw GitHub, "
                        "ou /skills install owner/repo.",
                        None,
                    )

        if not skill_md.strip() or not self._looks_like_skill_markdown(skill_md):
            return False, "Le contenu telecharge ne ressemble pas a un SKILL.md valide.", None

        inferred_hint = self._extract_skill_hint_from_url(final_url)
        base_name = self._sanitize_skill_name(skill_name or inferred_hint or self._derive_name_from_url(final_url))
        target = self.default_root / base_name
        idx = 2
        while target.exists():
            target = self.default_root / f"{base_name}-{idx}"
            idx += 1

        try:
            target.mkdir(parents=True, exist_ok=False)
            (target / "SKILL.md").write_text(skill_md, encoding="utf-8")
        except OSError as exc:
            return False, f"Ecriture impossible: {exc}", None

        return True, f"Skill installe dans {target}", target

    def reload(self, cwd: Path | None = None) -> int:
        base = cwd or Path.cwd()
        loaded: list[Skill] = []
        self._ensure_default_root()

        for root in _skill_dirs_from_cwd(base, include_home_paths=self.include_home_paths):
            if not root.is_dir():
                continue

            # Support d'un layout dossier/skill/SKILL.md
            for entry in sorted(root.iterdir()):
                if not entry.is_dir():
                    continue
                skill_file = entry / "SKILL.md"
                if not skill_file.is_file():
                    continue
                try:
                    content = skill_file.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue

                title, summary = _extract_title_and_summary(content, fallback=entry.name)
                # Inclut un extrait du contenu pour un matching plus fidèle au skill.
                keywords = _tokenize(" ".join([entry.name, title, summary, content[:4000]]))
                loaded.append(
                    Skill(
                        name=entry.name,
                        title=title,
                        path=entry,
                        skill_file=skill_file,
                        summary=summary,
                        content=content,
                        keywords=keywords,
                    )
                )

            # Support d'un SKILL.md directement à la racine d'un skills/
            direct = root / "SKILL.md"
            if direct.is_file():
                try:
                    content = direct.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    content = ""
                if content:
                    title, summary = _extract_title_and_summary(content, fallback=root.name)
                    keywords = _tokenize(" ".join([root.name, title, summary, content[:4000]]))
                    loaded.append(
                        Skill(
                            name=root.name,
                            title=title,
                            path=root,
                            skill_file=direct,
                            summary=summary,
                            content=content,
                            keywords=keywords,
                        )
                    )

        dedup: dict[str, Skill] = {}
        for s in loaded:
            dedup[str(s.skill_file.resolve())] = s

        self.skills = sorted(dedup.values(), key=lambda s: s.name.lower())
        return len(self.skills)

    def list(self) -> list[Skill]:
        return list(self.skills)

    def get_by_name(self, name: str) -> Skill | None:
        target = name.strip().lower()
        for skill in self.skills:
            if skill.name.lower() == target:
                return skill
        return None

    def render_catalog_for_prompt(self) -> str:
        if not self.skills:
            return ""
        lines = [
            "\n## Available Skills (SKILL.md)",
            "You may use the following skills when relevant:",
        ]
        for s in self.skills[:50]:
            summary = s.summary[:160] if s.summary else "No summary"
            lines.append(f"- {s.name}: {summary}")
        return "\n".join(lines) + "\n"

    def select_for_prompt(self, user_text: str, max_skills: int | None = None) -> list[Skill]:
        if not self.enabled or not self.skills:
            return []

        query_tokens = _tokenize(user_text)
        if not query_tokens:
            return []

        scored: list[tuple[int, Skill]] = []
        for skill in self.skills:
            score = len(query_tokens.intersection(skill.keywords))
            if score > 0:
                scored.append((score, skill))

        scored.sort(key=lambda x: (-x[0], x[1].name.lower()))
        limit = max_skills if max_skills is not None else self.max_active_skills
        return [s for _, s in scored[:max(0, limit)]]

    def render_active_skills_for_prompt(self, user_text: str) -> str:
        selected = self.select_for_prompt(user_text)
        if not selected:
            return ""

        parts = [
            "## Activated Skills (SKILL.md)",
            "Apply these skills if relevant to the current request.",
        ]
        for s in selected:
            parts.append(f"\n### Skill: {s.name}\nPath: {s.skill_file}\n{s.content[:12000]}")
        return "\n".join(parts)
