from __future__ import annotations

import dataclasses
import enum

_SECRET_KEYS = {"api_key", "secret", "token", "password"}


def _mask_secrets(d: dict) -> dict:
    for k, v in list(d.items()):
        if any(s in k for s in _SECRET_KEYS):
            d[k] = "***" if v else None
        elif isinstance(v, dict):
            _mask_secrets(v)
    return d


def extract_params(obj: object) -> dict:
    """Auto-extract serializable init parameters from an object.

    Handles plain attributes, dataclass fields, and nested objects.
    Masks values whose key matches a known secret pattern.
    """
    attrs = {}
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        attrs = dataclasses.asdict(obj)
    else:
        for k, v in vars(obj).items():
            if k.startswith("_"):
                if dataclasses.is_dataclass(v) and not isinstance(v, type):
                    attrs[k.lstrip("_")] = dataclasses.asdict(v)
                continue
            if isinstance(v, (str, int, float, bool, type(None), list)):
                attrs[k] = v
            elif isinstance(v, enum.Enum):
                attrs[k] = v.value
            elif dataclasses.is_dataclass(v) and not isinstance(v, type):
                attrs[k] = dataclasses.asdict(v)
    return _mask_secrets(attrs)
