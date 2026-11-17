"""Install/update the Ableton MIDI Remote Script on the user's first app launch.

The PKG itself only installs Clear Silence.app in /Applications. Keeping this
step outside the privileged Installer process avoids macOS privacy/TCC errors
when accessing an ordinary user's protected ~/Music directory.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import time
import uuid


class BridgeInstallError(RuntimeError):
    pass


def _same_file_bytes(left: Path, right: Path) -> bool:
    def sha(path: Path) -> bytes:
        h = hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda: f.read(1024 * 1024), b''):
                h.update(block)
        return h.digest()
    return sha(left) == sha(right)


def install_bridge(source: Path, user_home: Path) -> bool:
    """Install into user library. Return True only when an update was needed.

    Original bridge remains intact until a complete replacement has been staged.
    On any rename failure we attempt to restore it. All operations are scoped
    to ClearSilenceBridge, not the rest of the User Library or Ableton.
    """
    source = Path(source)
    user_home = Path(user_home)
    if not source.is_file():
        raise BridgeInstallError(f'В приложении не найден скрипт ClearSilenceBridge: {source}')
    root = user_home / 'Music' / 'Ableton' / 'User Library' / 'Remote Scripts'
    target = root / 'ClearSilenceBridge'
    backup_dir = root.parent / '.ClearSilence Backups'
    try:
        root.mkdir(parents=True, exist_ok=True)
        if not root.is_dir():
            raise BridgeInstallError(f'Недоступна папка Remote Scripts: {root}')
        current = target / '__init__.py'
        if current.is_file() and _same_file_bytes(current, source):
            return False
        backup_dir.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix='.ClearSilenceBridge.stage.', dir=root))
        try:
            destination = stage / '__init__.py'
            shutil.copyfile(source, destination)
            destination.chmod(0o644)
            # Confirm the source bytes were copied before touching the original.
            if not _same_file_bytes(source, destination):
                raise BridgeInstallError('Не удалось проверить копию Remote Script')
            backup = None
            if target.exists() or target.is_symlink():
                backup = backup_dir / ('ClearSilenceBridge.backup.%s-%s' % (
                    time.strftime('%Y%m%d-%H%M%S'), uuid.uuid4().hex[:8]))
                target.rename(backup)
            try:
                stage.rename(target)
            except Exception:
                if backup is not None:
                    backup.rename(target)
                raise
            return True
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    except (OSError, PermissionError) as exc:
        raise BridgeInstallError(
            f'Не удалось установить Remote Script в {root}: {exc}. '
            'Разреши Clear Silence доступ к папке «Музыка» в настройках macOS.'
        ) from exc
