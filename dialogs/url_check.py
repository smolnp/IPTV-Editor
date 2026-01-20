from typing import List, Dict, Any, Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar, 
    QListWidget, QListWidgetItem, QPushButton, 
    QDialogButtonBox, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from utilities.url_checker import URLCheckerWorker


class URLCheckDialog(QDialog):
    url_check_completed = pyqtSignal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Проверка ссылок каналов")
        self.resize(500, 400)
        
        self.urls_to_check: List[str] = []
        self.results: Dict[int, Dict[str, Any]] = {}
        self.checker: Optional[URLCheckerWorker] = None
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        self.info_label = QLabel("Подготовка к проверке...")
        layout.addWidget(self.info_label)
        
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        self.results_list = QListWidget()
        layout.addWidget(self.results_list)
        
        button_box = QDialogButtonBox()
        self.start_btn = QPushButton("Начать проверку")
        self.start_btn.clicked.connect(self.start_checking)
        
        self.stop_btn = QPushButton("Остановить")
        self.stop_btn.clicked.connect(self.stop_checking)
        self.stop_btn.setEnabled(False)
        
        self.close_btn = QPushButton("Закрыть")
        self.close_btn.clicked.connect(self.reject)
        
        self.apply_btn = QPushButton("Применить результаты")
        self.apply_btn.clicked.connect(self.accept)
        self.apply_btn.setEnabled(False)
        
        button_box.addButton(self.start_btn, QDialogButtonBox.ButtonRole.ActionRole)
        button_box.addButton(self.stop_btn, QDialogButtonBox.ButtonRole.ActionRole)
        button_box.addButton(self.apply_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        button_box.addButton(self.close_btn, QDialogButtonBox.ButtonRole.RejectRole)
        
        layout.addWidget(button_box)
    
    def set_urls(self, urls: List[str]):
        self.urls_to_check = urls
        self.info_label.setText(f"Готово к проверке {len(urls)} ссылок")
    
    def start_checking(self):
        if not self.urls_to_check:
            QMessageBox.warning(self, "Предупреждение", "Нет ссылок для проверки")
            return
        
        self.results_list.clear()
        self.results = {}
        self.apply_btn.setEnabled(False)
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.close_btn.setEnabled(False)
        
        self.checker = URLCheckerWorker(self.urls_to_check)
        self.checker.progress.connect(self.update_progress)
        self.checker.url_checked.connect(self.on_url_checked)
        self.checker.finished.connect(self.on_checking_finished)
        self.checker.error.connect(self.on_checking_error)
        
        self.checker.start()
    
    def stop_checking(self):
        if self.checker and self.checker.isRunning():
            self.checker.stop()
            if not self.checker.wait(2000):
                self.checker.terminate()
                self.checker.wait()
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.close_btn.setEnabled(True)
        self.apply_btn.setEnabled(True)
        self.info_label.setText("Проверка остановлена")
    
    def update_progress(self, current: int, total: int, status: str):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.info_label.setText(f"{status} - {current}/{total}")
    
    def on_url_checked(self, index: int, success: bool, message: str):
        url = self.urls_to_check[index] if index < len(self.urls_to_check) else ""
        url_short = url[:50] + "..." if len(url) > 50 else url
        
        if success is None:
            item = QListWidgetItem(f"⚠ {url_short}")
            item.setForeground(QColor("orange"))
            item.setToolTip(f"{url}\n{message}")
        elif success:
            item = QListWidgetItem(f"✓ {url_short}")
            item.setForeground(QColor("green"))
            item.setToolTip(f"{url}\n{message}")
        else:
            item = QListWidgetItem(f"✗ {url_short}")
            item.setForeground(QColor("red"))
            item.setToolTip(f"{url}\n{message}")
        
        self.results_list.addItem(item)
    
    def on_checking_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.close_btn.setEnabled(True)
        self.apply_btn.setEnabled(True)
        
        if self.checker:
            self.results = self.checker.get_results()
        
        working = sum(1 for r in self.results.values() if r.get('success') is True)
        not_working = sum(1 for r in self.results.values() if r.get('success') is False)
        unknown = sum(1 for r in self.results.values() if r.get('success') is None)
        
        self.info_label.setText(
            f"Проверка завершена. "
            f"Работают: {working}, не работают: {not_working}, неизвестно: {unknown}"
        )
    
    def on_checking_error(self, error_message: str):
        QMessageBox.critical(self, "Ошибка", error_message)
        self.on_checking_finished()
    
    def get_results(self) -> Dict[int, Dict[str, Any]]:
        return self.results
    
    def accept(self):
        self.url_check_completed.emit(self.results)
        super().accept()
    
    def reject(self):
        self.url_check_completed.emit(self.results)
        super().reject()
    
    def closeEvent(self, event):
        self.stop_checking()
        event.accept()