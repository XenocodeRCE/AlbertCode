#!/usr/bin/env python3
"""
Albert Code — Mockup CLI Interface 🇫🇷
Aucune dépendance externe requise.

Usage : python mockup_cli.py
"""

import os
import sys
import re
import time
from pathlib import Path

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Couleurs ANSI — Drapeau Français + UI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BLEU      = "\033[38;2;0;85;164m"
BLANC     = "\033[38;2;255;255;255m"
ROUGE     = "\033[38;2;239;65;53m"

GRIS      = "\033[38;2;100;100;100m"
GRIS_CL   = "\033[38;2;180;180;180m"
JAUNE     = "\033[38;2;255;193;37m"
VERT      = "\033[38;2;80;200;120m"
CYAN      = "\033[38;2;100;180;255m"
ORANGE    = "\033[38;2;255;150;50m"

BOLD      = "\033[1m"
DIM       = "\033[2m"
ITALIC    = "\033[3m"
RESET     = "\033[0m"

# Marge gauche constante (pas de centrage)
M = "  "

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ASCII Art "ALBERT" — Tricolore
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ART_B = [
    " █████╗ ██╗     ",
    "██╔══██╗██║     ",
    "███████║██║     ",
    "██╔══██║██║     ",
    "██║  ██║███████╗",
    "╚═╝  ╚═╝╚══════╝",
]

ART_W = [
    "██████╗ ███████╗",
    "██╔══██╗██╔════╝",
    "██████╔╝█████╗  ",
    "██╔══██╗██╔══╝  ",
    "██████╔╝███████╗",
    "╚═════╝ ╚══════╝",
]

