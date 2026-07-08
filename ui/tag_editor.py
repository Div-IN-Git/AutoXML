from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox
from models import TAG_OPTIONS


class TagCombo(QComboBox):
    tag_changed = Signal(object, str)

    def __init__(self, item, parent=None):
        super().__init__(parent); self.item = item
        self.setMinimumWidth(145); self.setFixedHeight(30)
        self.addItems(TAG_OPTIONS); self.setCurrentText(item.selected_tag)
        self.currentTextChanged.connect(self._changed)

    def _changed(self, value):
        self.item.selected_tag = value; self.tag_changed.emit(self.item, value)
