"""Review grid and IDE-style XML previews."""
from __future__ import annotations

import html
import re

from PySide6.QtCore import QRect, QSize, Qt, QRegularExpression, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QTextCharFormat, QSyntaxHighlighter
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPlainTextEdit, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from logic.xml_writer import build_output
from .tag_editor import TagCombo


COLORS = {
    "surname": "#4ED17B", "given-names": "#4C8DFF", "collab": "#FF971D",
    "suffix": "#F4CF39", "unknown": "#F4B400",
}
REF_LIST_RE = re.compile(
    r"<(?:[A-Za-z_][\w.-]*:)?ref-list\b[^>]*>.*?"
    r"</(?:[A-Za-z_][\w.-]*:)?ref-list\s*>", re.IGNORECASE | re.DOTALL,
)


def item_key(text: str) -> str:
    """Canonical identity used to link repeated XML values."""
    return " ".join(html.unescape(text).split()).casefold()


def ref_list_only(xml: str) -> str:
    match = REF_LIST_RE.search(xml)
    return match.group(0) if match else "No <ref-list> block found."


class XmlHighlighter(QSyntaxHighlighter):
    """Small XML syntax highlighter with an IDE-inspired palette."""

    def __init__(self, document):
        super().__init__(document)
        self.tag = self._format("#F07178")
        self.name = self._format("#FFCB6B", bold=True)
        self.attribute = self._format("#82AAFF")
        self.value = self._format("#C3E88D")
        self.entity = self._format("#C792EA")
        self.comment = self._format("#637777", italic=True)
        self.rules = (
            (QRegularExpression(r"</?\s*[A-Za-z_][\w:.-]*|/?>"), self.tag, 0),
            (QRegularExpression(r"</?\s*([A-Za-z_][\w:.-]*)"), self.name, 1),
            (QRegularExpression(r"\b([A-Za-z_:][\w:.-]*)(?=\s*=)"), self.attribute, 1),
            (QRegularExpression(r'("[^"\n]*"|\'[^\'\n]*\')'), self.value, 1),
            (QRegularExpression(r"&(?:#\d+|#x[0-9A-Fa-f]+|[A-Za-z][\w.-]*);"), self.entity, 0),
            (QRegularExpression(r"<!--.*?-->"), self.comment, 0),
        )

    @staticmethod
    def _format(color, *, bold=False, italic=False):
        result = QTextCharFormat(); result.setForeground(QColor(color))
        result.setFontWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal); result.setFontItalic(italic)
        return result

    def highlightBlock(self, text):
        for expression, style, capture in self.rules:
            iterator = expression.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next(); start = match.capturedStart(capture); length = match.capturedLength(capture)
                if start >= 0: self.setFormat(start, length, style)


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor); self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_line_numbers(event)


class CodeEditor(QPlainTextEdit):
    """Read-only code view with line numbers and XML highlighting."""

    def __init__(self, parent=None):
        super().__init__(parent); self.setReadOnly(True); self.setLineWrapMode(self.LineWrapMode.NoWrap)
        self.setFont(QFont("Cascadia Mono", 9)); self.numbers = LineNumberArea(self); self.highlighter = XmlHighlighter(self.document())
        self.blockCountChanged.connect(self._update_margin); self.updateRequest.connect(self._update_numbers)
        self._update_margin()

    def line_number_width(self):
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 14 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_margin(self, _count=0):
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def _update_numbers(self, rect, dy):
        if dy: self.numbers.scroll(0, dy)
        else: self.numbers.update(0, rect.y(), self.numbers.width(), rect.height())
        if rect.contains(self.viewport().rect()): self._update_margin()

    def resizeEvent(self, event):
        super().resizeEvent(event); rect = self.contentsRect()
        self.numbers.setGeometry(QRect(rect.left(), rect.top(), self.line_number_width(), rect.height()))

    def paint_line_numbers(self, event):
        painter = QPainter(self.numbers); painter.fillRect(event.rect(), QColor("#101923")); painter.setPen(QColor("#52606D"))
        block = self.firstVisibleBlock(); number = block.blockNumber(); top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(0, top, self.numbers.width() - 7, self.fontMetrics().height(), Qt.AlignmentFlag.AlignRight, str(number + 1))
            block = block.next(); top = bottom; bottom = top + round(self.blockBoundingRect(block).height()); number += 1


