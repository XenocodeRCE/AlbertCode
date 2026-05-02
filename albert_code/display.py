"""
Fonctions d'affichage terminal.

Composants UI inspirés du mockup tricolore Albert Code :
 - Boîtes Unicode ╭─╮╰─╯ avec titres optionnels
 - Ligne ⠋ → ✔ pour les tool calls inline
 - ▍ Albert prefix pour les réponses LLM
 - Confirmations dans des boîtes colorées [Y/N/A]
"""

from __future__ import annotations

import json
import re
import sys

from .config import C

# ─────────────────────────────────────────────────────────────────
#  Constantes de mise en page
# ─────────────────────────────────────────────────────────────────

_M = "  "   # marge gauche
_W = 68     # largeur des boîtes

# ASCII art "ALBERT" tricolore (même que le mockup)
_ART_B = [
    " █████╗ ██╗     ",
    "██╔══██╗██║     ",
    "███████║██║     ",
    "██╔══██║██║     ",
    "██║  ██║███████╗",
    "╚═╝  ╚═╝╚══════╝",
]
_ART_W = [
    "██████╗ ███████╗",
    "██╔══██╗██╔════╝",
    "██████╔╝█████╗  ",
    "██╔══██╗██╔══╝  ",
    "██████╔╝███████╗",
    "╚═════╝ ╚══════╝",
]
_ART_R = [
    "██████╗ ████████╗",
    "██╔══██╗╚══██╔══╝",
    "██████╔╝   ██║   ",
    "██╔══██╗   ██║   ",
    "██║  ██║   ██║   ",
    "╚═╝  ╚═╝   ╚═╝   ",
]

# ─────────────────────────────────────────────────────────────────
#  Helpers ANSI / texte
# ─────────────────────────────────────────────────────────────────

def strip_ansi(text: str) -> str:
    """Retire les codes couleur ANSI pour mesurer la largeur visible."""
    return re.sub(r"\033\[[^m]*m", "", text)


def clear_line() -> None:
    sys.stdout.write("\r\033[K")
    sys.stdout.flush()


# ─────────────────────────────────────────────────────────────────
#  Composants boîtes Unicode
# ─────────────────────────────────────────────────────────────────

def box_top(w: int = _W, color: str = "") -> str:
    c = color or C.GRAY
    return f"{_M}{c}╭{'─' * (w - 2)}╮{C.RESET}"


def box_bot(w: int = _W, color: str = "") -> str:
    c = color or C.GRAY
    return f"{_M}{c}╰{'─' * (w - 2)}╯{C.RESET}"


def box_empty(w: int = _W, color: str = "") -> str:
    c = color or C.GRAY
    return f"{_M}{c}│{C.RESET}{' ' * (w - 2)}{c}│{C.RESET}"


def box_row(text: str, w: int = _W, color: str = "") -> str:
    c = color or C.GRAY
    vis = len(strip_ansi(text))
    pad = max(0, w - 4 - vis)
    return f"{_M}{c}│{C.RESET} {text}{' ' * (pad + 1)}{c}│{C.RESET}"


def draw_box(lines: list[str], color: str = "", w: int = _W) -> list[str]:
    c = color or C.GRAY
    out = [box_top(w, c), box_empty(w, c)]
    for line in lines:
        out.append(box_row(line, w, c))
    out += [box_empty(w, c), box_bot(w, c)]
    return out


def draw_titled_box(
    title: str,
    lines: list[str],
    color: str = "",
    w: int = _W,
) -> list[str]:
    c      = color or C.GRAY
    t_vis  = f" {strip_ansi(title)} "
    dashes = max(0, w - 3 - len(t_vis))
    top    = f"{_M}{c}╭─ {C.RESET}{title} {c}{'─' * dashes}╮{C.RESET}"
    out    = [top, box_empty(w, c)]
    for line in lines:
        out.append(box_row(line, w, c))
    out += [box_empty(w, c), box_bot(w, c)]
    return out


def plines(lines: list[str]) -> None:
    for line in lines:
        print(line)


# ─────────────────────────────────────────────────────────────────
#  Logo ASCII + header compact
# ─────────────────────────────────────────────────────────────────

def print_logo() -> None:
    """Affiche le logo ASCII ALBERT en tricolore français."""
    print()
    for i in range(6):
        print(
            f"{_M}{C.BOLD}{C.BLEU}{_ART_B[i]}"
            f" {C.BLANC}{_ART_W[i]}"
            f" {C.ROUGE}{_ART_R[i]}{C.RESET}"
        )
    print()
    print(
        f"{_M}{C.GRAY}{'─' * 22}{C.RESET}"
        f"  {C.BOLD}{C.WHITE}c  o  d  e{C.RESET}"
        f"  {C.GRAY}{'─' * 22}{C.RESET}"
    )
    print()


