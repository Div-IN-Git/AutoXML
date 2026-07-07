#classifications , side dropbar options.
from __future__ import annotations

from dataclasses import dataclass

TAG_OPTIONS = (
    "given-names", "surname", "collab", "suffix","degree"
)

#"organization",
    # "department", "institution", "group", "publisher", "conference",
    # "journal", "email", "country", "city", "state", "role",
    # "project", "unknown",

@dataclass
class TagItem:
    text: str
    detected_tag: str
    selected_tag: str
    confidence: int
    reference_index: int
    author_index: int
    order: int

    @property
    def corrected(self) -> bool:
        return self.selected_tag != self.detected_tag

    @property
    def status(self) -> str:
        if self.selected_tag == "unknown":
            return "Unknown"
        if self.confidence < 75:
            return "Low confidence"
        return "Corrected" if self.corrected else "Detected"
