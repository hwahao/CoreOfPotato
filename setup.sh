#!/usr/bin/env bash
set -e

echo "Setting up Core of Potato v1.0.0..."

# Check if python3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but not found. Please install Python 3.9+."
    exit 1
fi

# Optional: set up a virtual environment if not already in one
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
fi

echo "Installing requirements..."
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt

echo "Installing Playwright browsers..."
playwright install chromium

if [ ! -f "config.json" ]; then
    echo "Copying config.example.json to config.json..."
    cp config.example.json config.json
fi

echo "Configuring CloakBrowser..."
python3 setup_cloak.py

echo "Setup complete! You can now run Core of Potato."
