<p align="center">
	<img src="https://github.com/XenocodeRCE/AlbertCode/blob/master/header.png" alt="Albert Code" />
</p>

# Albert Code

Agent CLI Python pour assister le dev avec Albert API.

## Apercu

Albert Code est un agent de code en terminal avec:
- REPL interactif
- Outils fichiers/recherche/shell/git
- Mode plan-first avec checklist TODO
- Checkpoints internes et undo
- Support de skills via SKILL.md

## Prerequis

- Python 3.10+
- Une cle API Albert

## Installation

```bash
pip install -e .
```

Option dev:

```bash
pip install -e ".[dev]"
```

Option memoire persistante (MemPalace + embeddings Albert API):

```bash
pip install -e ".[memory]"
```

## Lancement

Variable d'environnement:

```bash
# Linux/macOS
export ALBERT_API_KEY="votre_cle"

# Windows PowerShell
$env:ALBERT_API_KEY="votre_cle"
```

Demarrer le CLI:

```bash
albert-code
```

Ou:

```bash
python -m albert_code
```

Mode non interactif:

```bash
albert-code "analyse ce projet et propose un plan"
```

## Toutes les commandes

- /help: afficher l'aide
- /init [--force]: creer ou ecraser ALBERT.md
- /cwd: afficher le dossier courant
- /cd <chemin>: changer de dossier de travail
- /clear: reinitialiser la conversation
- /compact: compresser l'historique
- /stats: afficher les stats de session
- /status: afficher la configuration active
- /models: lister les alias/modeles supportes
- /model [id]: afficher ou changer le modele
- /rpm: afficher la jauge RPM du modele actif
- /limits: afficher les quotas API connus
- /skills: afficher l'etat et la liste des skills
- /skills on: activer les skills
- /skills off: desactiver les skills
- /skills reload: recharger les skills
- /skills use <nom>: epingler un skill
- /skills unuse <nom>: retirer un skill epingle
- /skills auto: revenir a la selection automatique
- /skills install <url|owner/repo> [nom]: installer un SKILL.md
- /auto: activer/desactiver l'auto-approve
- /fallback: activer/desactiver l'auto-fallback 429
- /memory: afficher l'etat du sous-systeme memoire
- /memory status: etat du palace memoire
- /memory search <query>: rechercher dans la memoire
- /memory save: sauvegarder la conversation courante
- /memory on|off: activer/desactiver le recall memoire automatique
- /memory clear: vider le palace memoire (confirmation)
- /verbose: verbosite maximale
- /quiet: verbosite minimale
- /normal (ou /v1): verbosite normale
- /plan: activer/desactiver le mode plan-first
- /history: afficher l'historique des checkpoints
- /todo: afficher la checklist du plan courant
- /todo clear: vider la checklist
- /todo check <N>: cocher une tache
- /undo [N]: restaurer le dernier checkpoint ou #N
- /git: activer/desactiver la protection snapshots
- /quit (ou /exit, /q): quitter

En mode plan-first, les messages 'continue, continuer, suite, next, go, poursuis, poursuivre' reprennent le TODO existant sans regenerer un nouveau plan.

Mode multi-ligne: taper """ seul pour entrer/sortir du mode multi-ligne.

## Configuration

- API key: ALBERT_API_KEY
- Fichier projet optionnel: .albert-code.toml
- Exemple: .albert-code.toml.example

Section memoire dans `.albert-code.toml`:

```toml
[memory]
enabled = true
auto_save = true
auto_recall = true
recall_top_k = 3
recall_max_tokens = 800
palace_path = "~/.albert-code/palace"
```

Les options CLI surchargent la configuration projet.

## Qualite et tests

```bash
pytest -q
ruff check .
```

## Licence

MIT. Voir LICENSE.