ART_R = [
    "██████╗ ████████╗",
    "██╔══██╗╚══██╔══╝",
    "██████╔╝   ██║   ",
    "██╔══██╗   ██║   ",
    "██║  ██║   ██║   ",
    "╚═╝  ╚═╝   ╚═╝   ",
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Utilitaires
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def strip_ansi(text):
    return re.sub(r'\033\[[^m]*m', '', text)

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

def p(text=""):
    """Print une ligne avec marge gauche."""
    print(f"{M}{text}")

def sep(w=64):
    """Séparateur horizontal."""
    p(f"{GRIS}{'─' * w}{RESET}")

def safe_input(prompt_str):
    """input() avec gestion propre de Ctrl+C."""
    try:
        return input(prompt_str)
    except (KeyboardInterrupt, EOFError):
        print(f"\n\n{M}{BOLD}{BLANC}Au revoir !{RESET} 🇫🇷\n")
        sys.exit(0)

def prompt_user(hint=""):
    """Vrai prompt ❯ en bas — c'est ici qu'on tape."""
    if hint:
        p(f"{DIM}{ITALIC}{GRIS}{hint}{RESET}")
    return safe_input(f"{M}{BOLD}{BLANC}❯{RESET} ")

def prompt_choice(options="Y/N"):
    """Prompt de choix [Y/N/A/E]."""
    return safe_input(f"{M}{BOLD}{BLANC}?{RESET} [{options}] ")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Composants UI — Boîtes Unicode (alignées à gauche)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def box_top(w, color=GRIS):
    return f"{M}{color}╭{'─' * (w - 2)}╮{RESET}"

def box_bot(w, color=GRIS):
    return f"{M}{color}╰{'─' * (w - 2)}╯{RESET}"

def box_empty(w, color=GRIS):
    return f"{M}{color}│{RESET}{' ' * (w - 2)}{color}│{RESET}"

def box_row(text, w, color=GRIS):
    vis = len(strip_ansi(text))
    pad = max(0, w - 4 - vis)
    return f"{M}{color}│{RESET} {text}{' ' * (pad + 1)}{color}│{RESET}"

def draw_box(lines, color=GRIS, w=68):
    out = [box_top(w, color), box_empty(w, color)]
    for l in lines:
        out.append(box_row(l, w, color))
    out += [box_empty(w, color), box_bot(w, color)]
    return out

def draw_titled_box(title, lines, color=GRIS, w=68):
    t = f" {title} "
    dashes = max(0, w - 3 - len(strip_ansi(t)))
    top = f"{M}{color}╭─{RESET}{t}{color}{'─' * dashes}╮{RESET}"
    out = [top, box_empty(w, color)]
    for l in lines:
        out.append(box_row(l, w, color))
    out += [box_empty(w, color), box_bot(w, color)]
    return out

def plines(lines):
    for l in lines:
        print(l)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Animation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def spinner(msg, duration=1.5):
    frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    t0 = time.time()
    i = 0
    while time.time() - t0 < duration:
        f = frames[i % len(frames)]
        sys.stdout.write(f"\r{M}  {JAUNE}{f}{RESET} {GRIS}{msg}{RESET}    ")
        sys.stdout.flush()
        time.sleep(0.08)
        i += 1
    sys.stdout.write(f"\r{M}  {VERT}✔{RESET} {GRIS_CL}{msg}{RESET}    \n")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Header compact (réutilisé sur chaque écran sauf accueil)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def header():
    print()
    p(f"{BOLD}{BLEU}AL{BLANC}BE{ROUGE}RT{RESET}"
      f" {BOLD}{BLANC}Code{RESET} {DIM}{GRIS}v0.1.0{RESET}"
      f"  {GRIS}·{RESET}  {CYAN}~/mon-projet{RESET}"
      f"  {GRIS}·{RESET}  {VERT}●{RESET} {GRIS}albert-large{RESET}")
    sep()
    print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ÉCRAN 1 — Accueil
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def screen_welcome():
    clear()
    W = 68
    print()

    # Logo tricolore
    for i in range(6):
        p(f"{BOLD}{BLEU}{ART_B[i]} {BLANC}{ART_W[i]} {ROUGE}{ART_R[i]}{RESET}")

    print()
    p(f"{GRIS}{'─' * 22}{RESET}  {BOLD}{BLANC}c  o  d  e{RESET}  {GRIS}{'─' * 22}{RESET}")
    print()

    # Boîte de bienvenue
    cwd = str(Path.cwd())
    if len(cwd) > 50:
        cwd = "..." + cwd[-47:]

    plines(draw_box([
        f"{JAUNE}✦{RESET}  {BOLD}{BLANC}Bienvenue sur Albert Code{RESET}  {DIM}{GRIS}v0.1.0{RESET}",
        "",
        f"   {GRIS_CL}/help{RESET} {GRIS}pour l'aide{RESET}  {GRIS}·{RESET}  {GRIS_CL}/status{RESET} {GRIS}pour la configuration{RESET}",
        f"   {GRIS}cwd:{RESET} {CYAN}{cwd}{RESET}",
    ], color=GRIS, w=W))

    print()

    # Conseils
    p(f"{BOLD}{BLANC}Conseils pour démarrer :{RESET}")
    print()
    p(f"  {BLANC}1.{RESET}  {GRIS_CL}Lancez{RESET} {CYAN}/init{RESET} {GRIS_CL}pour créer un{RESET} {BLANC}ALBERT.md{RESET}")
    p(f"  {BLANC}2.{RESET}  {GRIS_CL}Albert peut{RESET} {BLANC}lire, écrire, exécuter{RESET} {GRIS_CL}et chercher dans votre code{RESET}")
    p(f"  {BLANC}3.{RESET}  {GRIS_CL}Soyez aussi précis qu'avec un{RESET} {BLANC}collègue développeur{RESET}")
    p(f"  {BLANC}4.{RESET}  {GRIS_CL}Chaque action crée un{RESET} {VERT}commit git automatique{RESET} {GRIS_CL}(réversible){RESET}")

    print()

    # Barre de statut
    p(f"{VERT}●{RESET} {GRIS}Modèle:{RESET} {BLANC}albert-large{RESET}"
      f"  {GRIS}·{RESET}  {GRIS}Contexte:{RESET} {BLANC}128k{RESET}"
      f"  {GRIS}·{RESET}  {GRIS}Auto-approve:{RESET} {ROUGE}off{RESET}")

    print()

    # ← Le VRAI prompt, pas une boîte décorative
    prompt_user("Essayez \"analyse ce projet et suggère des améliorations\"")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ÉCRAN 2 — Conversation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def screen_conversation():
    clear()
    header()

    # Message utilisateur
    p(f"{BOLD}{BLEU}▍{RESET} {BOLD}{BLANC}Vous{RESET}  {DIM}{GRIS}14:32{RESET}")
    p(f"  {GRIS_CL}Explique-moi la structure de ce projet et propose des améliorations{RESET}")
    print()
    sep()
    print()

    # Réponse agent
    p(f"{BOLD}{ROUGE}▍{RESET} {BOLD}{BLANC}Albert{RESET}  {DIM}{GRIS}14:32{RESET}")
    print()

    # Spinners tool calls
    spinner("Lecture de src/main.py...", 0.6)
    spinner("Exploration de src/...", 0.4)
    spinner("Lecture de pyproject.toml...", 0.5)
    print()

    # Résultats des tools
    tools = [
        ("read_file",  f'{BLANC}"src/main.py"{RESET}',   "2.1 KB"),
        ("list_files", f'{BLANC}"src/"{RESET}',           "12 fichiers"),
        ("read_file",  f'{BLANC}"pyproject.toml"{RESET}', "0.8 KB"),
    ]
    for name, args, result in tools:
        p(f"  {VERT}✔{RESET} {JAUNE}{name}{RESET}{GRIS}({args}{GRIS}){RESET}  {DIM}{GRIS}→ {result}{RESET}")

    print()

    # Texte de réponse
    p(f"  {GRIS_CL}J'ai analysé votre projet. Voici ce que j'ai trouvé :{RESET}")
    print()
    p(f"  {GRIS_CL}Le projet contient{RESET} {BLANC}12 fichiers Python{RESET} {GRIS_CL}organisés en{RESET} {BLANC}3 modules{RESET}{GRIS_CL}.{RESET}")
    p(f"  {GRIS_CL}La structure est globalement bonne, mais je suggère :{RESET}")
    print()
    p(f"    {BLANC}1.{RESET} {GRIS_CL}Extraire la logique métier de{RESET} {CYAN}main.py{RESET} {GRIS_CL}dans un module dédié{RESET}")
    p(f"    {BLANC}2.{RESET} {GRIS_CL}Ajouter des tests unitaires ({ROUGE}aucun test détecté{GRIS_CL}){RESET}")
    p(f"    {BLANC}3.{RESET} {GRIS_CL}Utiliser{RESET} {CYAN}pydantic{RESET} {GRIS_CL}pour la validation des données{RESET}")
    print()
    p(f"  {GRIS_CL}Voulez-vous que je commence par l'une de ces améliorations ?{RESET}")
    print()
    p(f"  {DIM}{GRIS}⏱ 2.3s  ·  ↑ 1,247 tokens  ·  ↓ 856 tokens  ·  💰 ~0.003€{RESET}")
    print()
    sep()
    print()

    # Vrai prompt
    prompt_user()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ÉCRAN 3 — Permission
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def screen_permission():
    clear()
    W = 68
    header()

    # Utilisateur
    p(f"{BOLD}{BLEU}▍{RESET} {BOLD}{BLANC}Vous{RESET}  {DIM}{GRIS}14:35{RESET}")
    p(f"  {GRIS_CL}Oui, commence par ajouter les tests{RESET}")
    print()
    sep()
    print()

    # Agent
    p(f"{BOLD}{ROUGE}▍{RESET} {BOLD}{BLANC}Albert{RESET}  {DIM}{GRIS}14:35{RESET}")
    print()
    p(f"  {GRIS_CL}Je vais créer les fichiers de tests.{RESET}")
    print()

    # Boîte de permission (contenu seulement, pas les boutons)
    plines(draw_titled_box(
        f"{ORANGE}🔒 Permission requise{RESET}",
        [
            f"{BLANC}Albert veut créer un fichier :{RESET}",
            "",
            f"  {CYAN}📄 tests/test_main.py{RESET}  {DIM}{GRIS}(nouveau · 45 lignes){RESET}",
            "",
            f"  {DIM}{GRIS}@@ +1,6 @@{RESET}",
            f"  {VERT}+ import pytest{RESET}",
            f"  {VERT}+ from src.main import process_data{RESET}",
            f"  {VERT}+{RESET}",
            f"  {VERT}+ class TestProcessData:{RESET}",
            f"  {VERT}+     def test_valid_input(self):{RESET}",
            f"  {VERT}+         assert process_data(\"hello\") == ...{RESET}",
            f"  {DIM}{GRIS}  ... (+39 lignes){RESET}",
        ],
        color=ORANGE, w=W
    ))

    print()

    # Choix HORS de la boîte, juste au-dessus du prompt
    p(f"  {VERT}[Y]{RESET} {GRIS_CL}Accepter{RESET}"
      f"    {ROUGE}[N]{RESET} {GRIS_CL}Refuser{RESET}"
      f"    {JAUNE}[A]{RESET} {GRIS_CL}Toujours{RESET}"
      f"    {CYAN}[E]{RESET} {GRIS_CL}Éditer{RESET}")

    # Vrai prompt de choix
    prompt_choice("Y/N/A/E")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ÉCRAN 4 — Diff
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def screen_diff():
    clear()
    W = 68
    header()

    # Agent
    p(f"{BOLD}{ROUGE}▍{RESET} {BOLD}{BLANC}Albert{RESET}  {DIM}{GRIS}14:36 · en cours...{RESET}")
    print()
    p(f"  {GRIS_CL}Modification de{RESET} {CYAN}src/main.py{RESET} {GRIS_CL}pour améliorer la structure :{RESET}")
    print()

    # Boîte diff
    plines(draw_titled_box(
        f"{CYAN}📝 src/main.py{RESET} {DIM}{GRIS}(modifié){RESET}",
        [
            f"{DIM}{GRIS}@@ -23,5 +23,8 @@{RESET}",
            "",
            f"  {GRIS}21 │{RESET} {GRIS_CL}from pathlib import Path{RESET}",
            f"  {GRIS}22 │{RESET} {GRIS_CL}from typing import Optional{RESET}",
            f"  {ROUGE}23 │ ─ def process_data(data):{RESET}",
            f"  {ROUGE}24 │ ─     result = data.split(','){RESET}",
            f"  {ROUGE}25 │ ─     return result{RESET}",
            f"  {VERT}23 │ + def process_data(data: str) -> list[str]:{RESET}",
            f"  {VERT}24 │ +     \"\"\"Traite et valide les données d'entrée.\"\"\"{RESET}",
            f"  {VERT}25 │ +     if not isinstance(data, str):{RESET}",
            f"  {VERT}26 │ +         raise TypeError(\"str attendu\"){RESET}",
            f"  {VERT}27 │ +     result = data.strip().split(','){RESET}",
            f"  {VERT}28 │ +     return [item.strip() for item in result]{RESET}",
        ],
        color=CYAN, w=W
    ))

    print()

    # Choix hors boîte
    p(f"  {VERT}[Y]{RESET} {GRIS_CL}Appliquer{RESET}"
      f"    {ROUGE}[N]{RESET} {GRIS_CL}Rejeter{RESET}"
      f"    {CYAN}[E]{RESET} {GRIS_CL}Éditer avant d'appliquer{RESET}")

    prompt_choice("Y/N/E")

    # Après le choix → git commit
    print()
    plines(draw_titled_box(
        f"{VERT}🔀 Git auto-commit{RESET}",
        [
            f"{GRIS_CL}Le commit suivant sera créé automatiquement :{RESET}",
            "",
            f"  {DIM}{GRIS}${RESET} {BLANC}git commit -m{RESET} {VERT}\"refactor: type hints + validation process_data\"{RESET}",
        ],
        color=VERT, w=W
    ))

    print()
    spinner("Commit en cours...", 0.8)
    p(f"{VERT}✔{RESET} {GRIS_CL}Commit créé avec succès{RESET}")
    print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Main
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    screens = [
        screen_welcome,
        screen_conversation,
        screen_permission,
        screen_diff,
    ]

    for render in screens:
        render()

    # Au revoir
    clear()
    print()
    for i in range(6):
        p(f"{BOLD}{BLEU}{ART_B[i]} {BLANC}{ART_W[i]} {ROUGE}{ART_R[i]}{RESET}")
    print()
    p(f"{BOLD}{BLANC}Merci d'avoir testé le mockup Albert Code !{RESET}  🇫🇷")
    print()


if __name__ == "__main__":
    main()