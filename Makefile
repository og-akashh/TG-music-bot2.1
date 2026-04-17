# ══════════════════════════════════════════════════════════════════════════════
# Makefile — Developer convenience commands
# Usage: make <target>
# ══════════════════════════════════════════════════════════════════════════════

PYTHON   := python3
VENV     := .venv
PIP      := $(VENV)/bin/pip
PYBIN    := $(VENV)/bin/python
BOT_MOD  := bot.main

.PHONY: help venv install run session docker-build docker-up docker-down \
        docker-logs lint format clean

# ── Default target ────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Telegram Music Bot — Make Targets"
	@echo "  ─────────────────────────────────"
	@echo "  make venv          Create Python virtual environment"
	@echo "  make install       Install Python dependencies"
	@echo "  make run           Run the bot (local)"
	@echo "  make session       Generate Pyrogram string session"
	@echo "  make docker-build  Build Docker image"
	@echo "  make docker-up     Start all Docker services"
	@echo "  make docker-down   Stop all Docker services"
	@echo "  make docker-logs   Follow Docker bot logs"
	@echo "  make lint          Run ruff linter"
	@echo "  make format        Auto-format with black"
	@echo "  make clean         Remove cache, logs, __pycache__"
	@echo ""

# ── Setup ─────────────────────────────────────────────────────────────────────
venv:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip wheel

install: venv
	$(PIP) install -r requirements.txt

# ── Run ───────────────────────────────────────────────────────────────────────
run:
	@if [ ! -f .env ]; then \
		echo "ERROR: .env not found. Copy .env.example → .env and fill it in."; \
		exit 1; \
	fi
	$(PYBIN) -m $(BOT_MOD)

session:
	$(PYBIN) generate_session.py

# ── Docker ────────────────────────────────────────────────────────────────────
docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f bot

# ── Code quality ──────────────────────────────────────────────────────────────
lint:
	@$(VENV)/bin/ruff check bot/ dashboard/ || true

format:
	@$(VENV)/bin/black bot/ dashboard/ || true

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf cache/thumbs/*.png logs/*.log
	@echo "Cleaned."
