#!/usr/bin/env python3
"""plain text JATS mixed citation authors to structured XML by Divyanshu swain"""

from __future__ import annotations

import argparse
import html
import re
import sys
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Iterator, Sequence
import xml.etree.ElementTree as ET


def tag(name: bytes) -> bytes:
    """Regex fragment for an optionally namespace-prefixed XML tag name."""
    return rb"(?:[A-Za-z_][\w.-]*:)?" + name


REF_RE = re.compile(rb"<" + tag(rb"ref") + rb"(?=[\s>/])[^>]*>.*?</" + tag(rb"ref") + rb"\s*>", re.I | re.S)
MIXED_OPEN_RE = re.compile(rb"<" + tag(rb"mixed-citation") + rb"(?=[\s>/])[^>]*>", re.I | re.S)
YEAR_RE = re.compile(rb"<" + tag(rb"year") + rb"(?=[\s>/])[^>]*>", re.I | re.S)
EXISTING_RE = re.compile(rb"<" + tag(rb"(?:person-group|given-names|surname|collab)") + rb"(?=[\s>/])", re.I)
PERSON_GROUP_RE = re.compile(rb"<" + tag(rb"person-group") + rb"(?=[\s>/])", re.I)
XML_DECL_ENCODING_RE = re.compile(rb"<\?xml\b[^>]*\bencoding\s*=\s*(['\"])([^'\"]+)\1", re.I)

PREFIXES = {"de", "del", "della", "da", "di", "van", "von", "der", "den", "la", "le", "du", "st.", "st", "ter"}
TITLES = {"dr.", "prof.", "professor", "mr.", "mrs.", "ms.", "miss", "sir", "dame", "fr.", "rev.", "hon."}
SUFFIXES = {"jr.", "sr.", "ii", "iii", "iv", "v", "phd", "m.d.", "md", "dds", "dvm"}
ORG_WORDS = {
    "university", "institute", "institution", "technology", "council", "administration",
    "survey", "nations", "commission", "department", "ministry", "association", "society",
    "academy", "agency", "laboratory", "center", "centre", "school", "college", "committee",
    "foundation", "corporation", "inc.", "inc", "ltd.", "ltd", "llc", "museum", "library",
    "hospital", "research", "geological", "aeronautics", "smithsonian",
    "party", "limited",
}
ORG_ACRONYMS = {"NASA", "NOAA", "USGS", "WHO", "UNESCO", "JAXA", "ESA", "ISRO", "CSIRO", "CNRS"}


class TokenKind(Enum):
    WORD = auto()
    COMMA = auto()
    SEMICOLON = auto()
    AND = auto()
    AMP = auto()
    SPACE = auto()


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    text: str


@dataclass
class Name:
    given: str = ""
    surname: str = ""
    suffixes: list[str] | None = None
    collab: str = ""


@dataclass
class Stats:
    modified: int = 0
    skipped: int = 0
    failed: int = 0


class ParseError(ValueError):
    """A citation is ambiguous or unsafe to modify."""


def tokenize(text: str) -> list[Token]:
    """Lex author text without imposing name semantics.

    XML character references are kept in WORD tokens; ``&#x26;`` must not be
    mistaken for an author separator.  Periods and apostrophes remain part of
    words, which naturally supports initials and O'Brien/D'Amico.
    """
    result: list[Token] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            j = i + 1
            while j < len(text) and text[j].isspace():
                j += 1
            result.append(Token(TokenKind.SPACE, text[i:j])); i = j; continue
        if ch == "&":
            entity = re.match(r"&(?:#\d+|#x[0-9A-Fa-f]+|[A-Za-z][\w.-]*);", text[i:])
            if entity:
                raw_entity = entity.group(0)
                result.append(Token(TokenKind.AMP if raw_entity.casefold() == "&amp;" else TokenKind.WORD, raw_entity))
                i += len(raw_entity); continue
            result.append(Token(TokenKind.AMP, ch)); i += 1; continue
        if ch in ",;":
            result.append(Token(TokenKind.COMMA if ch == "," else TokenKind.SEMICOLON, ch)); i += 1; continue
        j = i + 1
        while j < len(text) and not text[j].isspace() and text[j] not in ",;&":
            j += 1
        word = text[i:j]
        result.append(Token(TokenKind.AND if word.casefold() == "and" else TokenKind.WORD, word)); i = j
    return result


