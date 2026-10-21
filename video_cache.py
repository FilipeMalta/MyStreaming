"""Completed video files only. Partial downloads are never served to the player."""
import hashlib
import os
import re
import shutil
from pathlib import Path
from core import DATA

CACHE_ROOT = DATA / 'video-cache'
MAX_BYTES = int(os.environ.get('TRILHA_CACHE_MB', '2048')) * 1024 * 1024


def cache_path(lesson):
    identity = f"{lesson['id']}:{lesson['size']}:{lesson.get('file_id') or lesson['filename']}"
    digest = hashlib.sha256(identity.encode()).hexdigest()
    return CACHE_ROOT / (digest + '.video')


def cached_video(lesson):
    path = cache_path(lesson)
    try:
        if path.is_file() and lesson['size'] > 0 and path.stat().st_size == lesson['size']:
            return path
    except OSError:
        pass
    return None


def reserve_space(size):
    if size <= 0 or size > MAX_BYTES:
        raise ValueError('Esta aula excede o limite do cache local (2 GB por padrão). Use o streaming ou ajuste TRILHA_CACHE_MB.')
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    files = [p for p in CACHE_ROOT.glob('*.video') if re.fullmatch(r'[0-9a-f]{64}\.video', p.name)]
    used = sum(p.stat().st_size for p in files)
    for path in sorted(files, key=lambda p: p.stat().st_mtime):
        if used + size <= MAX_BYTES:
            break
        try:
            length = path.stat().st_size
            path.unlink()
            used -= length
        except OSError:
            continue  # Windows may keep an actively playing file open.
    if used + size > MAX_BYTES:
        raise OSError('O cache está em uso. Feche outras aulas e tente novamente.')
    if shutil.disk_usage(CACHE_ROOT).free < size + 100 * 1024 * 1024:
        raise OSError('Não há espaço livre suficiente para preparar esta aula.')
