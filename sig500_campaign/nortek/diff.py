from __future__ import annotations

from .models import FieldChange


def format_diff(changes: tuple[FieldChange, ...]) -> str:
    changed = [item for item in changes if item.changed]
    unchanged = [item for item in changes if not item.changed]
    lines = ["Nortek field-level configuration diff", "======================================", "", "Changed:"]
    lines.extend(f"{item.path:<24} {item.original} -> {item.requested}" for item in changed)
    lines.extend(["", "Unchanged:"])
    lines.extend(f"{item.path:<24} {item.original}" for item in unchanged)
    return "\n".join(lines) + "\n"