def plain(value: str) -> str:
    return html.unescape(value).strip()


def words(value: str) -> list[str]:
    return [w for w in re.split(r"\s+", plain(value)) if w]


def is_initial_sequence(value: str) -> bool:
    """Accept A., A.D., A . D ., and arbitrary-length initial sequences."""
    compact = re.sub(r"\s+", "", plain(value))
    return bool(compact and re.fullmatch(r"(?:[A-Za-z]\.?){1,8}", compact) and ("." in compact or len(compact) == 1))


def is_organization(value: str) -> bool:
    decoded = plain(value)
    ws = words(decoded)
    if decoded.upper() in ORG_ACRONYMS:
        return True
    lowered = {w.casefold().strip(",") for w in ws}
    return bool(lowered & ORG_WORDS) or (len(ws) > 3 and "of" in lowered)


def split_suffixes(value: str) -> tuple[str, list[str]]:
    ws = words(value)
    found: list[str] = []
    while ws and ws[-1].casefold().rstrip(",") in SUFFIXES:
        found.insert(0, ws.pop().rstrip(","))
    return " ".join(ws), found


def strip_titles(value: str) -> tuple[str, list[str]]:
    ws = words(value)
    found: list[str] = []
    while ws and ws[0].casefold() in TITLES:
        found.append(ws.pop(0))
    return " ".join(ws), found


def parse_later_name(value: str) -> Name:
    value = value.strip()
    if not value:
        raise ParseError("empty author")
    if is_organization(value):
        return Name(collab=value)
    core, leading = strip_titles(value)
    core, trailing = split_suffixes(core)
    ws = words(core)
    if len(ws) < 2:
        raise ParseError(f"cannot split later author: {value!r}")

    # Surname begins at a recognized particle, otherwise the final word.
    surname_at = len(ws) - 1
    for idx in range(1, len(ws)):
        if ws[idx].casefold() in PREFIXES:
            surname_at = idx
            break
    given = " ".join(ws[:surname_at])
    surname = " ".join(ws[surname_at:])
    if not given or not surname:
        raise ParseError(f"invalid person name: {value!r}")
    return Name(given=given, surname=surname, suffixes=leading + trailing)


def meaningful(tokens: Sequence[Token]) -> str:
    return "".join(t.text for t in tokens).strip()


