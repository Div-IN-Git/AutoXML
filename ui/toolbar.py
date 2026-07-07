from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QStyle, QToolBar, QVBoxLayout, QWidget

try:
    import qtawesome as qta
except ImportError:  # usable even when the optional icon pack is absent
    qta = None


class AppToolBar(QToolBar):
    select_file = Signal(); select_folder = Signal(); refresh = Signal()
    process = Signal(); settings = Signal(); about = Signal()

    ACTIONS = (
        ("fa5s.file-code", "Select XML", "Ctrl+O", "select_file"),
        ("fa5s.folder-open", "Select Folder", "Ctrl+Shift+O", "select_folder"),
        ("fa5s.sync-alt", "Refresh", "F5", "refresh"),
        ("fa5s.play", "Process", "Ctrl+R", "process"),
        ("fa5s.cog", "Settings", "Ctrl+,", "settings"),
        ("fa5s.info-circle", "About", "F1", "about"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("appToolbar"); self.setMovable(False)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        brand = QWidget(); brand.setObjectName("brand"); brand_layout = QHBoxLayout(brand); brand_layout.setContentsMargins(4, 0, 18, 0)
        logo = QLabel("</>"); logo.setObjectName("logo")
        text = QWidget(); text_layout = QVBoxLayout(text); text_layout.setContentsMargins(0, 0, 0, 0); text_layout.setSpacing(0)
        title = QLabel("XML Tagger Pro"); title.setObjectName("brandTitle"); subtitle = QLabel("Smart XML Tagging & Editor"); subtitle.setObjectName("brandSubtitle")
        text_layout.addWidget(title); text_layout.addWidget(subtitle); brand_layout.addWidget(logo); brand_layout.addWidget(text)
        self.addWidget(brand); self.addSeparator()
        for icon_name, text, shortcut, signal_name in self.ACTIONS:
            icon = qta.icon(icon_name, color="#c9d1d9") if qta else self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
            action = self.addAction(icon, text); action.setShortcut(shortcut)
            action.triggered.connect(getattr(self, signal_name).emit)
            if text in {"Select Folder", "Refresh", "Process", "Export"}:
                self.addSeparator()
