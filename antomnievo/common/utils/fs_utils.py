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
