#Reference level author model.
from dataclasses import dataclass, field
from .tag import TagItem


@dataclass
class ReferenceAuthors:
    index: int
    original_region: str
    items: list[TagItem] = field(default_factory=list)
    editable: bool = True
