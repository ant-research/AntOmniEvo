import os


def get_latest_mtime(dir_path: str) -> float:
    """Return the most recent modification time of any file under dir_path."""
    latest = 0.0
    for root, _, files in os.walk(dir_path):
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                mt = os.path.getmtime(fpath)
                if mt > latest:
                    latest = mt
            except OSError:
                continue
    return latest


def file_written_since(path: str, since_ts: float, eps: float = 1e-3) -> bool:
    """True if `path` exists and was modified at or after `since_ts` (epoch seconds).

    Used to verify an agent actually (re)wrote its output file during its run —
    a pre-existing stale file does not count. `eps` tolerates coarse filesystem
    timestamp granularity.
    """
    try:
        return os.path.getmtime(path) >= since_ts - eps
    except OSError:
        return False
