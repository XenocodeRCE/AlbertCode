"""
Gestion de la fenêtre de contexte / tokens.

Stratégie :
  1. Estimation légère du nombre de tokens (heuristique : ~4 chars/token).
  2. Quand on dépasse TOKEN_THRESHOLD, les anciens messages sont résumés
     via un appel LLM dédié (résumé sémantique).
  3. Si le client LLM n'est pas fourni (tests, offline), on tronque
     simplement sans résumer.

Schéma après compaction :
  [system] [summary_assistant] [recent × KEEP_RECENT]
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .api import AlbertClient

# ──────────────────────────────────────────────
#  Paramètres
# ──────────────────────────────────────────────

# Seuil en tokens estimés avant de déclencher la compaction
TOKEN_THRESHOLD: int = 6_000
# Nombre de messages récents à toujours conserver intacts
KEEP_RECENT: int = 12


# ──────────────────────────────────────────────
#  Estimation tokens
# ──────────────────────────────────────────────

def _message_chars(msg: dict) -> int:
    """Nombre de caractères dans un message (contenu + éventuels tool_calls)."""
    total = len(str(msg.get("content") or ""))
    for tc in msg.get("tool_calls") or []:
        total += len(str(tc))
    return total


def estimate_tokens(messages: list[dict]) -> int:
    """Estimation grossière : 1 token ≈ 4 caractères (règle empirique OpenAI)."""
    return sum(_message_chars(m) for m in messages) // 4


def needs_compaction(messages: list[dict], threshold: int = TOKEN_THRESHOLD) -> bool:
    """Retourne True si l'historique dépasse le seuil de tokens estimés."""
    return estimate_tokens(messages) >= threshold


# ──────────────────────────────────────────────
#  Prompt de résumé
# ──────────────────────────────────────────────

_SUMMARIZE_PROMPT = """\
Voici un extrait d'une conversation entre un utilisateur et toi (un assistant de code).
Rédige un résumé DENSE et FACTUEL de ce qui a été fait, discuté et décidé.
Inclus : fichiers créés/modifiés, commandes exécutées, bugs trouvés/corrigés,
décisions d'architecture importantes.
Ne mets pas de titre. Écris en 150-250 mots maximum.
Le résumé sera réinjecté comme contexte au début de la prochaine fenêtre.

--- CONVERSATION À RÉSUMER ---
{conversation}
--- FIN ---
"""


def _format_for_summary(messages: list[dict]) -> str:
    """Sérialise les messages en texte lisible pour le prompt de résumé."""
    lines: list[str] = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content") or ""

        # Résumer les tool_calls (évite de surcharger le prompt)
        tool_calls = m.get("tool_calls")
        if tool_calls:
            tc_summary = "; ".join(
                f"{tc['function']['name']}({str(tc['function'].get('arguments',''))[:60]})"
                for tc in tool_calls
            )
            lines.append(f"[{role}] → appels outils : {tc_summary}")
        elif content.strip():
            # Tronquer les résultats d'outils trop longs
            if role == "tool":
                preview = content.strip()[:300]
                suffix = "…" if len(content) > 300 else ""
                lines.append(f"[tool result] {preview}{suffix}")
            else:
                lines.append(f"[{role}] {content.strip()}")
    return "\n".join(lines)


# ──────────────────────────────────────────────
#  Compaction
# ──────────────────────────────────────────────

def compact_history(
    messages: list[dict],
    client: "AlbertClient | None" = None,
    verbosity: int = 1,
    keep_recent: int = KEEP_RECENT,
) -> list[dict]:
    """
    Compresse l'historique pour rester sous le seuil de tokens.

    - Si `client` est fourni : résumé sémantique via LLM.
    - Sinon : remplacement par un placeholder textuel (mode dégradé).

    Retourne la nouvelle liste de messages.
    """
    if len(messages) <= keep_recent + 2:  # system + qqs messages → rien à faire
        return messages

    system = messages[0]
    # Garder les N derniers messages intacts
    recent   = messages[-keep_recent:]
    # Les messages intermédiaires à résumer (sans le system)
    to_summarize = messages[1: len(messages) - keep_recent]

    if not to_summarize:
        return messages

    tokens_before = estimate_tokens(messages)

    # ── Résumé LLM ───────────────────────────
    if client is not None:
        try:
            sys.stdout.write("  \033[2m🧠 Résumé du contexte en cours…\033[0m")
            sys.stdout.flush()

            conv_text = _format_for_summary(to_summarize)
            prompt    = _SUMMARIZE_PROMPT.format(conversation=conv_text)
            summary_text = client.chat_no_tools(
                [{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=400,
            )

            sys.stdout.write("\r\033[K")  # effacer la ligne spinner
            sys.stdout.flush()

        except Exception as exc:
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
            if verbosity >= 1:
                print(f"  \033[93m⚠️  Résumé LLM échoué ({exc}), troncature simple.\033[0m")
            summary_text = None
    else:
        summary_text = None

    # ── Construire le message de résumé ──────
    if summary_text:
        summary_msg: dict = {
            "role": "user",
            "content": (
                "[RÉSUMÉ DU CONTEXTE PRÉCÉDENT — généré automatiquement]\n"
                + summary_text
                + "\n[FIN DU RÉSUMÉ — la conversation continue ci-dessous]"
            ),
        }
    else:
        summary_msg = {
            "role": "user",
            "content": (
                f"[Contexte : {len(to_summarize)} messages antérieurs ont été compressés. "
                "La conversation continue ci-dessous.]"
            ),
        }

    new_messages = [system, summary_msg, *recent]
    tokens_after  = estimate_tokens(new_messages)

    if verbosity >= 1:
        mode = "résumé LLM" if summary_text else "troncature"
        print(
            f"  \033[2m📦 Contexte compressé ({mode}) : "
            f"~{tokens_before} → ~{tokens_after} tokens estimés\033[0m"
        )

    return new_messages
