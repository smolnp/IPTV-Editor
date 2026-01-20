from typing import List
from PyQt6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QMenu, QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QAction, QColor

from models.channel_data import ChannelData


class EditableTableWidgetItem(QTableWidgetItem):
    def __init__(self, text: str = ""):
        super().__init__(text)
        self.setFlags(self.flags() | Qt.ItemFlag.ItemIsEditable)


class ChannelTableWidget(QTableWidget):
    cell_edited = pyqtSignal(int, int, str)
    url_check_requested = pyqtSignal(int)
    edit_user_agent_requested = pyqtSignal(int)
    copy_channel_requested = pyqtSignal()
    copy_selected_channels_requested = pyqtSignal()
    copy_metadata_requested = pyqtSignal()
    copy_selected_metadata_requested = pyqtSignal()
    paste_channel_requested = pyqtSignal()
    paste_selected_channels_requested = pyqtSignal()
    paste_metadata_requested = pyqtSignal()
    paste_selected_metadata_requested = pyqtSignal()
    rename_groups_requested = pyqtSignal()
    add_to_blacklist_requested = pyqtSignal(int)
    add_selected_to_blacklist_requested = pyqtSignal()
    check_single_url_requested = pyqtSignal(int)
    check_selected_urls_requested = pyqtSignal()
    move_channel_up_requested = pyqtSignal(int)
    move_selected_up_requested = pyqtSignal()
    move_channel_down_requested = pyqtSignal(int)
    move_selected_down_requested = pyqtSignal()
    delete_channel_requested = pyqtSignal(int)
    delete_selected_channels_requested = pyqtSignal()
    new_channel_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.itemChanged.connect(self._on_item_changed)
        self._block_item_changed = False
        
    def _on_item_changed(self, item):
        if self._block_item_changed:
            return
            
        if isinstance(item, EditableTableWidgetItem):
            try:
                self._block_item_changed = True
                self.cell_edited.emit(item.row(), item.column(), item.text())
            finally:
                self._block_item_changed = False
    
    def _show_context_menu(self, position: QPoint):
        menu = QMenu(self)
        
        selected_rows = set()
        for item in self.selectedItems():
            selected_rows.add(item.row())
        
        if selected_rows:
            if len(selected_rows) == 1:
                row = list(selected_rows)[0]
                
                edit_ua_action = QAction("Редактировать User Agent...", menu)
                edit_ua_action.triggered.connect(lambda: self.edit_user_agent_requested.emit(row))
                menu.addAction(edit_ua_action)
                
                menu.addSeparator()
                
                new_channel_action = QAction("Новый канал", menu)
                new_channel_action.triggered.connect(lambda: self.new_channel_requested.emit())
                menu.addAction(new_channel_action)
                
                copy_channel_action = QAction("Копировать канал", menu)
                copy_channel_action.triggered.connect(lambda: self.copy_channel_requested.emit())
                menu.addAction(copy_channel_action)
                
                paste_channel_action = QAction("Вставить канал", menu)
                paste_channel_action.triggered.connect(lambda: self.paste_channel_requested.emit())
                menu.addAction(paste_channel_action)
                
                menu.addSeparator()
                
                copy_metadata_action = QAction("Копировать метаданные", menu)
                copy_metadata_action.triggered.connect(lambda: self.copy_metadata_requested.emit())
                menu.addAction(copy_metadata_action)
                
                paste_metadata_action = QAction("Вставить метаданные", menu)
                paste_metadata_action.triggered.connect(lambda: self.paste_metadata_requested.emit())
                menu.addAction(paste_metadata_action)
                
                menu.addSeparator()
                
                rename_groups_action = QAction("Переименование групп", menu)
                rename_groups_action.triggered.connect(lambda: self.rename_groups_requested.emit())
                menu.addAction(rename_groups_action)
                
                menu.addSeparator()
                
                add_to_blacklist_action = QAction("Добавить в чёрный список", menu)
                add_to_blacklist_action.triggered.connect(lambda: self.add_to_blacklist_requested.emit(row))
                menu.addAction(add_to_blacklist_action)
                
                menu.addSeparator()
                
                check_url_action = QAction("Проверить ссылку", menu)
                check_url_action.triggered.connect(lambda: self.check_single_url_requested.emit(row))
                menu.addAction(check_url_action)
                
                menu.addSeparator()
                
                move_up_action = QAction("Переместить вверх", menu)
                move_up_action.triggered.connect(lambda: self.move_channel_up_requested.emit(row))
                menu.addAction(move_up_action)
                
                move_down_action = QAction("Переместить вниз", menu)
                move_down_action.triggered.connect(lambda: self.move_channel_down_requested.emit(row))
                menu.addAction(move_down_action)
                
                menu.addSeparator()
                
                delete_action = QAction("Удалить канал", menu)
                delete_action.triggered.connect(lambda: self.delete_channel_requested.emit(row))
                menu.addAction(delete_action)
            else:
                count = len(selected_rows)
                menu.addAction(QAction(f"Выбрано каналов: {count}", menu))
                menu.addSeparator()
                
                new_channel_action = QAction("Новый канал", menu)
                new_channel_action.triggered.connect(lambda: self.new_channel_requested.emit())
                menu.addAction(new_channel_action)
                
                copy_channels_action = QAction(f"Копировать каналы ({count})", menu)
                copy_channels_action.triggered.connect(lambda: self.copy_selected_channels_requested.emit())
                menu.addAction(copy_channels_action)
                
                paste_channels_action = QAction(f"Вставить каналы ({count})", menu)
                paste_channels_action.triggered.connect(lambda: self.paste_selected_channels_requested.emit())
                menu.addAction(paste_channels_action)
                
                menu.addSeparator()
                
                copy_metadata_selected_action = QAction(f"Копировать метаданные ({count})", menu)
                copy_metadata_selected_action.triggered.connect(lambda: self.copy_selected_metadata_requested.emit())
                menu.addAction(copy_metadata_selected_action)
                
                paste_metadata_selected_action = QAction(f"Вставить метаданные ({count})", menu)
                paste_metadata_selected_action.triggered.connect(lambda: self.paste_selected_metadata_requested.emit())
                menu.addAction(paste_metadata_selected_action)
                
                menu.addSeparator()
                
                rename_groups_action = QAction("Переименование групп", menu)
                rename_groups_action.triggered.connect(lambda: self.rename_groups_requested.emit())
                menu.addAction(rename_groups_action)
                
                menu.addSeparator()
                
                delete_selected_action = QAction(f"Удалить выбранные ({count})", menu)
                delete_selected_action.triggered.connect(lambda: self.delete_selected_channels_requested.emit())
                menu.addAction(delete_selected_action)
                
                move_selected_up_action = QAction(f"Переместить вверх ({count})", menu)
                move_selected_up_action.triggered.connect(lambda: self.move_selected_up_requested.emit())
                menu.addAction(move_selected_up_action)
                
                move_selected_down_action = QAction(f"Переместить вниз ({count})", menu)
                move_selected_down_action.triggered.connect(lambda: self.move_selected_down_requested.emit())
                menu.addAction(move_selected_down_action)
                
                menu.addSeparator()
                
                check_selected_urls_action = QAction(f"Проверить ссылки ({count})", menu)
                check_selected_urls_action.triggered.connect(lambda: self.check_selected_urls_requested.emit())
                menu.addAction(check_selected_urls_action)
                
                add_selected_to_blacklist_action = QAction(f"Добавить в чёрный список ({count})", menu)
                add_selected_to_blacklist_action.triggered.connect(lambda: self.add_selected_to_blacklist_requested.emit())
                menu.addAction(add_selected_to_blacklist_action)
        else:
            new_channel_action = QAction("Новый канал", menu)
            new_channel_action.triggered.connect(lambda: self.new_channel_requested.emit())
            menu.addAction(new_channel_action)
            
            paste_channel_action = QAction("Вставить канал", menu)
            paste_channel_action.triggered.connect(lambda: self.paste_channel_requested.emit())
            menu.addAction(paste_channel_action)
            
            paste_metadata_action = QAction("Вставить метаданные", menu)
            paste_metadata_action.triggered.connect(lambda: self.paste_metadata_requested.emit())
            menu.addAction(paste_metadata_action)
            
            menu.addSeparator()
            
            rename_groups_action = QAction("Переименование групп", menu)
            rename_groups_action.triggered.connect(lambda: self.rename_groups_requested.emit())
            menu.addAction(rename_groups_action)
        
        menu.exec(self.mapToGlobal(position))
