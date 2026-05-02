"""
Interface en ligne de commande : REPL, commandes /, affichage, point d'entrée.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .agent import AgentSession
from .api import AlbertClient
from .config import (
    ALBERT_BASE,
    C,
    DEFAULT_MAX_STEPS,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
)
from .context import needs_compaction
from .display import (
    clear_line,
    draw_box,
    header,
    plines,
    print_assistant_text,
    print_logo,
    print_thinking,
)
from .project_config import load_project_config

_M = "  "  # marge gauche (cohérente avec display.py)

# Active readline si disponible (historique flèche ↑)
try:
    import readline  # noqa: F401
except ImportError:
    try:
        import pyreadline3 as readline  # noqa: F401  # Windows
    except ImportError:
        pass

# ──────────────────────────────────────────────
#  Textes d'interface
# ──────────────────────────────────────────────

HELP_TEXT = f"""
  {C.BOLD}{C.BLANC}Commandes Albert Code{C.RESET}

  {C.GRAY_LIGHT}/help{C.RESET}      — Afficher cette aide
    {C.GRAY_LIGHT}/init{C.RESET}      — Créer ALBERT.md dans le dossier courant
    {C.GRAY_LIGHT}/cwd{C.RESET}       — Afficher le dossier de travail courant
    {C.GRAY_LIGHT}/cd{C.RESET} <path> — Changer le dossier de travail courant
  {C.GRAY_LIGHT}/clear{C.RESET}     — Réinitialiser la conversation
  {C.GRAY_LIGHT}/compact{C.RESET}   — Compresser l'historique
  {C.GRAY_LIGHT}/stats{C.RESET}     — Statistiques de session
    {C.GRAY_LIGHT}/models{C.RESET}    — Alias et modèles supportés
    {C.GRAY_LIGHT}/model{C.RESET} [id] — Modèle actuel ou changer de modèle
    {C.GRAY_LIGHT}/rpm{C.RESET}       — Jauge RPM du modèle actif
    {C.GRAY_LIGHT}/limits{C.RESET}    — Quotas Albert API (RPM/RPD/TPM/TPD)
    {C.GRAY_LIGHT}/skills{C.RESET} [on|off|reload] — Skills SKILL.md
    {C.GRAY_LIGHT}/skills use{C.RESET} <nom>      — Epingler un skill pour les prochains prompts
    {C.GRAY_LIGHT}/skills unuse{C.RESET} <nom>    — Retirer un skill epingle
    {C.GRAY_LIGHT}/skills auto{C.RESET}           — Retour au mode selection automatique
    {C.GRAY_LIGHT}/skills install{C.RESET} <url|owner/repo> [nom] — Installer un SKILL.md
  {C.GRAY_LIGHT}/auto{C.RESET}      — Activer/désactiver l'auto-approbation
    {C.GRAY_LIGHT}/fallback{C.RESET}  — Activer/désactiver l'auto-fallback 429
        {C.GRAY_LIGHT}/memory status{C.RESET}          — Etat du palace memoire
        {C.GRAY_LIGHT}/memory search{C.RESET} <query>  — Recherche semantique memoire
        {C.GRAY_LIGHT}/memory save{C.RESET}            — Sauvegarder la conversation courante
        {C.GRAY_LIGHT}/memory on|off{C.RESET}          — Activer/desactiver le recall auto
        {C.GRAY_LIGHT}/memory clear{C.RESET}           — Vider le palace memoire
  {C.GRAY_LIGHT}/verbose{C.RESET}   — Afficher tous les outputs des outils
  {C.GRAY_LIGHT}/quiet{C.RESET}     — Masquer les détails des outils
  {C.GRAY_LIGHT}/normal{C.RESET}    — Verbosité normale (défaut)
  {C.GRAY_LIGHT}/plan{C.RESET}      — Mode plan-first
    {C.GRAY_LIGHT}/history{C.RESET}   — Historique des checkpoints
        {C.GRAY_LIGHT}/todo{C.RESET} [clear|check N] — Checklist du plan en cours
    {C.GRAY_LIGHT}/undo{C.RESET} [N]  — Restaurer le dernier checkpoint ou #N
    {C.GRAY_LIGHT}/git{C.RESET}       — Activer/désactiver la protection snapshots
  {C.GRAY_LIGHT}/quit{C.RESET}      — Quitter

  {C.DIM}Multi-ligne : tapez {C.WHITE}\"\"\"{C.DIM} seul pour entrer/quitter le mode multi-ligne.{C.RESET}
  {C.DIM}Historique  : flèche {C.WHITE}↑{C.DIM} pour rappeler le dernier prompt.{C.RESET}
