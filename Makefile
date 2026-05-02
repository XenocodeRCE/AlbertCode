# Makefile — Albert Code
# Cibles principales : lint, format, test, install, release

PYTHON   ?= python
PIP      ?= pip
PACKAGE  := albert_code
SRC      := mvp.py

.PHONY: help install install-dev lint format test clean build release

help:          ## Afficher cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ── Dépendances ────────────────────────────────────────────────
install:       ## Installer le package en mode éditable (pip install -e .)
	$(PIP) install -e .

install-dev:   ## Installer avec les dépendances de développement
	$(PIP) install -e ".[dev]"

# ── Qualité du code ────────────────────────────────────────────
lint:          ## Vérifier le style avec ruff
	ruff check $(SRC)

format:        ## Reformater le code avec ruff
	ruff format $(SRC)
	ruff check --fix $(SRC)

# ── Tests ──────────────────────────────────────────────────────
test:          ## Lancer les tests pytest
	pytest -v

# ── Nettoyage ──────────────────────────────────────────────────
clean:         ## Supprimer les artefacts de build
	rm -rf dist/ build/ *.egg-info __pycache__ .pytest_cache .ruff_cache

# ── Publication ────────────────────────────────────────────────
build:         ## Construire les distributions (sdist + wheel)
	$(PYTHON) -m build

release: clean build ## Publier sur PyPI via twine (nécessite TWINE_PASSWORD)
	$(PYTHON) -m twine upload dist/*
