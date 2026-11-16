#!/bin/bash
# Installs only UI dependencies in a PRIVATE venv outside Ableton and system Python.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
VENV="$HOME/Library/Application Support/ClearSilence/ui-venv"
PYTHON="$(command -v python3 || true)"
if [ -z "$PYTHON" ]; then echo 'Ошибка: нужен Python 3.10+.'; exit 1; fi
"$PYTHON" - <<'PY'
import sys
if sys.version_info < (3,10):
    raise SystemExit('Нужен Python 3.10+ для встроенного окна. Найден %s.' % sys.version.split()[0])
PY
printf 'Clear Silence v0.3 — установка окна приложения (pywebview)\n'
printf 'Python: %s\nСреда: %s\n' "$PYTHON" "$VENV"
mkdir -p "$(dirname "$VENV")"
"$PYTHON" -m venv "$VENV"
"$VENV/bin/python3" -m pip install 'pywebview>=5,<7'
"$VENV/bin/python3" - <<'PY'
import webview
print('Окно готово: pywebview установлен в отдельную среду.')
PY
printf '\nГотово. Открой Clear Silence.app (или 02_START.command).\n