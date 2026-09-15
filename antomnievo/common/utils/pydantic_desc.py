from __future__ import annotations

import types
from datetime import datetime
from typing import get_args, get_origin

from pydantic import BaseModel

_TYPE_DISPLAY: dict[type, str] = {
    str: "str",
    int: "int",
    float: "float",
    bool: "bool",
    datetime: "datetime",
    list: "list",
    types.NoneType: "null",
}


def display_type(ann) -> str:
    if ann in _TYPE_DISPLAY:
        return _TYPE_DISPLAY[ann]
    origin = get_origin(ann)
    if origin is list:
        args = get_args(ann)
        if args:
            inner = args[0].__name__ if hasattr(args[0], "__name__") else str(args[0])
            return f"list[{inner}]"
        return "list"
    # Union / Optional (e.g. Optional[str] -> str or null)
    if origin is types.UnionType:
        args = get_args(ann)
        parts = [display_type(a) for a in args if a is not type(None)]
        return " or ".join(parts) if parts else "null"
    # typing.Union (Python 3.9 compat)
    try:
        import typing
        if origin is typing.Union:
            args = get_args(ann)
            parts = [display_type(a) for a in args if a is not type(None)]
            return " or ".join(parts) if parts else "null"
    except AttributeError:
        pass
    if hasattr(ann, "__name__"):
        return ann.__name__
    return str(ann)


def is_pydantic_model(cls) -> bool:
    return isinstance(cls, type) and issubclass(cls, BaseModel)


def sub_model_fields(model_cls: type[BaseModel], indent: str = "  ", _visited: frozenset[type] | None = None) -> str:
    if _visited is None:
        _visited = frozenset()
    _visited = _visited | {model_cls}

    lines = []
    for fname, finfo in model_cls.model_fields.items():
        ann = finfo.annotation
        type_str = display_type(ann)
        desc = finfo.description or ""
        lines.append(f"{indent}- **{fname}** ({type_str}): {desc}" if desc else f"{indent}- **{fname}** ({type_str})")

        sub_cls = None
        origin = get_origin(ann)
        if origin is list:
            args = get_args(ann)
            if args and is_pydantic_model(args[0]):
                sub_cls = args[0]
        elif is_pydantic_model(ann):
            sub_cls = ann
        if sub_cls and sub_cls not in _visited:
            lines.append(sub_model_fields(sub_cls, indent=indent + "  ", _visited=_visited))

    return "\n".join(lines)


def model_fields_description(model_cls: type[BaseModel]) -> str:
    visited: frozenset[type] = frozenset({model_cls})
    lines = []
    for name, info in model_cls.model_fields.items():
        ann = info.annotation
        type_str = display_type(ann)
        desc = info.description or ""
        lines.append(f"- **{name}** ({type_str}): {desc}" if desc else f"- **{name}** ({type_str})")

        sub_cls = None
        origin = get_origin(ann)
        if origin is list:
            args = get_args(ann)
            if args and is_pydantic_model(args[0]):
                sub_cls = args[0]
        elif is_pydantic_model(ann):
            sub_cls = ann
        if sub_cls and sub_cls not in visited:
            lines.append(sub_model_fields(sub_cls, _visited=visited))

    return "\n".join(lines)
