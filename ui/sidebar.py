from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget, QLabel


class Sidebar(QWidget):
    document_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent); self.setObjectName("sidebar"); self.setMinimumWidth(220)
        layout = QVBoxLayout(self); layout.setContentsMargins(10, 10, 10, 10)
        title = QLabel("☰  FILES                                      0"); title.setObjectName("sectionTitle"); self.title = title
        self.search = QLineEdit(); self.search.setPlaceholderText("Search files…"); self.search.setClearButtonEnabled(True)
        self.list = QListWidget(); self.list.currentRowChanged.connect(self.document_selected)
        self.search.textChanged.connect(self._filter)
        layout.addWidget(title); layout.addWidget(self.search); layout.addWidget(self.list, 3)
        stats = QFrame(); stats.setObjectName("statsPanel"); stats_layout = QVBoxLayout(stats)
        stats_title = QLabel("⌁  STATS"); stats_title.setObjectName("sectionTitle"); stats_layout.addWidget(stats_title)
        self.stats = {}
        for name in ("Files Loaded", "Authors Found", "Collaborations", "Unknown Tags", "Corrections Made"):
            label = QLabel(); self.stats[name] = label; stats_layout.addWidget(label)
        layout.addWidget(stats, 2); self.update_stats({})

    def set_documents(self, documents):
        self.list.clear()
        for document in documents:
            item = QListWidgetItem("▧  " + document.name + "                                      ✓")
            item.setToolTip(str(document.path)); self.list.addItem(item)
        self.title.setText(f"☰  FILES                                      {len(documents)}")
        if documents: self.list.setCurrentRow(0)

    def _filter(self, text):
        query = text.casefold().strip()
        for row in range(self.list.count()): self.list.item(row).setHidden(query not in self.list.item(row).text().casefold())

    def update_stats(self, values):
        colors = ("#4C8DFF", "#3FB950", "#A875FF", "#F4B400", "#39A9FF")
        for (name, label), color in zip(self.stats.items(), colors):
            label.setText(f"<span style='color:{color}'>▪</span>  {name}<span style='float:right'><b>{values.get(name, 0)}</b></span>")
