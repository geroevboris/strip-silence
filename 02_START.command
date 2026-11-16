#!/bin/bash
HERE="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$HOME/Library/Application Support/ClearSilence/ui-venv/bin/python3"
if [ ! -x "$PYTHON" ]; then
  echo 'Не установлены компоненты отдельного окна. Один раз запусти 03_SETUP_UI.command.'
  read -r -p 'Enter для закрытия… ' _
  exit 1
fi
cd "$HERE" || exit 1
"$PYTHON" "$HERE/app.py"
status=$?
if [ "$status" -ne 0 ]; then
  echo "Clear Silence завершился с ошибкой: $status"
  read -r -p 'Enter для закрытия… ' _
fi
exit "$status"
