from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QSettings, QThreadPool, QTimer, Qt
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QStatusBar, QVBoxLayout, QWidget

from logic.background_worker import BatchExportWorker, BatchParseWorker
from logic.xml_parser import parse_document
from logic.xml_writer import export_document
from .dialogs import ProgressDialog
from .preview_panel import PreviewPanel
from .sidebar import Sidebar
from .toolbar import AppToolBar


STYLE = """
QWidget { background: #0F1722; color: #D8DEE9; font-family: 'Segoe UI'; font-size: 12px; }
QToolBar#appToolbar { background: #0D1520; border: 0; border-bottom: 1px solid #243142; spacing: 7px; padding: 7px 12px; }
QToolButton { border: 0; border-radius: 6px; padding: 7px 11px; } QToolButton:hover { background: #1B2A3C; }
#logo { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #36C5F0,stop:1 #4C6FFF); color:white; border-radius:6px; font-weight:bold; padding:10px 7px; }
#brandTitle { font-size:14px; font-weight:700; color:white; } #brandSubtitle { font-size:9px; color:#8593A6; }
#sidebar { background: #111B28; border-right: 1px solid #243142; }
#sectionTitle { color: #8B949E; font-weight: 700; font-size: 11px; padding: 5px; }
QListWidget, QTableWidget, QPlainTextEdit { background: #141F2D; border: 1px solid #273547; border-radius: 7px; outline: 0; }
QTableWidget { alternate-background-color: #172333; selection-background-color: #234A7C; selection-color: white; }
QListWidget::item { padding: 8px; border-radius: 5px; } QListWidget::item:selected { background: #224B8F; color: white; }
QHeaderView::section { background: #192638; border: 0; border-bottom: 1px solid #2B3A4D; padding: 8px; font-weight: 600; }
QTableWidget::item { padding: 6px; border-bottom: 1px solid #253346; }
QLineEdit, QComboBox { background: #121D2A; border: 1px solid #29394D; border-radius: 6px; padding: 7px; }
QComboBox { min-height: 18px; }
QLineEdit:focus, QComboBox:focus { border: 1px solid #4C8DFF; }
QComboBox QAbstractItemView { background: #172333; selection-background-color: #4C8DFF; }
QStatusBar { background: #0D1520; border-top: 1px solid #243142; }
#statsPanel, #previewCard { background: #141F2D; border: 1px solid #273547; border-radius: 7px; }
#fileTab { background:#172333; border-radius:6px; padding:10px 16px; font-weight:600; }
#cardTitle { font-size:10px; font-weight:700; color:#B7C3D4; } #muted { color:#8492A6; }
#toast { background: #172333; border: 1px solid #4C8DFF; border-radius: 8px; padding: 10px 18px; color: white; }
QProgressBar { border: 0; border-radius: 6px; background: #192638; text-align: center; height: 14px; }
QProgressBar::chunk { background: #4C8DFF; border-radius: 6px; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.documents = []; self.paths = []; self.worker = None; self.export_after_parse = False
        self.selected_folder = None; self.parse_errors = []
        self.pool = QThreadPool.globalInstance(); self.settings_store = QSettings("XMLTools", "Reference Tagger")
        self.setWindowTitle("XML Tagger Pro"); self.resize(1440, 900); self.setMinimumSize(1050, 680)
        self.setStyleSheet(STYLE)
        self.toolbar = AppToolBar(); self.addToolBar(self.toolbar)
        self.sidebar = Sidebar(); self.preview = PreviewPanel()
        central = QWidget(); body = QHBoxLayout(central); body.setContentsMargins(0, 0, 0, 0); body.setSpacing(0)
        body.addWidget(self.sidebar); right = QWidget(); right_layout = QVBoxLayout(right); right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.preview, 1); body.addWidget(right, 1)
        self.setCentralWidget(central); self.setStatusBar(QStatusBar()); self.statusBar().showMessage("Ready")
        self.toast = QLabel(self); self.toast.setObjectName("toast"); self.toast.hide()
        self.sidebar.document_selected.connect(self.show_document); self.preview.data_changed.connect(self.update_stats)
        self.toolbar.select_file.connect(self.select_file); self.toolbar.select_folder.connect(self.select_folder)
        self.toolbar.refresh.connect(self.refresh); self.toolbar.process.connect(self.process_and_save)
        self.toolbar.settings.connect(self.show_settings); self.toolbar.about.connect(self.show_about)

    def select_file(self):
        initial = self.settings_store.value("lastFolder", str(Path.home()))
        filename, _ = QFileDialog.getOpenFileName(self, "Select XML", initial, "XML files (*.xml)")
        if filename:
            self.selected_folder = None; self.paths = [Path(filename)]
            self.settings_store.setValue("lastFolder", str(Path(filename).parent)); self.load_documents()

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select XML folder", self.settings_store.value("lastFolder", str(Path.home())))
        if folder:
            root = Path(folder).resolve(); self.selected_folder = root
            self.paths = sorted(
                p for p in root.rglob("*.xml")
                if "output" not in {part.casefold() for part in p.relative_to(root).parts[:-1]}
            )
            self.settings_store.setValue("lastFolder", folder)
            if not self.paths: self.notify("No XML files found", error=True)
            else: self.load_documents()

    def refresh(self):
        """Return the application to a completely fresh session."""
        if self.worker and hasattr(self.worker, "cancel"):
            self.worker.cancel()
            # Ignore late signals from work that was active during the reset.
            for signal in (self.worker.signals.result, self.worker.signals.error, self.worker.signals.finished):
                try: signal.disconnect()
                except RuntimeError: pass
        if hasattr(self, "progress"): self.progress.close()
        self.documents = []; self.paths = []; self.selected_folder = None
        self.parse_errors = []; self.export_after_parse = False; self.worker = None
        self.sidebar.search.clear(); self.sidebar.set_documents([]); self.preview.filter.setCurrentIndex(0)
        self.preview.auto.setChecked(True); self.preview.set_document(None); self.update_stats()
        self.toast.hide(); self.statusBar().showMessage("Ready — select an XML file or folder")

    def load_documents(self, *, export_after=False):
        if not self.paths: self.notify("Select an XML file or folder first", error=True); return
        self.export_after_parse = export_after; self.parse_errors = []
        self.progress = ProgressDialog(self); self.worker = BatchParseWorker(self.paths, parse_document)
        self.worker.signals.progress.connect(self.progress.update_progress); self.worker.signals.result.connect(self._loaded)
        self.worker.signals.error.connect(self._record_parse_error)
        self.worker.signals.finished.connect(self.progress.accept); self.progress.rejected.connect(self.worker.cancel)
        self.pool.start(self.worker); self.progress.show(); self.statusBar().showMessage("Processing…")

    def _loaded(self, documents):
        self.documents = documents; self.sidebar.set_documents(documents); self.update_stats()
        if self.parse_errors:
            message = f"Loaded {len(documents)} file(s); skipped {len(self.parse_errors)} malformed XML file(s)"
            self.notify(message, error=True)
        else:
            self.notify(f"{len(documents)} XML file(s) parsed")
        self.statusBar().showMessage(f"{len(documents)} file(s) loaded")
        if self.export_after_parse:
            self.export_after_parse = False
            QTimer.singleShot(0, self._export_documents)

    def _record_parse_error(self, message):
        self.parse_errors.append(message)
        self.statusBar().showMessage(f"Skipping malformed XML ({len(self.parse_errors)} so far)")

    def process_and_save(self):
        """Save reviewed parsing results when the toolbar Process is clicked."""
        if self.documents:
            self._export_documents()
        elif self.paths:
            self.load_documents(export_after=True)
        else:
            self.notify("Select an XML file or folder first", error=True)

    def _export_documents(self):
        if not self.documents:
            self.notify("Nothing to process", True); return
        output_dir = (self.selected_folder or self.documents[0].path.parent) / "output"
        exporter = lambda document: export_document(document, output_dir)
        self.progress = ProgressDialog(self); self.progress.setWindowTitle("Saving parsed XML")
        self.worker = BatchExportWorker(self.documents, exporter)
        self.worker.signals.progress.connect(self.progress.update_progress)
        self.worker.signals.result.connect(lambda outputs: self._export_finished(outputs, output_dir))
        self.worker.signals.error.connect(lambda message: self.notify("Processing failed: " + message, True))
        self.worker.signals.finished.connect(self.progress.accept); self.progress.rejected.connect(self.worker.cancel)
        self.pool.start(self.worker); self.progress.show(); self.statusBar().showMessage("Saving parsed XML…")

    def _export_finished(self, outputs, output_dir):
        self.notify(f"Saved {len(outputs)} file(s) to {output_dir}")

    def show_document(self, index):
        self.preview.set_document(self.documents[index] if 0 <= index < len(self.documents) else None)

    def update_stats(self):
        items = [item for document in self.documents for item in document.items]
        values = {
            "Files Loaded": len(self.documents), "Authors Found": sum(i.selected_tag in {"given-names", "surname"} for i in items),
            "Collaborations": sum(i.selected_tag == "collab" for i in items),
            "Unknown Tags": sum(i.selected_tag == "unknown" for i in items), "Corrections Made": sum(i.corrected for i in items),
        }
        self.sidebar.update_stats(values)

    def notify(self, text, error=False):
        self.toast.setText(("✕  " if error else "✓  ") + text); self.toast.adjustSize()
        self.toast.move(self.width() - self.toast.width() - 24, self.height() - self.toast.height() - 48); self.toast.show(); self.toast.raise_()
        QTimer.singleShot(3500, self.toast.hide); self.statusBar().showMessage(text, 5000)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.toast.isVisible(): self.toast.move(self.width() - self.toast.width() - 24, self.height() - self.toast.height() - 48)

    def show_settings(self):
        QMessageBox.information(self, "Settings", "Exports are always written to an output folder beside each source file.\nOriginal XML files are never modified.")

    def show_about(self):
        QMessageBox.about(self, "About XML Reference Tagger", "<h3>XML Reference Tagger</h3><p>A byte-preserving JATS author review and tagging utility.</p><p>Built with Python and Qt 6.</p>")
