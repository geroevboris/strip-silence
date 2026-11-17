#!/bin/bash
# Clear Silence: build the current main branch locally on an Apple Silicon Mac.
# Does not modify Ableton Live, the user's music files, or any installed app.
set -Eeuo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

BASE_DIR="$HOME/Downloads/ClearSilence-LocalBuild"
STAMP="$(date +%Y%m%d-%H%M%S)"
WORK_DIR="$BASE_DIR/$STAMP"
mkdir -p "$WORK_DIR"
LOG="$WORK_DIR/build.log"
exec > >(tee -a "$LOG") 2>&1

finish() {
  code=$?
  trap - EXIT
  echo
  if [ "$code" -eq 0 ]; then
    echo 'Сборка завершена. Установщик находится в открытой папке.'
  else
    echo 'Ошибка при локальной сборке. Подробности в файле:'
    echo "$LOG"
    echo 'Пришли последние 40 строк из этого файла, если потребуется помощь.'
  fi
  echo
  if [ -r /dev/tty ]; then
    read -r -p 'Нажми Enter, чтобы закрыть это окно… ' _dummy </dev/tty || true
  fi
  exit "$code"
}
trap finish EXIT

echo '=== Clear Silence · локальная сборка Apple Silicon ==='
echo "Отчёт: $LOG"
if [ "$(uname -s)" != 'Darwin' ] || [ "$(uname -m)" != 'arm64' ]; then
  echo 'Ошибка: нужен Mac с Apple Silicon, запущенный не через Rosetta.' >&2
  exit 1
fi

PY=""
for candidate in \
    /opt/homebrew/bin/python3.11 \
    /opt/homebrew/opt/python@3.11/bin/python3.11 \
    /Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11 \
    "$(command -v python3.11 || true)"; do
  if [ -n "$candidate" ] && [ -x "$candidate" ] && \
      "$candidate" -c 'import sys,platform; assert sys.version_info[:2]==(3,11) and platform.machine()=="arm64"' >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done
if [ -z "$PY" ] && command -v brew >/dev/null 2>&1; then
  echo 'Python 3.11 не найден. Устанавливаю через Homebrew…'
  brew install python@3.11
  candidate=/opt/homebrew/opt/python@3.11/bin/python3.11
  if [ -x "$candidate" ] && "$candidate" -c 'import sys,platform; assert sys.version_info[:2]==(3,11) and platform.machine()=="arm64"' >/dev/null 2>&1; then
    PY="$candidate"
  fi
fi
if [ -z "$PY" ]; then
  echo 'Нужен Python 3.11 для Apple Silicon. Установи его с python.org или через Homebrew:' >&2
  echo 'brew install python@3.11' >&2
  exit 1
fi

echo "Python: $PY"
for cmd in curl unzip sips iconutil pkgbuild codesign; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Не найдена системная команда: $cmd" >&2
    exit 1
  fi
done

echo 'Получаю исходники из main…'
ARCHIVE="$WORK_DIR/source.zip"
curl --fail --location --retry 3 --connect-timeout 20 --silent --show-error \
  'https://github.com/geroevboris/strip-silence/archive/refs/heads/main.zip' \
  --output "$ARCHIVE"
unzip -q "$ARCHIVE" -d "$WORK_DIR"
PROJECT="$WORK_DIR/strip-silence-main"
if [ ! -f "$PROJECT/packaging/build_installer.sh" ]; then
  echo 'Архив репозитория не содержит ожидаемый сборочный скрипт.' >&2
  exit 1
fi

echo 'Создаю изолированное окружение…'
"$PY" -m venv "$WORK_DIR/.venv"
VENV_PY="$WORK_DIR/.venv/bin/python3"
"$VENV_PY" -m pip install --upgrade pip
"$VENV_PY" -m pip install 'pyinstaller>=6.10,<7' 'pywebview>=5,<7' 'pyobjc-framework-WebKit>=10,<13'

# package script uses python3; put isolated environment at the front of PATH.
export PATH="$WORK_DIR/.venv/bin:$PATH"
cd "$PROJECT"
echo 'Запускаю тесты и нативную упаковку macOS…'
bash packaging/build_installer.sh

PKG="$(find "$PROJECT/package-output" -maxdepth 1 -type f -name 'Clear_Silence_*_macOS_Apple_Silicon.pkg' -print -quit)"
if [ -z "$PKG" ] || [ ! -s "$PKG" ]; then
  echo 'В package-output нет готового PKG.' >&2
  exit 1
fi

echo "PKG: $PKG"
shasum -a 256 "$PKG"
open -R "$PKG"