class AuthorParser:
    """A small deterministic parser for citation author lists."""

    def __init__(self, source: str):
        self.tokens = tokenize(source)
        self.pos = 0

    def take_until(self, kinds: set[TokenKind]) -> tuple[str, TokenKind | None]:
        start = self.pos
        while self.pos < len(self.tokens) and self.tokens[self.pos].kind not in kinds:
            self.pos += 1
        text = meaningful(self.tokens[start:self.pos])
        stop = self.tokens[self.pos].kind if self.pos < len(self.tokens) else None
        if stop is not None:
            self.pos += 1
        return text, stop

    def parse(self) -> list[Name]:
        # First author has a mandatory semantic comma: Surname, Given Names.
        first_left, stop = self.take_until({TokenKind.COMMA, TokenKind.SEMICOLON, TokenKind.AND, TokenKind.AMP})
        if not first_left:
            raise ParseError("missing first author")
        if is_organization(first_left):
            names = [Name(collab=first_left)]
        elif stop is None and len(words(first_left)) >= 2:
            # Rare display-name form found in otherwise conventional lists,
            # e.g. William “Strata” Smith.
            names = [parse_later_name(first_left)]
        else:
            if stop is not TokenKind.COMMA:
                raise ParseError("first personal author lacks surname comma")
            first_surname, surname_titles = strip_titles(first_left)
            first_right, stop = self.take_until({TokenKind.COMMA, TokenKind.SEMICOLON, TokenKind.AND, TokenKind.AMP})
            core, leading = strip_titles(first_right)
            core, trailing = split_suffixes(core)
            # Bibliographies sometimes write "Mitchum, Jr., R. M.".  In that
            # form the first comma-delimited field contains only the suffix.
            if not core and trailing and stop is TokenKind.COMMA:
                core, stop = self.take_until({TokenKind.COMMA, TokenKind.SEMICOLON, TokenKind.AND, TokenKind.AMP})
            if not core:
                raise ParseError("first author lacks given names")
            names = [Name(given=core, surname=first_surname, suffixes=surname_titles + leading + trailing)]

        # Each remaining segment is Given Names + Surname (or an organization).
        while self.pos < len(self.tokens) or stop is not None:
            while self.pos < len(self.tokens) and self.tokens[self.pos].kind in {TokenKind.SPACE, TokenKind.COMMA, TokenKind.SEMICOLON, TokenKind.AND, TokenKind.AMP}:
                self.pos += 1
            if self.pos >= len(self.tokens):
                break
            part, stop = self.take_until({TokenKind.COMMA, TokenKind.SEMICOLON, TokenKind.AND, TokenKind.AMP})
            if part:
                # A suffix may be comma-separated from the person it follows:
                # "G. J. Grabowski, Jr., A. R. Carroll".
                if part.casefold().rstrip(",") in SUFFIXES and names and not names[-1].collab:
                    if names[-1].suffixes is None:
                        names[-1].suffixes = []
                    names[-1].suffixes.append(part.rstrip(","))
                elif len(words(part)) == 1 and stop is TokenKind.COMMA:
                    # Some lists inconsistently use Surname, Given for a later
                    # author too ("and Maynard, J. B.").
                    given, stop = self.take_until({TokenKind.COMMA, TokenKind.SEMICOLON, TokenKind.AND, TokenKind.AMP})
                    if not given:
                        raise ParseError(f"missing given names after {part!r}")
                    core, suffixes = split_suffixes(given)
                    names.append(Name(given=core, surname=part, suffixes=suffixes))
                else:
                    names.append(parse_later_name(part))
        if not names:
            raise ParseError("no authors")
        return names


def xml_text(value: str) -> str:
    """Escape literal markup while retaining already-present XML entities."""
    pieces = re.split(r"(&(?:#\d+|#x[0-9A-Fa-f]+|[A-Za-z][\w.-]*);)", value)
    return "".join(p if p.startswith("&") and p.endswith(";") else p.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") for p in pieces)


def render(names: Sequence[Name]) -> str:
    rendered: list[str] = []
    for index, n in enumerate(names):
        if n.collab:
            item = f"<collab>{xml_text(n.collab)}</collab>"
        else:
            if index == 0:
                item = f"<surname>{xml_text(n.surname)}</surname>, <given-names>{xml_text(n.given)}</given-names>"
            else:
                item = f"<given-names>{xml_text(n.given)}</given-names> <surname>{xml_text(n.surname)}</surname>"
            for suffix in n.suffixes or []:
                item += f", <suffix>{xml_text(suffix)}</suffix>"
        rendered.append(item)
    if len(rendered) == 1:
        body = rendered[0]
    elif len(rendered) == 2:
        body = rendered[0] + ", and " + rendered[1]
    else:
        body = ", ".join(rendered[:-1]) + ", and " + rendered[-1]
    return '<person-group person-group-type="author">' + body + "</person-group>"


def encoding_of(data: bytes) -> str:
    match = XML_DECL_ENCODING_RE.search(data[:512])
    return match.group(2).decode("ascii") if match else "utf-8"


def validate_xml(data: bytes, label: str) -> None:
    try:
        ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"{label} is not well-formed XML: {exc}") from exc


