from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FieldChange:
    command: str
    parameter: str
    original: object
    requested: object
    changed: bool

    @property
    def path(self) -> str:
        return f"{self.command}.{self.parameter}"


@dataclass
class NortekValidation:
    status: str = "CANDIDATE_REQUIRES_INSTRUMENT_VALIDATION"
    warnings: list[str] = field(default_factory=list)
