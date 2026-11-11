import logging

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def setup_logging(level=logging.INFO):
    """Configure the root logger so all `logging.getLogger(__name__)` inherit uniformly."""
    root = logging.getLogger()
    if root.handlers:
        return root

    # Root at WARNING — suppress noisy third-party libs by default
    root.setLevel(logging.WARNING)

    formatter = logging.Formatter(LOG_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    # Only the antomnievo namespace logs at the requested level. Script entry
    # points (antomnievo/example/.../*.py) run with __name__ == "__main__" when
    # launched via `python file.py` / VS Code `program:${file}`, which is NOT
    # under antomnievo.* — so their module-level `logging.getLogger(__name__)`
    # would otherwise inherit root's WARNING and silently drop their own logs.
    # Attach the same handler/level to __main__ so script logs show too.
    for name in ("antomnievo", "__main__"):
        lg = logging.getLogger(name)
        lg.setLevel(level)
        lg.addHandler(console_handler)

    return root


logger = logging.getLogger(__name__)