def header(cwd: str = "", model: str = "") -> None:
    """Ligne de contexte compacte : AL|BE|RT Code · ~/cwd · ● model."""
    cwd_part   = f"  {C.GRAY}·{C.RESET}  {C.CYAN}{cwd}{C.RESET}" if cwd else ""
    model_part = f"  {C.GRAY}·{C.RESET}  {C.GREEN}●{C.RESET} {C.GRAY}{model}{C.RESET}" if model else ""
    print()
    print(
        f"{_M}{C.BOLD}{C.BLEU}AL{C.BLANC}BE{C.ROUGE}RT{C.RESET}"
        f" {C.BOLD}{C.WHITE}Code{C.RESET}"
        f" {C.DIM}{C.GRAY}v0.1{C.RESET}"
        f"{cwd_part}{model_part}"
    )
    print(f"{_M}{C.GRAY}{'─' * 64}{C.RESET}")
    print()


# ─────────────────────────────────────────────────────────────────
#  État interne : ligne ⠋ pending
# ─────────────────────────────────────────────────────────────────

_pending: dict = {"active": False, "icon": "", "name": "", "summary": ""}

# Outils affichés en ligne (pas de confirmation → pas de boîte)
_INLINE_TOOLS: frozenset[str] = frozenset({
    "read_file", "list_files", "grep_search",
    "git_status", "git_diff", "git_log",
})

_ICON: dict[str, str] = {
    "read_file":       "📖",
    "write_file":      "✍️",
    "edit_file":       "✏️",
    "multi_edit_file": "🛠️",
    "run_bash":        "💻",
    "grep_search":     "🔍",
    "list_files":      "📁",
    "git_status":      "📊",
    "git_diff":        "🔎",
    "git_log":         "📆",
}


def _icon(name: str) -> str:
    return _ICON.get(name, "🔧")


def _args_summary(name: str, args: dict) -> str:
    """Résumé compact des arguments pour la ligne de log."""
    if name == "read_file":
        path  = args.get("path", "?")
        start = args.get("start_line")
        end   = args.get("end_line")
        rng   = f":{start}-{end}" if start or end else ""
        return f"{C.CYAN}{path}{rng}{C.RESET}"
    if name in ("write_file", "edit_file"):
        return f"{C.CYAN}{args.get('path', '?')}{C.RESET}"
    if name == "multi_edit_file":
        path = args.get("path", "?")
        n    = len(args.get("patches", []))
        return f"{C.CYAN}{path}{C.RESET}  {C.DIM}{n} patch{'es' if n > 1 else ''}{C.RESET}"
    if name == "run_bash":
        cmd   = args.get("command", "?")
        short = cmd[:56] + ("…" if len(cmd) > 56 else "")
        return f"{C.YELLOW}{short}{C.RESET}"
    if name == "grep_search":
        pat  = args.get("pattern", "?")
        path = args.get("path", ".")
        return f"{C.CYAN}'{pat}'{C.RESET} {C.GRAY}in {path}{C.RESET}"
    if name == "list_files":
        path = args.get("path", ".")
        pat  = args.get("pattern", "")
        return f"{C.CYAN}{path}{C.RESET}" + (f"  {C.DIM}({pat}){C.RESET}" if pat else "")
    if name in ("git_status", "git_diff", "git_log"):
        extra = args.get("path", "") or str(args.get("n", ""))
        return f"{C.DIM}{extra}{C.RESET}" if extra else ""
    return f"{C.DIM}{json.dumps(args, ensure_ascii=False)[:60]}{C.RESET}"


def _result_oneliner(result: str) -> str:
    first = result.split("\n")[0].strip()
    if len(first) > 64:
        first = first[:61] + "…"
    return f"{C.DIM}{first}{C.RESET}"


