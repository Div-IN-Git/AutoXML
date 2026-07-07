#Read only document analysis built on the byte preserving CLI parser.
from __future__ import annotations

import re
from pathlib import Path

import main as engine
from models import Document, ReferenceAuthors
from .tag_detector import detect_name


def parse_document(path: Path) -> Document:
    data = path.read_bytes()
    engine.validate_xml(data, str(path))
    encoding = engine.encoding_of(data)
    document = Document(path.resolve(), data, encoding)
    ref_index = 0
    for match in engine.REF_RE.finditer(data):
        ref = match.group(0)
        mixed = engine.MIXED_OPEN_RE.search(ref)
        year = engine.YEAR_RE.search(ref, mixed.end()) if mixed else None
        if not mixed or not year:
            continue
        region = ref[mixed.end():year.start()]
        original = region.decode(encoding)
        record = ReferenceAuthors(ref_index, original)
        ref_index += 1
        if engine.PERSON_GROUP_RE.search(ref) or engine.EXISTING_RE.search(region) or b"<" in region:
            record.editable = False
            document.references.append(record)
            continue
        author_text = re.sub(r"(?:\s*,\s*)$", "", original.strip())
        try:
            names = engine.AuthorParser(author_text).parse()
            order = 0
            for name_index, name in enumerate(names):
                detected = detect_name(name, record.index, name_index, order, first=name_index == 0)
                record.items.extend(detected)
                order += len(detected)
        except engine.ParseError:
            record.editable = False
        document.references.append(record)
    return document
