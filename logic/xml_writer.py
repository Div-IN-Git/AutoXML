"""Export reviewed documents while retaining all unrelated source bytes."""
from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

import main as engine
from models import Document


XML_TAGS = {"given-names", "surname", "collab", "suffix"}


def _render_items(items) -> str:
    authors = []
    for author_index in sorted({item.author_index for item in items}):
        author_items = sorted((item for item in items if item.author_index == author_index), key=lambda value: value.order)
        parts = []
        for item in author_items:
            tag = item.selected_tag

            if tag in {"organization", "department", "institution", "group"}: tag = "collab"
            text = engine.xml_text(item.text)
            parts.append((tag, f"<{tag}>{text}</{tag}>" if tag in XML_TAGS else text))
        author = ""
        for position, (tag, markup) in enumerate(parts):
            if position:
                previous = parts[position - 1][0]
                separator = ", " if tag == "suffix" or (author_index == 0 and previous == "surname" and tag == "given-names") else " "
                author += separator
            author += markup
        authors.append(author)
    if len(authors) == 1: body = authors[0]
    elif len(authors) == 2: body = authors[0] + ", and " + authors[1]
    else: body = ", ".join(authors[:-1]) + ", and " + authors[-1]
    return '<person-group person-group-type="author">' + body + "</person-group>"


def build_output(document: Document) -> bytes:
    by_index = {ref.index: ref for ref in document.references}
    output = bytearray(); cursor = 0; index = 0
    for match in engine.REF_RE.finditer(document.data):
        output.extend(document.data[cursor:match.start()])
        ref = match.group(0); replacement = ref
        mixed = engine.MIXED_OPEN_RE.search(ref)
        year = engine.YEAR_RE.search(ref, mixed.end()) if mixed else None
        if mixed and year:
            record = by_index.get(index); index += 1
            if record and record.editable and record.items:
                region = ref[mixed.end():year.start()].decode(document.encoding)
                lead = region[:len(region) - len(region.lstrip())]
                trail = region[len(region.rstrip()):]
                new_region = lead + _render_items(record.items) + ("," + trail if trail else ", ")
                replacement = ref[:mixed.end()] + new_region.encode(document.encoding) + ref[year.start():]
        output.extend(replacement); cursor = match.end()
    output.extend(document.data[cursor:])
    result = bytes(output)
    engine.validate_xml(result, "generated output")
    return result


def export_document(document: Document) -> Path:
    output_dir = document.path.parent / "output"
    output_dir.mkdir(exist_ok=True)
    destination = output_dir / document.path.name
    # Atomic replacement protects an earlier successful export if writing is
    # interrupted. Originals are outside output_dir and cannot be overwritten.
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(build_output(document))
    temporary.replace(destination)
    return destination
