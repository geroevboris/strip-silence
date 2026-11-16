#!/bin/bash
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
if ! command -v python3 >/dev/null; then
  echo "Требуется установленный Python 3 (для интерфейса и WAV-анализа)."
  read -p "Нажми Enter..."
  exit 1
fi
python3 "$HERE/app.py"
status=$?
echo "Приложение завершилось с кодом $status"
read -p "Нажми Enter..."
