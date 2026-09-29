from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

COMMAND_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\b")
ASSIGNMENT_RE = re.compile(
    r"(?P<key>[A-Za-z][A-Za-z0-9_]*)\s*=\s*(?P<value>\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|[^,;\s]+)"
)
KNOWN_COMMANDS = {
    "SETDEFAULT",
    "SETPLAN",
    "SETAVG",
    "SETBURST",
    "SETECHO",
    "SETTMAVG",
    "SAVE",
}


def _typed(raw: str) -> Any:
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    try:
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return raw


@dataclass
class CommandOccurrence:
    name: str
    start: int
    end: int
    text: str
    parameters: dict[str, Any] = field(default_factory=dict)
    raw_parameters: dict[str, str] = field(default_factory=dict)


@dataclass
class DeployDocument:
    text: str
    commands: list[CommandOccurrence]
    newline: str = "\n"

    def command(self, name: str) -> CommandOccurrence:
        matches = [item for item in self.commands if item.name == name.upper()]
        if not matches:
            raise KeyError(f"command {name} not present")
        return matches[-1]

    def get(self, command: str, parameter: str) -> Any:
        occurrence = self.command(command)
        try:
            return occurrence.parameters[parameter.upper()]
        except KeyError as exc:
            raise KeyError(f"{command}.{parameter} not present") from exc

    def relevant_settings(self) -> dict[str, dict[str, Any]]:
        fields = {
            "SETPLAN": ("MIAVG", "AVG", "BURST", "MIBURST", "DIAVG", "DIBURST"),
            "SETAVG": ("AI", "NPING", "NB", "NC", "CS", "BD", "CY"),
            "SETBURST": ("SR", "NS", "NB", "CH", "ECHO"),
            "SETECHO": ("NC", "BINSIZE", "BD", "FREQ1", "XMIT1", "PL1", "PULSECOMP1"),
            "SETTMAVG": ("EN", "AVG"),
        }
        result: dict[str, dict[str, Any]] = {}
        for command, names in fields.items():
            try:
                item = self.command(command)
            except KeyError:
                continue
            result[command] = {name: item.parameters[name] for name in names if name in item.parameters}
        return result

    @property
    def metadata_lines(self) -> list[str]:
        return [line for line in self.text.splitlines(keepends=True) if line.lstrip().startswith("#$")]

    @property
    def instrument_type(self) -> str | None:
        match = re.search(r"(?im)^#\$.*?(?:instrument|instrumenttype|type)\s*[:=]\s*([^\r\n,]+)", self.text)
        return match.group(1).strip().strip('"') if match else None

    @property
    def orientation(self) -> str | None:
        match = re.search(r"(?im)(?:orientation|orient)\s*[:=]\s*\"?([A-Za-z-]+)", self.text)
        return match.group(1) if match else None


def parse_deploy(source: str | bytes | Path) -> DeployDocument:
    if isinstance(source, Path):
        raw = source.read_bytes()
        text = raw.decode("utf-8-sig")
    elif isinstance(source, bytes):
        text = source.decode("utf-8-sig")
    else:
        text = source
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    offsets: list[int] = []
    position = 0
    for line in lines:
        offsets.append(position)
        position += len(line)
    starts: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if line.lstrip().startswith(("#", ";")):
            continue
        match = COMMAND_RE.match(line)
        remainder = line[match.end() :].lstrip() if match else ""
        if match and not remainder.startswith("="):
            starts.append((index, match.group(1).upper()))
    commands: list[CommandOccurrence] = []
    for item_index, (line_index, name) in enumerate(starts):
        next_line = starts[item_index + 1][0] if item_index + 1 < len(starts) else len(lines)
        start = offsets[line_index]
        end = offsets[next_line] if next_line < len(offsets) else len(text)
        block = text[start:end]
        parameters: dict[str, Any] = {}
        raw_parameters: dict[str, str] = {}
        for assignment in ASSIGNMENT_RE.finditer(block):
            key = assignment.group("key").upper()
            raw_value = assignment.group("value")
            parameters[key] = _typed(raw_value)
            raw_parameters[key] = raw_value
        commands.append(CommandOccurrence(name, start, end, block, parameters, raw_parameters))
    return DeployDocument(text, commands, newline)
