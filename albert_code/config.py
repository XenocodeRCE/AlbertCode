"""
Configuration globale et constantes d'Albert Code.
"""

import os
import sys

# ──────────────────────────────────────────────
#  Palette de couleurs — tricolore français (RGB)
# ──────────────────────────────────────────────

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    ITALIC = "\033[3m"

    # Tricolore
    BLEU   = "\033[38;2;0;85;164m"     # Bleu français
    BLANC  = "\033[38;2;255;255;255m"  # Blanc
    ROUGE  = "\033[38;2;239;65;53m"    # Rouge français

    # Palette UI (utilise les mêmes valeurs que le tricolore quand cohérent)
    BLUE        = "\033[38;2;0;85;164m"
    WHITE       = "\033[38;2;255;255;255m"
    RED         = "\033[38;2;239;65;53m"
    GREEN       = "\033[38;2;80;200;120m"
    YELLOW      = "\033[38;2;255;193;37m"
    CYAN        = "\033[38;2;100;180;255m"
    ORANGE      = "\033[38;2;255;150;50m"
    GRAY        = "\033[38;2;100;100;100m"
    GRAY_LIGHT  = "\033[38;2;180;180;180m"

    # Legacy (backward compat)
    MAGENTA = "\033[95m"
    BG_GRAY = "\033[48;5;236m"


# Active le support ANSI sur Windows
if sys.platform == "win32":
    os.system("")

# ──────────────────────────────────────────────
#  Constantes API / Agent
# ──────────────────────────────────────────────

ALBERT_BASE      = "https://albert.api.etalab.gouv.fr/v1"
DEFAULT_MODEL    = "openweight-large"
DEFAULT_MAX_STEPS = 25
DEFAULT_TIMEOUT  = 60
