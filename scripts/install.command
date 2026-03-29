#!/bin/bash
# install.command — double-click this file to install the Sinhalese dictionaries.
# It copies the dictionary bundles into ~/Library/Dictionaries/ and opens
# Dictionary.app so you can enable them in Preferences.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")"; pwd)"
INSTALL_DIR="$HOME/Library/Dictionaries"
DICTS=("english-sinhala.dictionary" "sinhala-english.dictionary")

echo "Installing Sinhalese dictionaries..."
mkdir -p "$INSTALL_DIR"

for dict in "${DICTS[@]}"; do
    src="$SCRIPT_DIR/$dict"
    if [ ! -d "$src" ]; then
        echo "Error: $dict not found next to this script." >&2
        exit 1
    fi
    rm -rf "$INSTALL_DIR/$dict"
    cp -r "$src" "$INSTALL_DIR/$dict"
    echo "  Installed $dict"
done

echo ""
echo "Done! Opening Dictionary preferences..."
echo "Enable 'english-sinhala' and 'sinhala-english' in the list."
echo ""

open -a Dictionary
osascript -e 'tell application "Dictionary" to activate'
osascript -e 'tell application "System Events" to keystroke "," using command down' 2>/dev/null || true
