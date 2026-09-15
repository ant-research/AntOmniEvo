from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FileSchema(BaseModel):
    type: Literal["file"] = "file"
    name: str
    description: str


class FolderSchema(BaseModel):
    type: Literal["folder"] = "folder"
    name: str
    description: str
    files: list[FileSchema | FolderSchema] = Field(default_factory=list)

    def tree_lines(self, indent: str = "") -> list[str]:
        lines = [f"{self.name}/"]
        for i, f in enumerate(self.files):
            is_last = i == len(self.files) - 1
            connector = "└── " if is_last else "├── "
            continuation = "    " if is_last else "│   "
            if isinstance(f, FolderSchema):
                sub_lines = f.tree_lines(indent=indent + continuation)
                lines.append(f"{indent}{connector}{sub_lines[0]}")
                lines.extend(sub_lines[1:])
            else:
                lines.append(f"{indent}{connector}{f.name}")
        return lines


SpecSchema = FileSchema | FolderSchema


def render_spec_schema(schema: SpecSchema) -> str:
    if isinstance(schema, FileSchema):
        return f"# {schema.name}\n\n{schema.description}"

    parts = [f"# {schema.name}/\n\n{schema.description}"]

    tree_lines = schema.tree_lines()
    parts.append("Spec directory structure:\n```\n" + "\n".join(tree_lines) + "\n```")

    desc_lines: list[str] = []
    _collect_descriptions(schema.files, desc_lines, depth=0)
    parts.append("\n".join(desc_lines))

    return "\n\n".join(parts)


def _collect_descriptions(
    entries: list[FileSchema | FolderSchema],
    lines: list[str],
    depth: int,
) -> None:
    for entry in entries:
        name_suffix = "/" if isinstance(entry, FolderSchema) else ""
        heading = "#" * (depth + 2)
        first_line, *rest = entry.description.split("\n", 1)
        lines.append(f"{heading} {entry.name}{name_suffix}")
        lines.append("")
        lines.append(first_line)
        if rest:
            lines.append("")
            lines.append(rest[0].strip())
        lines.append("")
        if isinstance(entry, FolderSchema) and entry.files:
            _collect_descriptions(entry.files, lines, depth + 1)