def _diff_lines_for_box(name: str, args: dict) -> list[str]:
    """Lignes de diff/contenu à afficher dans la boîte de confirmation."""
    lines: list[str] = []

    if name == "write_file":
        content = args.get("content", "")
        rows    = content.split("\n")
        for row in rows[:8]:
            lines.append(f"  {C.GREEN}+{C.RESET} {C.DIM}{row[:60]}{C.RESET}")
        if len(rows) > 8:
            lines.append(f"  {C.DIM}… (+{len(rows) - 8} lignes){C.RESET}")

    elif name == "edit_file":
        old_lines = args.get("old_text", "").split("\n")
        new_lines = args.get("new_text", "").split("\n")
        for row in old_lines[:4]:
            lines.append(f"  {C.RED}-{C.RESET} {C.DIM}{row[:60]}{C.RESET}")
        if len(old_lines) > 4:
            lines.append(f"  {C.DIM}… ({len(old_lines) - 4} lignes supprimées){C.RESET}")
        for row in new_lines[:4]:
            lines.append(f"  {C.GREEN}+{C.RESET} {C.DIM}{row[:60]}{C.RESET}")
        if len(new_lines) > 4:
            lines.append(f"  {C.DIM}… ({len(new_lines) - 4} lignes ajoutées){C.RESET}")

    elif name == "multi_edit_file":
        patches = args.get("patches", [])
        for i, patch in enumerate(patches[:4], 1):
            old_raw = patch.get("old_text", "")
            new_raw = patch.get("new_text", "")
            old_s   = old_raw.split("\n")[0][:56]
            new_s   = new_raw.split("\n")[0][:56]
            if i > 1:
                lines.append("")
            lines.append(f"  {C.DIM}Patch {i}/{min(len(patches), 4)}{C.RESET}")
            lines.append(f"  {C.RED}-{C.RESET} {C.DIM}{old_s}{'…' if len(old_raw) > 56 else ''}{C.RESET}")
            lines.append(f"  {C.GREEN}+{C.RESET} {C.DIM}{new_s}{'…' if len(new_raw) > 56 else ''}{C.RESET}")
        if len(patches) > 4:
            lines.append(f"  {C.DIM}… et {len(patches) - 4} autre(s) patch(es){C.RESET}")

    elif name == "run_bash":
        cmd = args.get("command", "")
        lines.append(f"  {C.DIM}${C.RESET} {C.WHITE}{cmd[:60]}{C.RESET}")
        if len(cmd) > 60:
            lines.append(f"  {C.DIM}  {cmd[60:118]}{'…' if len(cmd) > 120 else ''}{C.RESET}")

    return lines


# ─────────────────────────────────────────────────────────────────
#  API publique
# ─────────────────────────────────────────────────────────────────

def print_thinking() -> None:
    """Indique que l'agent attend la réponse API (sans saut de ligne)."""
    sys.stdout.write(f"{_M}  {C.DIM}⠋  Albert réfléchit…{C.RESET}")
    sys.stdout.flush()


def print_tool_call(name: str, args: dict) -> None:
    """Affiche un tool call.

    Outils lecture (inline) : ligne ⠋ sans saut de ligne → écrasée par ✔.
    Outils écriture (box)   : boîte colorée avec diff/contenu.
    """
    global _pending
    icon    = _icon(name)
    summary = _args_summary(name, args)

    if name in _INLINE_TOOLS:
        _pending = {"active": True, "icon": icon, "name": name, "summary": summary}
        sys.stdout.write(
            f"\n{_M}  {C.DIM}⠋{C.RESET} {icon} "
            f"{C.YELLOW}{name}{C.RESET}  {summary}"
        )
        sys.stdout.flush()

    else:
        _pending = {"active": False, "name": name, "summary": summary}
        path = args.get("path", "")

        if name == "run_bash":
            title = "💻 Commande"
            color = C.CYAN
        elif name == "write_file":
            title = f"✍️  Nouveau fichier · {C.CYAN}{path}{C.RESET}"
            color = C.CYAN
        elif name == "edit_file":
            title = f"✏️  Modification · {C.CYAN}{path}{C.RESET}"
            color = C.CYAN
        elif name == "multi_edit_file":
            n     = len(args.get("patches", []))
            title = f"🛠️  Patches · {C.CYAN}{path}{C.RESET}  {C.DIM}({n} patches){C.RESET}"
            color = C.CYAN
        else:
            title = f"🔧 {name}"
            color = C.GRAY

        diff = _diff_lines_for_box(name, args)
        print()
        plines(draw_titled_box(title, diff, color=color))


