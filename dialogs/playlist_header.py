from typing import Dict
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QLineEdit, QCheckBox, QListWidget,
    QPushButton, QTableWidget, QTableWidgetItem,
    QInputDialog, QMessageBox, QDialogButtonBox
)
from PyQt6.QtCore import Qt

from widgets.enhanced_text_edit import EnhancedTextEdit
from utilities.playlist_header_manager import PlaylistHeaderManager


class PlaylistHeaderDialog(QDialog):
    def __init__(self, header_manager: PlaylistHeaderManager, parent=None):
        super().__init__(parent)
        self.header_manager = header_manager
        self.setWindowTitle("Менеджер заголовка плейлиста")
        self.resize(600, 400)
        
        self._setup_ui()
        self._load_current_settings()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        general_group = QGroupBox("Основные настройки")
        general_layout = QFormLayout(general_group)
        
        self.playlist_name_edit = QLineEdit()
        general_layout.addRow("Название плейлиста:", self.playlist_name_edit)
        
        self.include_extm3u_check = QCheckBox("Включить #EXTM3U заголовок")
        self.include_extm3u_check.setChecked(True)
        general_layout.addRow(self.include_extm3u_check)
        
        layout.addWidget(general_group)
        
        epg_group = QGroupBox("Источники EPG (Electronic Program Guide)")
        epg_layout = QVBoxLayout(epg_group)
        
        self.epg_list = QListWidget()
        epg_layout.addWidget(self.epg_list)
        
        epg_btn_layout = QHBoxLayout()
        
        self.add_epg_btn = QPushButton("Добавить")
        self.add_epg_btn.clicked.connect(self._add_epg_source)
        
        self.edit_epg_btn = QPushButton("Редактировать")
        self.edit_epg_btn.clicked.connect(self._edit_epg_source)
        
        self.remove_epg_btn = QPushButton("Удалить")
        self.remove_epg_btn.clicked.connect(self._remove_epg_source)
        
        epg_btn_layout.addWidget(self.add_epg_btn)
        epg_btn_layout.addWidget(self.edit_epg_btn)
        epg_btn_layout.addWidget(self.remove_epg_btn)
        
        epg_layout.addLayout(epg_btn_layout)
        
        layout.addWidget(epg_group)
        
        custom_group = QGroupBox("Пользовательские атрибуты")
        custom_layout = QVBoxLayout(custom_group)
        
        self.custom_attrs_table = QTableWidget()
        self.custom_attrs_table.setColumnCount(2)
        self.custom_attrs_table.setHorizontalHeaderLabels(["Ключ", "Значение"])
        self.custom_attrs_table.horizontalHeader().setStretchLastSection(True)
        custom_layout.addWidget(self.custom_attrs_table)
        
        custom_btn_layout = QHBoxLayout()
        
        self.add_attr_btn = QPushButton("Добавить")
        self.add_attr_btn.clicked.connect(self._add_custom_attribute)
        
        self.edit_attr_btn = QPushButton("Редактировать")
        self.edit_attr_btn.clicked.connect(self._edit_custom_attribute)
        
        self.remove_attr_btn = QPushButton("Удалить")
        self.remove_attr_btn.clicked.connect(self._remove_custom_attribute)
        
        custom_btn_layout.addWidget(self.add_attr_btn)
        custom_btn_layout.addWidget(self.edit_attr_btn)
        custom_btn_layout.addWidget(self.remove_attr_btn)
        
        custom_layout.addLayout(custom_btn_layout)
        
        layout.addWidget(custom_group)
        
        preview_group = QGroupBox("Предпросмотр заголовка")
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_text = EnhancedTextEdit()
        self.preview_text.setMaximumHeight(100)
        self.preview_text.setReadOnly(True)
        preview_layout.addWidget(self.preview_text)
        
        layout.addWidget(preview_group)
        
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Reset
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(self._reset_to_default)
        
        layout.addWidget(button_box)
    
    def _load_current_settings(self):
        self.playlist_name_edit.setText(self.header_manager.playlist_name)
        
        self.epg_list.clear()
        for epg_source in self.header_manager.epg_sources:
            self.epg_list.addItem(epg_source)
        
        self._update_custom_attrs_table()
        self._update_preview()
    
    def _update_custom_attrs_table(self):
        self.custom_attrs_table.setRowCount(len(self.header_manager.custom_attributes))
        
        for i, (key, value) in enumerate(self.header_manager.custom_attributes.items()):
            self.custom_attrs_table.setItem(i, 0, QTableWidgetItem(key))
            self.custom_attrs_table.setItem(i, 1, QTableWidgetItem(value))
    
    def _update_preview(self):
        preview_text = self.header_manager.get_header_text()
        self.preview_text.setPlainText(preview_text)
    
    def _add_epg_source(self):
        epg_url, ok = QInputDialog.getText(
            self, "Добавить EPG источник",
            "Введите URL EPG источника:",
            QLineEdit.EchoMode.Normal,
            "http://example.com/epg.xml"
        )
        
        if ok and epg_url:
            self.epg_list.addItem(epg_url)
            self._update_from_ui()
    
    def _edit_epg_source(self):
        current_item = self.epg_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Предупреждение", "Выберите EPG источник для редактирования")
            return
        
        epg_url, ok = QInputDialog.getText(
            self, "Редактировать EPG источник",
            "Введите новый URL EPG источника:",
            QLineEdit.EchoMode.Normal,
            current_item.text()
        )
        
        if ok and epg_url:
            current_item.setText(epg_url)
            self._update_from_ui()
    
    def _remove_epg_source(self):
        current_item = self.epg_list.currentItem()
        if current_item:
            reply = QMessageBox.question(
                self, "Подтверждение",
                f"Удалить EPG источник '{current_item.text()}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                row = self.epg_list.row(current_item)
                self.epg_list.takeItem(row)
                self._update_from_ui()
    
    def _add_custom_attribute(self):
        key, ok1 = QInputDialog.getText(
            self, "Добавить атрибут",
            "Введите ключ атрибута:",
            QLineEdit.EchoMode.Normal
        )
        
        if ok1 and key:
            value, ok2 = QInputDialog.getText(
                self, "Добавить атрибут",
                f"Введите значение для атрибута '{key}':",
                QLineEdit.EchoMode.Normal
            )
            
            if ok2:
                self.header_manager.add_custom_attribute(key, value)
                self._update_custom_attrs_table()
                self._update_preview()
    
    def _edit_custom_attribute(self):
        current_row = self.custom_attrs_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Предупреждение", "Выберите атрибут для редактирования")
            return
        
        key_item = self.custom_attrs_table.item(current_row, 0)
        value_item = self.custom_attrs_table.item(current_row, 1)
        
        if key_item and value_item:
            old_key = key_item.text()
            old_value = value_item.text()
            
            new_key, ok1 = QInputDialog.getText(
                self, "Редактировать атрибут",
                "Введите новый ключ атрибута:",
                QLineEdit.EchoMode.Normal,
                old_key
            )
            
            if ok1 and new_key:
                new_value, ok2 = QInputDialog.getText(
                    self, "Редактировать атрибут",
                    f"Введите новое значение для атрибута '{new_key}':",
                    QLineEdit.EchoMode.Normal,
                    old_value
                )
                
                if ok2:
                    self.header_manager.remove_custom_attribute(old_key)
                    self.header_manager.add_custom_attribute(new_key, new_value)
                    self._update_custom_attrs_table()
                    self._update_preview()
    
    def _remove_custom_attribute(self):
        current_row = self.custom_attrs_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Предупреждение", "Выберите атрибут для удаления")
            return
        
        key_item = self.custom_attrs_table.item(current_row, 0)
        if key_item:
            key = key_item.text()
            reply = QMessageBox.question(
                self, "Подтверждение",
                f"Удалить атрибут '{key}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.header_manager.remove_custom_attribute(key)
                self._update_custom_attrs_table()
                self._update_preview()
    
    def _reset_to_default(self):
        reply = QMessageBox.question(
            self, "Подтверждение",
            "Сбросить все настройки заголовка к значениям по умолчанию?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.playlist_name_edit.clear()
            self.epg_list.clear()
            self.header_manager.custom_attributes.clear()
            self._update_custom_attrs_table()
            self._update_preview()
    
    def _update_from_ui(self):
        epg_sources = []
        for i in range(self.epg_list.count()):
            epg_sources.append(self.epg_list.item(i).text())
        self.header_manager.update_epg_sources(epg_sources)
        
        self.header_manager.set_playlist_name(self.playlist_name_edit.text())
        
        self._update_preview()
    
    def accept(self):
        self._update_from_ui()
        super().accept()