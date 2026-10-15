"""Cache helpers for the incremental steps (cut pieces, the voice, words, the matte).

Every cache key names the source file by its real path, size and modification time, so a re-shot take saved under
the old name never reuses old work. Keys are sha1 hashes of a JSON dump of everything that shapes the output (the
exact ffmpeg arguments, the model and its settings), plus a version string per cache, bumped when the code that makes
the output changes.
"""
import hashlib
import json
import os
import subprocess
from functools import lru_cache


def file_id(path):
    """what identifies a file for a cache: its real path, size and modification time in nanoseconds"""
    p = os.path.realpath(os.path.expanduser(path))
    st = os.stat(p)
    return {"path": p, "size": st.st_size, "mtime_ns": st.st_mtime_ns}


def take_id(path, head=1 << 20):
    """the name of one take's cache: sha1 of its first 1 MB plus its size and modification time"""
    fid = file_id(path)
    h = hashlib.sha1()
    with open(fid["path"], "rb") as fh:
        h.update(fh.read(head))
    h.update(f"|{fid['size']}|{fid['mtime_ns']}".encode())
    return h.hexdigest()


def key(*parts):
    """a stable sha1 of the parts (anything json can write); changes when any part changes"""
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


@lru_cache(maxsize=None)
def ffmpeg_version():
    """the first line of `ffmpeg -version`: an upgraded ffmpeg (a new x264, a new resampler) makes new pieces"""
    out = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout
    return out.splitlines()[0] if out else "unknown"


def legacy_trusted(cache_path, src_path):
    """a cache written before keys carried the source's identity is trusted only if it was written after the source
    last changed (a re-shot take saved under the old name is newer than the old cache)"""
    try:
        return os.path.getmtime(cache_path) >= os.path.getmtime(src_path)
    except OSError:
        return False


def read_json(path, default=None):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_json(path, data, indent=1):
    """write next to the target, then rename: a crash never leaves half a cache file"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=indent)
    os.replace(tmp, path)


def same_file(path, rec):
    """is the file at path still the one recorded in rec ({size, mtime_ns})?"""
    try:
        st = os.stat(path)
    except OSError:
        return False
    return bool(rec) and st.st_size == rec.get("size") and st.st_mtime_ns == rec.get("mtime_ns")


def stamp(path, cache_key):
    """the record same_file() checks: the key that made the file, its size and modification time"""
    st = os.stat(path)
    return {"key": cache_key, "size": st.st_size, "mtime_ns": st.st_mtime_ns}


def lru_evict(entries, keep, budget):
    """which cache files to remove: entries = [(path, size, last_used)], keep = paths in use now (never removed),
    budget = bytes the unused ones may take. Keeps the most recently used unused files that fit, returns the rest."""
    spare = sorted((e for e in entries if e[0] not in keep), key=lambda e: e[2], reverse=True)
    out, used = [], 0
    for path, size, _ in spare:
        if used + size <= budget:
            used += size
        else:
            out.append(path)
    return out
