#!/bin/bash
set -e

# ── 1. Create .env from example if it doesn't exist ──────────────────────────
if [ ! -f /workspace/.env ]; then
  cp /workspace/.env.example /workspace/.env
  echo "✔ Created .env from .env.example"
  echo "  ⚠  Remember to set OPENAI_API_KEY in /workspace/.env before starting the app."
else
  echo "✔ .env already exists — skipping copy."
fi

# ── 2. Auto-source .env in every new terminal session ────────────────────────
if ! grep -q 'source /workspace/.env' ~/.bashrc 2>/dev/null; then
  echo '' >> ~/.bashrc
  echo '# Load project .env vars into the shell' >> ~/.bashrc
  echo 'set -a; [ -f /workspace/.env ] && . /workspace/.env; set +a' >> ~/.bashrc
  echo "✔ Added .env auto-load to ~/.bashrc"
fi

# ── 3. Create virtual environment and install Python dependencies ────────────
VENV=/workspace/.venv

if [ ! -d "$VENV" ]; then
  echo "Creating Python virtual environment at $VENV ..."
  python -m venv "$VENV"
  echo "✔ Virtual environment created."
else
  echo "✔ Virtual environment already exists — skipping creation."
fi

echo "Installing Python dependencies into venv..."
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r /workspace/backend/requirements.txt
echo "✔ Python dependencies installed."

# ── 4. Auto-activate venv in every new terminal session ──────────────────────
if ! grep -q 'source /workspace/.venv/bin/activate' ~/.bashrc 2>/dev/null; then
  echo '' >> ~/.bashrc
  echo '# Auto-activate project venv' >> ~/.bashrc
  echo 'source /workspace/.venv/bin/activate' >> ~/.bashrc
  echo "✔ Added venv auto-activation to ~/.bashrc"
fi

# Activate now for the current script session
source "$VENV/bin/activate"

echo ""
echo "Setup complete! Open a new terminal — the venv will activate automatically."
