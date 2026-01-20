from typing import List, Dict, Any
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QComboBox, QListWidget, QCheckBox,
    QRadioButton, QPushButton, QLabel, QDialogButtonBox,
    QTableWidget, QTableWidgetItem
)
from PyQt6.QtCore import Qt

from models.channel_data import ChannelData


class CopyMetadataDialog(QDialog):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setWindowTitle("Копирование метаданных между плейлистами")
        self.resize(600, 400)
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        info_label = QLabel("Копирование метаданных из одного плейлиста в другой")
        info_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(info_label)
        
        source_group = QGroupBox("Исходный плейлист (откуда копировать)")
        source_layout = QVBoxLayout(source_group)
        
        self.source_tab_combo = QComboBox()
        source_layout.addWidget(QLabel("Выберите вкладку:"))
        source_layout.addWidget(self.source_tab_combo)
        
        self.source_channels_list = QListWidget()
        self.source_channels_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        source_layout.addWidget(QLabel("Выберите каналы:"))
        source_layout.addWidget(self.source_channels_list)
        
        layout.addWidget(source_group)
        
        target_group = QGroupBox("Целевой плейлист (куда вставить)")
        target_layout = QVBoxLayout(target_group)
        
        self.target_tab_combo = QComboBox()
        target_layout.addWidget(QLabel("Выберите вкладку:"))
        target_layout.addWidget(self.target_tab_combo)
        
        self.target_channels_list = QListWidget()
        self.target_channels_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        target_layout.addWidget(QLabel("Выберите каналы для обновления:"))
        target_layout.addWidget(self.target_channels_list)
        
        layout.addWidget(target_group)
        
        options_group = QGroupBox("Параметры копирования")
        options_layout = QVBoxLayout(options_group)
        
        self.copy_tvg_id_check = QCheckBox("Копировать TVG-ID")
        self.copy_tvg_id_check.setChecked(True)
        options_layout.addWidget(self.copy_tvg_id_check)
        
        self.copy_logo_check = QCheckBox("Копировать логотип")
        self.copy_logo_check.setChecked(True)
        options_layout.addWidget(self.copy_logo_check)
        
        self.copy_group_check = QCheckBox("Копировать группу")
        self.copy_group_check.setChecked(True)
        options_layout.addWidget(self.copy_group_check)
        
        self.copy_user_agent_check = QCheckBox("Копировать User-Agent")
        self.copy_user_agent_check.setChecked(True)
        options_layout.addWidget(self.copy_user_agent_check)
        
        self.copy_headers_check = QCheckBox("Копировать заголовки HTTP")
        self.copy_headers_check.setChecked(True)
        options_layout.addWidget(self.copy_headers_check)
        
        self.match_by_name_radio = QRadioButton("Сопоставлять по названию канала")
        self.match_by_name_radio.setChecked(True)
        options_layout.addWidget(self.match_by_name_radio)
        
        self.match_by_name_group_radio = QRadioButton("Сопоставлять по названию и группе")
        options_layout.addWidget(self.match_by_name_group_radio)
        
        layout.addWidget(options_group)
        
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        preview_btn = QPushButton("Предпросмотр изменений")
        preview_btn.clicked.connect(self._preview_changes)
        button_box.addButton(preview_btn, QDialogButtonBox.ButtonRole.ActionRole)
        
        layout.addWidget(button_box)
        
        self._populate_tab_lists()
        
        self.source_tab_combo.currentIndexChanged.connect(self._update_source_channels)
        self.target_tab_combo.currentIndexChanged.connect(self._update_target_channels)
    
    def _populate_tab_lists(self):
        self.source_tab_combo.clear()
        self.target_tab_combo.clear()
        
        for i in range(self.main_window.tab_widget.count()):
            widget = self.main_window.tab_widget.widget(i)
            tab_name = self.main_window.tab_widget.tabText(i)
            
            if widget in self.main_window.tabs and self.main_window.tabs[widget] is not None:
                self.source_tab_combo.addItem(tab_name, i)
                self.target_tab_combo.addItem(tab_name, i)
        
        if self.source_tab_combo.count() > 0:
            self._update_source_channels()
            self._update_target_channels()
    
    def _update_source_channels(self):
        self.source_channels_list.clear()
        
        index = self.source_tab_combo.currentData()
        if index is None:
            return
        
        widget = self.main_window.tab_widget.widget(index)
        if widget not in self.main_window.tabs:
            return
        
        tab = self.main_window.tabs[widget]
        if tab is None:
            return
        
        for channel in tab.all_channels:
            item = QListWidgetItem(channel.name)
            item.setData(Qt.ItemDataRole.UserRole, channel)
            self.source_channels_list.addItem(item)
    
    def _update_target_channels(self):
        self.target_channels_list.clear()
        
        index = self.target_tab_combo.currentData()
        if index is None:
            return
        
        widget = self.main_window.tab_widget.widget(index)
        if widget not in self.main_window.tabs:
            return
        
        tab = self.main_window.tabs[widget]
        if tab is None:
            return
        
        for channel in tab.all_channels:
            item = QListWidgetItem(channel.name)
            item.setData(Qt.ItemDataRole.UserRole, channel)
            self.target_channels_list.addItem(item)
    
    def _preview_changes(self):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTableWidget, QDialogButtonBox
        
        source_tab_index = self.source_tab_combo.currentData()
        target_tab_index = self.target_tab_combo.currentData()
        
        if source_tab_index is None or target_tab_index is None:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Предупреждение", "Выберите исходную и целевую вкладки")
            return
        
        if source_tab_index == target_tab_index:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Предупреждение", "Исходная и целевая вкладки не должны быть одинаковыми")
            return
        
        source_channels = []
        for item in self.source_channels_list.selectedItems():
            channel = item.data(Qt.ItemDataRole.UserRole)
            if channel:
                source_channels.append(channel)
        
        target_channels = []
        for item in self.target_channels_list.selectedItems():
            channel = item.data(Qt.ItemDataRole.UserRole)
            if channel:
                target_channels.append(channel)
        
        if not source_channels:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Предупреждение", "Выберите каналы в исходном плейлисте")
            return
        
        if not target_channels:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Предупреждение", "Выберите каналы в целевом плейлисте")
            return
        
        preview_dialog = QDialog(self)
        preview_dialog.setWindowTitle("Предпросмотр изменений")
        preview_dialog.resize(800, 600)
        
        layout = QVBoxLayout(preview_dialog)
        
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Название", "TVG-ID", "Логотип", "Группа", "User-Agent"])
        table.setRowCount(len(target_channels))
        
        match_func = None
        if self.match_by_name_radio.isChecked():
            match_func = lambda s, t: s.match_by_name(t)
        else:
            match_func = lambda s, t: s.match_by_name_and_group(t)
        
        for i, target_channel in enumerate(target_channels):
            source_channel = None
            for src_ch in source_channels:
                if match_func(src_ch, target_channel):
                    source_channel = src_ch
                    break
            
            table.setItem(i, 0, QTableWidgetItem(target_channel.name))
            
            if source_channel:
                old_tvg_id = target_channel.tvg_id or ""
                new_tvg_id = source_channel.tvg_id or ""
                if self.copy_tvg_id_check.isChecked() and new_tvg_id and old_tvg_id != new_tvg_id:
                    table.setItem(i, 1, QTableWidgetItem(f"{old_tvg_id} → {new_tvg_id}"))
                else:
                    table.setItem(i, 1, QTableWidgetItem(old_tvg_id))
                
                old_logo = target_channel.tvg_logo or ""
                new_logo = source_channel.tvg_logo or ""
                if self.copy_logo_check.isChecked() and new_logo and old_logo != new_logo:
                    table.setItem(i, 2, QTableWidgetItem(f"{old_logo} → {new_logo}"))
                else:
                    table.setItem(i, 2, QTableWidgetItem(old_logo))
                
                old_group = target_channel.group or ""
                new_group = source_channel.group or ""
                if self.copy_group_check.isChecked() and new_group and old_group != new_group:
                    table.setItem(i, 3, QTableWidgetItem(f"{old_group} → {new_group}"))
                else:
                    table.setItem(i, 3, QTableWidgetItem(old_group))
                
                old_ua = target_channel.user_agent or ""
                new_ua = source_channel.user_agent or ""
                if self.copy_user_agent_check.isChecked() and new_ua and old_ua != new_ua:
                    table.setItem(i, 4, QTableWidgetItem(f"{old_ua} → {new_ua}"))
                else:
                    table.setItem(i, 4, QTableWidgetItem(old_ua))
            else:
                table.setItem(i, 1, QTableWidgetItem(target_channel.tvg_id or ""))
                table.setItem(i, 2, QTableWidgetItem(target_channel.tvg_logo or ""))
                table.setItem(i, 3, QTableWidgetItem(target_channel.group or ""))
                table.setItem(i, 4, QTableWidgetItem(target_channel.user_agent or ""))
        
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(preview_dialog.reject)
        layout.addWidget(button_box)
        
        preview_dialog.exec()
    
    def get_selected_data(self):
        source_tab_index = self.source_tab_combo.currentData()
        target_tab_index = self.target_tab_combo.currentData()
        
        if source_tab_index is None or target_tab_index is None:
            return None
        
        source_channels = []
        for item in self.source_channels_list.selectedItems():
            channel = item.data(Qt.ItemDataRole.UserRole)
            if channel:
                source_channels.append(channel)
        
        target_channels = []
        for item in self.target_channels_list.selectedItems():
            channel = item.data(Qt.ItemDataRole.UserRole)
            if channel:
                target_channels.append(channel)
        
        return {
            'source_tab_index': source_tab_index,
            'target_tab_index': target_tab_index,
            'source_channels': source_channels,
            'target_channels': target_channels,
            'copy_tvg_id': self.copy_tvg_id_check.isChecked(),
            'copy_logo': self.copy_logo_check.isChecked(),
            'copy_group': self.copy_group_check.isChecked(),
            'copy_user_agent': self.copy_user_agent_check.isChecked(),
            'copy_headers': self.copy_headers_check.isChecked(),
            'match_by_name': self.match_by_name_radio.isChecked(),
            'match_by_name_and_group': self.match_by_name_group_radio.isChecked()
        }