"""


MODEL_ALIAS_TO_FULL: dict[str, str] = {
    "openweight-large": "openai/gpt-oss-120b",
    "openweight-medium": "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
    "openweight-small": "mistralai/Ministral-3-8B-Instruct-2512",
    "openweight-code": "Qwen/Qwen3-Coder-30B-A3B-Instruct",
    "openweight-audio": "openai/whisper-large-v3",
    "openweight-embeddings": "BAAI/bge-m3",
    "openweight-rerank": "BAAI/bge-reranker-v2-m3",
}

MODEL_FULL_TO_ALIAS: dict[str, str] = {
    full.lower(): alias for alias, full in MODEL_ALIAS_TO_FULL.items()
}

MODEL_LIMITS: dict[str, dict[str, str]] = {
    "openweight-large": {
        "full": MODEL_ALIAS_TO_FULL["openweight-large"],
        "exp": "RPM 10 | RPD 1 000 | TPM 128k | TPD 1.28M",
        "prod": "RPM 50 | RPD 5 000 | TPM 246k | TPD illimite",
    },
    "openweight-medium": {
        "full": MODEL_ALIAS_TO_FULL["openweight-medium"],
        "exp": "RPM 50 | RPD 1 000 | TPM 128k | TPD 2.46M",
        "prod": "RPM 100 | RPD 50 000 | TPM 246k | TPD illimite",
    },
    "openweight-small": {
        "full": MODEL_ALIAS_TO_FULL["openweight-small"],
        "exp": "RPM 50 | RPD 1 000 | TPM 128k | TPD 2.46M",
        "prod": "RPM 100 | RPD 50 000 | TPM 246k | TPD illimite",
    },
    "openweight-code": {
        "full": MODEL_ALIAS_TO_FULL["openweight-code"],
        "exp": "RPM 50 | RPD 1 000 | TPM 128k | TPD 2.46M",
        "prod": "RPM 100 | RPD 50 000 | TPM 246k | TPD illimite",
    },
    "openweight-audio": {
        "full": MODEL_ALIAS_TO_FULL["openweight-audio"],
        "exp": "RPM 50 | RPD 1 000 | TPM illimite | TPD illimite",
        "prod": "RPM 100 | RPD 5 000 | TPM illimite | TPD illimite",
    },
    "openweight-embeddings": {
        "full": MODEL_ALIAS_TO_FULL["openweight-embeddings"],
        "exp": "RPM 500 | RPD 50 000 | TPM illimite | TPD illimite",
        "prod": "RPM 2000 | RPD 200 000 | TPM illimite | TPD illimite",
    },
    "openweight-rerank": {
        "full": MODEL_ALIAS_TO_FULL["openweight-rerank"],
        "exp": "RPM 500 | RPD 50 000 | TPM illimite | TPD illimite",
        "prod": "RPM 2000 | RPD 200 000 | TPM illimite | TPD illimite",
    },
}


def _normalize_model_id(raw: str) -> tuple[str, str | None]:
    """
    Convertit un alias/nom complet en alias canonique quand possible.
    Retourne (model_effectif, warning_optionnel).
    """
    value = raw.strip()
    if not value:
        return value, ""

    lower = value.lower()
    if lower in MODEL_ALIAS_TO_FULL:
        return lower, None

    alias = MODEL_FULL_TO_ALIAS.get(lower)
    if alias:
        return alias, None

    return value, "Modele non reference localement (conserve tel quel)."


def _rpm_bar(percent: float, width: int = 20) -> str:
    p = max(0.0, min(100.0, percent))
    filled = int((p / 100.0) * width)
    return f"{'█' * filled}{'░' * (width - filled)}"


def _extract_command_arg(first_line: str, cmd: str) -> str:
    raw = first_line.strip()
    if not raw.lower().startswith(cmd.lower()):
        return ""
    return raw[len(cmd):].strip()


def _normalize_path_input(raw_path: str) -> str:
    path = raw_path.strip().strip('"').strip("'")
    return os.path.expandvars(os.path.expanduser(path))


def _default_albert_md_content(cwd: Path) -> str:
    return (
        "# ALBERT.md\n\n"
        "Contexte du projet pour Albert Code.\n\n"
        f"- Dossier racine: {cwd}\n"
        "- OS: Windows\n\n"
        "## Objectif\n"
        "Decrire ici ce que le projet doit faire.\n\n"
        "## Contraintes\n"
        "- Langage(s) et version(s)\n"
        "- Style de code\n"
        "- Regles de securite\n\n"
        "## Commandes utiles\n"
        "- Tests: python -m pytest -q\n"
        "- Lint: (a completer)\n"
        "- Build/Run: (a completer)\n"
    )


def print_welcome(
    model: str,
    auto_approve: bool,
    verbosity: int = 1,
    plan_first: bool = False,
    config_path: str = "",
) -> None:
    os.system("cls" if os.name == "nt" else "clear")
    cwd       = Path.cwd()
    cwd_str   = str(cwd).replace(str(Path.home()), "~")
    if len(cwd_str) > 50:
        cwd_str = "..." + cwd_str[-47:]
    auto_str  = f"{C.GREEN}ON{C.RESET}"  if auto_approve else f"{C.ROUGE}off{C.RESET}"

    # Logo ASCII tricolore + séparateur c  o  d  e
    print_logo()

    # Boîte de bienvenue
    plines(draw_box([
        f"{C.YELLOW}✦{C.RESET}  {C.BOLD}{C.WHITE}Bienvenue sur Albert Code{C.RESET}  {C.DIM}{C.GRAY}v0.1.0{C.RESET}",
        "",
        f"   {C.GRAY_LIGHT}/help{C.RESET} {C.GRAY}pour l'aide{C.RESET}  {C.GRAY}·{C.RESET}  {C.GRAY_LIGHT}/status{C.RESET} {C.GRAY}pour la configuration{C.RESET}",
        f"   {C.GRAY}cwd:{C.RESET} {C.CYAN}{cwd_str}{C.RESET}",
    ], color=C.GRAY))

    print()

    # Conseils pour démarrer
    _m = "  "
    print(f"{_m}{C.BOLD}{C.WHITE}Conseils pour démarrer :{C.RESET}")
    print()
    print(f"{_m}  {C.WHITE}1.{C.RESET}  {C.GRAY_LIGHT}Lancez{C.RESET} {C.CYAN}/init{C.RESET} {C.GRAY_LIGHT}pour créer un{C.RESET} {C.WHITE}ALBERT.md{C.RESET}")
    print(f"{_m}  {C.WHITE}2.{C.RESET}  {C.GRAY_LIGHT}Albert peut{C.RESET} {C.WHITE}lire, écrire, exécuter{C.RESET} {C.GRAY_LIGHT}et chercher dans votre code{C.RESET}")
    print(f"{_m}  {C.WHITE}3.{C.RESET}  {C.GRAY_LIGHT}Soyez aussi précis qu'avec un{C.RESET} {C.WHITE}collègue développeur{C.RESET}")
    print(f"{_m}  {C.WHITE}4.{C.RESET}  {C.GRAY_LIGHT}Chaque écriture crée un{C.RESET} {C.GREEN}checkpoint interne{C.RESET} {C.GRAY_LIGHT}(undo possible){C.RESET}")

    print()

    # Barre de statut compacte
    print(
        f"{_m}{C.GREEN}●{C.RESET} {C.GRAY}Modèle:{C.RESET} {C.WHITE}{model}{C.RESET}"
        f"  {C.GRAY}·{C.RESET}  {C.GRAY}Auto-approve:{C.RESET} {auto_str}"
    )

    print()


def print_stats(session: AgentSession) -> None:
    from .display import draw_box, plines  # import local pour éviter la circularité potentielle
    c = session.client
    plines(draw_box([
        f"{C.BOLD}{C.WHITE}Statistiques de session{C.RESET}",
        "",
        f"  {C.GRAY}Requêtes API   :{C.RESET}  {C.WHITE}{c.total_requests}{C.RESET}",
        f"  {C.GRAY}Tool calls     :{C.RESET}  {C.WHITE}{session.total_tool_calls}{C.RESET}",
        f"  {C.GRAY}Tokens input   :{C.RESET}  {C.WHITE}{c.total_input_tokens:,}{C.RESET}",
        f"  {C.GRAY}Tokens output  :{C.RESET}  {C.WHITE}{c.total_output_tokens:,}{C.RESET}",
        f"  {C.GRAY}Mémoire        :{C.RESET}  {C.WHITE}{len(session.messages)} messages{C.RESET}",
    ], color=C.GRAY))
    print()


# ──────────────────────────────────────────────
#  REPL
# ──────────────────────────────────────────────

def repl(session: AgentSession) -> None:
    """Boucle interactive Read-Eval-Print."""
    _hint = "Essayez \"analyse ce projet et suggère des améliorations\""
    _first = True
    while True:
        try:
            if _first:
                print(f"{_M}  {C.DIM}{C.ITALIC}{C.GRAY}{_hint}{C.RESET}")
                _first = False
            first_line = input(f"{_M}{C.BOLD}{C.WHITE}❯{C.RESET} ")

            if not first_line.strip():
                continue

            cmd_parts = first_line.strip().split()
            cmd = cmd_parts[0].lower() if cmd_parts else ""

            # ── Commandes spéciales ──────────────
            if cmd in ("/quit", "/exit", "/q"):
                session.save_memory_snapshot()
                print(f"\n{_M}  {C.DIM}Au revoir !{C.RESET}  {C.ROUGE}🇫🇷{C.RESET}\n")
                break
            elif cmd == "/help":
                print(HELP_TEXT)
                continue
            elif cmd == "/init":
                init_arg = _extract_command_arg(first_line, "/init").lower()
                force = init_arg in ("-f", "--force", "force")
                albert_path = Path.cwd() / "ALBERT.md"

                if albert_path.exists() and not force:
                    print(f"  {C.YELLOW}ALBERT.md existe deja.{C.RESET} Utilisez /init --force pour ecraser.\n")
                    continue

                try:
                    content = _default_albert_md_content(Path.cwd())
                    albert_path.write_text(content, encoding="utf-8")
                except OSError as exc:
                    print(f"  {C.RED}✗{C.RESET} Echec creation ALBERT.md: {exc}\n")
                    continue

                action = "mis a jour" if force else "cree"
                print(f"  {C.GREEN}✔{C.RESET} ALBERT.md {action} dans {C.CYAN}{Path.cwd()}{C.RESET}\n")
                continue
            elif cmd == "/cwd":
                print(f"  {C.GRAY}cwd:{C.RESET} {C.CYAN}{Path.cwd()}{C.RESET}\n")
                continue
            elif cmd == "/cd":
                raw_path = _extract_command_arg(first_line, "/cd")
                if not raw_path:
                    print(f"  {C.YELLOW}Usage: /cd <chemin>{C.RESET}\n")
                    continue

                target = Path(_normalize_path_input(raw_path))
                if not target.is_absolute():
                    target = (Path.cwd() / target).resolve()

                if not target.exists():
                    print(f"  {C.RED}✗{C.RESET} Dossier introuvable: {target}\n")
                    continue
                if not target.is_dir():
                    print(f"  {C.RED}✗{C.RESET} Ce chemin n'est pas un dossier: {target}\n")
                    continue

                try:
                    os.chdir(target)
                except OSError as exc:
                    print(f"  {C.RED}✗{C.RESET} Impossible de changer de dossier: {exc}\n")
                    continue

                session.project_cfg = load_project_config()
                session.reload_skills()
                session.messages.append({
                    "role": "system",
                    "content": (
                        f"Working directory changed to: {Path.cwd()}\n"
                        "Use this as base path for relative file operations."
                    ),
                })
                print(f"  {C.GREEN}✔{C.RESET} Dossier de travail: {C.CYAN}{Path.cwd()}{C.RESET}\n")
                continue
            elif cmd == "/clear":
                session.initialize()
                session.clear_todo()
                print(f"  {C.GREEN}🔄 Conversation réinitialisée.{C.RESET}\n")
                continue
            elif cmd == "/compact":
                session.save_memory_snapshot()
                session.compact_history()
                continue
            elif cmd == "/stats":
                print_stats(session)
                continue
            elif cmd == "/status":
                cwd_str = str(Path.cwd()).replace(str(Path.home()), "~")
                auto_str = f"{C.GREEN}ON{C.RESET}" if session.auto_approve else f"{C.ROUGE}off{C.RESET}"
                verb_label = {0: f"{C.DIM}quiet{C.RESET}", 1: "normal", 2: f"{C.GREEN}verbose{C.RESET}"}.get(session.verbosity, "normal")
                plan_str = f"{C.GREEN}ON{C.RESET}" if session.plan_first else f"{C.DIM}off{C.RESET}"
                safe_str = f"{C.GREEN}ON{C.RESET}" if session.snapshot_guard else f"{C.DIM}off{C.RESET}"
                fb = session.client.get_fallback_status()
                fb_str = f"{C.GREEN}ON{C.RESET}" if fb.get("enabled") else f"{C.DIM}off{C.RESET}"
                if fb.get("active"):
                    fb_str = (
                        f"{C.ORANGE}ACTIVE{C.RESET}"
                        f" {C.DIM}({fb.get('remaining_seconds', 0)}s){C.RESET}"
                    )
                rpm = session.client.get_rpm_usage()
                rpm_used = int(rpm.get("used", 0))
                rpm_limit = int(rpm.get("limit", 0))
                rpm_pct = float(rpm.get("percent", 0.0))
                rpm_color = C.GREEN if rpm_pct < 70 else (C.YELLOW if rpm_pct < 90 else C.RED)
                cp_count = len(session.list_checkpoints())
                skills_n = len(session.list_skills())
                skills_state = f"{C.GREEN}ON{C.RESET}" if session.skills_enabled else f"{C.DIM}off{C.RESET}"
                active_skills = ", ".join(session.active_skills[:3]) if session.active_skills else "-"
                pinned_skills = ", ".join(session.pinned_skills[:3]) if session.pinned_skills else "auto"
                todo_done, todo_total = session.todo_counts()
                mem = session.memory_status()
                mem_on = f"{C.GREEN}ON{C.RESET}" if mem.get("enabled") else f"{C.DIM}off{C.RESET}"
                mem_recall = f"{C.GREEN}ON{C.RESET}" if mem.get("auto_recall") else f"{C.DIM}off{C.RESET}"
                mem_state = f"{C.GREEN}ok{C.RESET}" if mem.get("available") else f"{C.YELLOW}degrade{C.RESET}"
                mem_entries = int(mem.get("entries", 0))
                plines(draw_box([
                    f"{C.BOLD}{C.WHITE}Configuration active{C.RESET}",
                    "",
                    f"  {C.GRAY}Modèle       :{C.RESET}  {C.WHITE}{session.client.model}{C.RESET}",
                    f"  {C.GRAY}Répertoire   :{C.RESET}  {C.CYAN}{cwd_str}{C.RESET}",
                    f"  {C.GRAY}Auto-approve :{C.RESET}  {auto_str}",
                    f"  {C.GRAY}Verbosité    :{C.RESET}  {verb_label}",
                    f"  {C.GRAY}Plan-first   :{C.RESET}  {plan_str}",
                    f"  {C.GRAY}Auto-fallback 429:{C.RESET} {fb_str}",
                    f"  {C.GRAY}RPM (60s)    :{C.RESET}  {rpm_color}{rpm_used}/{rpm_limit}{C.RESET} {C.DIM}({rpm_pct:.0f}%){C.RESET}",
                    f"  {C.GRAY}Skills SKILL.md:{C.RESET} {skills_state} {C.DIM}({skills_n} charges){C.RESET}",
                    f"  {C.GRAY}Mode skills  :{C.RESET}  {C.WHITE}{pinned_skills}{C.RESET}",
                    f"  {C.GRAY}Skills actifs:{C.RESET}  {C.WHITE}{active_skills}{C.RESET}",
                    f"  {C.GRAY}Memoire      :{C.RESET}  {mem_on} / recall {mem_recall} / {mem_state}",
                    f"  {C.GRAY}Palace       :{C.RESET}  {C.WHITE}{mem_entries}{C.RESET} entree(s)",
                    f"  {C.GRAY}TODO plan    :{C.RESET}  {C.WHITE}{todo_done}/{todo_total}{C.RESET}",
                    f"  {C.GRAY}Protection snapshots:{C.RESET} {safe_str}",
                    f"  {C.GRAY}Checkpoints  :{C.RESET}  {C.WHITE}{cp_count}{C.RESET}",
                    f"  {C.GRAY}Messages     :{C.RESET}  {C.WHITE}{len(session.messages)}{C.RESET}",
                ], color=C.GRAY))
                mem_warning = str(mem.get("warning", "")).strip()
                if mem_warning:
                    print(f"  {C.DIM}{mem_warning}{C.RESET}")
                print()
                continue
            elif cmd == "/memory":
                action = cmd_parts[1].lower() if len(cmd_parts) > 1 else "status"

                if action == "on":
                    session.set_memory_recall_enabled(True)
                    print(f"  Recall memoire : {C.GREEN}ON{C.RESET}\n")
                    continue
                if action == "off":
                    session.set_memory_recall_enabled(False)
                    print(f"  Recall memoire : {C.YELLOW}OFF{C.RESET}\n")
                    continue
                if action == "save":
                    ok = session.save_memory_snapshot(force=True)
                    if ok:
                        print(f"  {C.GREEN}✔{C.RESET} Conversation sauvegardee dans le palace\n")
                    else:
                        print(f"  {C.YELLOW}⚠{C.RESET} Sauvegarde memoire indisponible\n")
                    continue
                if action == "clear":
                    try:
                        ans = input(f"  {C.YELLOW}Confirmer suppression du palace ? [y/N]{C.RESET} ").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        ans = "n"
                    if ans not in ("y", "yes", "o", "oui"):
                        print(f"  {C.DIM}Annule.{C.RESET}\n")
                        continue
                    ok = session.clear_memory_store()
                    if ok:
                        print(f"  {C.GREEN}✔{C.RESET} Palace memoire vide\n")
                    else:
                        print(f"  {C.RED}✗{C.RESET} Impossible de vider le palace\n")
                    continue
                if action == "search":
                    query = _extract_command_arg(first_line, "/memory search")
                    if not query:
                        print(f"  {C.YELLOW}Usage: /memory search <query>{C.RESET}\n")
                        continue
                    results = session.recall_memories_for_prompt(query)
                    if not results:
                        mem = session.memory_status()
                        warning = str(mem.get("warning", "")).strip()
                        if warning:
                            print(f"  {C.YELLOW}⚠ {warning}{C.RESET}\n")
                        else:
                            print(f"  {C.DIM}Aucun resultat memoire.{C.RESET}\n")
                        continue
                    lines = [f"{C.BOLD}{C.WHITE}Resultats memoire{C.RESET}", ""]
                    for i, row in enumerate(results, start=1):
                        lines.append(
                            f"  {C.GRAY}{i}.{C.RESET} {C.WHITE}sim={float(row['similarity']):.3f}{C.RESET} "
                            f"{C.DIM}src={row['source_file']}{C.RESET}"
                        )
                        snippet = str(row["text"]).replace("\n", " ").strip()
                        lines.append(f"     {snippet[:160]}")
                    plines(draw_box(lines, color=C.GRAY))
                    print()
                    continue

                mem = session.memory_status()
                enabled = f"{C.GREEN}ON{C.RESET}" if mem.get("enabled") else f"{C.DIM}off{C.RESET}"
                auto_save = f"{C.GREEN}ON{C.RESET}" if mem.get("auto_save") else f"{C.DIM}off{C.RESET}"
                auto_recall = f"{C.GREEN}ON{C.RESET}" if mem.get("auto_recall") else f"{C.DIM}off{C.RESET}"
                available = f"{C.GREEN}ok{C.RESET}" if mem.get("available") else f"{C.YELLOW}degrade{C.RESET}"
                lines = [
                    f"{C.BOLD}{C.WHITE}Memoire persistante{C.RESET}",
                    "",
                    f"  {C.GRAY}Enabled:{C.RESET} {enabled}",
                    f"  {C.GRAY}Etat:{C.RESET} {available}",
                    f"  {C.GRAY}Auto-save:{C.RESET} {auto_save}",
                    f"  {C.GRAY}Auto-recall:{C.RESET} {auto_recall}",
                    f"  {C.GRAY}Top-k:{C.RESET} {mem.get('recall_top_k')}",
                    f"  {C.GRAY}Max tokens:{C.RESET} {mem.get('recall_max_tokens')}",
                    f"  {C.GRAY}Entrees:{C.RESET} {mem.get('entries', 0)}",
                    f"  {C.GRAY}Palace:{C.RESET} {mem.get('palace_path', '-')}",
                ]
                warning = str(mem.get("warning", "")).strip()
                if warning:
                    lines.extend(["", f"  {C.YELLOW}⚠ {warning}{C.RESET}"])
                plines(draw_box(lines, color=C.GRAY))
                print()
                continue
            elif cmd == "/skills":
                action = cmd_parts[1].lower() if len(cmd_parts) > 1 else ""
                if action == "on":
                    session.set_skills_enabled(True)
                    print(f"  Skills SKILL.md : {C.GREEN}ON{C.RESET}\n")
                    continue
                if action == "off":
                    session.set_skills_enabled(False)
                    print(f"  Skills SKILL.md : {C.YELLOW}OFF{C.RESET}\n")
                    continue
                if action == "reload":
                    n = session.reload_skills()
                    print(f"  {C.GREEN}✔{C.RESET} Skills recharges : {C.WHITE}{n}{C.RESET}\n")
                    continue
                if action == "use":
                    if len(cmd_parts) < 3:
                        print(f"  {C.YELLOW}Usage: /skills use <nom>{C.RESET}\n")
                        continue
                    ok, msg = session.pin_skill(cmd_parts[2])
                    if ok:
                        print(f"  {C.GREEN}✔{C.RESET} {msg}\n")
                    else:
                        print(f"  {C.RED}✗{C.RESET} {msg}\n")
                    continue
                if action == "unuse":
                    if len(cmd_parts) < 3:
                        print(f"  {C.YELLOW}Usage: /skills unuse <nom>{C.RESET}\n")
                        continue
                    ok, msg = session.unpin_skill(cmd_parts[2])
                    if ok:
                        print(f"  {C.GREEN}✔{C.RESET} {msg}\n")
                    else:
                        print(f"  {C.RED}✗{C.RESET} {msg}\n")
                    continue
                if action == "auto":
                    session.clear_pinned_skills()
                    print(f"  {C.GREEN}✔{C.RESET} Mode skills: selection automatique\n")
                    continue
                if action == "install":
                    if len(cmd_parts) < 3:
                        print(f"  {C.YELLOW}Usage: /skills install <url|owner/repo> [nom]{C.RESET}\n")
                        continue
                    url = cmd_parts[2]
                    name = cmd_parts[3] if len(cmd_parts) >= 4 else None
                    ok, msg = session.install_skill_from_url(url, skill_name=name)
                    if ok:
                        print(f"  {C.GREEN}✔{C.RESET} {msg}{C.RESET}\n")
                    else:
                        print(f"  {C.RED}✗{C.RESET} {msg}{C.RESET}\n")
                    continue

                skills = session.list_skills()
                state = f"{C.GREEN}ON{C.RESET}" if session.skills_enabled else f"{C.YELLOW}OFF{C.RESET}"
                skills_root = str(session.skill_registry.default_root).replace(str(Path.home()), "~")
                lines = [
                    f"{C.BOLD}{C.WHITE}Skills SKILL.md{C.RESET}",
                    "",
                    f"  {C.GRAY}Etat:{C.RESET} {state}",
                    f"  {C.GRAY}Charges:{C.RESET} {C.WHITE}{len(skills)}{C.RESET}",
                    f"  {C.GRAY}Mode:{C.RESET} {C.WHITE}{', '.join(session.pinned_skills) if session.pinned_skills else 'auto'}{C.RESET}",
                    f"  {C.GRAY}Dossier local:{C.RESET} {C.CYAN}{skills_root}{C.RESET}",
                    "",
                ]
                if skills:
                    for sk in skills[:20]:
                        summary = sk.summary[:90] if sk.summary else "No summary"
                        lines.append(f"  {C.CYAN}{sk.name}{C.RESET} {C.DIM}- {summary}{C.RESET}")
                else:
                    lines.append(f"  {C.DIM}Aucun SKILL.md detecte dans les emplacements standards.{C.RESET}")

                lines.extend([
                    "",
                    f"  {C.DIM}Actions: /skills on | /skills off | /skills reload | /skills use <nom> | /skills unuse <nom> | /skills auto | /skills install <url|owner/repo> [nom]{C.RESET}",
                    f"  {C.DIM}Dossiers: ~/.albert-code/skills, ~/.claude/skills, ~/.codex/skills{C.RESET}",
                ])
                plines(draw_box(lines, color=C.GRAY))
                print()
                continue
            elif cmd == "/rpm":
                rpm = session.client.get_rpm_usage()
                used = int(rpm.get("used", 0))
                limit = int(rpm.get("limit", 0))
                pct = float(rpm.get("percent", 0.0))
                window = int(rpm.get("window_seconds", 60))
                model = str(rpm.get("model", session.client.model))

                color = C.GREEN if pct < 70 else (C.YELLOW if pct < 90 else C.RED)
                bar = _rpm_bar(pct)
                remain = max(0, limit - used)
                lines = [
                    f"{C.BOLD}{C.WHITE}Jauge RPM (fenetre glissante){C.RESET}",
                    "",
                    f"  {C.GRAY}Modele:{C.RESET} {C.WHITE}{model}{C.RESET}",
                    f"  {C.GRAY}Fenetre:{C.RESET} {window}s",
                    f"  {C.GRAY}Usage:{C.RESET} {color}{used}/{limit}{C.RESET} {C.DIM}({pct:.0f}%){C.RESET}",
                    f"  {color}{bar}{C.RESET}",
                    f"  {C.GRAY}Marge restante:{C.RESET} {C.WHITE}{remain}{C.RESET} requete(s)",
                ]
                if pct >= 90:
                    lines.append(f"  {C.RED}Alerte:{C.RESET} proche de la limite RPM, ralentissez ou changez de modele.")
                elif pct >= 70:
                    lines.append(f"  {C.YELLOW}Attention:{C.RESET} charge elevee sur la minute en cours.")
                else:
                    lines.append(f"  {C.GREEN}OK:{C.RESET} marge confortable.")

                plines(draw_box(lines, color=C.GRAY))
                print()
                continue
            elif cmd == "/limits":
                active_model = session.client.model
                active_alias = active_model if active_model in MODEL_ALIAS_TO_FULL else MODEL_FULL_TO_ALIAS.get(active_model.lower(), "")
                active_full = MODEL_ALIAS_TO_FULL.get(active_alias, active_model)

                lines = [
                    f"{C.BOLD}{C.WHITE}Quotas Albert API (detail){C.RESET}",
                    "",
                    f"  {C.GRAY}Actuel:{C.RESET} {C.WHITE}{active_model}{C.RESET}  {C.DIM}({active_full}){C.RESET}",
                    "",
                    f"  {C.GRAY_LIGHT}Note:{C.RESET} quotas souvent appliques par acces API (cle/compte),",
                    f"  {C.GRAY_LIGHT}avec plafonds qui varient selon le modele / offre.{C.RESET}",
                    "",
                ]

                for alias, meta in MODEL_LIMITS.items():
                    lines.extend([
                        f"  {C.CYAN}{alias}{C.RESET}  {C.DIM}({meta['full']}){C.RESET}",
                        f"    {C.GRAY}EXP :{C.RESET} {meta['exp']}",
                        f"    {C.GRAY}PROD:{C.RESET} {meta['prod']}",
                        "",
                    ])

                lines.extend([
                    f"  {C.GRAY}Source:{C.RESET} {C.CYAN}https://albert.sites.beta.gouv.fr/prices/{C.RESET}",
                    f"  {C.GRAY}Modeles:{C.RESET} {C.CYAN}https://albert.sites.beta.gouv.fr/solutions/models/{C.RESET}",
                ])

                plines(draw_box(lines, color=C.GRAY))
                print()
                continue
            elif cmd == "/models":
                lines = [
                    f"{C.BOLD}{C.WHITE}Correspondance alias -> modele{C.RESET}",
                    "",
                ]
                for alias, full in MODEL_ALIAS_TO_FULL.items():
                    marker = f" {C.GREEN}<- actif{C.RESET}" if session.client.model == alias else ""
                    lines.append(f"  {C.CYAN}{alias}{C.RESET}  {C.GRAY}->{C.RESET}  {C.GRAY_LIGHT}{full}{C.RESET}{marker}")
                lines.extend([
                    "",
                    f"  {C.DIM}Utilisez /model <alias_ou_modele_complet>{C.RESET}",
                ])
                plines(draw_box(lines, color=C.GRAY))
                print()
                continue
            elif cmd == "/history":
                checkpoints = session.list_checkpoints()
                if not checkpoints:
                    print(f"  {C.DIM}Aucun checkpoint pour cette session.{C.RESET}\n")
                    continue

                lines = [f"{C.BOLD}{C.WHITE}Checkpoints de session{C.RESET}", ""]
                for cp in reversed(checkpoints[-20:]):
                    files_n = len(cp.files)
                    lines.append(
                        f"  {C.GRAY}#{cp.id:<3}{C.RESET} {C.GRAY_LIGHT}{cp.description}{C.RESET}"
                        f"  {C.DIM}({files_n} fichier{'s' if files_n > 1 else ''}){C.RESET}"
                    )

                plines(draw_box(lines, color=C.GRAY))
                print()
                continue
            elif cmd == "/todo":
                action = cmd_parts[1].lower() if len(cmd_parts) > 1 else ""
                if action == "clear":
                    session.clear_todo()
                    print(f"  {C.GREEN}✔{C.RESET} TODO vide\n")
                    continue
                if action == "check":
                    if len(cmd_parts) < 3:
                        print(f"  {C.YELLOW}Usage: /todo check <N>{C.RESET}\n")
                        continue
                    try:
                        idx = int(cmd_parts[2])
                    except ValueError:
                        print(f"  {C.YELLOW}Usage: /todo check <N>{C.RESET}\n")
                        continue
                    ok, msg = session.mark_todo_done(idx)
                    if ok:
                        print(f"  {C.GREEN}✔{C.RESET} {msg}\n")
                    else:
                        print(f"  {C.RED}✗{C.RESET} {msg}\n")
                    continue

                md = session.todo_markdown()
                if not md:
                    print(f"  {C.DIM}Aucun TODO actif. Activez /plan puis validez un plan.{C.RESET}\n")
                    continue

                lines = [f"{C.BOLD}{C.WHITE}TODO courant{C.RESET}", ""]
                for i, item in enumerate(session.todo_items, start=1):
                    mark = f"{C.GREEN}x{C.RESET}" if item.get("done") else " "
                    lines.append(f"  {C.GRAY}{i:>2}.{C.RESET} [{mark}] {item.get('text', '')}")
                lines.extend([
                    "",
                    f"  {C.DIM}Actions: /todo check <N> | /todo clear{C.RESET}",
                ])
                plines(draw_box(lines, color=C.GRAY))
                print()
                continue
            elif cmd == "/undo":
                target_id: int | None = None
                if len(cmd_parts) >= 2:
                    try:
                        target_id = int(cmd_parts[1])
                    except ValueError:
                        print(f"  {C.YELLOW}Usage: /undo [id_checkpoint]{C.RESET}\n")
                        continue
                else:
                    target_id = session.latest_checkpoint_id()

                if target_id is None:
                    print(f"  {C.DIM}Aucun checkpoint disponible à restaurer.{C.RESET}\n")
                    continue

                ok, msg = session.restore_checkpoint(target_id)
                color = C.GREEN if ok else C.RED
                icon = "✔" if ok else "✗"
                print(f"  {color}{icon}{C.RESET} {msg}\n")
                continue
            elif cmd == "/model":
                if len(cmd_parts) >= 2:
                    new_model = cmd_parts[1].strip()
                    if not new_model:
                        print(f"  {C.YELLOW}Usage: /model <alias_ou_id_modele>{C.RESET}\n")
                        continue

                    normalized, warning = _normalize_model_id(new_model)
                    old_model = session.client.model
                    session.client.model = normalized
                    old_full = MODEL_ALIAS_TO_FULL.get(old_model, old_model)
                    new_full = MODEL_ALIAS_TO_FULL.get(normalized, normalized)
                    print(
                        f"  {C.GREEN}✔{C.RESET} Modèle changé : "
                        f"{C.DIM}{old_model}{C.RESET} {C.GRAY}->{C.RESET} {C.WHITE}{normalized}{C.RESET}"
                    )
                    if old_full != old_model or new_full != normalized:
                        print(f"  {C.DIM}   {old_full} -> {new_full}{C.RESET}")
                    if warning:
                        print(f"  {C.YELLOW}⚠️  {warning}{C.RESET}")
                    print()
                else:
                    current = session.client.model
                    full = MODEL_ALIAS_TO_FULL.get(current, current)
                    print(f"  Modele : {C.WHITE}{current}{C.RESET}")
                    if full != current:
                        print(f"  Alias  : {C.DIM}{full}{C.RESET}")
                    print()
                continue
            elif cmd == "/auto":
                session.auto_approve = not session.auto_approve
                status = f"{C.GREEN}ON{C.RESET}" if session.auto_approve else f"{C.YELLOW}OFF{C.RESET}"
                print(f"  Auto-approve : {status}\n")
                continue
            elif cmd == "/fallback":
                session.client.auto_fallback_429 = not session.client.auto_fallback_429
                status = f"{C.GREEN}ON{C.RESET}" if session.client.auto_fallback_429 else f"{C.YELLOW}OFF{C.RESET}"
                print(f"  Auto-fallback 429 : {status}")
                if session.client.auto_fallback_429:
                    print(f"  {C.DIM}Si 429 repetes sur openweight-large -> fallback openweight-medium pendant 60s.{C.RESET}")
                print()
                continue
            elif cmd == "/verbose":
                session.verbosity = 2
                print(f"  Verbosité : {C.GREEN}verbose{C.RESET}\n")
                continue
            elif cmd == "/quiet":
                session.verbosity = 0
                print(f"  Verbosité : {C.DIM}quiet{C.RESET}\n")
                continue
            elif cmd in ("/normal", "/v1"):
                session.verbosity = 1
                print(f"  Verbosité : normal\n")
                continue
            elif cmd == "/plan":
                session.plan_first = not session.plan_first
                status = f"{C.GREEN}ON{C.RESET}" if session.plan_first else f"{C.YELLOW}OFF{C.RESET}"
                print(f"  Plan-first : {status}\n")
                continue
            elif cmd == "/git":
                session.snapshot_guard = not session.snapshot_guard
                status = f"{C.GREEN}ON{C.RESET}" if session.snapshot_guard else f"{C.YELLOW}OFF{C.RESET}"
                print(f"  Protection snapshots : {status}\n")
                continue

            # ── Mode multi-ligne ─────────────────
            if first_line.strip() == '"""':
                collected: list[str] = []
                print(f'  {C.DIM}(mode multi-ligne — retapez """ seul pour envoyer){C.RESET}')
                while True:
                    try:
                        line = input("  … ")
                    except (EOFError, KeyboardInterrupt):
                        break
                    if line.strip() == '"""':
                        break
                    collected.append(line)
                user_input = "\n".join(collected).strip()
                if not user_input:
                    continue
            else:
                user_input = first_line

            # ── Ajout dans l'historique ──────────
            session.add_user_message(user_input)

            # ── Mode plan-first ──────────────────
            continue_cmds = {"continue", "continuer", "suite", "next", "go", "poursuis", "poursuivre"}
            has_open_todo = any(not it.get("done") for it in session.todo_items)
            skip_replan = has_open_todo and user_input.strip().lower() in continue_cmds

            if session.plan_first and not skip_replan:
                plan_messages = session.messages[:-1] + [
                    {
                        "role": "user",
                        "content": (
                            user_input
                            + "\n\n[Instruction interne : décris uniquement ton plan d'action"
                            " en liste numérotée SANS appeler aucun outil. Termine par [FIN DU PLAN].]"
                        ),
                    }
                ]
                try:
                    sys.stdout.write(f"  {C.DIM}⏳ Génération du plan…{C.RESET}")
                    sys.stdout.flush()
                    plan_text = session.client.chat_no_tools(plan_messages)
                    clear_line()
                    print(f"\n  {C.CYAN}{C.BOLD}📋 Plan proposé :{C.RESET}")
                    print_assistant_text(plan_text)
                    try:
                        answer = input(f"  {C.YELLOW}Valider ce plan ? [O/n]{C.RESET} ").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        answer = "n"
                    if answer not in ("", "o", "oui", "y", "yes"):
                        session.messages.pop()
                        print(f"  {C.DIM}Plan annulé.{C.RESET}\n")
                        continue

                    n_todo = session.set_todo_from_plan(plan_text)
                    if n_todo > 0:
                        done, total = session.todo_counts()
                        todo_lines = [
                            f"{C.BOLD}{C.WHITE}TODO genere depuis le plan valide{C.RESET}",
                            f"  {C.GRAY}Progression:{C.RESET} {done}/{total}",
                            "",
                        ]
                        for i, item in enumerate(session.todo_items, start=1):
                            todo_lines.append(f"  {C.GRAY}{i:>2}.{C.RESET} [ ] {item.get('text', '')}")
                        plines(draw_box(todo_lines, color=C.CYAN))
                        print()
                except Exception as exc:
                    clear_line()
                    print(
                        f"  {C.YELLOW}⚠️  Impossible de générer le plan : {exc}. "
                        f"Exécution directe.{C.RESET}"
                    )
            elif session.plan_first and skip_replan and session.verbosity >= 1:
                done, total = session.todo_counts()
                print(f"  {C.DIM}↪ Reprise du TODO existant ({done}/{total}), sans nouveau plan.{C.RESET}")

            # ── Lancer l'agent ───────────────────
            session.run()

            # Compaction automatique basée sur les tokens estimés
            if needs_compaction(session.messages):
                session.compact_history()

        except KeyboardInterrupt:
            print(f"\n{_M}  {C.YELLOW}Interrompu.{C.RESET} Tapez /quit pour quitter.\n")
            continue
        except EOFError:
            session.save_memory_snapshot()
            print(f"\n{_M}  {C.DIM}Au revoir !{C.RESET}  {C.ROUGE}🇫🇷{C.RESET}\n")
            break


