#!/bin/sh
# Avvia la demo di NefroCenter WR (solo dati fittizi) su questo computer e apre il browser.
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then exec python3 avvia_demo.py "$@"; fi
if command -v python >/dev/null 2>&1; then exec python avvia_demo.py "$@"; fi
echo "Serve Python 3: https://www.python.org/downloads/"
read -r _
