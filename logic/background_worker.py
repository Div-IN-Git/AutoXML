#Reusable QRunnable workers. imported only when PySide6 is available.
from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    progress = Signal(int, str)
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class BatchParseWorker(QRunnable):
    def __init__(self, paths, parser):
        super().__init__(); self.paths = list(paths); self.parser = parser
        self.signals = WorkerSignals(); self.cancelled = False

    def cancel(self):
        self.cancelled = True

    @Slot()
    def run(self):
        documents = []
        total = max(1, len(self.paths))
        for position, path in enumerate(self.paths, 1):
            if self.cancelled: break
            self.signals.progress.emit(int(position * 100 / total), path.name)
            try:
                documents.append(self.parser(path))
            except Exception as exc:
                # A single malformed document must not abort folder mode.
                self.signals.error.emit(f"{path}: {exc}")
        self.signals.result.emit(documents)
        self.signals.finished.emit()


class BatchExportWorker(QRunnable):
    def __init__(self, documents, exporter):
        super().__init__(); self.documents = list(documents); self.exporter = exporter
        self.signals = WorkerSignals(); self.cancelled = False

    def cancel(self): self.cancelled = True

    @Slot()
    def run(self):
        outputs = []
        try:
            total = max(1, len(self.documents))
            for position, document in enumerate(self.documents, 1):
                if self.cancelled: break
                self.signals.progress.emit(int(position * 100 / total), document.name)
                outputs.append(self.exporter(document))
            self.signals.result.emit(outputs)
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()