# ──────────────────────────────────────────────
#  Point d'entrée
# ──────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Albert Code — Agent de code souverain",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemples :\n"
            "  albert-code\n"
            '  albert-code "crée un hello world"\n'
            '  albert-code --plan-first "refactorise main.py"\n'
            '  albert-code --quiet "lance les tests"'
        ),
    )
    parser.add_argument(
        "prompt", nargs="?", default=None,
        help="Prompt direct — exécute en mode non-interactif (CI/scripting)",
    )
    parser.add_argument("--model",       default=DEFAULT_MODEL,    help=f"Modèle Albert (défaut: {DEFAULT_MODEL})")
    parser.add_argument("--base-url",    default=ALBERT_BASE,      help="URL de l'API Albert")
    parser.add_argument("--api-key",     default=None,             help="Clé API (ou variable ALBERT_API_KEY)")
    parser.add_argument("--auto-approve", action="store_true",     help="Ne pas demander de confirmation")
    parser.add_argument("--auto-fallback", action="store_true",
                        help="Activer l'auto-fallback 429 (large -> medium 60s)")
    parser.add_argument("--max-steps",   type=int, default=DEFAULT_MAX_STEPS,
                        help=f"Limite de steps agent (défaut: {DEFAULT_MAX_STEPS})")
    parser.add_argument("--timeout",     type=float, default=DEFAULT_TIMEOUT,
                        help=f"Timeout API en secondes (défaut: {DEFAULT_TIMEOUT})")
    verb_group = parser.add_mutually_exclusive_group()
    verb_group.add_argument("--verbose", "-v", action="store_true",
                             help="Afficher tous les outputs des outils sans troncature")
    verb_group.add_argument("--quiet",   "-q", action="store_true",
                             help="Masquer les détails des outils (sortie minimaliste)")
    parser.add_argument("--plan-first", action="store_true",
                        help="Demander un plan validé avant d'exécuter chaque requête")
    parser.add_argument("--no-git-commit", action="store_true",
                        help="Désactiver les commits git automatiques après chaque écriture")
    args = parser.parse_args()

    verbosity = 2 if args.verbose else (0 if args.quiet else 1)

    api_key = args.api_key or os.getenv("ALBERT_API_KEY")
    if not api_key:
        print(f"\n  {C.RED}❌ Clé API requise !{C.RESET}")
        print(f"  {C.DIM}Définissez ALBERT_API_KEY ou passez --api-key 'votre_clé'{C.RESET}\n")
        raise SystemExit(1)

    # Charger la configuration projet (.albert-code.toml)
    project_cfg = load_project_config()
    if project_cfg.config_path and verbosity >= 1:
        short = str(project_cfg.config_path).replace(str(Path.home()), "~")
        print(f"  {C.DIM}📄 Config projet chargée : {short}{C.RESET}")
        if project_cfg.ignore_patterns:
            print(f"  {C.DIM}   ignore : {', '.join(project_cfg.ignore_patterns)}{C.RESET}")

    # Les flags CLI ont la priorité ; les valeurs du .toml ne s'appliquent
    # que si l'utilisateur n'a pas fourni d'argument explicite.
    effective_model   = args.model   if args.model   != DEFAULT_MODEL  else (project_cfg.model_name or args.model)
    effective_baseurl = args.base_url if args.base_url != ALBERT_BASE   else (project_cfg.base_url   or args.base_url)
    effective_timeout = args.timeout  if args.timeout  != DEFAULT_TIMEOUT else (project_cfg.timeout   or args.timeout)

    client = AlbertClient(
        base_url=effective_baseurl,
        api_key=api_key,
        model=effective_model,
        timeout=effective_timeout,
        auto_fallback_429=args.auto_fallback,
    )

    session = AgentSession(
        client=client,
        auto_approve=args.auto_approve,
        max_steps=args.max_steps,
        verbosity=verbosity,
        plan_first=args.plan_first,
        git_commit=not args.no_git_commit,
        persist_todo=True,
        project_cfg=project_cfg,
        memory_enabled=project_cfg.memory_enabled,
        memory_auto_save=project_cfg.memory_auto_save,
        memory_auto_recall=project_cfg.memory_auto_recall,
        memory_recall_top_k=project_cfg.memory_recall_top_k,
        memory_recall_max_tokens=project_cfg.memory_recall_max_tokens,
        memory_palace_path=project_cfg.memory_palace_path,
    )
    session.initialize()

    # Mode non-interactif
    if args.prompt:
        session.add_user_message(args.prompt)
        session.run()
        if client.total_requests > 0 and verbosity >= 1:
            print_stats(session)
        return

    print_welcome(args.model, args.auto_approve, verbosity, args.plan_first,
                  config_path=str(project_cfg.config_path) if project_cfg.config_path else "")
    repl(session)

    if client.total_requests > 0:
        print_stats(session)
