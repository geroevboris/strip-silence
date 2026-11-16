#!/bin/bash
# Clear Silence v0.2 -- install only the Remote Script; do not modify Live or its projects.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$HERE/ClearSilenceBridge/__init__.py"
LIBRARY="${CS_USER_LIBRARY:-$HOME/Music/Ableton/User Library}"
ROOT="$LIBRARY/Remote Scripts"
TARGET="$ROOT/ClearSilenceBridge"

on_exit() {
  code="$?"
  if [ "$code" -ne 0 ]; then
    printf '\nУстановка НЕ завершена. Ничего не меняй в Ableton до исправления доступа.\n'
  fi
  if [ -t 0 ]; then
    printf '\nНажми Enter для закрытия окна... '
    read -r _answer || true
  fi
}
trap on_exit EXIT

show_access_help() {
  printf '\nНЕТ ПРАВ НА ЗАПИСЬ в:\n%s\n\n' "$ROOT"
  printf 'Это ошибка доступа macOS, а не ошибка Ableton.\n'
  printf '1. Проверь в macOS: Системные настройки -> Конфиденциальность и безопасность\n'
  printf '   -> Файлы и папки -> Terminal -> Музыка (разрешить доступ, если есть пункт).\n'
  printf '2. В Finder открой эту папку, нажми Cmd+I и проверь\n'
  printf '   «Общий доступ и права доступа»: у твоей учётной записи должно быть «Чтение и запись».\n'
  printf '3. Не запускай этот установщик через sudo.\n'
  printf '4. Если User Library перенесена в другое место, укажи её путь так:\n'
  printf '   CS_USER_LIBRARY="/путь/к/User Library" ./01_INSTALL.command\n'
  printf '\nПрава найденных папок (эти строки можно прислать для диагностики):\n'
  ls -ldeO "$HOME/Music" "$LIBRARY" "$ROOT" 2>&1 || true
  printf '\n'
}

printf 'Clear Silence — установка Remote Script v0.2\n'
printf 'Источник: %s\n' "$SOURCE"
printf 'Библиотека: %s\n' "$LIBRARY"
if [ ! -f "$SOURCE" ]; then
  echo 'Ошибка: файл ClearSilenceBridge/__init__.py не найден в архиве.'
  exit 1
fi

if ! mkdir -p "$ROOT"; then
  show_access_help
  exit 1
fi

# Actual write test: mkdir -p can succeed even when the directory is read-only.
TESTFILE="$ROOT/.clear_silence_write_test_$$"
if ! (umask 077; : > "$TESTFILE") 2>/dev/null; then
  show_access_help
  exit 1
fi
rm -f "$TESTFILE" || true

STAGING="$(mktemp -d "$ROOT/.ClearSilenceBridge.new.XXXXXX")" || {
  show_access_help
  exit 1
}
# Install file contents only; no potentially blocked extended attributes from Downloads.
if ! install -m 644 "$SOURCE" "$STAGING/__init__.py"; then
  rm -rf "$STAGING"
  echo 'Не удалось скопировать скрипт во временную папку.'
  exit 1
fi

BACKUP_ROOT="$LIBRARY/.ClearSilence Backups"
if ! mkdir -p "$BACKUP_ROOT"; then
  echo 'Не удалось создать папку для резервных копий. Установка отменена.'
  rm -rf "$STAGING"
  exit 1
fi
# Older installers left backups in Remote Scripts, where Live could mistake
# them for additional Control Surfaces. Move only our own old backups away.
for OLD in "$ROOT"/ClearSilenceBridge.backup.*; do
  if [ -d "$OLD" ]; then
    dest="$BACKUP_ROOT/$(basename "$OLD")"
    [ -e "$dest" ] && dest="$dest-$$"
    mv "$OLD" "$dest" 2>/dev/null || true
  fi
done
BACKUP=""
if [ -e "$TARGET" ] || [ -L "$TARGET" ]; then
  BACKUP="$BACKUP_ROOT/ClearSilenceBridge.backup.$(date +%Y%m%d-%H%M%S)-$$"
  if ! mv "$TARGET" "$BACKUP"; then
    rm -rf "$STAGING"
    echo 'Не удалось переименовать прежний ClearSilenceBridge (не удалял его).'
    show_access_help
    exit 1
  fi
fi
if ! mv "$STAGING" "$TARGET"; then
  echo 'Не удалось установить скрипт. Восстанавливаю прежнюю версию.'
  [ -n "$BACKUP" ] && mv "$BACKUP" "$TARGET" || true
  [ -d "$STAGING" ] && rm -rf "$STAGING"
  show_access_help
  exit 1
fi

printf '\nУстановлено: %s\n' "$TARGET"
[ -n "$BACKUP" ] && printf 'Старая версия сохранена: %s\n' "$BACKUP"
printf '1. Полностью закрой и снова открой Live.\n'
printf '2. Settings -> Link, Tempo & MIDI -> Control Surface: ClearSilenceBridge.\n'
printf '3. MIDI Input / Output: None.\n'
printf '4. После этого открой Clear Silence.app (или 02_START.command).\n'
