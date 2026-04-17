#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# setup.sh — One-shot VPS setup for Ubuntu 22.04 LTS
#
# What it does:
#   1. Updates the system
#   2. Installs Python 3.11, pip, git, ffmpeg, MongoDB, Redis
#   3. Creates a Python virtual environment
#   4. Installs all Python dependencies
#   5. Copies .env.example → .env and reminds you to fill it in
#   6. Creates a systemd service so the bot auto-starts on reboot
#
# Usage (run as root or with sudo):
#   chmod +x setup.sh && sudo ./setup.sh
# ══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_DIR/.venv"
SERVICE_NAME="musicbot"
SERVICE_USER="${SUDO_USER:-$USER}"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Telegram Music Bot — VPS Setup         ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. System update ─────────────────────────────────────────────────────────
echo "[1/7] Updating system packages…"
apt-get update -qq
apt-get upgrade -y -qq

# ── 2. System dependencies ───────────────────────────────────────────────────
echo "[2/7] Installing system dependencies…"
apt-get install -y -qq \
    python3.11 python3.11-venv python3.11-dev \
    python3-pip \
    ffmpeg \
    git \
    curl \
    build-essential \
    libssl-dev \
    libffi-dev \
    libpng-dev \
    libjpeg-dev \
    libfreetype6-dev

# ── 3. MongoDB ───────────────────────────────────────────────────────────────
echo "[3/7] Installing MongoDB 7.0…"
if ! command -v mongod &>/dev/null; then
    curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc \
        | gpg --dearmor -o /usr/share/keyrings/mongodb-server-7.0.gpg
    echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] \
        https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" \
        > /etc/apt/sources.list.d/mongodb-org-7.0.list
    apt-get update -qq
    apt-get install -y -qq mongodb-org
fi
systemctl enable --now mongod
echo "    MongoDB status: $(systemctl is-active mongod)"

# ── 4. Redis ─────────────────────────────────────────────────────────────────
echo "[4/7] Installing Redis…"
apt-get install -y -qq redis-server
systemctl enable --now redis-server
echo "    Redis status: $(systemctl is-active redis-server)"

# ── 5. Python virtual environment ────────────────────────────────────────────
echo "[5/7] Creating Python virtual environment…"
python3.11 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip wheel -q
"$VENV_DIR/bin/pip" install -r "$REPO_DIR/requirements.txt" -q
echo "    Virtual env: $VENV_DIR"

# ── 6. .env setup ────────────────────────────────────────────────────────────
echo "[6/7] Setting up .env…"
if [ ! -f "$REPO_DIR/.env" ]; then
    cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
    echo "    ⚠️  .env created. Please edit it now:"
    echo "    nano $REPO_DIR/.env"
else
    echo "    .env already exists — skipping."
fi

# Create cache and log directories
mkdir -p "$REPO_DIR/cache/thumbs" "$REPO_DIR/logs"
chown -R "$SERVICE_USER:$SERVICE_USER" "$REPO_DIR/cache" "$REPO_DIR/logs"

# ── 7. systemd service ───────────────────────────────────────────────────────
echo "[7/7] Installing systemd service…"

cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Telegram Voice Chat Music Bot
After=network.target mongod.service redis-server.service
Requires=mongod.service redis-server.service

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${REPO_DIR}
Environment=PATH=${VENV_DIR}/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=${VENV_DIR}/bin/python -m bot.main
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Setup complete!                                     ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Next steps:                                         ║"
echo "║                                                      ║"
echo "║  1. Edit your .env file:                             ║"
echo "║     nano ${REPO_DIR}/.env"
echo "║                                                      ║"
echo "║  2. Generate a Pyrogram session string:              ║"
echo "║     ${VENV_DIR}/bin/python generate_session.py"
echo "║                                                      ║"
echo "║  3. Start the bot:                                   ║"
echo "║     systemctl start ${SERVICE_NAME}                  ║"
echo "║                                                      ║"
echo "║  4. Check logs:                                      ║"
echo "║     journalctl -u ${SERVICE_NAME} -f                 ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
