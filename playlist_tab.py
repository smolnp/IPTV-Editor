import os
import re
import csv
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidgetItem, QAbstractItemView,
    QHeaderView, QMessageBox, QInputDialog, QDialog,
    QTableWidget, QLabel, QFrame, QLineEdit, QDialogButtonBox,
    QListWidgetItem, QCheckBox, QHBoxLayout, QPushButton,
    QFileDialog, QGroupBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QKeySequence, QColor, QShortcut
import chardet

from models.channel_data import ChannelData
from widgets.channel_table import ChannelTableWidget, EditableTableWidgetItem
from utilities.playlist_header_manager import PlaylistHeaderManager
from utilities.blacklist_manager import BlacklistManager
from utilities.undo_redo_manager import UndoRedoManager
from dialogs.url_check import URLCheckDialog
from dialogs.playlist_header import PlaylistHeaderDialog
from dialogs.edit_groups_order import EditGroupsOrderDialog
from dialogs.remove_metadata import RemoveMetadataDialog
import logging

logger = logging.getLogger(__name__)


class PlaylistTab(QWidget):
    channel_selected = pyqtSignal(ChannelData)
    undo_state_changed = pyqtSignal(bool, bool)
    info_changed = pyqtSignal(str)
    
    def __init__(self, filepath: str = None, parent=None, blacklist_manager: BlacklistManager = None):
        super().__init__(parent)
        self.filepath = filepath
        self.all_channels: List[ChannelData] = []
        self.filtered_channels: List[ChannelData] = []
        self.selected_channels: List[ChannelData] = []
        self.current_channel: Optional[ChannelData] = None
        self.modified = False
        self.blacklist_manager = blacklist_manager
        self.parent_window = None
        
        self.header_manager = PlaylistHeaderManager()
        self.is_sorted_mode = False
        
        parent_widget = parent
        while parent_widget and not hasattr(parent_widget, 'statusBar'):
            parent_widget = parent_widget.parent()
        self.parent_window = parent_widget
        
        self.undo_manager = UndoRedoManager()
        
        self._setup_ui()
        self._setup_shortcuts()
        
        if filepath and os.path.exists(filepath):
            self._load_file(filepath)
        else:
            self._save_state("Инициализация")
            self._update_info()
    
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        self.table = ChannelTableWidget()
        self._setup_table()
        
        main_layout.addWidget(self.table)
        
        self.table.cell_edited.connect(self._on_cell_edited)
        self.table.url_check_requested.connect(self._check_single_url)
        self.table.edit_user_agent_requested.connect(self._edit_user_agent)
        self.table.copy_channel_requested.connect(self._copy_channel)
        self.table.copy_selected_channels_requested.connect(self._copy_selected_channels)
        self.table.copy_metadata_requested.connect(self._copy_metadata)
        self.table.copy_selected_metadata_requested.connect(self._copy_selected_metadata)
        self.table.paste_channel_requested.connect(self._paste_channel)
        self.table.paste_selected_channels_requested.connect(self._paste_selected_channels)
        self.table.paste_metadata_requested.connect(self._paste_metadata)
        self.table.paste_selected_metadata_requested.connect(self._paste_selected_metadata)
        self.table.rename_groups_requested.connect(self._rename_groups)
        self.table.add_to_blacklist_requested.connect(self._add_to_blacklist)
        self.table.add_selected_to_blacklist_requested.connect(self._add_selected_to_blacklist)
        self.table.check_single_url_requested.connect(self._check_single_url)
        self.table.check_selected_urls_requested.connect(self._check_selected_urls)
        self.table.move_channel_up_requested.connect(self._move_channel_up)
        self.table.move_selected_up_requested.connect(self._move_selected_up)
        self.table.move_channel_down_requested.connect(self._move_channel_down)
        self.table.move_selected_down_requested.connect(self._move_selected_down)
        self.table.delete_channel_requested.connect(self._delete_channel)
        self.table.delete_selected_channels_requested.connect(self._delete_selected_channels)
        self.table.new_channel_requested.connect(self._new_channel)
    
    def _setup_table(self):
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["№", "Статус", "Название", "Группа", "TVG-ID", "Логотип", "URL"])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)
        
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 60)
        self.table.setColumnWidth(2, 250)
        self.table.setColumnWidth(3, 150)
        self.table.setColumnWidth(4, 150)
        self.table.setColumnWidth(5, 200)
        self.table.setColumnWidth(6, 400)
        
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.doubleClicked.connect(self._on_double_click)
    
    def _setup_shortcuts(self):
        shortcuts = {
            QKeySequence("Ctrl+S"): self._save_changes,
            QKeySequence("Delete"): self._delete_channel,
            QKeySequence("Ctrl+Shift+Delete"): self._delete_selected_channels,
            QKeySequence("Ctrl+Z"): self._undo,
            QKeySequence("Ctrl+Y"): self._redo,
            QKeySequence("Ctrl+A"): self._select_all_channels,
            QKeySequence("Ctrl+C"): self._copy_channel,
            QKeySequence("Ctrl+V"): self._paste_channel,
            QKeySequence("Ctrl+Up"): self._move_channel_up,
            QKeySequence("Ctrl+Down"): self._move_channel_down,
            QKeySequence("Ctrl+Shift+Up"): self._move_selected_up,
            QKeySequence("Ctrl+Shift+Down"): self._move_selected_down,
            QKeySequence("F2"): self._edit_current_cell,
        }
        
        for key, slot in shortcuts.items():
            shortcut = QShortcut(key, self)
            shortcut.activated.connect(slot)
    
    def _load_file(self, filepath: str):
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            self.header_manager.parse_header(content)
            
            lines = content.split('\n')
            
            start_index = 0
            for i, line in enumerate(lines):
                if line.startswith('#EXTINF:'):
                    start_index = i
                    break
            
            self._parse_m3u('\n'.join(lines[start_index:]))
            
            if self.blacklist_manager:
                original_count = len(self.all_channels)
                filtered, removed = self.blacklist_manager.filter_channels(self.all_channels)
                self.all_channels = filtered
                
                if removed > 0:
                    QMessageBox.information(self, "Информация", 
                                          f"При загрузке удалено {removed} каналов из чёрного списка")
            
            self._apply_filter()
            self._update_info()
            
            self.modified = False
            self._update_modified_status()
            
            self._save_state("Загрузка файла")
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить файл:\n{str(e)}")
    
    def _parse_m3u(self, content: str):
        self.all_channels.clear()
        
        lines = content.splitlines()
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                i += 1
                continue
            
            if line.startswith('#EXTINF:'):
                channel = ChannelData()
                channel.extinf = line
                
                if ',' in line:
                    parts = line.split(',', 1)
                    channel.name = parts[1].strip()
                
                attrs_part = line.split(',')[0] if ',' in line else line
                
                tvg_id_match = re.search(r'tvg-id="([^"]*)"', attrs_part)
                if tvg_id_match:
                    channel.tvg_id = tvg_id_match.group(1)
                
                logo_match = re.search(r'tvg-logo="([^"]*)"', attrs_part)
                if logo_match:
                    channel.tvg_logo = logo_match.group(1)
                
                group_match = re.search(r'group-title="([^"]*)"', attrs_part)
                if group_match:
                    channel.group = group_match.group(1)
                else:
                    channel.group = "Без группы"
                
                j = i + 1
                has_url = False
                url_lines = []
                extvlcopt_lines = []
                
                while j < len(lines):
                    next_line = lines[j].strip()
                    if not next_line:
                        j += 1
                        continue
                    
                    if next_line.startswith('#EXTINF:'):
                        break
                    
                    if next_line.startswith('#'):
                        extvlcopt_lines.append(next_line)
                    else:
                        url_lines.append(next_line)
                        has_url = True
                        break
                    
                    j += 1
                
                if has_url:
                    j += 1
                    
                    while j < len(lines):
                        next_line = lines[j].strip()
                        if not next_line:
                            j += 1
                            continue
                        
                        if next_line.startswith('#EXTINF:'):
                            break
                        
                        if next_line.startswith('#'):
                            extvlcopt_lines.append(next_line)
                        else:
                            break
                        
                        j += 1
                else:
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                
                if url_lines:
                    channel.url = '\n'.join(url_lines)
                    channel.has_url = True
                else:
                    channel.url = ""
                    channel.has_url = False
                
                channel.extvlcopt_lines = extvlcopt_lines
                channel.parse_extvlcopt_headers()
                if 'User-Agent' in channel.extra_headers:
                    channel.user_agent = channel.extra_headers['User-Agent']
                
                self.all_channels.append(channel)
                i = j
            else:
                i += 1
        
        self.filtered_channels = self.all_channels.copy()
    
    def save_to_file(self, filepath: str = None) -> bool:
        if filepath:
            self.filepath = filepath
        
        if not self.filepath:
            return False
        
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                header_text = self.header_manager.get_header_text()
                if header_text:
                    f.write(header_text)
                else:
                    f.write('#EXTM3U\n\n')
                
                for channel in self.all_channels:
                    f.write(channel.extinf + '\n')
                    
                    for extra_line in channel.extvlcopt_lines:
                        f.write(extra_line + '\n')
                    
                    if channel.url:
                        f.write(channel.url + '\n')
                    else:
                        f.write('\n')
            
            self.modified = False
            self._update_modified_status()
            return True
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить файл:\n{str(e)}")
            return False
    
    def _apply_filter(self):
        parent = self.parent_window
        
        if parent and hasattr(parent, 'search_edit') and hasattr(parent, 'group_combo'):
            search_text = parent.search_edit.text().lower() if parent.search_edit else ""
            group_filter = parent.group_combo.currentText() if parent.group_combo else "Все группы"
        else:
            search_text = ""
            group_filter = "Все группы"
        
        if group_filter == "Все группы":
            self.filtered_channels = self.all_channels.copy()
        else:
            self.filtered_channels = [ch for ch in self.all_channels if ch.group == group_filter]
        
        if search_text:
            self.filtered_channels = [
                ch for ch in self.filtered_channels
                if (search_text in ch.name.lower() or 
                    search_text in ch.group.lower() or
                    search_text in (ch.tvg_id or "").lower() or
                    search_text in ch.url.lower())
            ]
        
        self._update_table()
        self._update_info()
    
    def _update_table(self):
        selected_rows = []
        if self.table.selectedItems():
            selected_rows = list(set(item.row() for item in self.table.selectedItems()))
        
        scroll_value = self.table.verticalScrollBar().value()
        
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        
        try:
            row_count = len(self.filtered_channels)
            self.table.setRowCount(row_count)
            
            for i, channel in enumerate(self.filtered_channels):
                self._update_table_row(i, channel)
            
            if selected_rows:
                for row in selected_rows:
                    if row < self.table.rowCount():
                        self.table.selectRow(row)
            
            self.table.verticalScrollBar().setValue(scroll_value)
            
        finally:
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)
        
        self._update_info()
    
    def _update_table_row(self, row: int, channel: ChannelData):
        if row >= self.table.rowCount():
            return
        
        self.table.blockSignals(True)
        try:
            number_item = QTableWidgetItem(str(row + 1))
            number_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if self.is_sorted_mode:
                number_item.setBackground(channel.get_change_color())
            self.table.setItem(row, 0, number_item)
            
            status_item = QTableWidgetItem(channel.get_status_icon())
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setForeground(channel.get_status_color())
            status_item.setToolTip(channel.get_status_tooltip())
            self.table.setItem(row, 1, status_item)
            
            self.table.setItem(row, 2, EditableTableWidgetItem(channel.name))
            self.table.setItem(row, 3, EditableTableWidgetItem(channel.group))
            self.table.setItem(row, 4, EditableTableWidgetItem(channel.tvg_id))
            self.table.setItem(row, 5, EditableTableWidgetItem(channel.tvg_logo))
            
            url_item = EditableTableWidgetItem(channel.url)
            if channel.user_agent:
                url_item.setForeground(QColor("green"))
                url_item.setToolTip(f"User Agent: {channel.user_agent}\n{channel.url}")
            self.table.setItem(row, 6, url_item)
        finally:
            self.table.blockSignals(False)
    
    def _update_info(self):
        total = len(self.all_channels)
        with_url = sum(1 for ch in self.all_channels if ch.has_url and ch.url and ch.url.strip())
        without_url = total - with_url
        
        working = sum(1 for ch in self.all_channels if ch.url_status is True)
        not_working = sum(1 for ch in self.all_channels if ch.url_status is False)
        unknown = sum(1 for ch in self.all_channels if (ch.url_status is None) and ch.has_url and ch.url and ch.url.strip())
        
        if self.is_sorted_mode:
            moved_up = sum(1 for ch in self.all_channels if ch.sort_change < 0)
            moved_down = sum(1 for ch in self.all_channels if ch.sort_change > 0)
            same_position = sum(1 for ch in self.all_channels if ch.sort_change == 0)
            
            info_text = (f"Каналов: {total} | С URL: {with_url} | Работают: {working} | "
                        f"Не работают: {not_working} | Не проверялись: {unknown} | "
                        f"Сортировка: ↑{moved_up} ↓{moved_down} ={same_position}")
        else:
            info_text = f"Каналов: {total} | С URL: {with_url} | Работают: {working} | Не работают: {not_working} | Не проверялись: {unknown}"
        
        self.info_changed.emit(info_text)
    
    def _save_state(self, description: str = ""):
        self.undo_manager.save_state(self.all_channels, description)
        self.undo_state_changed.emit(
            self.undo_manager.can_undo(),
            self.undo_manager.can_redo()
        )
    
    def _undo(self):
        state = self.undo_manager.undo()
        if state:
            self.all_channels = [ChannelData.from_dict(ch) for ch in state['channels']]
            
            self.current_channel = None
            self.selected_channels = []
            
            self._apply_filter()
            self._update_info()
            
            self.undo_state_changed.emit(
                self.undo_manager.can_undo(),
                self.undo_manager.can_redo()
            )
            
            self.modified = True
            self._update_modified_status()
            
            if self.parent_window and hasattr(self.parent_window, '_update_group_filter'):
                self.parent_window._update_group_filter()
    
    def _redo(self):
        state = self.undo_manager.redo()
        if state:
            self.all_channels = [ChannelData.from_dict(ch) for ch in state['channels']]
            
            self.current_channel = None
            self.selected_channels = []
            
            self._apply_filter()
            self._update_info()
            
            self.undo_state_changed.emit(
                self.undo_manager.can_undo(),
                self.undo_manager.can_redo()
            )
            
            self.modified = True
            self._update_modified_status()
            
            if self.parent_window and hasattr(self.parent_window, '_update_group_filter'):
                self.parent_window._update_group_filter()
    
    def _update_modified_status(self):
        self._update_info()
    
    def _on_cell_edited(self, row: int, column: int, new_value: str):
        if 0 <= row < len(self.filtered_channels):
            channel = self.filtered_channels[row]
            
            self.table.blockSignals(True)
            try:
                if column == 2:
                    channel.name = new_value.strip()
                    channel.update_extinf()
                elif column == 3:
                    channel.group = new_value.strip() or "Без группы"
                    channel.update_extinf()
                elif column == 4:
                    channel.tvg_id = new_value.strip()
                    channel.update_extinf()
                elif column == 5:
                    channel.tvg_logo = new_value.strip()
                    channel.update_extinf()
                elif column == 6:  # URL
                    channel.url = new_value.strip()
                    channel.has_url = bool(channel.url)
                    channel.url_status = None
                    channel.url_check_time = None
                
                self._update_table_row(row, channel)
            finally:
                self.table.blockSignals(False)
            
            self._save_state("Редактирование в таблице")
            
            self.modified = True
            self._update_modified_status()
            
            self._update_info()
    
    def _on_selection_changed(self):
        selected_items = self.table.selectedItems()
        if not selected_items:
            self.selected_channels = []
            if hasattr(self, 'undo_state_changed'):
                self.undo_state_changed.emit(
                    self.undo_manager.can_undo(),
                    self.undo_manager.can_redo()
                )
            return
        
        rows = set()
        for item in selected_items:
            rows.add(item.row())
        
        self.selected_channels = []
        for row in sorted(rows):
            if 0 <= row < len(self.filtered_channels):
                channel = self.filtered_channels[row]
                self.selected_channels.append(channel)
                self.current_channel = channel
        
        if hasattr(self, 'undo_state_changed'):
            self.undo_state_changed.emit(
                self.undo_manager.can_undo(),
                self.undo_manager.can_redo()
            )
    
    def _on_double_click(self, index):
        if index.isValid():
            self.table.edit(index)
        self._on_selection_changed()
    
    def _edit_user_agent(self, row: int):
        if 0 <= row < len(self.filtered_channels):
            channel = self.filtered_channels[row]
            
            current_ua = channel.user_agent or ""
            new_ua, ok = QInputDialog.getText(
                self, "Редактирование User Agent",
                "Введите User Agent для канала:",
                QLineEdit.EchoMode.Normal,
                current_ua
            )
            
            if ok:
                self._save_state("Изменение User Agent")
                
                channel.user_agent = new_ua.strip()
                if channel.user_agent:
                    channel.extra_headers['User-Agent'] = channel.user_agent
                elif 'User-Agent' in channel.extra_headers:
                    del channel.extra_headers['User-Agent']
                channel.update_extvlcopt_from_headers()
                
                self._update_table_row(row, channel)
                self.modified = True
                self._update_modified_status()
                
                self._show_status_message(f"User Agent обновлен для канала '{channel.name}'", 3000)
    
    def _show_status_message(self, message: str, timeout: int = 3000):
        if self.parent_window and hasattr(self.parent_window, 'statusBar'):
            self.parent_window.statusBar().showMessage(message, timeout)
    
    def _new_channel(self):
        self._save_state("Создание нового канала")
        
        channel = ChannelData()
        channel.name = "Новый канал"
        channel.group = "Без группы"
        channel.update_extinf()
        
        self.all_channels.append(channel)
        
        self._apply_filter()
        
        if self.parent_window and hasattr(self.parent_window, '_update_group_filter'):
            self.parent_window._update_group_filter()
        
        self.modified = True
        self._update_modified_status()
        
        self.table.setCurrentCell(len(self.filtered_channels) - 1, 2)
        self.table.edit(self.table.currentIndex())
        
        self._show_status_message("Создан новый канал", 2000)
    
    def _copy_channel(self):
        if self.current_channel:
            parent = self.parent_window
            if parent and hasattr(parent, 'copied_channel'):
                parent.copied_channel = self.current_channel.copy()
                self._show_status_message(f"Канал '{self.current_channel.name}' скопирован в буфер", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Выберите канал для копирования")
    
    def _copy_selected_channels(self):
        if not self.selected_channels:
            QMessageBox.warning(self, "Предупреждение", "Выберите каналы для копирования")
            return
        
        parent = self.parent_window
        if parent and hasattr(parent, 'copied_channels'):
            parent.copied_channels = [ch.copy() for ch in self.selected_channels]
            self._show_status_message(f"Скопировано {len(self.selected_channels)} каналов в буфер", 3000)
    
    def _copy_metadata(self):
        if self.current_channel:
            parent = self.parent_window
            if parent and hasattr(parent, 'copied_metadata'):
                parent.copied_metadata = self.current_channel.copy_metadata_only()
                self._show_status_message(f"Метаданные канала '{self.current_channel.name}' скопированы", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Выберите канал для копирования метаданных")
    
    def _copy_selected_metadata(self):
        if not self.selected_channels:
            QMessageBox.warning(self, "Предупреждение", "Выберите каналы для копирования метаданных")
            return
        
        parent = self.parent_window
        if parent and hasattr(parent, 'copied_metadata_list'):
            parent.copied_metadata_list = [ch.copy_metadata_only() for ch in self.selected_channels]
            self._show_status_message(f"Метаданные {len(self.selected_channels)} каналов скопированы", 3000)
    
    def _paste_channel(self):
        parent = self.parent_window
        
        if not parent or not hasattr(parent, 'copied_channel') or not parent.copied_channel:
            QMessageBox.warning(self, "Предупреждение", "Нет скопированного канала")
            return
        
        self._save_state("Вставка канала")
        
        channel = parent.copied_channel.copy()
        
        if self.current_channel:
            try:
                idx = self.all_channels.index(self.current_channel) + 1
                self.all_channels.insert(idx, channel)
            except ValueError:
                self.all_channels.append(channel)
        else:
            self.all_channels.append(channel)
        
        self._apply_filter()
        
        if self.parent_window and hasattr(self.parent_window, '_update_group_filter'):
            self.parent_window._update_group_filter()
        
        self.modified = True
        self._update_modified_status()
        
        self._show_status_message("Канал вставлен из буфера", 3000)
    
    def _paste_selected_channels(self):
        parent = self.parent_window
        
        if not parent or not hasattr(parent, 'copied_channels') or not parent.copied_channels:
            QMessageBox.warning(self, "Предупреждение", "Нет скопированных каналов")
            return
        
        self._save_state("Вставка нескольких каналов")
        
        for channel in parent.copied_channels:
            new_channel = channel.copy()
            
            if self.current_channel:
                try:
                    idx = self.all_channels.index(self.current_channel) + 1
                    self.all_channels.insert(idx, new_channel)
                except ValueError:
                    self.all_channels.append(new_channel)
            else:
                self.all_channels.append(new_channel)
        
        self._apply_filter()
        
        if self.parent_window and hasattr(self.parent_window, '_update_group_filter'):
            self.parent_window._update_group_filter()
        
        self.modified = True
        self._update_modified_status()
        
        self._show_status_message(f"Вставлено {len(parent.copied_channels)} каналов из буфера", 3000)
    
    def _paste_metadata(self):
        parent = self.parent_window
        
        if not parent or not hasattr(parent, 'copied_metadata') or not parent.copied_metadata:
            QMessageBox.warning(self, "Предупреждение", "Нет скопированных метаданных")
            return
        
        if not self.current_channel:
            QMessageBox.warning(self, "Предупреждение", "Выберите канал для вставки метаданных")
            return
        
        self._save_state("Вставка метаданных")
        
        self.current_channel.update_metadata_from(parent.copied_metadata)
        self._update_table()
        
        self.modified = True
        self._update_modified_status()
        
        self._show_status_message("Метаданные вставлены", 3000)
    
    def _paste_selected_metadata(self):
        parent = self.parent_window
        
        if not parent or not hasattr(parent, 'copied_metadata_list') or not parent.copied_metadata_list:
            QMessageBox.warning(self, "Предупреждение", "Нет скопированных метаданных")
            return
        
        if not self.selected_channels:
            QMessageBox.warning(self, "Предупреждение", "Выберите каналы для вставки метаданных")
            return
        
        if len(parent.copied_metadata_list) != len(self.selected_channels):
            QMessageBox.warning(self, "Предупреждение", 
                              "Количество скопированных метаданных должно совпадать с количеством выбранных каналов")
            return
        
        self._save_state("Вставка метаданных в выбранные каналы")
        
        for i, channel in enumerate(self.selected_channels):
            if i < len(parent.copied_metadata_list):
                channel.update_metadata_from(parent.copied_metadata_list[i])
        
        self._update_table()
        
        self.modified = True
        self._update_modified_status()
        
        self._show_status_message(f"Метаданные вставлены в {len(self.selected_channels)} каналов", 3000)
    
    def _rename_groups(self):
        if not self.selected_channels:
            QMessageBox.warning(self, "Предупреждение", "Выберите каналы для переименования групп")
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Групповое переименование групп")
        dialog.resize(400, 200)
        
        layout = QVBoxLayout(dialog)
        
        info_label = QLabel(f"Выбрано каналов для переименования групп: {len(self.selected_channels)}")
        layout.addWidget(info_label)
        
        current_group_label = QLabel("Текущая группа выбранных каналов:")
        layout.addWidget(current_group_label)
        
        groups = set(ch.group for ch in self.selected_channels)
        if len(groups) == 1:
            current_group = list(groups)[0]
        else:
            current_group = "РАЗНЫЕ ГРУППЫ"
        
        current_group_value = QLabel(f"<b>{current_group}</b>")
        layout.addWidget(current_group_value)
        
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)
        
        new_group_label = QLabel("Новая группа:")
        layout.addWidget(new_group_label)
        
        new_group_edit = QLineEdit()
        if len(groups) == 1:
            new_group_edit.setText(current_group)
        new_group_edit.setPlaceholderText("Введите новое название группы")
        layout.addWidget(new_group_edit)
        
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_group = new_group_edit.text().strip()
            if not new_group:
                QMessageBox.warning(self, "Предупреждение", "Введите название новой группы")
                return
            
            if new_group == current_group:
                QMessageBox.information(self, "Информация", "Группа не изменилась")
                return
            
            self._save_state("Групповое переименование групп")
            
            for channel in self.selected_channels:
                channel.group = new_group
                channel.update_extinf()
            
            self._apply_filter()
            
            if self.parent_window and hasattr(self.parent_window, '_update_group_filter'):
                self.parent_window._update_group_filter()
            
            self.modified = True
            self._update_modified_status()
            
            self._show_status_message(f"Группа изменена у {len(self.selected_channels)} каналов", 3000)
    
    def _add_to_blacklist(self, row: int = -1):
        if row == -1:
            if not self.current_channel:
                QMessageBox.warning(self, "Предупреждение", "Выберите канал для добавления в чёрный список")
                return
            channel_to_blacklist = self.current_channel
        else:
            if 0 <= row < len(self.filtered_channels):
                channel_to_blacklist = self.filtered_channels[row]
            else:
                return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Добавить в чёрный список")
        dialog.resize(400, 200)
        
        layout = QVBoxLayout(dialog)
        
        info_label = QLabel(f"Добавить канал в чёрный список:")
        layout.addWidget(info_label)
        
        name_label = QLabel(f"Название: {channel_to_blacklist.name}")
        layout.addWidget(name_label)
        
        tvg_id_label = QLabel(f"TVG-ID: {channel_to_blacklist.tvg_id}")
        layout.addWidget(tvg_id_label)
        
        options_group = QGroupBox("Параметры фильтрации")
        options_layout = QVBoxLayout(options_group)
        
        self.use_name_check = QCheckBox("Фильтровать по названию")
        self.use_name_check.setChecked(True)
        options_layout.addWidget(self.use_name_check)
        
        self.use_tvg_id_check = QCheckBox("Фильтровать по TVG-ID")
        self.use_tvg_id_check.setChecked(bool(channel_to_blacklist.tvg_id))
        options_layout.addWidget(self.use_tvg_id_check)
        
        layout.addWidget(options_group)
        
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = channel_to_blacklist.name if self.use_name_check.isChecked() else ""
            tvg_id = channel_to_blacklist.tvg_id if self.use_tvg_id_check.isChecked() else ""
            
            if not name and not tvg_id:
                QMessageBox.warning(self, "Предупреждение", 
                                   "Выберите хотя бы один параметр для фильтрации (название или TVG-ID)")
                return
            
            if self.blacklist_manager:
                if self.blacklist_manager.add_channel(name, tvg_id):
                    if channel_to_blacklist in self.all_channels:
                        self._save_state("Добавление в чёрный список")
                        self.all_channels.remove(channel_to_blacklist)
                        
                        self._apply_filter()
                        
                        QMessageBox.information(self, "Успех", 
                                              "Канал добавлен в чёрный список и удален из плейлиста")
                    else:
                        QMessageBox.information(self, "Успех", 
                                              "Канал добавлен в чёрный список")
    
    def _add_selected_to_blacklist(self):
        if not self.selected_channels:
            QMessageBox.warning(self, "Предупреждение", "Выберите каналы для добавления в чёрный список")
            return
        
        for channel in self.selected_channels:
            self._add_to_blacklist(self.filtered_channels.index(channel) if channel in self.filtered_channels else -1)
    
    def _check_single_url(self, row: int):
        if 0 <= row < len(self.filtered_channels):
            channel = self.filtered_channels[row]
            if channel and channel.url:
                self._check_urls([channel.url], [channel])
            else:
                QMessageBox.warning(self, "Предупреждение", "У выбранного канала нет URL")
    
    def _check_selected_urls(self):
        if not self.selected_channels:
            QMessageBox.warning(self, "Предупреждение", "Выберите каналы для проверки")
            return
        
        urls = []
        channels_with_urls = []
        
        for channel in self.selected_channels:
            if channel.url and channel.url.strip():
                urls.append(channel.url)
                channels_with_urls.append(channel)
        
        if not urls:
            QMessageBox.information(self, "Информация", "У выбранных каналов нет URL")
            return
        
        self._check_urls(urls, channels_with_urls)
    
    def check_all_urls(self):
        urls = []
        channels_with_urls = []
        
        for channel in self.all_channels:
            if channel.url and channel.url.strip():
                urls.append(channel.url)
                channels_with_urls.append(channel)
        
        if not urls:
            QMessageBox.information(self, "Информация", "Нет URL для проверки")
            return
        
        self._check_urls(urls, channels_with_urls)
    
    def check_selected_urls(self):
        self._check_selected_urls()
    
    def _check_urls(self, urls: List[str], channels: List[ChannelData]):
        if not urls:
            return
        
        dialog = URLCheckDialog(self)
        dialog.set_urls(urls)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        
        def on_check_completed(results):
            self._process_url_check_results(results, channels)
        
        dialog.url_check_completed.connect(on_check_completed)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            pass
    
    def _process_url_check_results(self, results: Dict[int, Dict[str, Any]], channels: List[ChannelData]):
        if not results:
            return
        
        self._save_state("Проверка ссылок")
        
        for idx, result in results.items():
            if idx < len(channels):
                channel = channels[idx]
                channel.url_status = result.get('success')
                channel.url_check_time = datetime.now()
        
        self._apply_filter()
        self._update_info()
        
        self.modified = True
        self._update_modified_status()
        
        self.undo_state_changed.emit(
            self.undo_manager.can_undo(),
            self.undo_manager.can_redo()
        )
    
    def delete_channels_without_urls(self):
        channels_without_urls = [ch for ch in self.all_channels if not ch.has_url or not ch.url or not ch.url.strip()]
        
        if not channels_without_urls:
            QMessageBox.information(self, "Информация", "Нет каналов без ссылок")
            return
        
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Найдено {len(channels_without_urls)} каналов без ссылок. Удалить их?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self._save_state("Удаление каналов без ссылок")
            
            for channel in channels_without_urls:
                if channel in self.all_channels:
                    self.all_channels.remove(channel)
            
            self._apply_filter()
            
            if self.parent_window and hasattr(self.parent_window, '_update_group_filter'):
                self.parent_window._update_group_filter()
            
            self.modified = True
            self._update_modified_status()
            
            QMessageBox.information(self, "Успех", f"Удалено {len(channels_without_urls)} каналов без ссылок")
    
    def _find_duplicate_urls(self) -> Dict[str, List[ChannelData]]:
        url_map = {}
        
        for channel in self.all_channels:
            if channel.url and channel.url.strip():
                url = channel.url.strip()
                if url not in url_map:
                    url_map[url] = []
                url_map[url].append(channel)
        
        return {url: channels for url, channels in url_map.items() if len(channels) > 1}
    
    def find_duplicate_urls(self):
        duplicates = self._find_duplicate_urls()
        
        if not duplicates:
            QMessageBox.information(self, "Информация", "Дубликаты по URL не найдены")
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Поиск дубликатов по URL")
        dialog.resize(800, 600)
        
        layout = QVBoxLayout(dialog)
        
        info_label = QLabel(f"Найдено {len(duplicates)} URL с дубликатами:")
        layout.addWidget(info_label)
        
        tabs = QTabWidget()
        
        for url, channels in duplicates.items():
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)
            
            table = QTableWidget()
            table.setColumnCount(5)
            table.setHorizontalHeaderLabels(["Название", "Группа", "TVG-ID", "Статус", "Выбрать"])
            table.setRowCount(len(channels))
            
            for i, channel in enumerate(channels):
                table.setItem(i, 0, QTableWidgetItem(channel.name))
                table.setItem(i, 1, QTableWidgetItem(channel.group))
                table.setItem(i, 2, QTableWidgetItem(channel.tvg_id))
                
                status_item = QTableWidgetItem(channel.get_status_icon())
                status_item.setForeground(channel.get_status_color())
                table.setItem(i, 3, status_item)
                
                checkbox_item = QTableWidgetItem()
                checkbox_item.setCheckState(Qt.CheckState.Checked)
                table.setItem(i, 4, checkbox_item)
            
            table.horizontalHeader().setStretchLastSection(True)
            tab_layout.addWidget(table)
            
            btn_layout = QHBoxLayout()
            
            select_all_btn = QPushButton("Выбрать все")
            select_all_btn.clicked.connect(lambda checked, t=table: self._select_all_in_table(t))
            btn_layout.addWidget(select_all_btn)
            
            deselect_all_btn = QPushButton("Снять выделение")
            deselect_all_btn.clicked.connect(lambda checked, t=table: self._deselect_all_in_table(t))
            btn_layout.addWidget(deselect_all_btn)
            
            delete_selected_btn = QPushButton("Удалить выбранные")
            delete_selected_btn.clicked.connect(lambda checked, ch=channels, t=table, d=dialog: 
                                               self._delete_selected_duplicates(ch, t, d))
            btn_layout.addWidget(delete_selected_btn)
            
            tab_layout.addLayout(btn_layout)
            
            url_display = url[:50] + "..." if len(url) > 50 else url
            tabs.addTab(tab, f"{len(channels)} дубл. ({url_display})")
        
        layout.addWidget(tabs)
        
        delete_all_btn = QPushButton("Удалить все дубликаты (кроме первого в каждой группе)")
        delete_all_btn.clicked.connect(lambda: self._remove_all_duplicates(duplicates, dialog))
        layout.addWidget(delete_all_btn)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        dialog.exec()
    
    def _select_all_in_table(self, table: QTableWidget):
        for i in range(table.rowCount()):
            item = table.item(i, 4)
            if item:
                item.setCheckState(Qt.CheckState.Checked)
    
    def _deselect_all_in_table(self, table: QTableWidget):
        for i in range(table.rowCount()):
            item = table.item(i, 4)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)
    
    def _delete_selected_duplicates(self, channels: List[ChannelData], table: QTableWidget, dialog: QDialog):
        selected_channels = []
        
        for i in range(table.rowCount()):
            item = table.item(i, 4)
            if item and item.checkState() == Qt.CheckState.Checked:
                if i < len(channels):
                    selected_channels.append(channels[i])
        
        if not selected_channels:
            QMessageBox.warning(dialog, "Предупреждение", "Выберите каналы для удаления")
            return
        
        if len(selected_channels) >= len(channels):
            QMessageBox.warning(dialog, "Предупреждение", 
                              "Нельзя удалить все каналы. Оставьте хотя бы один.")
            return
        
        reply = QMessageBox.question(
            dialog, "Подтверждение",
            f"Удалить выбранные {len(selected_channels)} дубликатов?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self._save_state("Удаление дубликатов по URL")
            
            for channel in selected_channels:
                if channel in self.all_channels:
                    self.all_channels.remove(channel)
            
            self._apply_filter()
            if self.parent_window and hasattr(self.parent_window, '_update_group_filter'):
                self.parent_window._update_group_filter()
            self.modified = True
            self._update_modified_status()
            
            QMessageBox.information(dialog, "Успех", f"Удалено {len(selected_channels)} дубликатов")
            dialog.accept()
    
    def _remove_all_duplicates(self, duplicates: Dict[str, List[ChannelData]], dialog: QDialog):
        reply = QMessageBox.question(
            dialog, "Подтверждение",
            "Удалить все дубликаты, оставляя только первый канал в каждой группе?\n"
            "Это действие нельзя отменить!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self._save_state("Удаление всех дубликатов по URL")
            
            removed_count = 0
            
            for url, channels in duplicates.items():
                for i in range(1, len(channels)):
                    if channels[i] in self.all_channels:
                        self.all_channels.remove(channels[i])
                        removed_count += 1
            
            self._apply_filter()
            if self.parent_window and hasattr(self.parent_window, '_update_group_filter'):
                self.parent_window._update_group_filter()
            self.modified = True
            self._update_modified_status()
            
            QMessageBox.information(dialog, "Успех", 
                                  f"Удалено {removed_count} дубликатов")
            dialog.accept()
    
    def remove_duplicate_urls(self):
        duplicates = self._find_duplicate_urls()
        
        if not duplicates:
            QMessageBox.information(self, "Информация", "Дубликаты по URL не найдены")
            return
        
        total_duplicates = sum(len(channels) - 1 for channels in duplicates.values())
        
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Найдено {total_duplicates} дубликатов по URL.\n"
            "Удалить дубликаты, оставляя только первый канал в каждой группе?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self._save_state("Удаление дубликатов по URL")
            
            removed_count = 0
            
            for url, channels in duplicates.items():
                for i in range(1, len(channels)):
                    if channels[i] in self.all_channels:
                        self.all_channels.remove(channels[i])
                        removed_count += 1
            
            self._apply_filter()
            if self.parent_window and hasattr(self.parent_window, '_update_group_filter'):
                self.parent_window._update_group_filter()
            self.modified = True
            self._update_modified_status()
            
            QMessageBox.information(self, "Успех", 
                                  f"Удалено {removed_count} дубликатов по URL")
    
    def _merge_duplicates(self):
        if not self.all_channels:
            QMessageBox.information(self, "Информация", "Нет каналов для проверки")
            return
        
        duplicates = {}
        for channel in self.all_channels:
            key = (channel.name, channel.group)
            if key not in duplicates:
                duplicates[key] = []
            duplicates[key].append(channel)
        
        dup_count = sum(len(channels) - 1 for channels in duplicates.values() if len(channels) > 1)
        
        if dup_count == 0:
            QMessageBox.information(self, "Информация", "Дубликаты по названию и группе не найдены")
            return
        
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Найдено {dup_count} дубликатов. Удалить их?\n"
            f"Будет оставлен только первый канал из каждой группы дубликатов.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self._save_state("Объединение дубликатов")
            
            new_list = []
            seen = set()
            
            for channel in self.all_channels:
                key = (channel.name, channel.group)
                if key not in seen:
                    new_list.append(channel)
                    seen.add(key)
            
            removed = len(self.all_channels) - len(new_list)
            self.all_channels = new_list
            
            self._apply_filter()
            
            if self.parent_window and hasattr(self.parent_window, '_update_group_filter'):
                self.parent_window._update_group_filter()
            
            QMessageBox.information(self, "Успех", f"Удалено {removed} дубликатов")
            self.modified = True
            self._update_modified_status()
    
    def edit_playlist_header(self):
        dialog = PlaylistHeaderDialog(self.header_manager, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.modified = True
            self._update_modified_status()
            self._show_status_message("Заголовок плейлиста обновлен", 2000)
    
    def apply_blacklist(self):
        if not self.blacklist_manager:
            return 0
        
        original_count = len(self.all_channels)
        filtered, removed = self.blacklist_manager.filter_channels(self.all_channels)
        
        if removed > 0:
            self._save_state("Применение чёрного списка")
            self.all_channels = filtered
            
            self._apply_filter()
            
            self.modified = True
            self._update_modified_status()
        
        return removed
    
    def _save_changes(self):
        self._show_status_message("Изменения сохранены автоматически", 2000)
    
    def _edit_current_cell(self):
        current_item = self.table.currentItem()
        if current_item:
            self.table.editItem(current_item)
    
    def _select_all_channels(self):
        self.table.selectAll()
        self._on_selection_changed()
    
    def _delete_channel(self, row: int = -1):
        if row == -1:
            if not self.selected_channels:
                if not self.current_channel:
                    QMessageBox.warning(self, "Предупреждение", "Выберите канал для удаления")
                    return
                channels_to_delete = [self.current_channel]
            else:
                channels_to_delete = self.selected_channels
        else:
            if 0 <= row < len(self.filtered_channels):
                channels_to_delete = [self.filtered_channels[row]]
            else:
                return
        
        if len(channels_to_delete) == 1:
            message = f"Удалить канал '{channels_to_delete[0].name}'?"
        else:
            message = f"Удалить выбранные {len(channels_to_delete)} каналов?"
        
        reply = QMessageBox.question(
            self, "Подтверждение", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self._save_state("Удаление канала")
            
            for channel in channels_to_delete:
                if channel in self.all_channels:
                    self.all_channels.remove(channel)
            
            self._apply_filter()
            
            if self.parent_window and hasattr(self.parent_window, '_update_group_filter'):
                self.parent_window._update_group_filter()
            
            self.modified = True
            self._update_modified_status()
            
            self._show_status_message(f"Канал удален", 2000)
    
    def _delete_selected_channels(self):
        if not self.selected_channels:
            QMessageBox.warning(self, "Предупреждение", "Выберите каналы для удаления")
            return
        
        self._delete_channel()
    
    def _move_channel_up(self, row: int = -1):
        if row == -1:
            if not self.current_channel:
                QMessageBox.warning(self, "Предупреждение", "Выберите канал для перемещения")
                return
            channel_to_move = self.current_channel
        else:
            if 0 <= row < len(self.filtered_channels):
                channel_to_move = self.filtered_channels[row]
            else:
                return
        
        try:
            idx = self.all_channels.index(channel_to_move)
            self._move_channel_up_in_list(idx)
        except ValueError:
            pass
    
    def _move_selected_up(self):
        if not self.selected_channels:
            QMessageBox.warning(self, "Предупреждение", "Выберите каналы для перемещения")
            return
        
        indices = []
        for channel in self.selected_channels:
            try:
                idx = self.all_channels.index(channel)
                indices.append(idx)
            except ValueError:
                continue
        
        if not indices:
            return
        
        indices.sort()
        
        moved_count = 0
        for idx in indices:
            if idx > 0:
                if self._move_channel_up_in_list(idx - moved_count):
                    moved_count += 1
    
    def _move_channel_down(self, row: int = -1):
        if row == -1:
            if not self.current_channel:
                QMessageBox.warning(self, "Предупреждение", "Выберите канал для перемещения")
                return
            channel_to_move = self.current_channel
        else:
            if 0 <= row < len(self.filtered_channels):
                channel_to_move = self.filtered_channels[row]
            else:
                return
        
        try:
            idx = self.all_channels.index(channel_to_move)
            self._move_channel_down_in_list(idx)
        except ValueError:
            pass
    
    def _move_selected_down(self):
        if not self.selected_channels:
            QMessageBox.warning(self, "Предупреждение", "Выберите каналы для перемещения")
            return
        
        indices = []
        for channel in self.selected_channels:
            try:
                idx = self.all_channels.index(channel)
                indices.append(idx)
            except ValueError:
                continue
        
        if not indices:
            return
        
        indices.sort(reverse=True)
        
        for idx in indices:
            if idx < len(self.all_channels) - 1:
                self._move_channel_down_in_list(idx)
    
    def _move_channel_up_in_list(self, idx: int):
        if idx <= 0:
            return False
        
        self._save_state("Перемещение канала вверх")
        
        self.all_channels[idx], self.all_channels[idx - 1] = \
            self.all_channels[idx - 1], self.all_channels[idx]
        
        self._apply_filter()
        
        selected_indices = []
        for channel in self.selected_channels:
            try:
                new_idx = self.all_channels.index(channel)
                selected_indices.append(new_idx)
            except ValueError:
                continue
        
        self.table.clearSelection()
        for new_idx in selected_indices:
            if new_idx < len(self.all_channels):
                channel = self.all_channels[new_idx]
                if channel in self.filtered_channels:
                    table_idx = self.filtered_channels.index(channel)
                    self.table.selectRow(table_idx)
        
        self.modified = True
        self._update_modified_status()
        
        return True
    
    def _move_channel_down_in_list(self, idx: int):
        if idx >= len(self.all_channels) - 1:
            return False
        
        self._save_state("Перемещение канала вниз")
        
        self.all_channels[idx], self.all_channels[idx + 1] = \
            self.all_channels[idx + 1], self.all_channels[idx]
        
        self._apply_filter()
        
        selected_indices = []
        for channel in self.selected_channels:
            try:
                new_idx = self.all_channels.index(channel)
                selected_indices.append(new_idx)
            except ValueError:
                continue
        
        self.table.clearSelection()
        for new_idx in selected_indices:
            if new_idx < len(self.all_channels):
                channel = self.all_channels[new_idx]
                if channel in self.filtered_channels:
                    table_idx = self.filtered_channels.index(channel)
                    self.table.selectRow(table_idx)
        
        self.modified = True
        self._update_modified_status()
        
        return True
    
    def remove_all_urls(self):
        if not self.all_channels:
            QMessageBox.information(self, "Информация", "Нет каналов для обработки")
            return
        
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить все ссылки из {len(self.all_channels)} каналов?\n"
            "Это действие нельзя отменить!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self._save_state("Удаление всех ссылок")
            
            for channel in self.all_channels:
                channel.url = ""
                channel.has_url = False
                channel.url_status = None
                channel.url_check_time = None
                channel.update_extinf()
            
            self._apply_filter()
            
            self.modified = True
            self._update_modified_status()
            
            QMessageBox.information(self, "Успех", f"Удалены ссылки из {len(self.all_channels)} каналов")
    
    def remove_metadata(self, metadata_options: Dict[str, bool]):
        if not self.all_channels:
            QMessageBox.information(self, "Информация", "Нет каналов для обработки")
            return
        
        channels_to_modify = []
        
        for channel in self.all_channels:
            should_modify = False
            
            if metadata_options.get('tvg_id', False) and channel.tvg_id:
                should_modify = True
            if metadata_options.get('tvg_logo', False) and channel.tvg_logo:
                should_modify = True
            if metadata_options.get('group_title', False) and channel.group:
                should_modify = True
            if metadata_options.get('user_agent', False) and channel.user_agent:
                should_modify = True
            if metadata_options.get('catchup', False) and '#EXTINF' in channel.extinf and ('catchup=' in channel.extinf or 'catchup-days=' in channel.extinf or 'catchup-source=' in channel.extinf):
                should_modify = True
            
            if should_modify:
                channels_to_modify.append(channel)
        
        if not channels_to_modify:
            QMessageBox.information(self, "Информация", "Не найдено каналов с указанными метаданными")
            return
        
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить выбранные метаданные из {len(channels_to_modify)} каналов?\n"
            "Это действие нельзя отменить!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self._save_state("Удаление метаданных")
            
            for channel in channels_to_modify:
                if metadata_options.get('tvg_id', False):
                    channel.tvg_id = ""
                if metadata_options.get('tvg_logo', False):
                    channel.tvg_logo = ""
                if metadata_options.get('group_title', False):
                    channel.group = "Без группы"
                if metadata_options.get('user_agent', False):
                    channel.user_agent = ""
                    if 'User-Agent' in channel.extra_headers:
                        del channel.extra_headers['User-Agent']
                    channel.update_extvlcopt_from_headers()
                
                if metadata_options.get('catchup', False) and '#EXTINF' in channel.extinf:
                    extinf_line = channel.extinf
                    extinf_line = re.sub(r'catchup="[^"]*"', '', extinf_line)
                    extinf_line = re.sub(r'catchup-days="[^"]*"', '', extinf_line)
                    extinf_line = re.sub(r'catchup-source="[^"]*"', '', extinf_line)
                    extinf_line = re.sub(r'\s+', ' ', extinf_line).strip()
                    channel.extinf = extinf_line
                
                channel.update_extinf()
            
            self._apply_filter()
            
            self.modified = True
            self._update_modified_status()
            
            QMessageBox.information(self, "Успех", f"Удалены метаданные из {len(channels_to_modify)} каналов")
    
    def delete_channels_without_metadata(self):
        if not self.all_channels:
            QMessageBox.information(self, "Информация", "Нет каналов для обработки")
            return
        
        channels_without_metadata = []
        
        for channel in self.all_channels:
            has_metadata = (
                bool(channel.tvg_id) or
                bool(channel.tvg_logo) or
                bool(channel.group and channel.group != "Без группы") or
                bool(channel.user_agent) or
                bool('catchup=' in channel.extinf or 'catchup-days=' in channel.extinf or 'catchup-source=' in channel.extinf)
            )
            
            if not has_metadata:
                channels_without_metadata.append(channel)
        
        if not channels_without_metadata:
            QMessageBox.information(self, "Информация", "Нет каналов без метаданных")
            return
        
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Найдено {len(channels_without_metadata)} каналов без метаданных. Удалить их?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self._save_state("Удаление каналов без метаданных")
            
            for channel in channels_without_metadata:
                if channel in self.all_channels:
                    self.all_channels.remove(channel)
            
            self._apply_filter()
            
            if self.parent_window and hasattr(self.parent_window, '_update_group_filter'):
                self.parent_window._update_group_filter()
            
            self.modified = True
            self._update_modified_status()
            
            QMessageBox.information(self, "Успех", f"Удалено {len(channels_without_metadata)} каналов без метаданных")
    
    def sort_playlist_by_groups(self, show_change_column: bool = True):
        if not self.all_channels:
            QMessageBox.warning(self, "Предупреждение", "Нет каналов для сортировки")
            return
        
        try:
            self._save_state("Сортировка по группам")
            
            original_positions = {id(ch): i for i, ch in enumerate(self.all_channels)}
            
            grouped_channels = {}
            for channel in self.all_channels:
                group = channel.group or "Без группы"
                if group not in grouped_channels:
                    grouped_channels[group] = []
                grouped_channels[group].append(channel)
            
            for group in grouped_channels:
                grouped_channels[group].sort(key=lambda x: (
                    not x.name.startswith('●'),
                    x.name.lower()
                ))
            
            sorted_channels = []
            
            all_groups = sorted(grouped_channels.keys())
            for group_name in all_groups:
                for channel in grouped_channels[group_name]:
                    original_pos = original_positions.get(id(channel), -1)
                    if original_pos >= 0:
                        current_pos = len(sorted_channels)
                        channel.sort_change = original_pos - current_pos
                    sorted_channels.append(channel)
            
            self.all_channels = sorted_channels
            self.is_sorted_mode = True
            
            self._apply_filter()
            self._update_info()
            
            self.modified = True
            self._update_modified_status()
            
            moved_up = sum(1 for ch in self.all_channels if ch.sort_change < 0)
            moved_down = sum(1 for ch in self.all_channels if ch.sort_change > 0)
            same_position = sum(1 for ch in self.all_channels if ch.sort_change == 0)
            
            self._show_status_message(
                f"Сортировка завершена: ↑{moved_up} ↓{moved_down} ={same_position}",
                3000
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", 
                f"Ошибка при сортировке:\n{str(e)}")
    
    def reset_sort_view(self):
        self.is_sorted_mode = False
        for channel in self.all_channels:
            channel.sort_change = 0
        self._apply_filter()
        self._update_info()
        self._show_status_message("Вид сортировки сброшен", 2000)
    
    def edit_groups_order(self):
        current_groups = sorted({ch.group for ch in self.all_channels if ch.group})
        all_groups = current_groups.copy()
        dialog = EditGroupsOrderDialog(current_groups, all_groups, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._show_status_message("Порядок групп обновлен", 2000)
    
    def export_sorting_stats(self):
        if not self.all_channels or not self.is_sorted_mode:
            QMessageBox.warning(self, "Предупреждение", "Нет данных для экспорта")
            return
        
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Экспорт статистики сортировки",
            f"sorting_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV Files (*.csv);;All Files (*.*)"
        )
        
        if filepath:
            try:
                with open(filepath, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    
                    writer.writerow(['Статистика сортировки M3U плейлиста'])
                    writer.writerow(['Дата', datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                    writer.writerow(['Исходный файл', self.filepath or ''])
                    writer.writerow([])
                    
                    moved_up = sum(1 for ch in self.all_channels if ch.sort_change < 0)
                    moved_down = sum(1 for ch in self.all_channels if ch.sort_change > 0)
                    same_position = sum(1 for ch in self.all_channels if ch.sort_change == 0)
                    channels_with_url = 0
                    channels_without_url = 0
                    
                    groups_summary = {}
                    
                    for channel in self.all_channels:
                        if channel.url:
                            channels_with_url += 1
                        else:
                            channels_without_url += 1
                        
                        group = channel.group or "Без группы"
                        if group not in groups_summary:
                            groups_summary[group] = {'total': 0, 'with_url': 0, 'without_url': 0}
                        
                        groups_summary[group]['total'] += 1
                        if channel.url:
                            groups_summary[group]['with_url'] += 1
                        else:
                            groups_summary[group]['without_url'] += 1
                    
                    writer.writerow(['Общая статистика'])
                    writer.writerow(['Всего каналов:', len(self.all_channels)])
                    writer.writerow(['Каналов с ссылкой:', channels_with_url])
                    writer.writerow(['Каналов без ссылки:', channels_without_url])
                    writer.writerow(['Поднялось:', moved_up])
                    writer.writerow(['Опустилось:', moved_down])
                    writer.writerow(['Без изменений:', same_position])
                    writer.writerow([])
                    
                    writer.writerow(['Статистика по группам'])
                    writer.writerow(['Группа', 'Всего каналов', 'С ссылкой', 'Без ссылки'])
                    for group, stats in sorted(groups_summary.items()):
                        writer.writerow([group, stats['total'], stats['with_url'], stats['without_url']])
                    writer.writerow([])
                    
                    writer.writerow(['Подробный список каналов'])
                    writer.writerow(['Номер', 'Название', 'Группа', 'Изменение', 'URL', 'Статус'])
                    
                    for i, channel in enumerate(self.all_channels, 1):
                        change = channel.sort_change
                        change_text = f"{abs(change)} позиц. {'вверх' if change < 0 else 'вниз' if change > 0 else 'без изменений'}"
                        status = channel.get_status_icon()
                        url = channel.url if channel.url else "Нет ссылки"
                        
                        writer.writerow([
                            i,
                            channel.name,
                            channel.group,
                            change_text,
                            url,
                            status
                        ])
                
                QMessageBox.information(self, "Успех", "Статистика успешно экспортирована")
                self._show_status_message("Статистика экспортирована", 2000)
                
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка экспорта: {str(e)}")
    
    def is_empty(self) -> bool:
        return (len(self.all_channels) == 0 and 
                not self.filepath and 
                not self.modified)