#Rule-based conversion from parser results to editable UI tokens.
from __future__ import annotations

from main import Name
from models import TagItem


def detect_name(name: Name, reference_index: int, author_index: int, start_order: int, *, first: bool = False) -> list[TagItem]:
    items: list[TagItem] = []
    order = start_order
    if name.collab:
        items.append(TagItem(name.collab, "collab", "collab", 99, reference_index, author_index, order))
        return items
    components = ((name.surname, "surname", 97), (name.given, "given-names", 96)) if first else ((name.given, "given-names", 96), (name.surname, "surname", 97))
    for text, tag, confidence in components:
        if text:
            items.append(TagItem(text, tag, tag, confidence, reference_index, author_index, order)); order += 1
    for suffix in name.suffixes or []:
        items.append(TagItem(suffix, "suffix", "suffix", 98, reference_index, author_index, order)); order += 1
    return items
