"""
Boucle agent : orchestration des étapes LLM → tool calls → résultats.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .api import AlbertClient
from .config import ALBERT_BASE, C, DEFAULT_MAX_STEPS
from .context import compact_history as _compact, needs_compaction
from .display import (
    ask_confirmation,
    clear_line,
    print_assistant_text,
    print_thinking,
    print_tool_call,
    print_tool_result,
)
from .git_autocommit import auto_commit
from .memory.palace import AlbertMemoryPalace
from .project_config import ProjectConfig, format_for_prompt
from .prompts import SYSTEM_PROMPT
from .skills import Skill, SkillRegistry
from .snapshots import get_store, reset_store
from .tools import DANGEROUS_TOOLS, TOOL_EXECUTORS


@dataclass
class AgentSession:
    client:       AlbertClient
    messages:     list  = field(default_factory=list)
    auto_approve: bool  = False
    max_steps:    int   = DEFAULT_MAX_STEPS
    step_count:   int   = 0
    total_tool_calls: int = 0
    verbosity:    int   = 1   # 0=quiet  1=normal  2=verbose
    plan_first:   bool  = False
    git_commit:   bool  = True  # auto-commit après chaque écriture
    snapshot_guard: bool = True  # checkpoints internes avant écriture
    skills_enabled: bool = True
    active_skills: list[str] = field(default_factory=list)
    pinned_skills: list[str] = field(default_factory=list)
    todo_items: list[dict] = field(default_factory=list)  # [{"text": str, "done": bool}]
    persist_todo: bool = False
    todo_file_name: str = ".albert-code.todo.md"
    skill_registry: SkillRegistry = field(default_factory=SkillRegistry)
    project_cfg:  ProjectConfig = field(default_factory=ProjectConfig)
    memory_enabled: bool = True
    memory_auto_save: bool = True
    memory_auto_recall: bool = True
    memory_recall_top_k: int = 3
    memory_recall_max_tokens: int = 800
    memory_palace_path: str = "~/.albert-code/palace"
    memory_store: AlbertMemoryPalace | None = None
    _memory_warning_shown: bool = False

    # ──────────────────────────────────────────
    #  Initialisation
    # ──────────────────────────────────────────

    def initialize(self) -> None:
        """Crée le message système initial avec le contexte courant."""
        os_info    = f"{platform.system()} {platform.release()}"
        cwd        = os.getcwd()
        project_instructions = format_for_prompt(self.project_cfg)
        self.skill_registry.enabled = self.skills_enabled
        self.skill_registry.reload(Path(cwd))
        self.active_skills = []
        self.todo_items = []
        self._load_todo()
        self._ensure_memory_store()
        self.pinned_skills = [
            n for n in self.pinned_skills
            if self.skill_registry.get_by_name(n) is not None
        ]
        skills_catalog = self.skill_registry.render_catalog_for_prompt()
        reset_store()
        system_msg = SYSTEM_PROMPT.format(
            cwd=cwd,
            os_info=os_info,
            project_instructions=project_instructions,
            skills_catalog=skills_catalog,
        )
        self.messages = [{"role": "system", "content": system_msg}]

    def _ensure_memory_store(self) -> None:
        if self.memory_store is not None:
            return
        self.memory_store = AlbertMemoryPalace(
            enabled=self.memory_enabled,
            base_url=getattr(self.client, "base_url", ALBERT_BASE),
            palace_path=self.memory_palace_path,
            api_key=getattr(self.client, "api_key", None),
        )

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return len(text) // 4

    def _build_memory_context(self, query: str) -> str:
        self._ensure_memory_store()
        if not self.memory_auto_recall or self.memory_store is None:
            return ""

        memories = self.memory_store.recall(query, top_k=self.memory_recall_top_k)
        if not memories:
            status = self.memory_store.get_status()
            warning = str(status.get("warning", "")).strip()
            if warning and not self._memory_warning_shown:
                print(f"  {C.YELLOW}⚠️  {warning}{C.RESET}")
                self._memory_warning_shown = True
            return ""

        lines = ["[Mémoire contextuelle]"]
        for i, item in enumerate(memories, start=1):
            chunk = (
                f"{i}. (sim={item.similarity:.3f}, src={item.source_file})\n"
                f"{item.text.strip()}"
            )
            lines.append(chunk)
            current = "\n\n".join(lines)
            if self._estimate_tokens(current) >= self.memory_recall_max_tokens:
                lines.pop()
                break

        if len(lines) == 1:
            return ""
        lines.append("[/Mémoire contextuelle]")
        return "\n\n".join(lines)

    def recall_memories_for_prompt(self, query: str, top_k: int | None = None) -> list[dict[str, object]]:
        self._ensure_memory_store()
        if self.memory_store is None:
            return []
        results = self.memory_store.recall(query, top_k=top_k or self.memory_recall_top_k)
        return [
            {
                "text": it.text,
                "similarity": it.similarity,
                "source_file": it.source_file,
            }
            for it in results
        ]

    def save_memory_snapshot(self, force: bool = False) -> bool:
        self._ensure_memory_store()
        if self.memory_store is None:
            return False
        if not force and not self.memory_auto_save:
            return False
        ok = self.memory_store.save_conversation(self.messages)
        if not ok:
            status = self.memory_store.get_status()
            warning = str(status.get("warning", "")).strip()
            if warning and not self._memory_warning_shown:
                print(f"  {C.YELLOW}⚠️  {warning}{C.RESET}")
                self._memory_warning_shown = True
        return ok

    def memory_status(self) -> dict[str, object]:
        self._ensure_memory_store()
        if self.memory_store is None:
            return {"enabled": False, "available": False, "warning": "Memoire indisponible"}
        status = self.memory_store.get_status()
        status["auto_save"] = self.memory_auto_save
        status["auto_recall"] = self.memory_auto_recall
        status["recall_top_k"] = self.memory_recall_top_k
        status["recall_max_tokens"] = self.memory_recall_max_tokens
        return status

    def clear_memory_store(self) -> bool:
        self._ensure_memory_store()
        if self.memory_store is None:
            return False
        return self.memory_store.clear()

    def add_user_message(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def list_skills(self) -> list[Skill]:
        return self.skill_registry.list()

    def reload_skills(self) -> int:
        n = self.skill_registry.reload(Path.cwd())
        self.active_skills = []
        return n

    def install_skill_from_url(self, url: str, skill_name: str | None = None) -> tuple[bool, str]:
        ok, msg, _ = self.skill_registry.install_from_url(url, skill_name=skill_name)
        if ok:
            self.reload_skills()
        return ok, msg

    def set_skills_enabled(self, enabled: bool) -> None:
        self.skills_enabled = enabled
        self.skill_registry.enabled = enabled
        if not enabled:
            self.active_skills = []

    def pin_skill(self, name: str) -> tuple[bool, str]:
        skill = self.skill_registry.get_by_name(name)
        if skill is None:
            return False, f"Skill introuvable: {name}"
        if skill.name not in self.pinned_skills:
            self.pinned_skills.append(skill.name)
        return True, f"Skill epingle: {skill.name}"

    def unpin_skill(self, name: str) -> tuple[bool, str]:
        target = name.strip().lower()
        before = len(self.pinned_skills)
        self.pinned_skills = [s for s in self.pinned_skills if s.lower() != target]
        if len(self.pinned_skills) == before:
            return False, f"Skill non epingle: {name}"
        return True, f"Skill retire: {name}"

    def clear_pinned_skills(self) -> None:
        self.pinned_skills = []

    def set_todo_from_plan(self, plan_text: str) -> int:
        """Construit une checklist TODO à partir d'un plan texte."""
        lines = [ln.strip() for ln in plan_text.splitlines() if ln.strip()]
        tasks: list[str] = []

        for ln in lines:
            m_num = (
                ln.startswith("1.") or ln.startswith("2.") or ln.startswith("3.")
                or ln.startswith("4.") or ln.startswith("5.") or ln.startswith("6.")
                or ln.startswith("7.") or ln.startswith("8.") or ln.startswith("9.")
            )
            m_bul = ln.startswith("- ") or ln.startswith("* ")
            if m_num:
                parts = ln.split(".", 1)
                candidate = parts[1].strip() if len(parts) > 1 else ""
            elif m_bul:
                candidate = ln[2:].strip()
            else:
                candidate = ""

            if candidate:
                low = candidate.lower()
                if "[fin du plan]" in low or "plan propose" in low:
                    continue
                tasks.append(candidate)

        if not tasks:
            # fallback: prendre les 3 premières lignes non vides significatives
            tasks = [ln for ln in lines[:3] if len(ln) > 8]

        self.todo_items = [{"text": t, "done": False} for t in tasks[:12]]
        self._save_todo()
        return len(self.todo_items)

    def todo_counts(self) -> tuple[int, int]:
        total = len(self.todo_items)
        done = sum(1 for it in self.todo_items if it.get("done"))
        return done, total

    def todo_markdown(self) -> str:
        if not self.todo_items:
            return ""
        out = ["## TODO", ""]
        for it in self.todo_items:
            mark = "x" if it.get("done") else " "
            out.append(f"- [{mark}] {it.get('text', '')}")
        return "\n".join(out)

    def mark_next_todo_done(self) -> bool:
        for it in self.todo_items:
            if not it.get("done"):
                it["done"] = True
                self._save_todo()
                return True
        return False

    def clear_todo(self) -> None:
        self.todo_items = []
        self._save_todo()

    def mark_todo_done(self, index_1_based: int) -> tuple[bool, str]:
        idx = index_1_based - 1
        if idx < 0 or idx >= len(self.todo_items):
            return False, f"Index TODO invalide: {index_1_based}"
        self.todo_items[idx]["done"] = True
        self._save_todo()
        return True, f"TODO #{index_1_based} coche"

    def _todo_path(self) -> Path:
        return Path.cwd() / self.todo_file_name

    def _save_todo(self) -> None:
        if not self.persist_todo:
            return

        path = self._todo_path()
        if not self.todo_items:
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass
            return

        lines = [
            "# Albert Code TODO",
            "",
            "<!-- generated by Albert Code -->",
            "",
        ]
        for it in self.todo_items:
            mark = "x" if it.get("done") else " "
            text = str(it.get("text", "")).strip()
            if text:
                lines.append(f"- [{mark}] {text}")

        try:
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            pass

    def _load_todo(self) -> None:
        self.todo_items = []
        if not self.persist_todo:
            return

        path = self._todo_path()
        if not path.exists():
            return

        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return

        items: list[dict] = []
        for raw in content.splitlines():
            ln = raw.strip()
            if not ln.startswith("- [") or len(ln) < 7:
                continue
            if len(ln) < 5 or ln[2] != "[" or ln[4] != "]":
                continue
            marker = ln[3].lower()
            done = marker == "x"
            text = ln[6:].strip() if len(ln) > 6 else ""
            if text:
                items.append({"text": text, "done": done})

        self.todo_items = items[:12]

    def _messages_with_active_skills(self) -> list:
        """Construit les messages de requête avec injection contextuelle de skills."""
        if not self.skills_enabled or not self.messages:
            self.active_skills = []
            return self.messages

        last = self.messages[-1]
        if last.get("role") != "user":
            self.active_skills = []
            return self.messages

        prompt = str(last.get("content", ""))
        memory_blob = self._build_memory_context(prompt)
        selected: list[Skill]
        if self.pinned_skills:
            selected = []
            for name in self.pinned_skills:
                sk = self.skill_registry.get_by_name(name)
                if sk is not None:
                    selected.append(sk)
            selected = selected[: self.skill_registry.max_active_skills]
        else:
            selected = self.skill_registry.select_for_prompt(prompt)
        self.active_skills = [s.name for s in selected]

        skill_blob = ""
        if selected:
            parts = [
                "## Activated Skills (SKILL.md)",
                "Apply these skills if relevant to the current request.",
            ]
            for s in selected:
                parts.append(f"\n### Skill: {s.name}\nPath: {s.skill_file}\n{s.content[:12000]}")
            skill_blob = "\n".join(parts)
        todo_blob = self.todo_markdown()

        extra_msgs: list[dict] = []
        if skill_blob:
            extra_msgs.append({"role": "system", "content": skill_blob})
        if memory_blob:
            extra_msgs.append({"role": "system", "content": memory_blob})
        if todo_blob:
            extra_msgs.append({
                "role": "system",
                "content": (
                    f"{todo_blob}\n\n"
                    "Use this checklist as execution tracker. "
                    "Prioritize unchecked items and avoid redoing checked ones."
                ),
            })

        if not extra_msgs:
            return self.messages

        return self.messages[:-1] + extra_msgs + [last]

    def list_checkpoints(self) -> list:
        """Retourne l'historique des checkpoints de la session."""
        return get_store().list()

    def latest_checkpoint_id(self) -> int | None:
        cp = get_store().latest()
        return cp.id if cp else None

    def restore_checkpoint(self, cp_id: int) -> tuple[bool, str]:
        """Restaure un checkpoint donné."""
        return get_store().restore(cp_id)

    @staticmethod
    def _snapshot_paths_for_tool(fn_name: str, fn_args: dict) -> list[str]:
        """Détermine les fichiers à sauvegarder avant exécution d'un tool."""
        if fn_name in {"write_file", "edit_file", "multi_edit_file"}:
            path = fn_args.get("path", "")
            if isinstance(path, str) and path.strip():
                return [path]
        return []

    # ──────────────────────────────────────────
    #  Boucle agent
    # ──────────────────────────────────────────

    def run(self) -> str:
        """Exécute la boucle agent jusqu'à une réponse finale ou la limite de steps."""
        self.step_count = 0

        while self.step_count < self.max_steps:
            self.step_count += 1

            if self.verbosity >= 1:
                print_thinking()

            try:
                t0       = time.time()
                request_messages = self._messages_with_active_skills()
                response = self.client.chat(request_messages)
                duration = time.time() - t0
            except Exception as exc:
                clear_line()
                print(f"\n  {C.RED}❌ Erreur API : {exc}{C.RESET}\n")
                return ""

            clear_line()

            choice       = response["choices"][0]
            message      = choice["message"]
            finish_reason = choice.get("finish_reason", "")

            self.messages.append(message)

            tool_calls = message.get("tool_calls", [])

            # Texte narratif éventuel avant les tool calls
            if message.get("content"):
                text = message["content"].strip()
                if text:
                    print_assistant_text(text)

            # Pas de tool_calls → réponse finale
            if not tool_calls:
                if self.verbosity >= 1:
                    ms = int(duration * 1000)
                    print(f"  {C.DIM}({ms}ms | step {self.step_count}){C.RESET}")
                return message.get("content", "")

            # Afficher la métadonnée du step
            if self.verbosity >= 1:
                ms    = int(duration * 1000)
                n     = len(tool_calls)
                label = f"{n} tool{'s' if n > 1 else ''}"
                print(f"  {C.DIM}({ms}ms | step {self.step_count} | {label}){C.RESET}")

            # Exécuter chaque tool call
            step_success = False
            for tc in tool_calls:
                fn_name     = tc["function"]["name"]
                fn_args_raw = tc["function"].get("arguments", "{}")
                tc_id       = tc.get("id", "call_unknown")
                checkpoint_id: int | None = None
                checkpoint_path: str = ""

                try:
                    fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                except json.JSONDecodeError:
                    fn_args = {}

                if self.verbosity >= 1:
                    print_tool_call(fn_name, fn_args)

                # Confirmation pour les outils dangereux
                if fn_name in DANGEROUS_TOOLS and not self.auto_approve:
                    if not ask_confirmation(fn_name, fn_args):
                        result = "❌ Action refused by user."
                        print(f"  {C.YELLOW}  ⏭️  Refusé{C.RESET}")
                        self.messages.append({
                            "role":        "tool",
                            "tool_call_id": tc_id,
                            "content":     result,
                        })
                        continue

                executor = TOOL_EXECUTORS.get(fn_name)
                if executor:
                    try:
                        if self.snapshot_guard:
                            snap_paths = self._snapshot_paths_for_tool(fn_name, fn_args)
                            if snap_paths:
                                cp = get_store().take(
                                    description=f"{fn_name}  {', '.join(snap_paths)}",
                                    paths=snap_paths,
                                )
                                checkpoint_id = cp.id
                                checkpoint_path = snap_paths[0]

                        # Injecter les ignore patterns du projet pour les outils qui les utilisent
                        if fn_name in ("list_files", "grep_search") and self.project_cfg.ignore_patterns:
                            fn_args = {**fn_args, "_ignore_patterns": self.project_cfg.ignore_patterns}
                        result = executor(fn_args)
                        if not str(result).startswith(("❌", "⚠️")):
                            step_success = True
                    except Exception as exc:
                        result = f"❌ Tool execution error: {exc}"
                else:
                    result = f"❌ Unknown tool: {fn_name}"

                self.total_tool_calls += 1

                if self.verbosity >= 1:
                    is_big = self.verbosity < 2 and result.count("\n") > 15
                    print_tool_result(result, collapsed=is_big)

                if (
                    self.verbosity >= 1
                    and checkpoint_id is not None
                    and not result.startswith(("❌", "⚠️"))
                ):
                    print(
                        f"  {C.DIM}🛟 checkpoint #{checkpoint_id}{C.RESET}"
                        f" {C.GRAY}({checkpoint_path}){C.RESET}"
                    )

                # Auto-commit si l'écriture a réussi
                if self.git_commit:
                    auto_commit(fn_name, fn_args, result, self.verbosity)

                self.messages.append({
                    "role":        "tool",
                    "tool_call_id": tc_id,
                    "content":     result,
                })

            if step_success and self.todo_items:
                if self.mark_next_todo_done() and self.verbosity >= 1:
                    done, total = self.todo_counts()
                    print(f"  {C.DIM}☑ TODO {done}/{total}{C.RESET}")

        print(f"\n  {C.YELLOW}⚠️  Limite de {self.max_steps} étapes atteinte.{C.RESET}\n")
        return ""

    # ──────────────────────────────────────────
    #  Gestion de l'historique
    # ──────────────────────────────────────────

    def compact_history(self) -> None:
        """Compresse les messages intermédiaires pour économiser des tokens."""
        self.messages = _compact(self.messages, client=self.client, verbosity=self.verbosity)

    def set_memory_recall_enabled(self, enabled: bool) -> None:
        self.memory_auto_recall = enabled