def print_tool_result(result: str, collapsed: bool = False) -> None:
    """Affiche le résultat d'un tool call.

    Si une ligne ⠋ pending est active : l'écrase avec ✔ + résumé.
    Sinon (après une boîte) : affiche une ligne de statut.
    En mode verbose (collapsed=False) : détaille le résultat sous la ligne ✔.
    """
    global _pending
    ok   = not result.startswith(("❌", "⚠️"))
    tick = f"{C.GREEN}✔{C.RESET}" if ok else f"{C.RED}✗{C.RESET}"

    if _pending.get("active"):
        clear_line()
        icon     = _pending["icon"]
        name     = _pending["name"]
        summary  = _pending["summary"]
        oneliner = _result_oneliner(result)
        print(
            f"{_M}  {tick} {icon} {C.YELLOW}{name}{C.RESET}"
            f"  {summary}  {C.DIM}→{C.RESET}  {oneliner}"
        )
        # Mode verbose : affiche le contenu complet
        if not collapsed and result.count("\n") > 0:
            for line in result.split("\n")[:40]:
                print(f"{_M}    {C.DIM}{line}{C.RESET}")
            extra = result.count("\n") + 1 - 40
            if extra > 0:
                print(f"{_M}    {C.DIM}… ({extra} lignes supplémentaires){C.RESET}")
        _pending = {"active": False}

    else:
        name = str(_pending.get("name", ""))
        if name == "run_bash":
            rows = result.split("\n")
            lines: list[str] = []

            for row in rows[:14]:
                short_row = row if len(row) <= 60 else row[:59] + "…"
                lines.append(f"  {C.DIM}{short_row}{C.RESET}")

            extra = len(rows) - 14
            if extra > 0:
                lines.append(f"  {C.DIM}… ({extra} lignes supplémentaires){C.RESET}")

            title_color = C.GREEN if ok else C.RED
            print()
            plines(draw_titled_box(
                f"{title_color}📤 Résultat commande{C.RESET}",
                lines,
                color=C.GRAY,
            ))
            _pending = {"active": False}
            return

        first = result.split("\n")[0].strip()
        short = first[:80] if len(first) <= 80 else first[:77] + "…"
        print(f"\n{_M}  {tick}  {C.DIM}{short}{C.RESET}")
        _pending = {"active": False}


def print_assistant_text(text: str) -> None:
    """Affiche la réponse narrative de l'agent avec le préfixe ▍ Albert."""
    print()
    print(f"{_M}{C.BOLD}{C.ROUGE}▍{C.RESET} {C.BOLD}{C.WHITE}Albert{C.RESET}")
    print()
    for line in text.split("\n"):
        print(f"{_M}  {C.GRAY_LIGHT}{line}{C.RESET}")
    print()


def ask_confirmation(tool_name: str, args: dict) -> bool:
    """Demande confirmation dans une boîte orange + choix [Y/N/A] en dessous."""
    if tool_name == "run_bash":
        cmd   = args.get("command", "")
        short = cmd[:64] + ("…" if len(cmd) > 64 else "")
        box_lines = [
            f"Albert veut {C.WHITE}exécuter la commande{C.RESET} :",
            "",
            f"  {C.DIM}${C.RESET} {C.WHITE}{short}{C.RESET}",
        ]
    elif tool_name == "write_file":
        path = args.get("path", "?")
        box_lines = [
            f"Albert veut {C.WHITE}créer / écraser{C.RESET} :",
            "",
            f"  {C.CYAN}📄 {path}{C.RESET}",
        ]
    elif tool_name in ("edit_file", "multi_edit_file"):
        path    = args.get("path", "?")
        patches = args.get("patches", [args.get("old_text", "")])
        n       = len(patches)
        label   = f"{n} modification{'s' if n > 1 else ''}"
        box_lines = [
            f"Albert veut {C.WHITE}modifier{C.RESET} "
            f"{C.CYAN}{path}{C.RESET}  {C.DIM}({label}){C.RESET}",
        ]
    else:
        box_lines = [f"Albert veut exécuter : {C.WHITE}{tool_name}{C.RESET}"]

    print()
    plines(draw_titled_box(
        f"{C.ORANGE}🔒 Permission requise{C.RESET}",
        box_lines,
        color=C.ORANGE,
    ))
    print()
    print(
        f"{_M}  {C.GREEN}[Y]{C.RESET} {C.GRAY_LIGHT}Accepter{C.RESET}"
        f"    {C.RED}[N]{C.RESET} {C.GRAY_LIGHT}Refuser{C.RESET}"
        f"    {C.YELLOW}[A]{C.RESET} {C.GRAY_LIGHT}Toujours accepter{C.RESET}"
        f"    {C.DIM}[stop]{C.RESET} {C.GRAY_LIGHT}Arrêter{C.RESET}"
    )
    try:
        answer = input(f"{_M}  {C.BOLD}{C.WHITE}?{C.RESET} [Y/N/A] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False

    if answer in ("stop", "s"):
        raise KeyboardInterrupt("Arrêté par l'utilisateur")
    return answer in ("", "y", "o", "yes", "oui", "a", "always", "toujours")
