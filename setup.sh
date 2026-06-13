#!/bin/bash
set -e

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   BookLeaf Cover Checker — Setup Script      ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── Detect OS ─────────────────────────────────────────────────────────────────
OS="$(uname -s)"

if [[ "$OS" == "Linux" ]]; then
  echo "▶ Installing system dependencies (Tesseract OCR + Poppler)..."
  sudo apt-get update -qq
  sudo apt-get install -y tesseract-ocr poppler-utils
  echo "  ✅ Tesseract and Poppler installed"

elif [[ "$OS" == "Darwin" ]]; then
  echo "▶ macOS detected. Installing via Homebrew..."
  if ! command -v brew &>/dev/null; then
    echo "  Homebrew not found. Install it from https://brew.sh then re-run this script."
    exit 1
  fi
  brew install tesseract poppler
  echo "  ✅ Tesseract and Poppler installed via Homebrew"

else
  echo "  ⚠️  Windows detected (or unknown OS)."
  echo "  Please install manually:"
  echo "    1. Tesseract: https://github.com/UB-Mannheim/tesseract/wiki"
  echo "       Install to: C:\\Program Files\\Tesseract-OCR\\"
  echo "    2. Poppler:    https://github.com/oschwartz10612/poppler-windows/releases"
  echo "       Extract and add to PATH."
  echo ""
fi

# ── Python packages ────────────────────────────────────────────────────────────
echo "▶ Installing Python packages..."
pip install -r requirements.txt
echo "  ✅ Python packages installed"

# ── Create folders ─────────────────────────────────────────────────────────────
echo "▶ Creating required directories..."
mkdir -p static/annotations test_covers uploads_tmp
echo "  ✅ Directories created"

# ── Copy .env template if needed ──────────────────────────────────────────────
if [[ ! -f ".env" ]]; then
  cp .env.example .env
  echo "  ✅ .env file created from template"
else
  echo "  ℹ️  .env already exists — skipping"
fi

# ── Done ───────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║              ✅ Setup complete!               ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo ""
echo "  1. Edit .env and fill in your API keys:"
echo "       nano .env"
echo ""
echo "  2. Add credentials.json (Google Drive service account key)"
echo "       See README.md → 'How to get API keys' for instructions"
echo ""
echo "  3. Start the app:"
echo "       python app.py"
echo ""
echo "  4. Open in your browser:"
echo "       http://localhost:5000"
echo ""
