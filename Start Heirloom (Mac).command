#!/bin/bash
# Double-click to start Heirloom on a Mac.
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null; then
  echo "Heirloom needs Python 3. Get it free from https://www.python.org/downloads/"
  read -p "Press Enter to close."
  exit 1
fi
python3 start_heirloom.py
