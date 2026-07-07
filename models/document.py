#XML docu and its in memory review state.
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from .author import ReferenceAuthors


@dataclass
class Document:
    path: Path
    data: bytes
    encoding: str
    references: list[ReferenceAuthors] = field(default_factory=list)
    error: str = ""

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def items(self):
        return [item for ref in self.references for item in ref.items]

    @property
    def corrections(self) -> int:
        return sum(item.corrected for item in self.items)
