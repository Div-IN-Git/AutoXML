from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)
from logic.xml_writer import build_output
from .tag_editor import TagCombo

COLORS = {"surname": "#4ED17B", "given-names": "#4C8DFF", "organization": "#A875FF", "collab": "#FF971D", "suffix": "#F4CF39", "unknown": "#F4B400"}


class PreviewPanel(QWidget):
    data_changed = Signal(); process_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent); self.document = None
        root = QVBoxLayout(self); root.setContentsMargins(10, 10, 10, 10); root.setSpacing(10)
        controls = QHBoxLayout(); self.file_label = QLabel("▧  No file selected"); self.file_label.setObjectName("fileTab")
        self.search = QLineEdit(); self.search.setPlaceholderText("⌕  Search in current file…"); self.search.setClearButtonEnabled(True)
        self.filter = QComboBox(); self.filter.addItem("All Tags"); self.filter.addItems(("surname", "given-names", "organization", "collab", "suffix", "unknown"))
        self.auto = QCheckBox("Auto Detect"); self.auto.setChecked(True)
        controls.addWidget(self.file_label); controls.addStretch(); controls.addWidget(self.search, 2); controls.addWidget(self.filter); controls.addWidget(self.auto)
        root.addLayout(controls)
        self.table = QTableWidget(0, 6); self.table.setHorizontalHeaderLabels(("#", "Detected Text", "Detected As", "Confidence", "Tag (You can edit)", "XML Path"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide(); self.table.setAlternatingRowColors(True); self.table.setMinimumHeight(310); self.table.setShowGrid(False)
        header = self.table.horizontalHeader(); header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch); header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        for col in (0, 2, 3, 4): header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.table, 3)
        bottom = QSplitter(Qt.Orientation.Horizontal); bottom.setMinimumHeight(245); bottom.addWidget(self._preview_card("XML PREVIEW (Original)", "original")); bottom.addWidget(self._preview_card("XML PREVIEW (Preview with your changes)", "changed")); bottom.addWidget(self._process_card())
        bottom.setStretchFactor(0, 4); bottom.setStretchFactor(1, 4); bottom.setStretchFactor(2, 2); root.addWidget(bottom, 2)
        self.search.textChanged.connect(self._filter_rows); self.filter.currentTextChanged.connect(self._filter_rows)

    def _preview_card(self, title, attr):
        frame = QFrame(); frame.setObjectName("previewCard"); layout = QVBoxLayout(frame); heading = QLabel(title); heading.setObjectName("cardTitle")
        editor = QPlainTextEdit(); editor.setReadOnly(True); editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        editor.setFont(QFont("Cascadia Mono", 9)); setattr(self, attr, editor); layout.addWidget(heading); layout.addWidget(editor); return frame

    def _process_card(self):
        frame = QFrame(); frame.setObjectName("processCard"); layout = QVBoxLayout(frame); layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QLabel("✓"); icon.setObjectName("successIcon"); icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Parsed Successfully"); title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel("Ready to process"); sub.setObjectName("muted"); sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        button = QPushButton("▶  Process Now"); button.setObjectName("primaryButton"); button.clicked.connect(self.process_requested)
        layout.addStretch(); layout.addWidget(icon); layout.addWidget(title); layout.addWidget(sub); layout.addStretch(); layout.addWidget(button); return frame

    def set_document(self, document):
        self.document = document; self.search.clear(); self.table.setRowCount(0)
        self.file_label.setText("▧  " + document.name + "   ×" if document else "▧  No file selected")
        if not document: self.original.clear(); self.changed.clear(); return
        self.table.setRowCount(len(document.items))
        for row, item in enumerate(document.items):
            path = f"/ref[{item.reference_index + 1}]/person-group[{item.author_index + 1}]/{item.selected_tag}"
            values = (str(row + 1), item.text, item.detected_tag.replace("-", " ").title(), f"{item.confidence}%  {'━' * max(1, item.confidence // 20)}", path)
            for column, value in zip((0, 1, 2, 3, 5), values):
                cell = QTableWidgetItem(value); cell.setData(Qt.ItemDataRole.UserRole, item); self.table.setItem(row, column, cell)
            combo = TagCombo(item); combo.tag_changed.connect(self._item_changed); self.table.setCellWidget(row, 4, combo); self._color_row(row, item)
        self._update_previews()

    def _item_changed(self, item, _value):
        for row in range(self.table.rowCount()):
            if self.table.item(row, 1).data(Qt.ItemDataRole.UserRole) is item:
                self.table.item(row, 2).setText(item.selected_tag.replace("-", " ").title())
                self.table.item(row, 5).setText(f"/ref[{item.reference_index + 1}]/person-group[{item.author_index + 1}]/{item.selected_tag}")
                self._color_row(row, item); break
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
        self.original.setPlainText(original[:12000]); self.changed.setPlainText(changed[:12000])
