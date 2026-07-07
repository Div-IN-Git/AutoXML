from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QProgressBar, QVBoxLayout


class ProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Processing XML"); self.setModal(True); self.setMinimumWidth(420)
        layout = QVBoxLayout(self); self.message = QLabel("Preparing…"); self.bar = QProgressBar()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel); buttons.rejected.connect(self.reject)
        layout.addWidget(self.message); layout.addWidget(self.bar); layout.addWidget(buttons)

    def update_progress(self, percent, filename):
        self.bar.setValue(percent); self.message.setText(f"Processing\n{filename}")
