#!/bin/zsh
cd "$(dirname "$0")" || exit 1
python3 -m http.server 4173 -d web