def transform(data: bytes, *, test_mode: bool = False) -> tuple[bytes, Stats]:
    """Return transformed bytes and counters; individual bad refs are retained."""
    validate_xml(data, "input")
    encoding = encoding_of(data)
    stats = Stats()
    output = bytearray()
    cursor = 0
    for match in REF_RE.finditer(data):
        output.extend(data[cursor:match.start()])
        ref = match.group(0)
        replacement = ref
        try:
            mixed = MIXED_OPEN_RE.search(ref)
            if not mixed:
                stats.skipped += 1
                output.extend(ref); cursor = match.end(); continue
            year = YEAR_RE.search(ref, mixed.end())
            if not year:
                stats.skipped += 1
                output.extend(ref); cursor = match.end(); continue
            region = ref[mixed.end():year.start()]
            # Existing markup anywhere in ref is a hard skip for person-group;
            # author-level tags in the target span are likewise a hard skip.
            if PERSON_GROUP_RE.search(ref) or EXISTING_RE.search(region):
                stats.skipped += 1
                output.extend(ref); cursor = match.end(); continue
            if b"<" in region or b">" in region:
                raise ParseError("author region contains unsupported XML markup")

            text = region.decode(encoding)
            lead = text[:len(text) - len(text.lstrip())]
            trail = text[len(text.rstrip()):]
            author_text = text.strip()
            # The comma immediately preceding year belongs to citation style,
            # not to the final author.
            author_text = re.sub(r"(?:\s*,\s*)$", "", author_text)
            names = AuthorParser(author_text).parse()
            new_region = lead + render(names) + (", " if not trail else "," + trail)
            replacement = ref[:mixed.end()] + new_region.encode(encoding) + ref[year.start():]
            # Validate each replacement inside a harmless wrapper before use.
            ET.fromstring(b"<root>" + replacement + b"</root>")
            stats.modified += 1
            if test_mode:
                print("Original:\n\n" + text + "\n\nParsed:\n\n" + new_region + "\n")
        except Exception as exc:  # one malformed citation must not end the run
            stats.failed += 1
            if test_mode:
                print(f"Warning: reference left unchanged: {exc}", file=sys.stderr)
            replacement = ref
        output.extend(replacement)
        cursor = match.end()
    output.extend(data[cursor:])
    result = bytes(output)
    validate_xml(result, "output")
    return result, stats


def output_path_for(source: Path) -> Path:
    return source.with_name(source.stem + "_authors" + source.suffix)


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="input JATS/XML file")
    parser.add_argument("output", nargs="?", type=Path, help="new output file (default: INPUT_authors.xml)")
    parser.add_argument("--test-mode", action="store_true", help="print original and parsed author regions")
    parser.add_argument("--overwrite", action="store_true", help="allow replacing an existing output file")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_cli().parse_args(argv)
    source: Path = args.input.resolve()
    destination: Path = (args.output or output_path_for(source)).resolve()
    if source == destination:
        print("error: output must differ from input; the original is never modified", file=sys.stderr)
        return 2
    if not source.is_file():
        print(f"error: input file not found: {source}", file=sys.stderr)
        return 2
    if destination.exists() and not args.overwrite:
        print(f"error: output already exists (use --overwrite): {destination}", file=sys.stderr)
        return 2
    try:
        result, stats = transform(source.read_bytes(), test_mode=args.test_mode)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(result)
    except (OSError, ValueError, LookupError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Modified references: {stats.modified}")
    print(f"Skipped references: {stats.skipped}")
    print(f"Failed references: {stats.failed}")
    print(f"Output: {destination}")
    return 0


def launch_gui() -> int:
    """Start the desktop application, keeping Qt an optional CLI dependency."""
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "PySide6 is not installed. Install desktop dependencies with:\n"
            "  python -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    # logic.xml_parser imports this module as ``main``. When launched as a
    # script, expose the already-loaded module under that canonical name to
    # avoid executing it twice.
    sys.modules.setdefault("main", sys.modules[__name__])
    app = QApplication(sys.argv)
    app.setApplicationName("XML Reference Tagger")
    app.setOrganizationName("XMLTools")
    # qt-material is an available theme dependency, while this application
    # uses a purpose-built stylesheet to match its dense editor layout.  Its
    # generic theme is intentionally not applied over the branded palette.
    from ui.main_window import MainWindow
    window = MainWindow(); window.show()
    return app.exec()


if __name__ == "__main__":
    # Preserve the production CLI: providing an input path runs a batch
    # conversion; launching without arguments opens the review application.
    raise SystemExit(launch_gui() if len(sys.argv) == 1 else main())