class PreviewPanel(QWidget):
    data_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent); self.document = None; self.occurrences = {}
        root = QVBoxLayout(self); root.setContentsMargins(10, 10, 10, 10); root.setSpacing(10)
        controls = QHBoxLayout(); self.file_label = QLabel("▧  No file selected"); self.file_label.setObjectName("fileTab")
        self.search = QLineEdit(); self.search.setPlaceholderText("⌕  Search in current file…"); self.search.setClearButtonEnabled(True)
        self.filter = QComboBox(); self.filter.addItem("All Tags"); self.filter.addItems(("surname", "given-names", "collab", "suffix", "unknown"))
        self.auto = QCheckBox("Auto Detect"); self.auto.setChecked(True)
        controls.addWidget(self.file_label); controls.addStretch(); controls.addWidget(self.search, 2); controls.addWidget(self.filter); controls.addWidget(self.auto); root.addLayout(controls)

        self.table = QTableWidget(0, 6); self.table.setHorizontalHeaderLabels(("#", "Detected Text", "Detected As", "Confidence", "Tag (You can edit)", "XML Path"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(38); self.table.verticalHeader().hide(); self.table.setAlternatingRowColors(True); self.table.setMinimumHeight(310); self.table.setShowGrid(False)
        header = self.table.horizontalHeader(); header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch); header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        for column in (0, 2, 3, 4): header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.table, 3)

        bottom = QSplitter(Qt.Orientation.Horizontal); bottom.setMinimumHeight(245)
        bottom.addWidget(self._preview_card("XML PREVIEW (Original)", "original")); bottom.addWidget(self._preview_card("XML PREVIEW (Preview with your changes)", "changed"))
        bottom.setStretchFactor(0, 1); bottom.setStretchFactor(1, 1); bottom.setSizes((600, 600)); root.addWidget(bottom, 2)
        self.search.textChanged.connect(self._filter_rows); self.filter.currentTextChanged.connect(self._filter_rows)

    def _preview_card(self, title, attr):
        frame = QFrame(); frame.setObjectName("previewCard"); layout = QVBoxLayout(frame)
        heading = QLabel(title); heading.setObjectName("cardTitle"); editor = CodeEditor()
        setattr(self, attr, editor); layout.addWidget(heading); layout.addWidget(editor); return frame

    def set_document(self, document):
        self.document = document; self.search.clear(); self.table.setRowCount(0); self.occurrences = {}
        self.file_label.setText("▧  " + document.name + "   ×" if document else "▧  No file selected")
        if not document: self.original.clear(); self.changed.clear(); return

        representatives = []
        for item in document.items:
            key = item_key(item.text)
            if key not in self.occurrences: representatives.append(item); self.occurrences[key] = []
            self.occurrences[key].append(item)
        self.table.setRowCount(len(representatives))
        for row, item in enumerate(representatives):
            count = len(self.occurrences[item_key(item.text)])
            path = f"/ref[{item.reference_index + 1}]/person-group[{item.author_index + 1}]/{item.selected_tag}"
            if count > 1: path += f"  (+{count - 1} occurrences)"
            values = (str(row + 1), item.text, item.detected_tag.replace("-", " ").title(), f"{item.confidence}%  {'━' * max(1, item.confidence // 20)}", path)
            for column, value in zip((0, 1, 2, 3, 5), values):
                cell = QTableWidgetItem(value); cell.setData(Qt.ItemDataRole.UserRole, item); self.table.setItem(row, column, cell)
            combo = TagCombo(item); combo.tag_changed.connect(self._item_changed)
            holder = QWidget(); cell_layout = QHBoxLayout(holder); cell_layout.setContentsMargins(6, 4, 6, 4); cell_layout.addWidget(combo)
            self.table.setCellWidget(row, 4, holder); self._color_row(row, item)
        self._update_previews()

    def _item_changed(self, representative, value):
        linked = self.occurrences.get(item_key(representative.text), [representative])
        for item in linked: item.selected_tag = value
        for row in range(self.table.rowCount()):
            if self.table.item(row, 1).data(Qt.ItemDataRole.UserRole) is representative:
                count = len(linked); path = f"/ref[{representative.reference_index + 1}]/person-group[{representative.author_index + 1}]/{value}"
                if count > 1: path += f"  (+{count - 1} occurrences)"
                self.table.item(row, 5).setText(path); self._color_row(row, representative); break
        self._update_previews(); self.data_changed.emit()

    def _color_row(self, row, item):
        color = QColor(COLORS.get(item.selected_tag, "#55C2C3")); self.table.item(row, 2).setForeground(color); self.table.item(row, 3).setForeground(color)

    def _filter_rows(self, _value=""):
        query = self.search.text().casefold().strip(); tag = self.filter.currentText()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1).data(Qt.ItemDataRole.UserRole)
            matches = query in (item.text + " " + item.selected_tag).casefold() and (tag == "All Tags" or item.selected_tag == tag)
            self.table.setRowHidden(row, not matches)

    def _update_previews(self):
        if not self.document: return
        original = self.document.data.decode(self.document.encoding, errors="replace")
        try: changed = build_output(self.document).decode(self.document.encoding, errors="replace")
        except Exception as exc: changed = f"Preview unavailable: {exc}"
        self.original.setPlainText(ref_list_only(original)); self.changed.setPlainText(ref_list_only(changed))
