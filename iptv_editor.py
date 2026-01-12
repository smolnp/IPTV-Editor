import sys
import os
import re
import json
import requests
import shutil
import concurrent.futures
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Optional, Dict, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse, urljoin, quote
import time
import random

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QTableWidget, QTableWidgetItem,
    QGroupBox, QFormLayout, QLineEdit, QPushButton, QComboBox,
    QLabel, QMenuBar, QMenu, QStatusBar, QToolBar,
    QFileDialog, QMessageBox, QDialog, QDialogButtonBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QAbstractItemView,
    QListWidget, QListWidgetItem, QScrollArea, QGridLayout,
    QInputDialog, QToolButton, QStyle, QTextEdit, QCheckBox,
    QRadioButton, QProgressBar, QProgressDialog, QFrame,
    QPlainTextEdit, QSpacerItem, QSizePolicy, QSlider
)
from PyQt6.QtCore import (
    Qt, QTimer, QSettings, QSize, QPoint, QMimeData,
    QStringListModel, QEvent, pyqtSignal,
    QThread
)
from PyQt6.QtGui import (
    QAction, QKeySequence, QColor, QFont, QIcon,
    QTextCursor, QClipboard, QDesktopServices, QPalette,
    QContextMenuEvent, QShortcut, QTextCharFormat, QSyntaxHighlighter,
    QFontMetrics, QPainter
)


# ===================== СИСТЕМНЫЕ НАСТРОЙКИ =====================
class SystemThemeManager:
    """Менеджер системных тем и настроек"""
    
    @staticmethod
    def get_hotkeys() -> Dict[str, str]:
        """Получение системных горячих клавиш"""
        return {
            'open': 'Ctrl+O',
            'save': 'Ctrl+S',
            'save_as': 'Ctrl+Shift+S',
            'new': 'Ctrl+N',
            'find': 'Ctrl+F',
            'add': 'Ctrl+A',
            'delete': 'Delete',
            'exit': 'Alt+F4',
            'copy': 'Ctrl+C',
            'paste': 'Ctrl+V',
            'undo': 'Ctrl+Z',
            'redo': 'Ctrl+Y'
        }
    
    @staticmethod
    def get_config_dir() -> str:
        """Получение директории для конфигурации с поддержкой Linux"""
        if sys.platform == "linux" or sys.platform == "linux2":
            config_home = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
            return os.path.join(config_home, "iptv_editor")
        elif sys.platform == "darwin":
            return os.path.expanduser("~/Library/Application Support/IPTVEditor")
        else:
            return os.path.expanduser("~/.iptv_editor")


# ===================== МЕНЕДЖЕР ЗАГОЛОВКА ПЛЕЙЛИСТА =====================
class PlaylistHeaderManager:
    """Менеджер заголовка плейлиста"""
    
    def __init__(self):
        self.header_lines: List[str] = []
        self.epg_sources: List[str] = []
        self.custom_attributes: Dict[str, str] = {}
        self.playlist_name: str = ""
        self.has_extm3u: bool = False
    
    def parse_header(self, content: str):
        """Парсинг заголовка плейлиста из содержимого"""
        self.header_lines = []
        self.epg_sources = []
        self.custom_attributes = {}
        self.playlist_name = ""
        self.has_extm3u = False
        
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('#EXTM3U'):
                self.has_extm3u = True
                self.header_lines.append(line)
                # Парсинг атрибутов #EXTM3U
                if ' ' in line:
                    attrs_line = line[8:]  # Пропускаем "#EXTM3U "
                    # Парсинг атрибутов вида key="value" или key=value
                    attrs = re.findall(r'(\S+?)=["\']?([^"\'\s]+)["\']?', attrs_line)
                    for key, value in attrs:
                        if key.lower() == 'url-tvg':
                            self.epg_sources.append(value)
                        else:
                            self.custom_attributes[key] = value
                            
            elif line.startswith('#PLAYLIST:'):
                self.playlist_name = line[10:]  # Пропускаем "#PLAYLIST:"
                self.header_lines.append(line)
            elif line.startswith('#'):
                self.header_lines.append(line)
            else:
                # Первая не-комментарийная строка - конец заголовка
                break
    
    def update_epg_sources(self, sources: List[str]):
        """Обновление EPG источников"""
        self.epg_sources = sources
        self._update_extm3u_line()
    
    def set_playlist_name(self, name: str):
        """Установка названия плейлиста"""
        self.playlist_name = name
        self._update_playlist_name_line()
    
    def add_custom_attribute(self, key: str, value: str):
        """Добавление пользовательского атрибута"""
        self.custom_attributes[key] = value
        self._update_extm3u_line()
    
    def remove_custom_attribute(self, key: str):
        """Удаление пользовательского атрибута"""
        if key in self.custom_attributes:
            del self.custom_attributes[key]
            self._update_extm3u_line()
    
    def _update_extm3u_line(self):
        """Обновление строки #EXTM3U"""
        # Удаляем существующую строку #EXTM3U
        self.header_lines = [line for line in self.header_lines if not line.startswith('#EXTM3U')]
        
        # Создаем новую строку
        parts = ["#EXTM3U"]
        
        # Добавляем EPG источники
        for epg_source in self.epg_sources:
            parts.append(f'url-tvg="{epg_source}"')
        
        # Добавляем пользовательские атрибуты
        for key, value in self.custom_attributes.items():
            parts.append(f'{key}="{value}"')
        
        # Вставляем строку в начало
        self.header_lines.insert(0, ' '.join(parts))
    
    def _update_playlist_name_line(self):
        """Обновление строки с названием плейлиста"""
        # Удаляем существующую строку #PLAYLIST
        self.header_lines = [line for line in self.header_lines if not line.startswith('#PLAYLIST:')]
        
        if self.playlist_name:
            # Вставляем после #EXTM3U
            extm3u_index = -1
            for i, line in enumerate(self.header_lines):
                if line.startswith('#EXTM3U'):
                    extm3u_index = i
                    break
            
            if extm3u_index >= 0:
                self.header_lines.insert(extm3u_index + 1, f'#PLAYLIST:{self.playlist_name}')
            else:
                self.header_lines.append(f'#PLAYLIST:{self.playlist_name}')
    
    def get_header_text(self) -> str:
        """Получение текста заголовка"""
        return '\n'.join(self.header_lines) + '\n' if self.header_lines else ''


# ===================== ДИАЛОГ УПРАВЛЕНИЯ ЗАГОЛОВКОМ ПЛЕЙЛИСТА =====================
class PlaylistHeaderDialog(QDialog):
    """Диалог управления заголовком плейлиста"""
    
    def __init__(self, playlist_tab: 'PlaylistTab', parent=None):
        super().__init__(parent)
        self.playlist_tab = playlist_tab
        self.header_manager = playlist_tab.header_manager
        self.setWindowTitle("Управление заголовком плейлиста")
        self.resize(600, 400)
        
        self._setup_ui()
        self._load_header_data()
    
    def _setup_ui(self):
        """Настройка интерфейса диалога"""
        layout = QVBoxLayout(self)
        
        # Основная информация
        info_group = QGroupBox("Основная информация")
        info_layout = QFormLayout(info_group)
        
        self.playlist_name_edit = QLineEdit()
        self.playlist_name_edit.setPlaceholderText("Введите название плейлиста")
        info_layout.addRow("Название плейлиста:", self.playlist_name_edit)
        
        layout.addWidget(info_group)
        
        # EPG источники
        epg_group = QGroupBox("EPG источники")
        epg_layout = QVBoxLayout(epg_group)
        
        self.epg_list = QListWidget()
        epg_layout.addWidget(self.epg_list)
        
        epg_btn_layout = QHBoxLayout()
        
        self.add_epg_btn = QPushButton("Добавить EPG")
        self.add_epg_btn.clicked.connect(self._add_epg_source)
        
        self.remove_epg_btn = QPushButton("Удалить EPG")
        self.remove_epg_btn.clicked.connect(self._remove_selected_epg)
        
        epg_btn_layout.addWidget(self.add_epg_btn)
        epg_btn_layout.addWidget(self.remove_epg_btn)
        
        epg_layout.addLayout(epg_btn_layout)
        
        layout.addWidget(epg_group)
        
        # Пользовательские атрибуты
        attrs_group = QGroupBox("Дополнительные атрибуты")
        attrs_layout = QVBoxLayout(attrs_group)
        
        self.attrs_table = QTableWidget()
        self.attrs_table.setColumnCount(2)
        self.attrs_table.setHorizontalHeaderLabels(["Ключ", "Значение"])
        self.attrs_table.horizontalHeader().setStretchLastSection(True)
        
        attrs_layout.addWidget(self.attrs_table)
        
        attrs_btn_layout = QHBoxLayout()
        
        self.add_attr_btn = QPushButton("Добавить атрибут")
        self.add_attr_btn.clicked.connect(self._add_custom_attribute)
        
        self.remove_attr_btn = QPushButton("Удалить атрибут")
        self.remove_attr_btn.clicked.connect(self._remove_selected_attribute)
        
        attrs_btn_layout.addWidget(self.add_attr_btn)
        attrs_btn_layout.addWidget(self.remove_attr_btn)
        
        attrs_layout.addLayout(attrs_btn_layout)
        
        layout.addWidget(attrs_group)
        
        # Предпросмотр заголовка
        preview_group = QGroupBox("Предпросмотр заголовка")
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_edit = QPlainTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setMaximumHeight(100)
        preview_layout.addWidget(self.preview_edit)
        
        layout.addWidget(preview_group)
        
        # Кнопки
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._apply_changes)
        button_box.rejected.connect(self.reject)
        
        layout.addWidget(button_box)
        
        # Подключаем сигналы для обновления предпросмотра
        self.playlist_name_edit.textChanged.connect(self._update_preview)
        self.epg_list.itemChanged.connect(self._update_preview)
    
    def _load_header_data(self):
        """Загрузка данных заголовка"""
        self.playlist_name_edit.setText(self.header_manager.playlist_name)
        
        # Загружаем EPG источники
        self.epg_list.clear()
        for epg_source in self.header_manager.epg_sources:
            item = QListWidgetItem(epg_source)
            self.epg_list.addItem(item)
        
        # Загружаем пользовательские атрибуты
        self.attrs_table.setRowCount(len(self.header_manager.custom_attributes))
        for i, (key, value) in enumerate(self.header_manager.custom_attributes.items()):
            self.attrs_table.setItem(i, 0, QTableWidgetItem(key))
            self.attrs_table.setItem(i, 1, QTableWidgetItem(value))
        
        self._update_preview()
    
    def _update_preview(self):
        """Обновление предпросмотра заголовка"""
        # Создаем временный заголовок для предпросмотра
        temp_manager = PlaylistHeaderManager()
        temp_manager.epg_sources = [self.epg_list.item(i).text() 
                                    for i in range(self.epg_list.count())]
        temp_manager.playlist_name = self.playlist_name_edit.text()
        temp_manager.custom_attributes = {}
        
        for i in range(self.attrs_table.rowCount()):
            key_item = self.attrs_table.item(i, 0)
            value_item = self.attrs_table.item(i, 1)
            if key_item and value_item:
                temp_manager.custom_attributes[key_item.text()] = value_item.text()
        
        temp_manager._update_extm3u_line()
        temp_manager._update_playlist_name_line()
        
        preview_text = temp_manager.get_header_text()
        self.preview_edit.setPlainText(preview_text)
    
    def _add_epg_source(self):
        """Добавление EPG источника"""
        url, ok = QInputDialog.getText(
            self, "Добавить EPG источник",
            "Введите URL EPG источника:",
            text="https://"
        )
        
        if ok and url:
            item = QListWidgetItem(url)
            self.epg_list.addItem(item)
            self._update_preview()
    
    def _remove_selected_epg(self):
        """Удаление выбранного EPG источника"""
        selected_items = self.epg_list.selectedItems()
        if selected_items:
            for item in selected_items:
                self.epg_list.takeItem(self.epg_list.row(item))
            self._update_preview()
    
    def _add_custom_attribute(self):
        """Добавление пользовательского атрибута"""
        key, ok1 = QInputDialog.getText(
            self, "Добавить атрибут",
            "Введите ключ атрибута:"
        )
        
        if ok1 and key:
            value, ok2 = QInputDialog.getText(
                self, "Добавить атрибут",
                f"Введите значение для '{key}':"
            )
            
            if ok2:
                row = self.attrs_table.rowCount()
                self.attrs_table.insertRow(row)
                self.attrs_table.setItem(row, 0, QTableWidgetItem(key))
                self.attrs_table.setItem(row, 1, QTableWidgetItem(value))
                self._update_preview()
    
    def _remove_selected_attribute(self):
        """Удаление выбранного атрибута"""
        selected_rows = set()
        for item in self.attrs_table.selectedItems():
            selected_rows.add(item.row())
        
        for row in sorted(selected_rows, reverse=True):
            self.attrs_table.removeRow(row)
        
        self._update_preview()
    
    def _apply_changes(self):
        """Применение изменений"""
        # Сохраняем изменения в заголовке плейлиста
        self.playlist_tab._save_state("Изменение заголовка плейлиста")
        
        # Обновляем EPG источники
        self.header_manager.epg_sources = [
            self.epg_list.item(i).text() for i in range(self.epg_list.count())
        ]
        
        # Обновляем название плейлиста
        self.header_manager.set_playlist_name(self.playlist_name_edit.text())
        
        # Обновляем пользовательские атрибуты
        self.header_manager.custom_attributes.clear()
        for i in range(self.attrs_table.rowCount()):
            key_item = self.attrs_table.item(i, 0)
            value_item = self.attrs_table.item(i, 1)
            if key_item and value_item:
                self.header_manager.custom_attributes[key_item.text()] = value_item.text()
        
        # Обновляем заголовок
        self.header_manager._update_extm3u_line()
        self.header_manager._update_playlist_name_line()
        
        # Помечаем вкладку как измененную
        self.playlist_tab.modified = True
        self.playlist_tab._update_modified_status()
        
        self.accept()


# ===================== МОДЕЛИ ДАННЫХ =====================
class ChannelData:
    """Данные канала IPTV"""
    
    def __init__(self):
        self.name: str = ""
        self.group: str = "Без группы"
        self.tvg_id: str = ""
        self.tvg_logo: str = ""
        self.url: str = ""
        self.extinf: str = ""
        self.extvlcopt_lines: List[str] = []
        self.extra_headers: Dict[str, str] = {}
        self.has_url: bool = True
        self.url_status: Optional[bool] = None
        self.url_check_time: Optional[datetime] = None
        self.link_source: str = ""  # Источник ссылки
    
    def copy(self) -> 'ChannelData':
        """Создание копии канала"""
        channel = ChannelData()
        channel.name = self.name
        channel.group = self.group
        channel.tvg_id = self.tvg_id
        channel.tvg_logo = self.tvg_logo
        channel.url = self.url
        channel.extinf = self.extinf
        channel.extvlcopt_lines = self.extvlcopt_lines.copy()
        channel.extra_headers = self.extra_headers.copy()
        channel.has_url = self.has_url
        channel.url_status = self.url_status
        channel.url_check_time = self.url_check_time
        channel.link_source = self.link_source
        return channel
    
    def update_extinf(self):
        """Обновление строки #EXTINF на основе данных"""
        parts = ["#EXTINF:-1"]
        if self.tvg_id:
            parts.append(f'tvg-id="{self.tvg_id}"')
        if self.tvg_logo:
            parts.append(f'tvg-logo="{self.tvg_logo}"')
        if self.group:
            parts.append(f'group-title="{self.group}"')
        parts.append(f',{self.name}')
        self.extinf = ' '.join(parts)
    
    def parse_extvlcopt_headers(self):
        """Парсинг заголовков из строк #EXTVLCOPT"""
        self.extra_headers = {}
        for line in self.extvlcopt_lines:
            if line.startswith('#EXTVLCOPT:http-user-agent='):
                user_agent = line.replace('#EXTVLCOPT:http-user-agent=', '').strip('"')
                self.extra_headers['User-Agent'] = user_agent
            elif line.startswith('#EXTVLCOPT:http-referrer='):
                referrer = line.replace('#EXTVLCOPT:http-referrer=', '').strip('"')
                self.extra_headers['Referer'] = referrer
            elif line.startswith('#EXTVLCOPT:http-header='):
                header_line = line.replace('#EXTVLCOPT:http-header=', '').strip('"')
                if ':' in header_line:
                    key, value = header_line.split(':', 1)
                    self.extra_headers[key.strip()] = value.strip()
    
    def update_extvlcopt_from_headers(self):
        """Обновление строк #EXTVLCOPT из заголовков"""
        self.extvlcopt_lines = []
        for key, value in self.extra_headers.items():
            if key.lower() == 'user-agent':
                self.extvlcopt_lines.append(f'#EXTVLCOPT:http-user-agent="{value}"')
            elif key.lower() == 'referer':
                self.extvlcopt_lines.append(f'#EXTVLCOPT:http-referrer="{value}"')
            else:
                self.extvlcopt_lines.append(f'#EXTVLCOPT:http-header="{key}: {value}"')
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь"""
        return {
            'name': self.name,
            'group': self.group,
            'tvg_id': self.tvg_id,
            'tvg_logo': self.tvg_logo,
            'url': self.url,
            'extinf': self.extinf,
            'extvlcopt_lines': self.extvlcopt_lines,
            'extra_headers': self.extra_headers,
            'has_url': self.has_url,
            'url_status': self.url_status,
            'url_check_time': self.url_check_time.isoformat() if self.url_check_time else None,
            'link_source': self.link_source
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChannelData':
        """Создание из словаря"""
        channel = cls()
        channel.name = data.get('name', '')
        channel.group = data.get('group', 'Без группы')
        channel.tvg_id = data.get('tvg_id', '')
        channel.tvg_logo = data.get('tvg_logo', '')
        channel.url = data.get('url', '')
        channel.extinf = data.get('extinf', '')
        channel.extvlcopt_lines = data.get('extvlcopt_lines', [])
        channel.extra_headers = data.get('extra_headers', {})
        channel.has_url = data.get('has_url', True)
        channel.url_status = data.get('url_status')
        channel.link_source = data.get('link_source', '')
        
        check_time = data.get('url_check_time')
        if check_time:
            try:
                channel.url_check_time = datetime.fromisoformat(check_time)
            except:
                channel.url_check_time = None
        
        return channel
    
    def get_status_icon(self) -> str:
        """Получение иконки статуса URL"""
        if not self.has_url or not self.url or not self.url.strip():
            return "∅"
        elif self.url_status is None:
            return "?"
        elif self.url_status is True:
            return "✓"
        elif self.url_status is False:
            return "✗"
        else:
            return "?"
    
    def get_status_color(self) -> QColor:
        """Получение цвета статуса URL"""
        if not self.has_url or not self.url or not self.url.strip():
            return QColor("gray")
        elif self.url_status is None:
            return QColor("orange")
        elif self.url_status is True:
            return QColor("green")
        elif self.url_status is False:
            return QColor("red")
        else:
            return QColor("orange")
    
    def get_status_tooltip(self) -> str:
        """Получение подсказки для статуса"""
        if not self.has_url or not self.url or not self.url.strip():
            return "Нет URL"
        elif self.url_status is None:
            return "Не проверялось"
        elif self.url_status:
            if self.url_check_time:
                return f"Работает (проверено: {self.url_check_time.strftime('%H:%M:%S')})"
            else:
                return "Работает"
        else:
            if self.url_check_time:
                return f"Не работает (проверено: {self.url_check_time.strftime('%H:%M:%S')})"
            else:
                return "Не работает"


# ===================== EPG МОДЕЛИ =====================
class EPGChannel:
    """Информация о канале из EPG"""
    
    def __init__(self):
        self.tvg_id: str = ""
        self.name: str = ""
        self.logo: str = ""
        self.group: str = ""
    
    def to_dict(self) -> Dict[str, str]:
        """Конвертация в словарь"""
        return {
            'tvg_id': self.tvg_id,
            'name': self.name,
            'logo': self.logo,
            'group': self.group
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> 'EPGChannel':
        """Создание из словаря"""
        channel = cls()
        channel.tvg_id = data.get('tvg_id', '')
        channel.name = data.get('name', '')
        channel.logo = data.get('logo', '')
        channel.group = data.get('group', '')
        return channel


class EPGSource:
    """Источник EPG"""
    
    def __init__(self):
        self.name: str = ""
        self.url: str = ""
        self.channels: List[EPGChannel] = []
        self.last_update: Optional[datetime] = None
        self.enabled: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь"""
        return {
            'name': self.name,
            'url': self.url,
            'channels': [ch.to_dict() for ch in self.channels],
            'last_update': self.last_update.isoformat() if self.last_update else None,
            'enabled': self.enabled
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EPGSource':
        """Создание из словаря"""
        source = cls()
        source.name = data.get('name', '')
        source.url = data.get('url', '')
        source.channels = [EPGChannel.from_dict(ch) for ch in data.get('channels', [])]
        
        last_update = data.get('last_update')
        if last_update:
            try:
                source.last_update = datetime.fromisoformat(last_update)
            except:
                source.last_update = None
        
        source.enabled = data.get('enabled', True)
        return source


class EPGManager:
    """Менеджер EPG источников"""
    
    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = SystemThemeManager.get_config_dir()
        
        self.config_dir = config_dir
        self.epg_dir = os.path.join(config_dir, "epg")
        self.sources_file = os.path.join(self.epg_dir, "sources.json")
        self.sources: List[EPGSource] = []
        
        self._ensure_dirs()
        self._load_sources()
        
        # Добавляем источники по умолчанию, если нет других
        if not self.sources:
            self.add_default_sources()
    
    def _ensure_dirs(self):
        """Создание директорий для EPG"""
        if not os.path.exists(self.epg_dir):
            os.makedirs(self.epg_dir, exist_ok=True)
    
    def _load_sources(self):
        """Загрузка источников EPG"""
        try:
            if os.path.exists(self.sources_file):
                with open(self.sources_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.sources = [EPGSource.from_dict(item) for item in data]
                    else:
                        self.sources = []
            else:
                self.sources = []
                self._save_sources()
        except Exception as e:
            print(f"Ошибка загрузки источников EPG: {e}")
            self.sources = []
    
    def _save_sources(self):
        """Сохранение источников EPG"""
        try:
            with open(self.sources_file, 'w', encoding='utf-8') as f:
                json.dump([s.to_dict() for s in self.sources], f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Ошибка сохранения источников EPG: {e}")
            return False
    
    def add_default_sources(self):
        """Добавление предустановленных источников EPG"""
        default_sources = [
            {
                'name': 'Пример EPG (Онлайн)',
                'url': 'https://raw.githubusercontent.com/iptv-org/epg/master/samples/epg.xml'
            },
            {
                'name': 'Локальный пример EPG',
                'url': os.path.join(self.epg_dir, "example.xml")
            }
        ]
        
        added = 0
        for source_data in default_sources:
            if not any(s.url == source_data['url'] for s in self.sources):
                source = EPGSource()
                source.name = source_data['name']
                source.url = source_data['url']
                source.enabled = True
                self.sources.append(source)
                added += 1
        
        if added > 0:
            self._save_sources()
            print(f"Добавлено {added} источников EPG по умолчанию")
        
        return added
    
    def add_source(self, name: str, url: str) -> bool:
        """Добавление нового источника EPG"""
        for source in self.sources:
            if source.url == url:
                return False
        
        source = EPGSource()
        source.name = name
        source.url = url
        source.last_update = datetime.now()
        
        self.sources.append(source)
        return self._save_sources()
    
    def remove_source(self, index: int) -> bool:
        """Удаление источника EPG"""
        if 0 <= index < len(self.sources):
            self.sources.pop(index)
            return self._save_sources()
        return False
    
    def update_source(self, index: int, name: str = None, url: str = None, enabled: bool = None) -> bool:
        """Обновление источника EPG"""
        if 0 <= index < len(self.sources):
            source = self.sources[index]
            if name is not None:
                source.name = name
            if url is not None:
                source.url = url
            if enabled is not None:
                source.enabled = enabled
            return self._save_sources()
        return False
    
    def get_all_sources(self) -> List[EPGSource]:
        """Получение всех источников EPG"""
        return self.sources.copy()
    
    def get_enabled_sources(self) -> List[EPGSource]:
        """Получение включенных источников EPG"""
        return [s for s in self.sources if s.enabled]
    
    def download_epg(self, source: EPGSource) -> bool:
        """Загрузка EPG из источника"""
        try:
            content = ""
            
            if source.url.startswith('http'):
                print(f"Загружаем EPG из URL: {source.url}")
                response = requests.get(source.url, timeout=30)
                response.raise_for_status()
                
                # Проверяем кодировку
                if response.encoding is None:
                    response.encoding = 'utf-8'
                
                content = response.text
                print(f"Загружено {len(content)} символов")
                
            elif os.path.exists(source.url):
                print(f"Загружаем EPG из файла: {source.url}")
                
                # Пробуем разные кодировки
                encodings = ['utf-8', 'utf-8-sig', 'windows-1251', 'cp1251', 'iso-8859-1', 'latin-1', 'cp866']
                for encoding in encodings:
                    try:
                        with open(source.url, 'r', encoding=encoding) as f:
                            content = f.read()
                        print(f"Файл прочитан с кодировкой {encoding}")
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    # Если не удалось прочитать ни с одной кодировкой
                    with open(source.url, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    print("Файл прочитан с игнорированием ошибок кодировки")
            else:
                print(f"Источник не найден: {source.url}")
                return False
            
            # Проверяем, что это XML
            if not content.strip().startswith('<?xml') and not content.strip().startswith('<tv'):
                print("Предупреждение: файл не начинается с XML declaration или <tv>")
                # Добавляем XML заголовок если его нет
                if not content.strip().startswith('<?xml'):
                    content = '<?xml version="1.0" encoding="UTF-8"?>\n' + content
            
            self._parse_xmltv(content, source)
            source.last_update = datetime.now()
            self._save_sources()
            
            print(f"Загружено {len(source.channels)} каналов из источника {source.name}")
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"Ошибка загрузки EPG по URL: {e}")
            return False
        except IOError as e:
            print(f"Ошибка чтения файла EPG: {e}")
            return False
        except Exception as e:
            print(f"Неожиданная ошибка при загрузке EPG: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _parse_xmltv(self, content: str, source: EPGSource):
        """Парсинг XMLTV формата с правильной обработкой display-name"""
        try:
            source.channels = []
            
            # Пробуем распарсить XML
            try:
                # Удаляем возможные лишние символы в начале
                content_clean = content.strip()
                if content_clean.startswith('<?xml'):
                    end_decl = content_clean.find('?>') + 2
                    xml_content = content_clean[end_decl:].strip()
                else:
                    xml_content = content_clean
                
                # Добавляем корневой тег если его нет
                if not xml_content.startswith('<tv>'):
                    xml_content = '<tv>' + xml_content + '</tv>'
                
                root = ET.fromstring(xml_content)
            except ET.ParseError as e:
                print(f"Ошибка парсинга XML: {e}")
                self._parse_xmltv_simple(content, source)
                return
            
            # Находим все элементы channel
            for channel_elem in root.findall('.//channel'):
                channel = EPGChannel()
                
                # Получаем ID канала
                channel.tvg_id = channel_elem.get('id', '')
                
                # Ищем display-name элементы
                display_names = []
                
                # Метод 1: Ищем по имени тега
                for display_name_elem in channel_elem.findall('display-name'):
                    if display_name_elem.text:
                        text = display_name_elem.text.strip()
                        if text:
                            display_names.append(text)
                
                # Метод 2: Если не нашли, ищем вложенный текст
                if not display_names:
                    text_content = channel_elem.text or ""
                    if text_content.strip():
                        display_names.append(text_content.strip())
                
                # Выбираем название
                if display_names:
                    # Предпочитаем названия на русском
                    for name in display_names:
                        # Простая проверка на кириллицу
                        if any('\u0400' <= c <= '\u04FF' for c in name):
                            channel.name = name
                            break
                    
                    # Если русское не нашли, берем первое
                    if not channel.name:
                        channel.name = display_names[0]
                elif channel.tvg_id:
                    # Только если совсем нет display-name
                    channel.name = channel.tvg_id
                else:
                    # Пропускаем канал без названия и ID
                    continue
                
                # Ищем логотип
                icon_elem = channel_elem.find('icon')
                if icon_elem is not None:
                    channel.logo = icon_elem.get('src', '')
                
                # Ищем группу
                group_elem = channel_elem.find('extension')
                if group_elem is not None:
                    group_elem2 = group_elem.find('group')
                    if group_elem2 is not None and group_elem2.text:
                        channel.group = group_elem2.text.strip()
                else:
                    # Ищем group-title напрямую
                    group_elem = channel_elem.find('group')
                    if group_elem is not None and group_elem.text:
                        channel.group = group_elem.text.strip()
                
                source.channels.append(channel)
            
            print(f"Загружено {len(source.channels)} каналов из EPG")
            
        except Exception as e:
            print(f"Ошибка парсинга XMLTV: {e}")
            import traceback
            traceback.print_exc()
            self._parse_xmltv_simple(content, source)
    
    def _parse_xmltv_simple(self, content: str, source: EPGSource):
        """Резервный метод парсинга XMLTV для простых случаев"""
        try:
            source.channels = []
            lines = content.split('\n')
            in_channel = False
            current_channel = None
            
            for line in lines:
                line = line.strip()
                
                # Ищем начало канала
                if '<channel id="' in line or '<channel id=\'' in line:
                    in_channel = True
                    current_channel = EPGChannel()
                    
                    # Извлекаем ID
                    import re
                    match = re.search(r'id=["\']([^"\']+)["\']', line)
                    if match:
                        current_channel.tvg_id = match.group(1)
                
                elif in_channel and '<display-name' in line:
                    # Извлекаем название (учитываем все display-name)
                    display_names = []
                    
                    # Извлекаем текст из текущей строки
                    if '>' in line and '</display-name>' in line:
                        start = line.find('>') + 1
                        end = line.find('</display-name>')
                        if end > start:
                            name = line[start:end].strip()
                            if name:
                                display_names.append(name)
                    
                    # Если нашли display-name, добавляем первое
                    if display_names:
                        current_channel.name = display_names[0]
                
                elif in_channel and '<icon src="' in line or '<icon src=\'' in line:
                    # Извлекаем логотип
                    match = re.search(r'src=["\']([^"\']+)["\']', line)
                    if match:
                        current_channel.logo = match.group(1)
                
                elif in_channel and '</channel>' in line:
                    # Завершаем канал
                    if current_channel:
                        # Если не нашли display-name, используем ID
                        if not current_channel.name and current_channel.tvg_id:
                            current_channel.name = current_channel.tvg_id
                        
                        # Добавляем канал, если есть хотя бы ID
                        if current_channel.name:
                            source.channels.append(current_channel)
                    in_channel = False
                    current_channel = None
                    
            print(f"Загружено {len(source.channels)} каналов из EPG через простой парсер")
            
        except Exception as e:
            print(f"Ошибка парсинга XMLTV старым методом: {e}")
            source.channels = []
    
    def _clean_channel_name(self, name: str) -> str:
        """Очистка названия канала для лучшего сравнения"""
        if not name:
            return ""
        
        # Удаляем общие слова
        stop_words = ['тв', 'tv', 'hd', 'full hd', 'fhd', 'uhd', '4k', 
                      'канал', 'channel', 'телеканал', 'online', 'онлайн']
        
        cleaned = name
        for word in stop_words:
            cleaned = cleaned.replace(word, '')
        
        # Удаляем лишние пробелы и символы
        cleaned = re.sub(r'[^\w\s]', ' ', cleaned)  # Удаляем пунктуацию
        cleaned = re.sub(r'\s+', ' ', cleaned)  # Удаляем лишние пробелы
        cleaned = cleaned.strip()
        
        return cleaned
    
    def find_channel_by_name(self, channel_name: str) -> Optional[EPGChannel]:
        """Поиск канала по имени во всех источниках с улучшенной логикой"""
        if not channel_name:
            return None
        
        print(f"Поиск EPG для канала: '{channel_name}'")
        
        # Подготовка имени для поиска
        search_name = channel_name.lower().strip()
        
        for source in self.get_enabled_sources():
            print(f"  Проверяем источник: {source.name} ({len(source.channels)} каналов)")
            
            for epg_channel in source.channels:
                if not epg_channel.name:
                    continue
                    
                epg_name = epg_channel.name.lower()
                
                # 1. Точное совпадение (без учета регистра)
                if epg_name == search_name:
                    print(f"    Найдено точное совпадение: {epg_channel.name}")
                    return epg_channel
                
                # 2. Удаляем общие слова и символы для лучшего сравнения
                clean_search = self._clean_channel_name(search_name)
                clean_epg = self._clean_channel_name(epg_name)
                
                if clean_search and clean_epg:
                    # Точное совпадение после очистки
                    if clean_epg == clean_search:
                        print(f"    Найдено после очистки: {epg_channel.name}")
                        return epg_channel
                    
                    # Частичное совпадение после очистки
                    if clean_search in clean_epg or clean_epg in clean_search:
                        print(f"    Найдено частичное совпадение: {epg_channel.name}")
                        return epg_channel
                
                # 3. Совпадение по TVG-ID
                if epg_channel.tvg_id and epg_channel.tvg_id.lower() == search_name:
                    print(f"    Найдено по TVG-ID: {epg_channel.name}")
                    return epg_channel
        
        print("  Совпадений не найдено")
        return None
    
    def find_similar_channels(self, channel_name: str, limit: int = 5) -> List[EPGChannel]:
        """Поиск похожих каналов по имени с улучшенной логикой"""
        results = []
        channel_name_lower = channel_name.lower()
        clean_search = self._clean_channel_name(channel_name_lower)
        
        for source in self.get_enabled_sources():
            for epg_channel in source.channels:
                if not epg_channel.name:
                    continue
                    
                epg_name_lower = epg_channel.name.lower()
                clean_epg = self._clean_channel_name(epg_name_lower)
                
                # Определяем уровень совпадения
                score = 0
                
                if epg_name_lower == channel_name_lower:
                    score = 100
                elif channel_name_lower in epg_name_lower:
                    score = 90
                elif epg_name_lower in channel_name_lower:
                    score = 80
                elif clean_epg and clean_search:
                    if clean_epg == clean_search:
                        score = 95
                    elif clean_search in clean_epg:
                        score = 85
                    elif clean_epg in clean_search:
                        score = 75
                    else:
                        # Используем нечеткое сравнение
                        import difflib
                        similarity = difflib.SequenceMatcher(None, clean_search, clean_epg).ratio()
                        score = int(similarity * 100)
                
                if score > 50:
                    results.append((score, epg_channel))
        
        results.sort(key=lambda x: x[0], reverse=True)
        return [ch for score, ch in results[:limit]]
    
    def auto_fill_channels(self, playlist_tab: 'PlaylistTab', progress_callback=None) -> Dict[str, int]:
        """Автоматическое заполнение каналов из EPG"""
        if not playlist_tab:
            return {'updated': 0, 'total': 0}
        
        total_updated = 0
        channels = playlist_tab.all_channels
        
        for i, channel in enumerate(channels):
            if progress_callback:
                if not progress_callback(i, len(channels)):
                    break
            
            if channel.name:
                epg_channel = self.find_channel_by_name(channel.name)
                if epg_channel:
                    updated = False
                    
                    if not channel.tvg_id and epg_channel.tvg_id:
                        channel.tvg_id = epg_channel.tvg_id
                        updated = True
                    
                    if not channel.tvg_logo and epg_channel.logo:
                        channel.tvg_logo = epg_channel.logo
                        updated = True
                    
                    if not channel.group and epg_channel.group:
                        channel.group = epg_channel.group
                        updated = True
                    
                    if updated:
                        channel.update_extinf()
                        total_updated += 1
                        print(f"Обновлен канал: {channel.name}")
        
        return {'updated': total_updated, 'total': len(channels)}


# ===================== ДИАЛОГ УПРАВЛЕНИЯ EPG =====================
class EPGManagerDialog(QDialog):
    """Диалог управления EPG источниками"""
    
    def __init__(self, epg_manager: EPGManager, parent=None):
        super().__init__(parent)
        self.epg_manager = epg_manager
        self.setWindowTitle("Управление источниками EPG")
        self.resize(800, 500)
        
        self._setup_ui()
        self._load_sources()
    
    def _setup_ui(self):
        """Настройка интерфейса диалога"""
        layout = QVBoxLayout(self)
        
        add_group = QGroupBox("Добавить источник EPG")
        add_layout = QFormLayout(add_group)
        
        self.source_name_edit = QLineEdit()
        self.source_name_edit.setPlaceholderText("Название источника (например: EPG TV)")
        
        self.source_url_edit = QLineEdit()
        self.source_url_edit.setPlaceholderText("URL или путь к файлу XMLTV")
        self.source_url_edit.setToolTip(
            "URL EPG источника (например: http://example.com/epg.xml)\n"
            "Или путь к локальному файлу XMLTV"
        )
        
        add_layout.addRow("Название:", self.source_name_edit)
        add_layout.addRow("URL/Путь:", self.source_url_edit)
        
        add_btn = QPushButton("Добавить и загрузить")
        add_btn.clicked.connect(self._add_source)
        add_layout.addRow("", add_btn)
        
        layout.addWidget(add_group)
        
        list_group = QGroupBox("Источники EPG")
        list_layout = QVBoxLayout(list_group)
        
        self.sources_table = QTableWidget()
        self.sources_table.setColumnCount(5)
        self.sources_table.setHorizontalHeaderLabels(["✓", "Название", "URL/Путь", "Каналов", "Обновлено"])
        
        self.sources_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sources_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        
        header = self.sources_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        
        self.sources_table.setColumnWidth(0, 30)
        self.sources_table.setColumnWidth(3, 80)
        self.sources_table.setColumnWidth(4, 120)
        
        list_layout.addWidget(self.sources_table)
        
        btn_layout = QHBoxLayout()
        
        self.update_btn = QPushButton("🔄 Обновить")
        self.update_btn.clicked.connect(self._update_selected_source)
        self.update_btn.setEnabled(False)
        
        self.remove_btn = QPushButton("🗑️ Удалить")
        self.remove_btn.clicked.connect(self._remove_selected_source)
        self.remove_btn.setEnabled(False)
        
        self.toggle_btn = QPushButton("✓ Вкл/Выкл")
        self.toggle_btn.clicked.connect(self._toggle_selected_source)
        self.toggle_btn.setEnabled(False)
        
        self.view_channels_btn = QPushButton("👁️ Просмотр каналов")
        self.view_channels_btn.clicked.connect(self._view_channels)
        self.view_channels_btn.setEnabled(False)
        
        btn_layout.addWidget(self.update_btn)
        btn_layout.addWidget(self.remove_btn)
        btn_layout.addWidget(self.toggle_btn)
        btn_layout.addWidget(self.view_channels_btn)
        
        list_layout.addLayout(btn_layout)
        
        layout.addWidget(list_group)
        
        self.sources_table.itemSelectionChanged.connect(self._on_selection_changed)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _load_sources(self):
        """Загрузка источников в таблицу"""
        sources = self.epg_manager.get_all_sources()
        self.sources_table.setRowCount(len(sources))
        
        for i, source in enumerate(sources):
            enabled_item = QTableWidgetItem()
            enabled_item.setCheckState(Qt.CheckState.Checked if source.enabled else Qt.CheckState.Unchecked)
            enabled_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.sources_table.setItem(i, 0, enabled_item)
            
            self.sources_table.setItem(i, 1, QTableWidgetItem(source.name))
            
            url_display = source.url
            if len(url_display) > 50:
                url_display = url_display[:47] + "..."
            self.sources_table.setItem(i, 2, QTableWidgetItem(url_display))
            self.sources_table.item(i, 2).setToolTip(source.url)
            
            channels_count = len(source.channels)
            self.sources_table.setItem(i, 3, QTableWidgetItem(str(channels_count)))
            self.sources_table.item(i, 3).setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            if source.last_update:
                update_text = source.last_update.strftime("%d.%m.%Y %H:%M")
            else:
                update_text = "Никогда"
            self.sources_table.setItem(i, 4, QTableWidgetItem(update_text))
    
    def _on_selection_changed(self):
        """Обработка изменения выбора"""
        has_selection = len(self.sources_table.selectedItems()) > 0
        self.update_btn.setEnabled(has_selection)
        self.remove_btn.setEnabled(has_selection)
        self.toggle_btn.setEnabled(has_selection)
        self.view_channels_btn.setEnabled(has_selection)
    
    def _add_source(self):
        """Добавление нового источника EPG"""
        name = self.source_name_edit.text().strip()
        url = self.source_url_edit.text().strip()
        
        if not name or not url:
            QMessageBox.warning(self, "Предупреждение", "Заполните название и URL источника")
            return
        
        if url.startswith('http'):
            if not re.match(r'^https?://', url):
                QMessageBox.warning(self, "Предупреждение", "Некорректный URL")
                return
        elif not os.path.exists(url):
            reply = QMessageBox.question(
                self, "Подтверждение",
                "Локальный файл не найден. Всё равно добавить?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
        
        progress_dialog = QProgressDialog("Загрузка EPG...", "Отмена", 0, 100, self)
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setAutoClose(True)
        progress_dialog.show()
        
        QApplication.processEvents()
        
        if self.epg_manager.add_source(name, url):
            source = self.epg_manager.sources[-1]
            if self.epg_manager.download_epg(source):
                QMessageBox.information(self, "Успех", f"Источник добавлен и загружен\nКаналов: {len(source.channels)}")
            else:
                QMessageBox.warning(self, "Предупреждение", "Источник добавлен, но не удалось загрузить EPG")
            
            self._load_sources()
            self.source_name_edit.clear()
            self.source_url_edit.clear()
        else:
            QMessageBox.warning(self, "Предупреждение", "Источник с таким URL уже существует")
        
        progress_dialog.close()
    
    def _update_selected_source(self):
        """Обновление выбранного источника"""
        selected_rows = set()
        for item in self.sources_table.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            return
        
        row = list(selected_rows)[0]
        if 0 <= row < len(self.epg_manager.sources):
            source = self.epg_manager.sources[row]
            
            progress_dialog = QProgressDialog(f"Обновление {source.name}...", "Отмена", 0, 100, self)
            progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            progress_dialog.setAutoClose(True)
            progress_dialog.show()
            
            QApplication.processEvents()
            
            if self.epg_manager.download_epg(source):
                self._load_sources()
                QMessageBox.information(self, "Успех", f"Источник обновлен\nКаналов: {len(source.channels)}")
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось обновить источник")
            
            progress_dialog.close()
    
    def _remove_selected_source(self):
        """Удаление выбранного источника"""
        selected_rows = set()
        for item in self.sources_table.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            return
        
        row = list(selected_rows)[0]
        if 0 <= row < len(self.epg_manager.sources):
            source = self.epg_manager.sources[row]
            
            reply = QMessageBox.question(
                self, "Подтверждение",
                f"Удалить источник '{source.name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                if self.epg_manager.remove_source(row):
                    self._load_sources()
                    QMessageBox.information(self, "Успех", "Источник удален")
    
    def _toggle_selected_source(self):
        """Включение/выключение источника"""
        selected_rows = set()
        for item in self.sources_table.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            return
        
        row = list(selected_rows)[0]
        if 0 <= row < len(self.epg_manager.sources):
            source = self.epg_manager.sources[row]
            new_state = not source.enabled
            
            if self.epg_manager.update_source(row, enabled=new_state):
                self._load_sources()
                status = "включен" if new_state else "выключен"
                QMessageBox.information(self, "Успех", f"Источник {status}")
    
    def _view_channels(self):
        """Просмотр каналов источника"""
        selected_rows = set()
        for item in self.sources_table.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            return
        
        row = list(selected_rows)[0]
        if 0 <= row < len(self.epg_manager.sources):
            source = self.epg_manager.sources[row]
            
            dialog = QDialog(self)
            dialog.setWindowTitle(f"Каналы источника: {source.name}")
            dialog.resize(600, 400)
            
            layout = QVBoxLayout(dialog)
            
            info_label = QLabel(f"Всего каналов: {len(source.channels)}")
            layout.addWidget(info_label)
            
            table = QTableWidget()
            table.setColumnCount(3)
            table.setHorizontalHeaderLabels(["TVG-ID", "Название", "Логотип"])
            table.setRowCount(len(source.channels))
            
            for i, channel in enumerate(source.channels):
                table.setItem(i, 0, QTableWidgetItem(channel.tvg_id))
                table.setItem(i, 1, QTableWidgetItem(channel.name))
                
                logo_display = channel.logo
                if len(logo_display) > 30:
                    logo_display = logo_display[:27] + "..."
                table.setItem(i, 2, QTableWidgetItem(logo_display))
                if channel.logo:
                    table.item(i, 2).setToolTip(channel.logo)
            
            table.horizontalHeader().setStretchLastSection(True)
            layout.addWidget(table)
            
            button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            button_box.rejected.connect(dialog.reject)
            layout.addWidget(button_box)
            
            dialog.exec()


# ===================== ДИАЛОГ АВТОЗАПОЛНЕНИЯ EPG =====================
class EPGAutoFillDialog(QDialog):
    """Диалог автоматического заполнения каналов из EPG"""
    
    def __init__(self, epg_manager: EPGManager, playlist_tab: 'PlaylistTab', parent=None):
        super().__init__(parent)
        self.epg_manager = epg_manager
        self.playlist_tab = playlist_tab
        self.setWindowTitle("Автозаполнение из EPG")
        self.resize(600, 500)
        
        self._setup_ui()
        self._scan_channels()
    
    def _setup_ui(self):
        """Настройка интерфейса диалога"""
        layout = QVBoxLayout(self)
        
        info_group = QGroupBox("Информация о EPG")
        info_layout = QVBoxLayout(info_group)
        
        enabled_sources = self.epg_manager.get_enabled_sources()
        sources_info = f"Включено источников EPG: {len(enabled_sources)}\n"
        
        if enabled_sources:
            total_channels = sum(len(s.channels) for s in enabled_sources)
            sources_info += f"Всего каналов в EPG: {total_channels}\n\n"
            
            for source in enabled_sources:
                channels_count = len(source.channels)
                last_update = source.last_update.strftime("%d.%m.%Y") if source.last_update else "Никогда"
                sources_info += f"• {source.name}: {channels_count} каналов (обновлено: {last_update})\n"
        else:
            sources_info += "Нет включенных источников EPG. Включите их в менеджере EPG."
        
        info_label = QLabel(sources_info)
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)
        
        layout.addWidget(info_group)
        
        options_group = QGroupBox("Параметры заполнения")
        options_layout = QVBoxLayout(options_group)
        
        self.fill_tvg_id_check = QCheckBox("Заполнять TVG-ID")
        self.fill_tvg_id_check.setChecked(True)
        options_layout.addWidget(self.fill_tvg_id_check)
        
        self.fill_logo_check = QCheckBox("Заполнять логотипы")
        self.fill_logo_check.setChecked(True)
        options_layout.addWidget(self.fill_logo_check)
        
        self.fill_group_check = QCheckBox("Заполнять группы")
        self.fill_group_check.setChecked(True)
        options_layout.addWidget(self.fill_group_check)
        
        self.only_empty_check = QCheckBox("Только для пустых полей")
        self.only_empty_check.setChecked(True)
        options_layout.addWidget(self.only_empty_check)
        
        options_layout.addSpacing(10)
        
        similarity_label = QLabel("Минимальная схожесть названий (%):")
        options_layout.addWidget(similarity_label)
        
        self.similarity_slider = QSlider(Qt.Orientation.Horizontal)
        self.similarity_slider.setMinimum(50)
        self.similarity_slider.setMaximum(100)
        self.similarity_slider.setValue(80)
        self.similarity_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.similarity_slider.setTickInterval(10)
        options_layout.addWidget(self.similarity_slider)
        
        self.similarity_label = QLabel("80%")
        self.similarity_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.similarity_slider.valueChanged.connect(
            lambda v: self.similarity_label.setText(f"{v}%")
        )
        options_layout.addWidget(self.similarity_label)
        
        layout.addWidget(options_group)
        
        channels_group = QGroupBox("Каналы для обработки")
        channels_layout = QVBoxLayout(channels_group)
        
        self.channels_list = QListWidget()
        self.channels_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        channels_layout.addWidget(self.channels_list)
        
        select_all_btn = QPushButton("Выделить все")
        select_all_btn.clicked.connect(self._select_all_channels)
        
        select_none_btn = QPushButton("Снять выделение")
        select_none_btn.clicked.connect(self._select_none_channels)
        
        select_btn_layout = QHBoxLayout()
        select_btn_layout.addWidget(select_all_btn)
        select_btn_layout.addWidget(select_none_btn)
        channels_layout.addLayout(select_btn_layout)
        
        layout.addWidget(channels_group)
        
        button_layout = QHBoxLayout()
        
        self.preview_btn = QPushButton("👁️ Предпросмотр")
        self.preview_btn.clicked.connect(self._show_preview)
        
        self.fill_btn = QPushButton("✅ Заполнить выбранные")
        self.fill_btn.clicked.connect(self._fill_channels)
        
        self.auto_fill_btn = QPushButton("🤖 Автоматическое заполнение")
        self.auto_fill_btn.clicked.connect(self._auto_fill_channels)
        self.auto_fill_btn.setToolTip("Автоматически найдет соответствия для всех каналов")
        
        button_layout.addWidget(self.preview_btn)
        button_layout.addWidget(self.fill_btn)
        button_layout.addWidget(self.auto_fill_btn)
        
        layout.addLayout(button_layout)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _scan_channels(self):
        """Сканирование каналов плейлиста"""
        if not self.playlist_tab:
            return
        
        self.channels_list.clear()
        
        for i, channel in enumerate(self.playlist_tab.all_channels):
            if channel.name:
                info = f"{channel.name}"
                if channel.group:
                    info += f" | Группа: {channel.group}"
                if channel.tvg_id:
                    info += f" | TVG-ID: {channel.tvg_id}"
                if not channel.tvg_id or not channel.tvg_logo:
                    info += " [требует заполнения]"
                
                item = QListWidgetItem(info)
                item.setData(Qt.ItemDataRole.UserRole, i)
                
                if not channel.tvg_id or not channel.tvg_logo:
                    item.setForeground(QColor("blue"))
                
                self.channels_list.addItem(item)
        
        self._select_all_channels()
    
    def _select_all_channels(self):
        """Выделить все каналы"""
        for i in range(self.channels_list.count()):
            item = self.channels_list.item(i)
            item.setSelected(True)
    
    def _select_none_channels(self):
        """Снять выделение со всех каналов"""
        for i in range(self.channels_list.count()):
            item = self.channels_list.item(i)
            item.setSelected(False)
    
    def _show_preview(self):
        """Показать предпросмотр заполнения"""
        selected_indices = []
        for i in range(self.channels_list.count()):
            item = self.channels_list.item(i)
            if item.isSelected():
                channel_idx = item.data(Qt.ItemDataRole.UserRole)
                selected_indices.append(channel_idx)
        
        if not selected_indices:
            QMessageBox.warning(self, "Предупреждение", "Выберите каналы для предпросмотра")
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Предпросмотр заполнения")
        dialog.resize(800, 400)
        
        layout = QVBoxLayout(dialog)
        
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["Название", "Текущий TVG-ID", "Новый TVG-ID", 
                                       "Текущий лого", "Новый лого", "Совпадение"])
        table.setRowCount(len(selected_indices))
        
        similarity_threshold = self.similarity_slider.value() / 100.0
        
        for row, channel_idx in enumerate(selected_indices):
            if 0 <= channel_idx < len(self.playlist_tab.all_channels):
                channel = self.playlist_tab.all_channels[channel_idx]
                
                similar_channels = self.epg_manager.find_similar_channels(channel.name, limit=1)
                
                table.setItem(row, 0, QTableWidgetItem(channel.name))
                table.setItem(row, 1, QTableWidgetItem(channel.tvg_id or ""))
                table.setItem(row, 3, QTableWidgetItem(channel.tvg_logo or ""))
                
                if similar_channels:
                    epg_channel = similar_channels[0]
                    table.setItem(row, 2, QTableWidgetItem(epg_channel.tvg_id))
                    table.setItem(row, 4, QTableWidgetItem(epg_channel.logo))
                    
                    import difflib
                    similarity = difflib.SequenceMatcher(None, 
                                                        channel.name.lower(), 
                                                        epg_channel.name.lower()).ratio()
                    match_item = QTableWidgetItem(f"{similarity:.1%}")
                    
                    if similarity >= similarity_threshold:
                        match_item.setForeground(QColor("green"))
                    else:
                        match_item.setForeground(QColor("orange"))
                    
                    table.setItem(row, 5, match_item)
                else:
                    table.setItem(row, 2, QTableWidgetItem("Не найдено"))
                    table.setItem(row, 4, QTableWidgetItem("Не найдено"))
                    match_item = QTableWidgetItem("0%")
                    match_item.setForeground(QColor("red"))
                    table.setItem(row, 5, match_item)
        
        table.horizontalHeader().setStretchLastSection(True)
        table.resizeColumnsToContents()
        layout.addWidget(table)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        dialog.exec()
    
    def _fill_channels(self):
        """Заполнить выбранные каналы"""
        selected_indices = []
        for i in range(self.channels_list.count()):
            item = self.channels_list.item(i)
            if item.isSelected():
                channel_idx = item.data(Qt.ItemDataRole.UserRole)
                selected_indices.append(channel_idx)
        
        if not selected_indices:
            QMessageBox.warning(self, "Предупреждение", "Выберите каналы для заполнения")
            return
        
        self.playlist_tab._save_state("Заполнение из EPG")
        
        similarity_threshold = self.similarity_slider.value() / 100.0
        filled_count = 0
        
        for channel_idx in selected_indices:
            if 0 <= channel_idx < len(self.playlist_tab.all_channels):
                channel = self.playlist_tab.all_channels[channel_idx]
                
                similar_channels = self.epg_manager.find_similar_channels(channel.name, limit=1)
                
                if similar_channels:
                    epg_channel = similar_channels[0]
                    
                    import difflib
                    similarity = difflib.SequenceMatcher(None, 
                                                        channel.name.lower(), 
                                                        epg_channel.name.lower()).ratio()
                    
                    if similarity >= similarity_threshold:
                        if self.fill_tvg_id_check.isChecked():
                            if not self.only_empty_check.isChecked() or not channel.tvg_id:
                                channel.tvg_id = epg_channel.tvg_id
                        
                        if self.fill_logo_check.isChecked():
                            if not self.only_empty_check.isChecked() or not channel.tvg_logo:
                                channel.tvg_logo = epg_channel.logo
                        
                        if self.fill_group_check.isChecked():
                            if not self.only_empty_check.isChecked() or not channel.group:
                                channel.group = epg_channel.group
                        
                        channel.update_extinf()
                        filled_count += 1
                        print(f"Заполнен канал: {channel.name}")
        
        self.playlist_tab._apply_filter()
        self.playlist_tab.modified = True
        self.playlist_tab._update_modified_status()
        
        QMessageBox.information(self, "Успех", 
                              f"Заполнено {filled_count} каналов из {len(selected_indices)} выбранных")
        
        self._scan_channels()
    
    def _auto_fill_channels(self):
        """Автоматическое заполнение всех каналов"""
        reply = QMessageBox.question(
            self, "Подтверждение",
            "Выполнить автоматическое заполнение для всех каналов?\n"
            "Будут использованы параметры заполнения сверху.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.No:
            return
        
        progress_dialog = QProgressDialog("Автоматическое заполнение...", "Отмена", 0, 100, self)
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setAutoClose(True)
        
        def progress_callback(current, total):
            progress = int((current / total) * 100) if total > 0 else 0
            progress_dialog.setValue(progress)
            QApplication.processEvents()
            return not progress_dialog.wasCanceled()
        
        self.playlist_tab._save_state("Автоматическое заполнение из EPG")
        
        result = self.epg_manager.auto_fill_channels(
            self.playlist_tab,
            progress_callback=progress_callback
        )
        
        progress_dialog.close()
        
        self.playlist_tab._apply_filter()
        self.playlist_tab.modified = True
        self.playlist_tab._update_modified_status()
        
        QMessageBox.information(self, "Успех", 
                              f"Автоматически заполнено {result['updated']} каналов из {result['total']}")
        
        self._scan_channels()


# ===================== ЧЁРНЫЙ СПИСОК =====================
class BlacklistManager:
    """Менеджер чёрного списка каналов"""
    
    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = SystemThemeManager.get_config_dir()
        
        self.config_dir = config_dir
        self.blacklist_file = os.path.join(config_dir, "blacklist.json")
        self.blacklist: List[Dict[str, str]] = []
        
        self._ensure_config_dir()
        self._load_blacklist()
    
    def _ensure_config_dir(self):
        """Создание директории для конфигурации"""
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir, exist_ok=True)
    
    def _load_blacklist(self):
        """Загрузка чёрного списка из файла"""
        try:
            if os.path.exists(self.blacklist_file):
                with open(self.blacklist_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.blacklist = data
                    else:
                        self.blacklist = []
            else:
                self.blacklist = []
                self._save_blacklist()
        except Exception as e:
            print(f"Ошибка загрузки чёрного списка: {e}")
            self.blacklist = []
    
    def _save_blacklist(self):
        """Сохранение чёрного списка в файл"""
        try:
            with open(self.blacklist_file, 'w', encoding='utf-8') as f:
                json.dump(self.blacklist, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Ошибка сохранения чёрного списка: {e}")
            return False
    
    def add_channel(self, name: str, tvg_id: str = "", group: str = ""):
        """Добавление канала в чёрный список"""
        for item in self.blacklist:
            if (item.get('name', '').lower() == name.lower() and
                item.get('tvg_id', '').lower() == tvg_id.lower()):
                return False
        
        self.blacklist.append({
            'name': name,
            'tvg_id': tvg_id,
            'group': group,
            'added_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        return self._save_blacklist()
    
    def remove_channel(self, name: str, tvg_id: str = ""):
        """Удаление канала из чёрного списка"""
        for i, item in enumerate(self.blacklist):
            if (item.get('name', '').lower() == name.lower() and
                item.get('tvg_id', '').lower() == tvg_id.lower()):
                del self.blacklist[i]
                self._save_blacklist()
                return True
        return False
    
    def get_all(self) -> List[Dict[str, str]]:
        """Получение всего чёрного списка"""
        return self.blacklist.copy()
    
    def clear(self):
        """Очистка чёрного списка"""
        self.blacklist.clear()
        self._save_blacklist()
    
    def filter_channels(self, channels: List['ChannelData']) -> List['ChannelData']:
        """Фильтрация каналов с удалением тех, что в чёрном списке"""
        filtered_channels = []
        removed_count = 0
        
        for channel in channels:
            should_remove = False
            
            for black_item in self.blacklist:
                name_match = black_item.get('name', '').lower() in channel.name.lower()
                tvg_id_match = (black_item.get('tvg_id', '') and 
                               black_item.get('tvg_id', '').lower() == channel.tvg_id.lower())
                
                group_match = False
                if black_item.get('group', ''):
                    group_match = black_item.get('group', '').lower() in channel.group.lower()
                
                if black_item.get('group', ''):
                    if group_match and (name_match or tvg_id_match):
                        should_remove = True
                        break
                else:
                    if name_match or tvg_id_match:
                        should_remove = True
                        break
            
            if not should_remove:
                filtered_channels.append(channel)
            else:
                removed_count += 1
        
        return filtered_channels, removed_count


# ===================== ДИАЛОГ ЧЁРНОГО СПИСКА =====================
class BlacklistDialog(QDialog):
    """Диалог управления чёрным списком"""
    
    def __init__(self, blacklist_manager: BlacklistManager, parent=None):
        super().__init__(parent)
        self.blacklist_manager = blacklist_manager
        self.setWindowTitle("Управление чёрным списком")
        self.resize(800, 500)
        
        self._setup_ui()
        self._load_blacklist()
    
    def _setup_ui(self):
        """Настройка интерфейса диалога"""
        layout = QVBoxLayout(self)
        
        add_group = QGroupBox("Добавить в чёрный список")
        add_layout = QFormLayout(add_group)
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Название канала (частичное совпадение)")
        
        self.tvg_id_edit = QLineEdit()
        self.tvg_id_edit.setPlaceholderText("TVG-ID (точное совпадение)")
        
        self.group_edit = QLineEdit()
        self.group_edit.setPlaceholderText("Группа (частичное совпадение, необязательно)")
        
        add_layout.addRow("Название:", self.name_edit)
        add_layout.addRow("TVG-ID:", self.tvg_id_edit)
        add_layout.addRow("Группа:", self.group_edit)
        
        add_btn = QPushButton("Добавить")
        add_btn.clicked.connect(self._add_to_blacklist)
        add_layout.addRow("", add_btn)
        
        layout.addWidget(add_group)
        
        list_group = QGroupBox("Чёрный список")
        list_layout = QVBoxLayout(list_group)
        
        self.blacklist_table = QTableWidget()
        self.blacklist_table.setColumnCount(4)
        self.blacklist_table.setHorizontalHeaderLabels(["Название", "TVG-ID", "Группа", "Дата добавления"])
        
        self.blacklist_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.blacklist_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        
        header = self.blacklist_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        
        list_layout.addWidget(self.blacklist_table)
        
        btn_layout = QHBoxLayout()
        
        self.remove_btn = QPushButton("Удалить выбранное")
        self.remove_btn.clicked.connect(self._remove_selected)
        self.remove_btn.setEnabled(False)
        
        clear_btn = QPushButton("Очистить список")
        clear_btn.clicked.connect(self._clear_blacklist)
        
        import_btn = QPushButton("Импорт из файла")
        import_btn.clicked.connect(self._import_blacklist)
        
        export_btn = QPushButton("Экспорт в файл")
        export_btn.clicked.connect(self._export_blacklist)
        
        btn_layout.addWidget(self.remove_btn)
        btn_layout.addWidget(clear_btn)
        btn_layout.addWidget(import_btn)
        btn_layout.addWidget(export_btn)
        
        list_layout.addLayout(btn_layout)
        
        layout.addWidget(list_group)
        
        self.blacklist_table.itemSelectionChanged.connect(self._on_selection_changed)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _load_blacklist(self):
        """Загрузка чёрного списка в таблицу"""
        blacklist = self.blacklist_manager.get_all()
        self.blacklist_table.setRowCount(len(blacklist))
        
        for i, item in enumerate(blacklist):
            self.blacklist_table.setItem(i, 0, QTableWidgetItem(item.get('name', '')))
            self.blacklist_table.setItem(i, 1, QTableWidgetItem(item.get('tvg_id', '')))
            self.blacklist_table.setItem(i, 2, QTableWidgetItem(item.get('group', '')))
            self.blacklist_table.setItem(i, 3, QTableWidgetItem(item.get('added_date', '')))
    
    def _on_selection_changed(self):
        """Обработка изменения выбора"""
        has_selection = len(self.blacklist_table.selectedItems()) > 0
        self.remove_btn.setEnabled(has_selection)
    
    def _add_to_blacklist(self):
        """Добавление канала в чёрный список"""
        name = self.name_edit.text().strip()
        tvg_id = self.tvg_id_edit.text().strip()
        group = self.group_edit.text().strip()
        
        if not name and not tvg_id:
            QMessageBox.warning(self, "Предупреждение", "Укажите название канала или TVG-ID")
            return
        
        if self.blacklist_manager.add_channel(name, tvg_id, group):
            self._load_blacklist()
            self.name_edit.clear()
            self.tvg_id_edit.clear()
            self.group_edit.clear()
            
            parent = self.parent()
            while parent and not isinstance(parent, IPTVEditor):
                parent = parent.parent()
            
            if isinstance(parent, IPTVEditor):
                parent._apply_blacklist_to_all_tabs()
            
            QMessageBox.information(self, "Успех", "Канал добавлен в чёрный список")
        else:
            QMessageBox.warning(self, "Предупреждение", "Канал уже есть в чёрном списке")
    
    def _remove_selected(self):
        """Удаление выбранного элемента из чёрного списка"""
        selected_rows = set()
        for item in self.blacklist_table.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            return
        
        for row in sorted(selected_rows, reverse=True):
            name_item = self.blacklist_table.item(row, 0)
            tvg_id_item = self.blacklist_table.item(row, 1)
            
            if name_item and tvg_id_item:
                name = name_item.text()
                tvg_id = tvg_id_item.text()
                self.blacklist_manager.remove_channel(name, tvg_id)
        
        self._load_blacklist()
        
        parent = self.parent()
        while parent and not isinstance(parent, IPTVEditor):
            parent = parent.parent()
        
        if parent and isinstance(parent, IPTVEditor):
            parent._apply_blacklist_to_all_tabs()
    
    def _clear_blacklist(self):
        """Очистка всего чёрного списка"""
        reply = QMessageBox.question(
            self, "Подтверждение",
            "Вы уверены, что хотите очистить весь чёрный список?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.blacklist_manager.clear()
            self._load_blacklist()
            
            parent = self.parent()
            while parent and not isinstance(parent, IPTVEditor):
                parent = parent.parent()
            
            if parent and isinstance(parent, IPTVEditor):
                parent._apply_blacklist_to_all_tabs()
            
            QMessageBox.information(self, "Успех", "Чёрный список очищен")
    
    def _import_blacklist(self):
        """Импорт чёрного списка из файла"""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Импорт чёрного списка", "",
            "JSON файлы (*.json);;Текстовые файлы (*.txt);;Все файлы (*.*)"
        )
        
        if not filepath:
            return
        
        try:
            if filepath.lower().endswith('.json'):
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if isinstance(data, list):
                    imported = 0
                    for item in data:
                        if isinstance(item, dict):
                            name = item.get('name', '')
                            tvg_id = item.get('tvg_id', '')
                            group = item.get('group', '')
                            if name or tvg_id:
                                self.blacklist_manager.add_channel(name, tvg_id, group)
                                imported += 1
                    
                    self._load_blacklist()
                    
                    parent = self.parent()
                    while parent and not isinstance(parent, IPTVEditor):
                        parent = parent.parent()
                    
                    if parent and isinstance(parent, IPTVEditor):
                        parent._apply_blacklist_to_all_tabs()
                    
                    QMessageBox.information(self, "Успех", f"Импортировано {imported} записей")
                else:
                    QMessageBox.warning(self, "Ошибка", "Некорректный формат JSON файла")
            
            elif filepath.lower().endswith('.txt'):
                with open(filepath, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                imported = 0
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parts = line.split('|')
                        if len(parts) >= 2:
                            name = parts[0].strip()
                            tvg_id = parts[1].strip()
                            group = parts[2].strip() if len(parts) > 2 else ""
                            self.blacklist_manager.add_channel(name, tvg_id, group)
                            imported += 1
                
                self._load_blacklist()
                
                parent = self.parent()
                while parent and not isinstance(parent, IPTVEditor):
                    parent = parent.parent()
                
                if parent and isinstance(parent, IPTVEditor):
                    parent._apply_blacklist_to_all_tabs()
                
                QMessageBox.information(self, "Успех", f"Импортировано {imported} записей")
        
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось импортировать файл:\n{str(e)}")
    
    def _export_blacklist(self):
        """Экспорт чёрного списка в файл"""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Экспорт чёрного списка", "blacklist.json",
            "JSON файлы (*.json);;Текстовые файлы (*.txt);;Все файлы (*.*)"
        )
        
        if not filepath:
            return
        
        try:
            if filepath.lower().endswith('.json'):
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(self.blacklist_manager.get_all(), f, ensure_ascii=False, indent=2)
            
            elif filepath.lower().endswith('.txt'):
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write("# Чёрный список каналов\n")
                    f.write("# Формат: название|tvg-id|группа\n")
                    f.write("# Группа необязательна\n")
                    
                    for item in self.blacklist_manager.get_all():
                        name = item.get('name', '')
                        tvg_id = item.get('tvg_id', '')
                        group = item.get('group', '')
                        f.write(f"{name}|{tvg_id}|{group}\n")
            
            QMessageBox.information(self, "Успех", "Чёрный список экспортирован")
        
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать файл:\n{str(e)}")


# ===================== ПРОВЕРКА ССЫЛОК =====================
class URLCheckerWorker(QThread):
    """Воркер для проверки URL в отдельном потоке"""
    
    progress = pyqtSignal(int, int, str)
    url_checked = pyqtSignal(int, bool, str)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    
    def __init__(self, urls: List[str], timeout: int = 5):
        super().__init__()
        self.urls = urls
        self.timeout = timeout
        self._stop_requested = False
        self._results = {}
    
    def stop(self):
        """Остановка проверки"""
        self._stop_requested = True
    
    def run(self):
        """Запуск проверки URL"""
        try:
            total = len(self.urls)
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = []
                
                for i, url in enumerate(self.urls):
                    if self._stop_requested:
                        break
                    
                    future = executor.submit(self.check_single_url, url, i)
                    futures.append(future)
                
                completed = 0
                for future in concurrent.futures.as_completed(futures):
                    if self._stop_requested:
                        break
                    
                    try:
                        result = future.result(timeout=self.timeout + 2)
                        self._results[result['index']] = result
                        success_bool = result['success'] if result['success'] is not None else False
                        self.url_checked.emit(result['index'], success_bool, result['message'])
                    except Exception as e:
                        self.url_checked.emit(i, False, f"Ошибка: {str(e)}")
                    
                    completed += 1
                    progress = int((completed / total) * 100) if total > 0 else 0
                    self.progress.emit(completed, total, f"Проверено: {completed}/{total}")
            
            self.finished.emit()
            
        except Exception as e:
            self.error.emit(f"Ошибка при проверке URL: {str(e)}")
    
    def check_single_url(self, url: str, index: int) -> Dict[str, Any]:
        """Проверка одного URL"""
        if not url or not url.strip():
            return {'index': index, 'success': False, 'message': 'Пустой URL'}
        
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return {'index': index, 'success': False, 'message': 'Некорректный URL'}
            
            if parsed.scheme in ['http', 'https']:
                try:
                    response = requests.head(
                        url, 
                        timeout=self.timeout,
                        allow_redirects=True,
                        headers={
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                        }
                    )
                    
                    if response.status_code < 400:
                        return {'index': index, 'success': True, 'message': f'HTTP {response.status_code}'}
                    else:
                        return {'index': index, 'success': False, 'message': f'HTTP {response.status_code}'}
                
                except requests.exceptions.Timeout:
                    return {'index': index, 'success': False, 'message': 'Таймаут'}
                except requests.exceptions.ConnectionError:
                    return {'index': index, 'success': False, 'message': 'Ошибка соединения'}
                except requests.exceptions.RequestException as e:
                    return {'index': index, 'success': False, 'message': str(e)}
            
            elif parsed.scheme in ['rtmp', 'rtsp', 'udp', 'tcp', 'rtp']:
                return {'index': index, 'success': None, 'message': 'Потоковый протокол (проверка не поддерживается)'}
            
            else:
                return {'index': index, 'success': False, 'message': f'Неподдерживаемый протокол: {parsed.scheme}'}
                
        except Exception as e:
            return {'index': index, 'success': False, 'message': f'Ошибка: {str(e)}'}
    
    def get_results(self) -> Dict[int, Dict[str, Any]]:
        """Получение полных результатов проверки"""
        return self._results


class URLCheckDialog(QDialog):
    """Диалог проверки URL"""
    
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
        """Настройка интерфейса диалога"""
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
        """Установка URL для проверки"""
        self.urls_to_check = urls
        self.info_label.setText(f"Готово к проверке {len(urls)} ссылок")
    
    def start_checking(self):
        """Начать проверку"""
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
        """Остановить проверку"""
        if self.checker and self.checker.isRunning():
            self.checker.stop()
            self.checker.wait()
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.close_btn.setEnabled(True)
        self.apply_btn.setEnabled(True)
        self.info_label.setText("Проверка остановлена")
    
    def update_progress(self, current: int, total: int, status: str):
        """Обновление прогресса"""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.info_label.setText(f"{status} - {current}/{total}")
    
    def on_url_checked(self, index: int, success: bool, message: str):
        """Обработка проверки одного URL"""
        if self.checker:
            full_result = self.checker.get_results().get(index)
            if full_result:
                self.results[index] = full_result
            else:
                self.results[index] = {'success': None if not success else success, 'message': message}
        
        url = self.urls_to_check[index]
        url_short = url[:50] + "..." if len(url) > 50 else url
        
        if index in self.results and self.results[index]['success'] is None:
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
        """Обработка завершения проверки"""
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
        """Обработка ошибки проверка"""
        QMessageBox.critical(self, "Ошибка", error_message)
        self.on_checking_finished()
    
    def get_results(self) -> Dict[int, Dict[str, Any]]:
        """Получение результатов проверки"""
        return self.results
    
    def accept(self):
        """При закрытии окна передаем результаты"""
        self.url_check_completed.emit(self.results)
        super().accept()
    
    def reject(self):
        """При отмене также передаем результаты"""
        self.url_check_completed.emit(self.results)
        super().reject()
    
    def closeEvent(self, event):
        """Обработка закрытия окна"""
        self.stop_checking()
        event.accept()


# ===================== ОСТАЛЬНЫЕ КЛАССЫ =====================
class UndoRedoManager:
    """Менеджер отмены/повтора действий"""
    
    def __init__(self, max_steps: int = 50):
        self.max_steps = max_steps
        self.undo_stack: List[Dict[str, Any]] = []
        self.redo_stack: List[Dict[str, Any]] = []
    
    def save_state(self, channels: List[ChannelData], description: str = ""):
        """Сохранение состояния"""
        if self.redo_stack:
            self.redo_stack.clear()
        
        state = {
            'channels': [ch.to_dict() for ch in channels],
            'description': description,
            'timestamp': datetime.now().strftime("%H:%M:%S")
        }
        
        self.undo_stack.append(state)
        
        if len(self.undo_stack) > self.max_steps:
            self.undo_stack.pop(0)
    
    def can_undo(self) -> bool:
        return len(self.undo_stack) > 0
    
    def can_redo(self) -> bool:
        return len(self.redo_stack) > 0
    
    def undo(self) -> Optional[Dict[str, Any]]:
        """Отмена действия"""
        if not self.can_undo():
            return None
        
        current_state = self.undo_stack.pop()
        self.redo_stack.append(current_state)
        
        if self.undo_stack:
            return self.undo_stack[-1]
        else:
            return {
                'channels': [],
                'description': 'Начальное состояние',
                'timestamp': datetime.now().strftime("%H:%M:%S")
            }
    
    def redo(self) -> Optional[Dict[str, Any]]:
        """Повтор действия"""
        if not self.can_redo():
            return None
        
        state = self.redo_stack.pop()
        self.undo_stack.append(state)
        
        return state


# ===================== ВСПОМОГАТЕЛЬНЫЕ КЛАССЫ =====================
class M3USyntaxHighlighter(QSyntaxHighlighter):
    """Подсветка синтаксиса M3U"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []
        
        extinf_format = QTextCharFormat()
        extinf_format.setForeground(QColor("#FF6B6B"))
        extinf_format.setFontWeight(QFont.Weight.Bold)
        self.highlighting_rules.append((r'^#EXTINF.*', extinf_format))
        
        extvlcopt_format = QTextCharFormat()
        extvlcopt_format.setForeground(QColor("#4ECDC4"))
        extvlcopt_format.setFontItalic(True)
        self.highlighting_rules.append((r'^#EXTVLCOPT.*', extvlcopt_format))
        
        extx_format = QTextCharFormat()
        extx_format.setForeground(QColor("#9B59B6"))
        self.highlighting_rules.append((r'^#EXT.*', extx_format))
        
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#95A5A6"))
        comment_format.setFontItalic(True)
        self.highlighting_rules.append((r'^#.*', comment_format))
        
        attribute_format = QTextCharFormat()
        attribute_format.setForeground(QColor("#3498DB"))
        self.highlighting_rules.append((r'\b(tvg-id|tvg-logo|group-title)=\"[^"]*\"', attribute_format))
        
        url_format = QTextCharFormat()
        url_format.setForeground(QColor("#2ECC71"))
        url_format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
        self.highlighting_rules.append((r'^(?!\s*#).*://.*', url_format))
        
        http_format = QTextCharFormat()
        http_format.setForeground(QColor("#E67E22"))
        self.highlighting_rules.append((r'^https?://[^\s]+', http_format))
        
        rtmp_format = QTextCharFormat()
        rtmp_format.setForeground(QColor("#E74C3C"))
        self.highlighting_rules.append((r'^rtmp://[^\s]+', rtmp_format))
        
        udp_format = QTextCharFormat()
        udp_format.setForeground(QColor("#F39C12"))
        self.highlighting_rules.append((r'^udp://[^\s]+', udp_format))
    
    def highlightBlock(self, text):
        """Применение правил подсветки к блоку текста"""
        for pattern, format in self.highlighting_rules:
            expression = re.compile(pattern)
            for match in expression.finditer(text):
                start = match.start()
                length = match.end() - start
                self.setFormat(start, length, format)


class EnhancedTextEdit(QPlainTextEdit):
    """Улучшенное текстовое поле с подсветкой синтаксиса и нумерацией строк"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(QFont("Courier New", 10))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.highlighter = M3USyntaxHighlighter(self.document())
        
        self.setViewportMargins(40, 0, 0, 0)
        
        self.line_number_area = LineNumberArea(self)
        self.update_line_number_area_width()
        
        self.textChanged.connect(self.update_line_numbers)
        self.verticalScrollBar().valueChanged.connect(self.update_line_numbers)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
    
    def update_line_number_area_width(self):
        """Обновление ширины области с номерами строк"""
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)
    
    def line_number_area_width(self):
        """Вычисление ширины области с номерами строк"""
        digits = 1
        count = max(1, self.blockCount())
        while count >= 10:
            count /= 10
            digits += 1
        space = 3 + self.fontMetrics().horizontalAdvance('9') * digits
        return space
    
    def update_line_numbers(self):
        """Обновление отображения номеров строк"""
        self.update_line_number_area_width()
        self.line_number_area.update()
    
    def update_line_number_area(self, rect, dy):
        """Обновление области номеров строк"""
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width()
    
    def resizeEvent(self, event):
        """Обработка изменения размера"""
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            cr.left(), cr.top(),
            self.line_number_area_width(), cr.height()
        )
    
    def _show_context_menu(self, position: QPoint):
        """Показать контекстное меню"""
        menu = QMenu(self)
        
        undo_action = QAction("Отменить", menu)
        undo_action.triggered.connect(self.undo)
        menu.addAction(undo_action)
        
        redo_action = QAction("Повторить", menu)
        redo_action.triggered.connect(self.redo)
        menu.addAction(redo_action)
        
        menu.addSeparator()
        
        cut_action = QAction("Вырезать", menu)
        cut_action.triggered.connect(self.cut)
        menu.addAction(cut_action)
        
        copy_action = QAction("Копировать", menu)
        copy_action.triggered.connect(self.copy)
        menu.addAction(copy_action)
        
        paste_action = QAction("Вставить", menu)
        paste_action.triggered.connect(self.paste)
        menu.addAction(paste_action)
        
        menu.addSeparator()
        
        select_all_action = QAction("Выделить всё", menu)
        select_all_action.triggered.connect(self.selectAll)
        menu.addAction(select_all_action)
        
        menu.addSeparator()
        
        format_action = QAction("Форматировать M3U", menu)
        format_action.triggered.connect(self.format_m3u)
        menu.addAction(format_action)
        
        menu.addSeparator()
        
        clear_action = QAction("Очистить", menu)
        clear_action.triggered.connect(self.clear)
        menu.addAction(clear_action)
        
        menu.exec(self.mapToGlobal(position))
    
    def format_m3u(self):
        """Форматирование M3U кода"""
        text = self.toPlainText()
        lines = text.split('\n')
        
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if line:
                if line.startswith('#EXTINF'):
                    if ',' in line:
                        parts = line.split(',', 1)
                        attrs = parts[0]
                        name = parts[1].strip()
                        attrs = re.sub(r'\s+', ' ', attrs)
                        formatted_lines.append(f'{attrs},{name}')
                    else:
                        formatted_lines.append(line)
                elif line.startswith('#EXTVLCOPT'):
                    line = re.sub(r'\s+', ' ', line)
                    formatted_lines.append(line)
                elif not line.startswith('#'):
                    formatted_lines.append(line.strip())
                else:
                    formatted_lines.append(line)
        
        self.setPlainText('\n'.join(formatted_lines))


class LineNumberArea(QWidget):
    """Область для отображения номеров строк"""
    
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
    
    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)
    
    def paintEvent(self, event):
        """Отрисовка номеров строк"""
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor("#2C3E50"))
        
        block = self.editor.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.editor.blockBoundingGeometry(block).translated(self.editor.contentOffset()).top()
        bottom = top + self.editor.blockBoundingRect(block).height()
        
        painter.setPen(QColor("#BDC3C7"))
        painter.setFont(self.editor.font())
        
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.drawText(0, int(top), self.width() - 3, 
                               self.editor.fontMetrics().height(),
                               Qt.AlignmentFlag.AlignRight, number)
            
            block = block.next()
            top = bottom
            bottom = top + self.editor.blockBoundingRect(block).height()
            block_number += 1


class TextEditWithContextMenu(QTextEdit):
    """Текстовое поле с контекстным меню"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
    
    def _show_context_menu(self, position: QPoint):
        """Показать кастомное контекстное меню"""
        menu = QMenu(self)
        
        undo_action = QAction("Отменить", menu)
        undo_action.triggered.connect(self.undo)
        menu.addAction(undo_action)
        
        redo_action = QAction("Повторить", menu)
        redo_action.triggered.connect(self.redo)
        menu.addAction(redo_action)
        
        menu.addSeparator()
        
        cut_action = QAction("Вырезать", menu)
        cut_action.triggered.connect(self.cut)
        menu.addAction(cut_action)
        
        copy_action = QAction("Копировать", menu)
        copy_action.triggered.connect(self.copy)
        menu.addAction(copy_action)
        
        paste_action = QAction("Вставить", menu)
        paste_action.triggered.connect(self.paste)
        menu.addAction(paste_action)
        
        menu.addSeparator()
        
        select_all_action = QAction("Выделить всё", menu)
        select_all_action.triggered.connect(self.selectAll)
        menu.addAction(select_all_action)
        
        menu.addSeparator()
        
        clear_action = QAction("Очистить", menu)
        clear_action.triggered.connect(self.clear)
        menu.addAction(clear_action)
        
        menu.exec(self.mapToGlobal(position))


class LineEditWithContextMenu(QLineEdit):
    """Поле ввода с контекстным меню"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
    
    def _show_context_menu(self, position: QPoint):
        """Показать кастомное контекстное меню"""
        menu = QMenu(self)
        
        undo_action = QAction("Отменить", menu)
        undo_action.triggered.connect(self.undo)
        menu.addAction(undo_action)
        
        redo_action = QAction("Повторить", menu)
        redo_action.triggered.connect(self.redo)
        menu.addAction(redo_action)
        
        menu.addSeparator()
        
        cut_action = QAction("Вырезать", menu)
        cut_action.triggered.connect(self.cut)
        menu.addAction(cut_action)
        
        copy_action = QAction("Копировать", menu)
        copy_action.triggered.connect(self.copy)
        menu.addAction(copy_action)
        
        paste_action = QAction("Вставить", menu)
        paste_action.triggered.connect(self.paste)
        menu.addAction(paste_action)
        
        menu.addSeparator()
        
        select_all_action = QAction("Выделить всё", menu)
        select_all_action.triggered.connect(self.selectAll)
        menu.addAction(select_all_action)
        
        menu.addSeparator()
        
        clear_action = QAction("Очистить", menu)
        clear_action.triggered.connect(self.clear)
        menu.addAction(clear_action)
        
        menu.exec(self.mapToGlobal(position))


class ChannelTableWidget(QTableWidget):
    """Таблица каналов с контекстным меню"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
    
    def _show_context_menu(self, position: QPoint):
        """Показать кастомное контекстное меню для таблица"""
        menu = QMenu(self)
        
        selected_rows = set()
        for item in self.selectedItems():
            selected_rows.add(item.row())
        
        if selected_rows:
            if len(selected_rows) == 1:
                # Контекстное меню для одного выбранного канала
                row = list(selected_rows)[0]
                item = self.itemAt(position)
                
                copy_name_action = QAction("Копировать название", menu)
                copy_name_action.triggered.connect(lambda: self._copy_channel_name(row))
                menu.addAction(copy_name_action)
                
                copy_url_action = QAction("Копировать URL", menu)
                copy_url_action.triggered.connect(lambda: self._copy_channel_url(row))
                menu.addAction(copy_url_action)
                
                menu.addSeparator()
                
                add_to_blacklist_action = QAction("Добавить в чёрный список", menu)
                add_to_blacklist_action.triggered.connect(lambda: self._add_to_blacklist(row))
                menu.addAction(add_to_blacklist_action)
                
                menu.addSeparator()
                
                check_url_action = QAction("Проверить ссылку", menu)
                check_url_action.triggered.connect(lambda: self._check_single_url(row))
                menu.addAction(check_url_action)
                
                menu.addSeparator()
                
                move_up_action = QAction("Переместить вверх", menu)
                move_up_action.triggered.connect(lambda: self._move_channel_up(row))
                menu.addAction(move_up_action)
                
                move_down_action = QAction("Переместить вниз", menu)
                move_down_action.triggered.connect(lambda: self._move_channel_down(row))
                menu.addAction(move_down_action)
                
                menu.addSeparator()
                
                delete_action = QAction("Удалить канал", menu)
                delete_action.triggered.connect(lambda: self._delete_channel(row))
                menu.addAction(delete_action)
            else:
                # Контекстное меню для нескольких выбранных каналов
                count = len(selected_rows)
                menu.addAction(QAction(f"Выбрано каналов: {count}", menu))
                menu.addSeparator()
                
                delete_selected_action = QAction(f"Удалить выбранные ({count})", menu)
                delete_selected_action.triggered.connect(self._delete_selected_channels)
                menu.addAction(delete_selected_action)
                
                move_selected_up_action = QAction(f"Переместить вверх ({count})", menu)
                move_selected_up_action.triggered.connect(self._move_selected_up)
                menu.addAction(move_selected_up_action)
                
                move_selected_down_action = QAction(f"Переместить вниз ({count})", menu)
                move_selected_down_action.triggered.connect(self._move_selected_down)
                menu.addAction(move_selected_down_action)
                
                menu.addSeparator()
                
                check_selected_urls_action = QAction(f"Проверить ссылки ({count})", menu)
                check_selected_urls_action.triggered.connect(self._check_selected_urls)
                menu.addAction(check_selected_urls_action)
                
                add_selected_to_blacklist_action = QAction(f"Добавить в чёрный список ({count})", menu)
                add_selected_to_blacklist_action.triggered.connect(self._add_selected_to_blacklist)
                menu.addAction(add_selected_to_blacklist_action)
        
        menu.exec(self.mapToGlobal(position))
    
    def _copy_channel_name(self, row: int):
        """Копировать название канала"""
        if 0 <= row < self.rowCount():
            item = self.item(row, 0)
            if item:
                clipboard = QApplication.clipboard()
                clipboard.setText(item.text())
    
    def _copy_channel_url(self, row: int):
        """Копировать URL канала"""
        if 0 <= row < self.rowCount():
            item = self.item(row, 2)
            if item:
                clipboard = QApplication.clipboard()
                clipboard.setText(item.text())
    
    def _add_to_blacklist(self, row: int):
        """Добавить канал в чёрный список"""
        parent = self.parent()
        while parent and not hasattr(parent, '_add_to_blacklist'):
            parent = parent.parent()
        
        if parent and hasattr(parent, '_add_to_blacklist'):
            parent._add_to_blacklist(row)
    
    def _add_selected_to_blacklist(self):
        """Добавить выбранные каналы в чёрный список"""
        parent = self.parent()
        while parent and not hasattr(parent, '_add_selected_to_blacklist'):
            parent = parent.parent()
        
        if parent and hasattr(parent, '_add_selected_to_blacklist'):
            parent._add_selected_to_blacklist()
    
    def _check_single_url(self, row: int):
        """Проверить ссылку одного канала"""
        parent = self.parent()
        while parent and not hasattr(parent, '_check_single_url'):
            parent = parent.parent()
        
        if parent and hasattr(parent, '_check_single_url'):
            parent._check_single_url(row)
    
    def _check_selected_urls(self):
        """Проверить ссылки выбранных каналов"""
        parent = self.parent()
        while parent and not hasattr(parent, '_check_selected_urls'):
            parent = parent.parent()
        
        if parent and hasattr(parent, '_check_selected_urls'):
            parent._check_selected_urls()
    
    def _move_channel_up(self, row: int):
        """Переместить канал вверх"""
        parent = self.parent()
        while parent and not hasattr(parent, '_move_channel_up'):
            parent = parent.parent()
        
        if parent and hasattr(parent, '_move_channel_up'):
            parent._move_channel_up(row)
    
    def _move_selected_up(self):
        """Переместить выбранные каналы вверх"""
        parent = self.parent()
        while parent and not hasattr(parent, '_move_selected_up'):
            parent = parent.parent()
        
        if parent and hasattr(parent, '_move_selected_up'):
            parent._move_selected_up()
    
    def _move_channel_down(self, row: int):
        """Переместить канал вниз"""
        parent = self.parent()
        while parent and not hasattr(parent, '_move_channel_down'):
            parent = parent.parent()
        
        if parent and hasattr(parent, '_move_channel_down'):
            parent._move_channel_down(row)
    
    def _move_selected_down(self):
        """Переместить выбранные каналы вниз"""
        parent = self.parent()
        while parent and not hasattr(parent, '_move_selected_down'):
            parent = parent.parent()
        
        if parent and hasattr(parent, '_move_selected_down'):
            parent._move_selected_down()
    
    def _delete_channel(self, row: int):
        """Удалить канал"""
        parent = self.parent()
        while parent and not hasattr(parent, '_delete_channel'):
            parent = parent.parent()
        
        if parent and hasattr(parent, '_delete_channel'):
            parent._delete_channel(row)
    
    def _delete_selected_channels(self):
        """Удалить выбранные каналы"""
        parent = self.parent()
        while parent and not hasattr(parent, '_delete_selected_channels'):
            parent = parent.parent()
        
        if parent and hasattr(parent, '_delete_selected_channels'):
            parent._delete_selected_channels()


# ===================== ВКЛАДКА ПЛЕЙЛИСТА =====================
class PlaylistTab(QWidget):
    """Вкладка с плейлистом"""
    
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
        
        # Менеджер заголовка плейлиста
        self.header_manager = PlaylistHeaderManager()
        
        # Находим родительское окно
        parent_widget = parent
        while parent_widget and not isinstance(parent_widget, IPTVEditor):
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
        """Настройка интерфейса вкладки"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        self.table = ChannelTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Название", "Группа", "URL", "Статус"])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(3, 60)
        
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.doubleClicked.connect(self._on_double_click)
        
        splitter.addWidget(self.table)
        
        edit_panel = QWidget()
        edit_layout = QVBoxLayout(edit_panel)
        edit_layout.setContentsMargins(5, 5, 5, 5)
        
        top_button_frame = QWidget()
        top_button_layout = QHBoxLayout(top_button_frame)
        top_button_layout.setContentsMargins(0, 0, 0, 0)
        
        self.new_btn = QPushButton("📝 Новый")
        self.new_btn.clicked.connect(self._new_channel)
        self.new_btn.setMinimumHeight(35)
        
        self.copy_btn = QPushButton("📋 Копировать")
        self.copy_btn.clicked.connect(self._copy_channel)
        self.copy_btn.setMinimumHeight(35)
        
        self.paste_btn = QPushButton("📎 Вставить")
        self.paste_btn.clicked.connect(self._paste_channel)
        self.paste_btn.setMinimumHeight(35)
        
        top_button_layout.addWidget(self.new_btn)
        top_button_layout.addWidget(self.copy_btn)
        top_button_layout.addWidget(self.paste_btn)
        
        edit_layout.addWidget(top_button_frame)
        
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.Shape.HLine)
        separator1.setFrameShadow(QFrame.Shadow.Sunken)
        separator1.setStyleSheet("background-color: #cccccc;")
        edit_layout.addWidget(separator1)
        
        edit_group = QGroupBox("📺 Редактирование канала")
        form_layout = QFormLayout(edit_group)
        form_layout.setContentsMargins(10, 10, 10, 10)
        form_layout.setSpacing(5)
        
        self.name_edit = LineEditWithContextMenu()
        self.group_edit = LineEditWithContextMenu()
        self.tvg_id_edit = LineEditWithContextMenu()
        self.logo_edit = LineEditWithContextMenu()
        self.url_edit = LineEditWithContextMenu()
        
        logo_layout = QHBoxLayout()
        logo_layout.addWidget(self.logo_edit)
        self.browse_logo_btn = QPushButton("...")
        self.browse_logo_btn.setFixedWidth(30)
        self.browse_logo_btn.clicked.connect(self._browse_logo)
        logo_layout.addWidget(self.browse_logo_btn)
        
        url_layout = QHBoxLayout()
        url_layout.addWidget(self.url_edit)
        self.paste_url_btn = QPushButton("📋")
        self.paste_url_btn.setFixedWidth(30)
        self.paste_url_btn.clicked.connect(self._paste_url)
        url_layout.addWidget(self.paste_url_btn)
        
        self.check_url_btn = QPushButton("🔍")
        self.check_url_btn.setFixedWidth(40)
        self.check_url_btn.clicked.connect(self._check_current_url)
        url_layout.addWidget(self.check_url_btn)
        
        form_layout.addRow("Название:", self.name_edit)
        form_layout.addRow("Группа:", self.group_edit)
        form_layout.addRow("TVG-ID:", self.tvg_id_edit)
        form_layout.addRow("Логотип:", logo_layout)
        form_layout.addRow("URL:", url_layout)
        
        edit_layout.addWidget(edit_group)
        
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.HLine)
        separator2.setFrameShadow(QFrame.Shadow.Sunken)
        separator2.setStyleSheet("background-color: #cccccc;")
        edit_layout.addWidget(separator2)
        
        middle_button_frame = QWidget()
        middle_button_layout = QHBoxLayout(middle_button_frame)
        middle_button_layout.setContentsMargins(0, 0, 0, 0)
        
        self.save_btn = QPushButton("💾 Сохранить")
        self.save_btn.clicked.connect(self._save_channel)
        self.save_btn.setMinimumHeight(35)
        
        self.delete_btn = QPushButton("🗑️ Удалить")
        self.delete_btn.clicked.connect(self._delete_channel)
        self.delete_btn.setMinimumHeight(35)
        
        self.blacklist_btn = QPushButton("⛔ В чёрный список")
        self.blacklist_btn.clicked.connect(self._add_to_blacklist_from_button)
        self.blacklist_btn.setMinimumHeight(35)
        
        middle_button_layout.addWidget(self.save_btn)
        middle_button_layout.addWidget(self.delete_btn)
        middle_button_layout.addWidget(self.blacklist_btn)
        
        edit_layout.addWidget(middle_button_frame)
        
        separator3 = QFrame()
        separator3.setFrameShape(QFrame.Shape.HLine)
        separator3.setFrameShadow(QFrame.Shadow.Sunken)
        separator3.setStyleSheet("background-color: #cccccc;")
        edit_layout.addWidget(separator3)
        
        text_edit_group = QGroupBox("📝 Редактирование M3U")
        text_edit_group.setMinimumHeight(250)
        text_edit_layout = QVBoxLayout(text_edit_group)
        
        info_label = QLabel("Редактируйте M3U-запись канала напрямую:")
        info_label.setStyleSheet("color: #7F8C8D; font-size: 9pt;")
        text_edit_layout.addWidget(info_label)
        
        self.m3u_text_edit = EnhancedTextEdit()
        self.m3u_text_edit.setMinimumHeight(150)
        self.m3u_text_edit.setPlaceholderText(
            "#EXTINF:-1 tvg-id=\"ID\" tvg-logo=\"URL\" group-title=\"Группа\",Название канала\n"
            "#EXTVLCOPT:http-user-agent=\"Mozilla/5.0\"\n"
            "#EXTVLCOPT:http-referrer=\"https://example.com/\"\n"
            "http://example.com/stream.m3u8"
        )
        
        text_edit_layout.addWidget(self.m3u_text_edit)
        
        edit_layout.addWidget(text_edit_group)
        
        separator4 = QFrame()
        separator4.setFrameShape(QFrame.Shape.HLine)
        separator4.setFrameShadow(QFrame.Shadow.Sunken)
        separator4.setStyleSheet("background-color: #cccccc;")
        edit_layout.addWidget(separator4)
        
        bottom_button_frame = QWidget()
        bottom_button_layout = QHBoxLayout(bottom_button_frame)
        bottom_button_layout.setContentsMargins(0, 0, 0, 0)
        
        self.apply_text_btn = QPushButton("✅ Применить изменения")
        self.apply_text_btn.setToolTip("Применить изменения из текстового редактора к каналу")
        self.apply_text_btn.clicked.connect(self._apply_text_edits)
        self.apply_text_btn.setMinimumHeight(35)
        
        self.format_text_btn = QPushButton("🎨 Форматировать")
        self.format_text_btn.setToolTip("Форматировать M3U код")
        self.format_text_btn.clicked.connect(self._format_m3u_text)
        self.format_text_btn.setMinimumHeight(35)
        
        self.blacklist_m3u_btn = QPushButton("⛔ В чёрный список")
        self.blacklist_m3u_btn.setToolTip("Добавить канал из M3U в чёрный список")
        self.blacklist_m3u_btn.clicked.connect(self._add_to_blacklist_from_m3u)
        self.blacklist_m3u_btn.setMinimumHeight(35)
        
        bottom_button_layout.addWidget(self.apply_text_btn)
        bottom_button_layout.addWidget(self.format_text_btn)
        bottom_button_layout.addWidget(self.blacklist_m3u_btn)
        
        edit_layout.addWidget(bottom_button_frame)
        
        edit_layout.addStretch()
        
        splitter.addWidget(edit_panel)
        splitter.setSizes([700, 500])
        
        main_layout.addWidget(splitter)
        
        self.m3u_text_edit.textChanged.connect(self._on_m3u_text_changed)
    
    def _show_status_message(self, message: str, timeout: int = 3000):
        """Показать временное сообщение"""
        if hasattr(self, 'undo_state_changed'):
            self.undo_state_changed.emit(True, True)
        
        parent = self.parent()
        while parent and not hasattr(parent, '_update_status_message'):
            parent = parent.parent()
        
        if parent and hasattr(parent, '_update_status_message'):
            parent._update_status_message(message, timeout)
    
    def _copy_channel(self):
        """Копирование канала в буфер"""
        if self.current_channel:
            parent = self.parent()
            while parent and not hasattr(parent, 'copied_channel'):
                parent = parent.parent()
            
            if parent and hasattr(parent, 'copied_channel'):
                parent.copied_channel = self.current_channel.copy()
                self._show_status_message(f"Канал '{self.current_channel.name}' скопирован в буфер", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Выберите канал для копирования")
    
    def _paste_channel(self):
        """Вставка канала из буфера"""
        parent = self.parent()
        while parent and not hasattr(parent, 'copied_channel'):
            parent = parent.parent()
        
        if not parent or not hasattr(parent, 'copied_channel') or not parent.copied_channel:
            QMessageBox.warning(self, "Предупреждение", "Нет скопированного канала")
            return
        
        self._save_state("Вставка канала")
        
        channel = parent.copied_channel.copy()
        channel.name = f"{channel.name} (вставка)"
        channel.update_extinf()
        
        if self.current_channel:
            try:
                idx = self.all_channels.index(self.current_channel) + 1
                self.all_channels.insert(idx, channel)
            except ValueError:
                self.all_channels.append(channel)
        else:
            self.all_channels.append(channel)
        
        self._update_m3u_text_editor()
        
        self._apply_filter()
        
        self._update_groups_in_main_window()
        
        self.modified = True
        self._update_modified_status()
        
        self._show_status_message("Канал вставлен из буфера", 3000)
    
    def _setup_shortcuts(self):
        """Настройка горячих клавиш"""
        shortcuts = {
            QKeySequence("Ctrl+S"): self._save_channel,
            QKeySequence("Ctrl+Shift+S"): self._apply_text_edits,
            QKeySequence("Ctrl+N"): self._new_channel,
            QKeySequence("Delete"): self._delete_channel,
            QKeySequence("Ctrl+Shift+Delete"): self._delete_selected_channels,
            QKeySequence("Ctrl+Z"): self._undo,
            QKeySequence("Ctrl+Y"): self._redo,
            QKeySequence("Ctrl+A"): self._select_all_channels,
            QKeySequence("Ctrl+B"): self._add_to_blacklist_from_button,
            QKeySequence("Ctrl+F"): self._format_m3u_text,
            QKeySequence("Ctrl+R"): self._update_text_from_form,
            QKeySequence("Ctrl+C"): self._copy_channel,
            QKeySequence("Ctrl+V"): self._paste_channel,
            QKeySequence("Ctrl+Up"): self._move_channel_up,
            QKeySequence("Ctrl+Down"): self._move_channel_down,
            QKeySequence("Ctrl+Shift+Up"): self._move_selected_up,
            QKeySequence("Ctrl+Shift+Down"): self._move_selected_down,
        }
        
        for key, slot in shortcuts.items():
            shortcut = QShortcut(key, self)
            shortcut.activated.connect(slot)
    
    def _on_m3u_text_changed(self):
        """Обработка изменения текста в M3U редакторе"""
        pass
    
    def _update_m3u_text_editor(self):
        """Обновление текстового редактора M3U данными текущего канала"""
        if not self.current_channel:
            self.m3u_text_edit.clear()
            return
        
        lines = []
        
        self.current_channel.update_extinf()
        lines.append(self.current_channel.extinf)
        
        for extra_line in self.current_channel.extvlcopt_lines:
            lines.append(extra_line)
        
        lines.append(self.current_channel.url)
        
        self.m3u_text_edit.setPlainText('\n'.join(lines))
    
    def _apply_text_edits(self):
        """Применение изменений из текстового редактора M3U"""
        if not self.current_channel:
            QMessageBox.warning(self, "Предупреждение", "Нет выбранного канала")
            return
        
        text = self.m3u_text_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Предупреждение", "Текст пуст")
            return
        
        lines = [line.rstrip() for line in text.split('\n') if line.strip()]
        
        if len(lines) < 1:
            QMessageBox.warning(self, "Предупреждение", 
                              "Некорректный формат M3U. Должна быть как минимум строка #EXTINF")
            return
        
        if not lines[0].startswith('#EXTINF:'):
            QMessageBox.warning(self, "Ошибка", "Первая строка должна начинаться с #EXTINF:")
            return
        
        self._save_state("Редактирование в M3U формате")
        
        try:
            extinf_line = lines[0]
            self.current_channel.extinf = extinf_line
            
            if ',' in extinf_line:
                parts = extinf_line.split(',', 1)
                self.current_channel.name = parts[1].strip()
                attrs_part = parts[0]
            else:
                attrs_part = extinf_line
                self.current_channel.name = ""
            
            tvg_id_match = re.search(r'tvg-id="([^"]*)"', attrs_part)
            if tvg_id_match:
                self.current_channel.tvg_id = tvg_id_match.group(1)
            else:
                self.current_channel.tvg_id = ""
            
            logo_match = re.search(r'tvg-logo="([^"]*)"', attrs_part)
            if logo_match:
                self.current_channel.tvg_logo = logo_match.group(1)
            else:
                self.current_channel.tvg_logo = ""
            
            group_match = re.search(r'group-title="([^"]*)"', attrs_part)
            if group_match:
                self.current_channel.group = group_match.group(1)
            else:
                self.current_channel.group = "Без группы"
            
            extvlcopt_lines = []
            url_found = ""
            
            for i in range(1, len(lines)):
                line = lines[i]
                if line.startswith('#'):
                    extvlcopt_lines.append(line)
                elif not url_found and not line.startswith('#'):
                    url_found = line.strip()
            
            self.current_channel.extvlcopt_lines = extvlcopt_lines
            self.current_channel.parse_extvlcopt_headers()
            
            self.current_channel.url = url_found
            self.current_channel.has_url = bool(url_found.strip())
            if url_found:
                self.current_channel.url_status = None
                self.current_channel.url_check_time = None
            
            self._load_channel_to_editor(self.current_channel)
            
            self._apply_filter()
            
            self._update_info()
            
            self.modified = True
            self._update_modified_status()
            
            self._show_status_message("Изменения применены из текстового редактора", 2000)
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось разобрать M3U формат:\n{str(e)}")
            self._undo()
    
    def _format_m3u_text(self):
        """Форматирование текста в M3U редакторе"""
        text = self.m3u_text_edit.toPlainText()
        if not text.strip():
            return
        
        lines = text.split('\n')
        formatted_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('#EXTINF:'):
                if ',' in line:
                    parts = line.split(',', 1)
                    attrs = parts[0].strip()
                    name = parts[1].strip()
                    attrs = re.sub(r'\s+', ' ', attrs)
                    formatted_lines.append(f'{attrs},{name}')
                else:
                    formatted_lines.append(line)
            
            elif line.startswith('#EXTVLCOPT'):
                line = re.sub(r'\s+', ' ', line)
                formatted_lines.append(line)
            
            elif line.startswith('#'):
                formatted_lines.append(line)
            
            else:
                formatted_lines.append(line)
        
        self.m3u_text_edit.setPlainText('\n'.join(formatted_lines))
        self._show_status_message("M3U код отформатирован", 2000)
    
    def _update_text_from_form(self):
        """Обновление текстового редактора из полей формы"""
        if not self.current_channel:
            return
        
        self.current_channel.update_extinf()
        
        self._update_m3u_text_editor()
        
        self._show_status_message("Текстовый редактор обновлен из формы", 2000)
    
    def _add_to_blacklist_from_m3u(self):
        """Добавить канал в чёрный список из M3U редактора"""
        text = self.m3u_text_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Предупреждение", "Нет данных в M3U редакторе")
            return
        
        lines = [line.rstrip() for line in text.split('\n') if line.strip()]
        
        if len(lines) < 1:
            QMessageBox.warning(self, "Предупреждение", 
                              "Некорректный формат M3U")
            return
        
        if not lines[0].startswith('#EXTINF:'):
            QMessageBox.warning(self, "Ошибка", "Первая строка должна начинаться с #EXTINF:")
            return
        
        try:
            extinf_line = lines[0]
            
            name = ""
            tvg_id = ""
            group = ""
            
            if ',' in extinf_line:
                parts = extinf_line.split(',', 1)
                name = parts[1].strip()
                attrs_part = parts[0]
            else:
                attrs_part = extinf_line
            
            tvg_id_match = re.search(r'tvg-id="([^"]*)"', attrs_part)
            if tvg_id_match:
                tvg_id = tvg_id_match.group(1)
            
            group_match = re.search(r'group-title="([^"]*)"', attrs_part)
            if group_match:
                group = group_match.group(1)
            
            if not name:
                QMessageBox.warning(self, "Предупреждение", "Не удалось извлечь название канала")
                return
            
            dialog = QDialog(self)
            dialog.setWindowTitle("Добавить в чёрный список из M3U")
            dialog.resize(400, 200)
            
            layout = QVBoxLayout(dialog)
            
            info_label = QLabel(f"Добавить канал в чёрный список:")
            layout.addWidget(info_label)
            
            name_label = QLabel(f"Название: {name}")
            layout.addWidget(name_label)
            
            tvg_id_label = QLabel(f"TVG-ID: {tvg_id}")
            layout.addWidget(tvg_id_label)
            
            group_label = QLabel(f"Группа: {group}")
            layout.addWidget(group_label)
            
            options_group = QGroupBox("Параметры фильтрации")
            options_layout = QVBoxLayout(options_group)
            
            self.use_name_check = QCheckBox("Фильтровать по названию")
            self.use_name_check.setChecked(True)
            options_layout.addWidget(self.use_name_check)
            
            self.use_tvg_id_check = QCheckBox("Фильтровать по TVG-ID")
            self.use_tvg_id_check.setChecked(bool(tvg_id))
            options_layout.addWidget(self.use_tvg_id_check)
            
            self.use_group_check = QCheckBox("Фильтровать по группе")
            self.use_group_check.setChecked(False)
            options_layout.addWidget(self.use_group_check)
            
            layout.addWidget(options_group)
            
            button_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok |
                QDialogButtonBox.StandardButton.Cancel
            )
            button_box.accepted.connect(dialog.accept)
            button_box.rejected.connect(dialog.reject)
            layout.addWidget(button_box)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                name_to_add = name if self.use_name_check.isChecked() else ""
                tvg_id_to_add = tvg_id if self.use_tvg_id_check.isChecked() else ""
                group_to_add = group if self.use_group_check.isChecked() else ""
                
                if not name_to_add and not tvg_id_to_add:
                    QMessageBox.warning(self, "Предупреждение", 
                                       "Выберите хотя бы один параметр для фильтрации (название или TVG-ID)")
                    return
                
                if self.blacklist_manager:
                    if self.blacklist_manager.add_channel(name_to_add, tvg_id_to_add, group_to_add):
                        QMessageBox.information(self, "Успех", 
                                              "Канал добавлен в чёрный список")
        
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось разобрать M3U формат:\n{str(e)}")
    
    def _save_state(self, description: str = ""):
        """Сохранение состояния для отмены"""
        self.undo_manager.save_state(self.all_channels, description)
        self._update_undo_info()
        self.undo_state_changed.emit(
            self.undo_manager.can_undo(),
            self.undo_manager.can_redo()
        )
    
    def _update_undo_info(self):
        """Обновление информации об отмене/повторе"""
        pass
    
    def _undo(self):
        """Отмена действия"""
        state = self.undo_manager.undo()
        if state:
            self.all_channels = [ChannelData.from_dict(ch) for ch in state['channels']]
            
            self.current_channel = None
            self.selected_channels = []
            self.name_edit.clear()
            self.group_edit.clear()
            self.tvg_id_edit.clear()
            self.logo_edit.clear()
            self.url_edit.clear()
            self.m3u_text_edit.clear()
            
            self._apply_filter()
            
            self._update_info()
            
            self.undo_state_changed.emit(
                self.undo_manager.can_undo(),
                self.undo_manager.can_redo()
            )
            
            self.modified = True
            self._update_modified_status()
            
            self._update_groups_in_main_window()
    
    def _redo(self):
        """Повтор действия"""
        state = self.undo_manager.redo()
        if state:
            self.all_channels = [ChannelData.from_dict(ch) for ch in state['channels']]
            
            self.current_channel = None
            self.selected_channels = []
            self.name_edit.clear()
            self.group_edit.clear()
            self.tvg_id_edit.clear()
            self.logo_edit.clear()
            self.url_edit.clear()
            self.m3u_text_edit.clear()
            
            self._apply_filter()
            
            self._update_info()
            
            self.undo_state_changed.emit(
                self.undo_manager.can_undo(),
                self.undo_manager.can_redo()
            )
            
            self.modified = True
            self._update_modified_status()
            
            self._update_groups_in_main_window()
    
    def _update_modified_status(self):
        """Обновление статуса изменений"""
        self._update_info()
    
    def _check_current_url(self):
        """Проверка URL текущего канала"""
        if not self.current_channel or not self.current_channel.url:
            QMessageBox.warning(self, "Предупреждение", "Нет URL для проверки")
            return
        
        url = self.current_channel.url.strip()
        self._check_urls([url], [self.current_channel])
    
    def _check_single_url(self, row: int):
        """Проверка URL одного канала из таблицы"""
        if 0 <= row < len(self.filtered_channels):
            channel = self.filtered_channels[row]
            if channel and channel.url:
                self._check_urls([channel.url], [channel])
            else:
                QMessageBox.warning(self, "Предупреждение", "У выбранного канала нет URL")
    
    def _check_selected_urls(self):
        """Проверка URL выбранных каналов"""
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
    
    def _check_urls(self, urls: List[str], channels: List[ChannelData]):
        """Проверка нескольких URL"""
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
        """Обработка результатов проверки URL"""
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
    
    def check_all_urls(self):
        """Проверка всех URL в плейлисте"""
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
        """Проверка URL выбранных каналов"""
        self._check_selected_urls()
    
    def remove_non_working_channels(self):
        """Удаление неработающих каналов"""
        non_working = [ch for ch in self.all_channels if ch.url_status is False]
        
        if not non_working:
            QMessageBox.information(self, "Информация", "Нет неработающих каналов")
            return
        
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Найдено {len(non_working)} неработающих каналов. Удалить их?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self._save_state("Удаление неработающих каналов")
            
            for channel in non_working:
                if channel in self.all_channels:
                    self.all_channels.remove(channel)
            
            self._apply_filter()
            
            self._update_groups_in_main_window()
            
            self.modified = True
            self._update_modified_status()
            
            QMessageBox.information(self, "Успех", f"Удалено {len(non_working)} неработающих каналов")
    
    def delete_channels_without_urls(self):
        """Удаление всех каналов без ссылок"""
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
            
            self._update_groups_in_main_window()
            
            self.modified = True
            self._update_modified_status()
            
            QMessageBox.information(self, "Успех", f"Удалено {len(channels_without_urls)} каналов без ссылок")
    
    def _update_groups_in_main_window(self):
        """Обновление списка групп в главном окне"""
        parent = self.parent()
        while parent and not isinstance(parent, IPTVEditor):
            parent = parent.parent()
        
        if parent:
            parent._update_group_filter()
    
    def _load_file(self, filepath: str):
        """Загрузка файла M3U"""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            # Парсим заголовок плейлиста
            self.header_manager.parse_header(content)
            
            # Удаляем заголовок для парсинга каналов
            lines = content.split('\n')
            
            # Находим индекс первой строки канала
            start_index = 0
            for i, line in enumerate(lines):
                if line.startswith('#EXTINF:'):
                    start_index = i
                    break
            
            # Парсим каналы
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
        """Парсинг M3U контента с поддержкой всех строк"""
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
                
                if has_url and url_lines:
                    for url in url_lines:
                        if url.strip():
                            channel.url = url.strip()
                            channel.has_url = True
                            break
                else:
                    channel.url = ""
                    channel.has_url = False
                
                channel.extvlcopt_lines = extvlcopt_lines
                channel.parse_extvlcopt_headers()
                
                self.all_channels.append(channel)
                i = j
            else:
                i += 1
        
        self.filtered_channels = self.all_channels.copy()
    
    def _apply_filter(self):
        """Применение фильтра к каналам"""
        parent = self.parent()
        while parent and not isinstance(parent, IPTVEditor):
            parent = parent.parent()
        
        if parent:
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
        
        self.table.viewport().update()
        
        self._update_info()
    
    def _update_table(self):
        """Обновление таблицы с отфильтрованными каналами"""
        self.table.setRowCount(len(self.filtered_channels))
        
        for i, channel in enumerate(self.filtered_channels):
            name_item = QTableWidgetItem(channel.name[:100] if channel.name else "")
            self.table.setItem(i, 0, name_item)
            
            group_item = QTableWidgetItem(channel.group[:50] if channel.group else "")
            self.table.setItem(i, 1, group_item)
            
            url_display = channel.url
            if url_display and len(url_display) > 50:
                url_display = url_display[:50] + "..."
            url_item = QTableWidgetItem(url_display or "")
            self.table.setItem(i, 2, url_item)
            
            status_item = QTableWidgetItem(channel.get_status_icon())
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setForeground(channel.get_status_color())
            status_item.setToolTip(channel.get_status_tooltip())
            self.table.setItem(i, 3, status_item)
    
    def _update_info(self):
        """Обновление информационной панели"""
        total = len(self.all_channels)
        with_url = sum(1 for ch in self.all_channels if ch.has_url and ch.url and ch.url.strip())
        without_url = total - with_url
        
        working = sum(1 for ch in self.all_channels if ch.url_status is True)
        not_working = sum(1 for ch in self.all_channels if ch.url_status is False)
        unknown = sum(1 for ch in self.all_channels if (ch.url_status is None) and ch.has_url and ch.url and ch.url.strip())
        
        info_text = f"Каналов: {total} | С URL: {with_url} | Работают: {working} | Не работают: {not_working} | Не проверялись: {unknown}"
        
        self.info_changed.emit(info_text)
    
    def _on_selection_changed(self):
        """Обработка изменения выбора"""
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
                self.selected_channels.append(self.filtered_channels[row])
        
        if self.selected_channels:
            self.current_channel = self.selected_channels[-1]
            self._load_channel_to_editor(self.current_channel)
        
        if hasattr(self, 'undo_state_changed'):
            self.undo_state_changed.emit(
                self.undo_manager.can_undo(),
                self.undo_manager.can_redo()
            )
    
    def _on_double_click(self, index):
        """Обработка двойного клика"""
        self._on_selection_changed()
    
    def _load_channel_to_editor(self, channel: ChannelData):
        """Загрузка данных канала в редактор"""
        self.name_edit.setText(channel.name)
        self.group_edit.setText(channel.group)
        self.tvg_id_edit.setText(channel.tvg_id)
        self.logo_edit.setText(channel.tvg_logo)
        self.url_edit.setText(channel.url)
        
        self._update_m3u_text_editor()
    
    def _browse_logo(self):
        """Выбор файла логотипа"""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Выберите логотип", "",
            "Изображения (*.png *.jpg *.jpeg *.gif *.bmp *.ico);;Все файлы (*.*)"
        )
        
        if filepath:
            self.logo_edit.setText(filepath)
    
    def _paste_url(self):
        """Вставка URL из буфера обмена"""
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text:
            self.url_edit.setText(text.strip())
    
    def _new_channel(self):
        """Создание нового канала"""
        self.current_channel = None
        self.selected_channels = []
        self.name_edit.clear()
        self.group_edit.setText("Без группы")
        self.tvg_id_edit.clear()
        self.logo_edit.clear()
        self.url_edit.clear()
        self.m3u_text_edit.clear()
        self.table.clearSelection()
    
    def _save_channel(self):
        """Сохранение канала"""
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Предупреждение", "Введите название канала")
            return
        
        self._save_state("Сохранение канала")
        
        name = self.name_edit.text().strip()
        group = self.group_edit.text().strip() or "Без группы"
        tvg_id = self.tvg_id_edit.text().strip()
        logo = self.logo_edit.text().strip()
        url = self.url_edit.text().strip()
        
        if self.current_channel:
            self.current_channel.name = name
            self.current_channel.group = group
            self.current_channel.tvg_id = tvg_id
            self.current_channel.tvg_logo = logo
            self.current_channel.url = url
            self.current_channel.has_url = bool(url.strip())
            if self.current_channel.url != url:
                self.current_channel.url_status = None
                self.current_channel.url_check_time = None
            self.current_channel.update_extinf()
        else:
            channel = ChannelData()
            channel.name = name
            channel.group = group
            channel.tvg_id = tvg_id
            channel.tvg_logo = logo
            channel.url = url
            channel.has_url = bool(url.strip())
            channel.update_extinf()
            
            self.all_channels.append(channel)
            self.current_channel = channel
        
        self._update_m3u_text_editor()
        
        self._apply_filter()
        
        self._update_groups_in_main_window()
        
        self.modified = True
        self._update_modified_status()
        
        self._show_status_message("Канал сохранен", 2000)
    
    def _select_all_channels(self):
        """Выделить все каналы в таблице"""
        self.table.selectAll()
        self._on_selection_changed()
    
    def _delete_channel(self, row: int = -1):
        """Удалить выбранный канал"""
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
            
            self._new_channel()
            
            self._apply_filter()
            
            self._update_groups_in_main_window()
            
            self.modified = True
            self._update_modified_status()
            
            self._show_status_message(f"Канал удален", 2000)
    
    def _delete_selected_channels(self):
        """Удалить выбранные каналы"""
        if not self.selected_channels:
            QMessageBox.warning(self, "Предупреждение", "Выберите каналы для удаления")
            return
        
        self._delete_channel()
    
    def _add_to_blacklist(self, row: int = -1):
        """Добавить канал в чёрный список"""
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
        
        group_label = QLabel(f"Группа: {channel_to_blacklist.group}")
        layout.addWidget(group_label)
        
        options_group = QGroupBox("Параметры фильтрации")
        options_layout = QVBoxLayout(options_group)
        
        self.use_name_check = QCheckBox("Фильтровать по названию")
        self.use_name_check.setChecked(True)
        options_layout.addWidget(self.use_name_check)
        
        self.use_tvg_id_check = QCheckBox("Фильтровать по TVG-ID")
        self.use_tvg_id_check.setChecked(bool(channel_to_blacklist.tvg_id))
        options_layout.addWidget(self.use_tvg_id_check)
        
        self.use_group_check = QCheckBox("Фильтровать по группе")
        self.use_group_check.setChecked(False)
        options_layout.addWidget(self.use_group_check)
        
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
            group = channel_to_blacklist.group if self.use_group_check.isChecked() else ""
            
            if not name and not tvg_id:
                QMessageBox.warning(self, "Предупреждение", 
                                   "Выберите хотя бы один параметр для фильтрации (название или TVG-ID)")
                return
            
            if self.blacklist_manager:
                if self.blacklist_manager.add_channel(name, tvg_id, group):
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
        """Добавить выбранные каналы в чёрный список"""
        if not self.selected_channels:
            QMessageBox.warning(self, "Предупреждение", "Выберите каналы для добавления в чёрный список")
            return
        
        for channel in self.selected_channels:
            self._add_to_blacklist(self.filtered_channels.index(channel) if channel in self.filtered_channels else -1)
    
    def _add_to_blacklist_from_button(self):
        """Добавить канал в чёрный список из кнопки"""
        self._add_to_blacklist()
    
    def _move_channel_up(self, row: int = -1):
        """Переместить канал вверх"""
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
        """Переместить выбранные каналы вверх"""
        if not self.selected_channels:
            QMessageBox.warning(self, "Предупреждение", "Выберите каналы для перемещения")
            return
        
        # Получаем индексы выбранных каналов в основном списке
        indices = []
        for channel in self.selected_channels:
            try:
                idx = self.all_channels.index(channel)
                indices.append(idx)
            except ValueError:
                continue
        
        if not indices:
            return
        
        # Сортируем индексы для корректного перемещения
        indices.sort()
        
        # Перемещаем каналы, начиная с самого верхнего
        moved_count = 0
        for idx in indices:
            if idx > 0:  # Нельзя переместить первый канал вверх
                if self._move_channel_up_in_list(idx - moved_count):
                    moved_count += 1
    
    def _move_channel_down(self, row: int = -1):
        """Переместить канал вниз"""
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
        """Переместить выбранные каналы вниз"""
        if not self.selected_channels:
            QMessageBox.warning(self, "Предупреждение", "Выберите каналы для перемещения")
            return
        
        # Получаем индексы выбранных каналов в основном списке
        indices = []
        for channel in self.selected_channels:
            try:
                idx = self.all_channels.index(channel)
                indices.append(idx)
            except ValueError:
                continue
        
        if not indices:
            return
        
        # Сортируем индексы для корректного перемещения (снизу вверх)
        indices.sort(reverse=True)
        
        # Перемещаем каналы, начиная с самого нижнего
        for idx in indices:
            if idx < len(self.all_channels) - 1:  # Нельзя переместить последний канал вниз
                self._move_channel_down_in_list(idx)
    
    def _move_channel_up_in_list(self, idx: int):
        """Перемещение канала вверх в основном списке"""
        if idx <= 0:
            return False
        
        self._save_state("Перемещение канала вверх")
        
        self.all_channels[idx], self.all_channels[idx - 1] = \
            self.all_channels[idx - 1], self.all_channels[idx]
        
        self._apply_filter()
        
        # Обновляем текущий канал
        if self.current_channel in self.all_channels:
            self._load_channel_to_editor(self.current_channel)
        
        # Выделяем перемещенные каналы
        selected_indices = []
        for channel in self.selected_channels:
            try:
                new_idx = self.all_channels.index(channel)
                selected_indices.append(new_idx)
            except ValueError:
                continue
        
        # Находим соответствующие индексы в отфильтрованном списке
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
        """Перемещение канала вниз в основном списке"""
        if idx >= len(self.all_channels) - 1:
            return False
        
        self._save_state("Перемещение канала вниз")
        
        self.all_channels[idx], self.all_channels[idx + 1] = \
            self.all_channels[idx + 1], self.all_channels[idx]
        
        self._apply_filter()
        
        # Обновляем текущий канал
        if self.current_channel in self.all_channels:
            self._load_channel_to_editor(self.current_channel)
        
        # Выделяем перемещенные каналы
        selected_indices = []
        for channel in self.selected_channels:
            try:
                new_idx = self.all_channels.index(channel)
                selected_indices.append(new_idx)
            except ValueError:
                continue
        
        # Находим соответствующие индексы в отфильтрованном списке
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
    
    def _merge_duplicates(self):
        """Объединение дубликатов"""
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
            QMessageBox.information(self, "Информация", "Дубликаты не найдены")
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
            
            self._update_groups_in_main_window()
            
            QMessageBox.information(self, "Успех", f"Удалено {removed} дубликатов")
            self.modified = True
            self._update_modified_status()
    
    def apply_blacklist(self):
        """Применить чёрный список к текущему плейлисту"""
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
    
    def save_to_file(self, filepath: str = None) -> bool:
        """Сохранение в файл с сохранением всех строк"""
        if filepath:
            self.filepath = filepath
        
        if not self.filepath:
            return False
        
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                # Записываем заголовок плейлиста
                header_text = self.header_manager.get_header_text()
                if header_text:
                    f.write(header_text)
                else:
                    f.write('#EXTM3U\n')
                
                # Записываем каналы
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
    
    def is_empty(self) -> bool:
        """Проверка, пуста ли вкладка"""
        return (len(self.all_channels) == 0 and 
                not self.filepath and 
                not self.modified)


# ===================== ГЛАВНОЕ ОКНО =====================
class IPTVEditor(QMainWindow):
    """Главное окно редактора IPTV"""
    
    def __init__(self):
        super().__init__()
        
        self.theme_manager = SystemThemeManager()
        self.blacklist_manager = BlacklistManager()
        self.epg_manager = EPGManager()
        
        self.tabs: Dict[QWidget, PlaylistTab] = {}
        self.current_tab: Optional[PlaylistTab] = None
        self.copied_channel: Optional[ChannelData] = None
        
        self.search_edit: Optional[QLineEdit] = None
        self.group_combo: Optional[QComboBox] = None
        
        self.undo_action: Optional[QAction] = None
        self.redo_action: Optional[QAction] = None
        
        self.menu_move_up_action: Optional[QAction] = None
        self.menu_move_down_action: Optional[QAction] = None
        
        self.toolbar_check_url_action: Optional[QAction] = None
        
        self.status_timer = QTimer()
        self.status_timer.setSingleShot(True)
        self.status_timer.timeout.connect(self._reset_status_bar)
        
        self.status_info_label: Optional[QLabel] = None
        self.status_modified_label: Optional[QLabel] = None
        self.status_undo_info_label: Optional[QLabel] = None
        
        self._apply_system_settings()
        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_status_bar()
        
        self._create_welcome_tab()
    
    def _apply_system_settings(self):
        """Применение системных настроек"""
        self.setWindowTitle("Редактор IPTV листов")
        self.resize(1200, 700)
        self.setMinimumSize(800, 600)
        self._center_window()
        
        if sys.platform == "linux" or sys.platform == "linux2":
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #f0f0f0;
                }
                QTableWidget {
                    alternate-background-color: #f8f8f8;
                    selection-background-color: #e1e1e1;
                }
                QTableWidget::item:selected {
                    background-color: #e1e1e1;
                }
                QToolBar {
                    spacing: 5px;
                    padding: 3px;
                    background-color: #e0e0e0;
                    border: 1px solid #c0c0c0;
                }
                QLineEdit {
                    padding: 2px;
                    margin: 0px;
                    border: 1px solid #c0c0c0;
                    border-radius: 3px;
                }
                QComboBox {
                    padding: 2px;
                    margin: 0px;
                    border: 1px solid #c0c0c0;
                    border-radius: 3px;
                }
                QStatusBar {
                    background-color: #e0e0e0;
                    border-top: 1px solid #c0c0c0;
                }
                QStatusBar::item {
                    border: none;
                }
                QLabel {
                    margin: 0px 5px;
                }
                QGroupBox {
                    border: 1px solid #c0c0c0;
                    border-radius: 5px;
                    margin-top: 10px;
                    font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px 0 5px;
                }
                QPushButton {
                    padding: 5px 10px;
                    border: 1px solid #c0c0c0;
                    border-radius: 3px;
                    background-color: #f8f8f8;
                }
                QPushButton:hover {
                    background-color: #e8e8e8;
                }
                QPushButton:pressed {
                    background-color: #d8d8d8;
                }
            """)
        else:
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #f0f0f0;
                }
                QTableWidget {
                    alternate-background-color: #f8f8f8;
                    selection-background-color: #e1e1e1;
                }
                QTableWidget::item:selected {
                    background-color: #e1e1e1;
                }
                QToolBar {
                    spacing: 5px;
                    padding: 3px;
                }
                QLineEdit {
                    padding: 2px;
                    margin: 0px;
                }
                QComboBox {
                    padding: 2px;
                    margin: 0px;
                }
                QStatusBar {
                    background-color: #e0e0e0;
                    border-top: 1px solid #c0c0c0;
                }
                QStatusBar::item {
                    border: none;
                }
                QLabel {
                    margin: 0px 5px;
                }
            """)
    
    def _center_window(self):
        """Центрирование окна"""
        screen_geometry = self.screen().geometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)
    
    def _setup_ui(self):
        """Настройка основного интерфейса"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._close_tab)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        
        layout.addWidget(self.tab_widget)
        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
    
    def _setup_status_bar(self):
        """Настройка статус бара с информацией"""
        self.status_info_label = QLabel()
        self.status_info_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.status_info_label.setStyleSheet("padding: 0px 5px;")
        
        self.status_modified_label = QLabel()
        self.status_modified_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_modified_label.setStyleSheet("padding: 0px 5px; font-weight: bold;")
        
        self.status_undo_info_label = QLabel()
        self.status_undo_info_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.status_undo_info_label.setStyleSheet("padding: 0px 5px; color: #666666;")
        
        self.status_bar.addPermanentWidget(self.status_info_label, 1)
        self.status_bar.addPermanentWidget(self.status_modified_label, 0)
        self.status_bar.addPermanentWidget(self.status_undo_info_label, 0)
        
        self._update_status_info("Нет открытых плейлистов")
        self._update_status_modified(False)
        self._update_status_undo_info(0, 0)
    
    def _update_status_info(self, text: str):
        """Обновление информации в статус баре"""
        if self.status_info_label:
            self.status_info_label.setText(text)
    
    def _update_status_modified(self, modified: bool):
        """Обновление статуса изменений в статус баре"""
        if self.status_modified_label:
            if modified:
                self.status_modified_label.setText("ИЗМЕНЕНО")
                self.status_modified_label.setStyleSheet("padding: 0px 5px; font-weight: bold; color: red;")
            else:
                self.status_modified_label.setText("")
    
    def _update_status_undo_info(self, undo_count: int, redo_count: int):
        """Обновление информации об отмене/повторе в статус бара"""
        if self.status_undo_info_label:
            self.status_undo_info_label.setText(f"Отмена: {undo_count} | Повтор: {redo_count}")
    
    def _filter_channels(self):
        """Фильтрация каналов в текущей вкладке"""
        if self.current_tab:
            self.current_tab._apply_filter()
    
    def _update_group_filter(self):
        """Обновление списка групп в комбобоксе"""
        if not self.current_tab or not self.group_combo:
            return
        
        current = self.group_combo.currentText()
        self.group_combo.blockSignals(True)
        try:
            self.group_combo.clear()
            self.group_combo.addItem("Все группы")
            
            groups = sorted({ch.group for ch in self.current_tab.all_channels if ch.group})
            for group in groups:
                self.group_combo.addItem(group)
            
            if current in groups:
                self.group_combo.setCurrentText(current)
            elif current == "Все группы":
                self.group_combo.setCurrentIndex(0)
        finally:
            self.group_combo.blockSignals(False)
    
    def _create_welcome_tab(self):
        """Создание вкладки-приветствия"""
        welcome_widget = QWidget()
        layout = QVBoxLayout(welcome_widget)
        
        title_label = QLabel("Добро пожаловать в редактор IPTV листов!")
        title_font = QFont()
        title_font.setPointSize(19)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        subtitle_label = QLabel("Выберите действие:")
        subtitle_font = QFont()
        subtitle_font.setPointSize(14)
        subtitle_label.setFont(subtitle_font)
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle_label)
        
        button_layout = QVBoxLayout()
        
        new_playlist_btn = QPushButton("Создать новый плейлист")
        new_playlist_btn.setMinimumHeight(40)
        new_playlist_btn.clicked.connect(self._create_new_playlist)
        
        open_playlist_btn = QPushButton("Открыть существующий плейлист")
        open_playlist_btn.setMinimumHeight(40)
        open_playlist_btn.clicked.connect(self._open_playlist)
        
        manage_blacklist_btn = QPushButton("Управление чёрного списка")
        manage_blacklist_btn.setMinimumHeight(40)
        manage_blacklist_btn.clicked.connect(self._manage_blacklist)
        
        button_layout.addWidget(new_playlist_btn)
        button_layout.addWidget(open_playlist_btn)
        button_layout.addWidget(manage_blacklist_btn)
        
        layout.addLayout(button_layout)
        layout.addStretch()
        
        self.welcome_widget = welcome_widget
        self.tab_widget.addTab(welcome_widget, "Добро пожаловать")
        self.tab_widget.setTabsClosable(False)
    
    def _remove_welcome_tab(self):
        """Удаление вкладки-приветствия"""
        if hasattr(self, 'welcome_widget'):
            index = self.tab_widget.indexOf(self.welcome_widget)
            if index >= 0:
                self.tab_widget.removeTab(index)
            self.tab_widget.setTabsClosable(True)
            del self.welcome_widget
    
    def _setup_menu(self):
        """Настройка меню"""
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("Файл")
        
        new_action = QAction("Создать", self)
        new_action.setShortcut(QKeySequence("Ctrl+N"))
        new_action.triggered.connect(self._create_new_playlist)
        file_menu.addAction(new_action)
        
        open_action = QAction("Открыть", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._open_playlist)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        save_action = QAction("Сохранить", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self._save_current)
        file_menu.addAction(save_action)
        
        save_as_action = QAction("Сохранить как...", self)
        save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_action.triggered.connect(self._save_as)
        file_menu.addAction(save_as_action)
        
        file_menu.addSeparator()
        
        import_action = QAction("Импорт из файла...", self)
        import_action.triggered.connect(self._import_channels)
        file_menu.addAction(import_action)
        
        export_action = QAction("Экспорт списка...", self)
        export_action.triggered.connect(self._export_list)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Выход", self)
        exit_action.setShortcut(QKeySequence("Alt+F4"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        edit_menu = menubar.addMenu("Правка")
        
        self.undo_action = QAction("Отменить", self)
        self.undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        self.undo_action.triggered.connect(self._undo)
        self.undo_action.setEnabled(False)
        edit_menu.addAction(self.undo_action)
        
        self.redo_action = QAction("Повторить", self)
        self.redo_action.setShortcut(QKeySequence("Ctrl+Y"))
        self.redo_action.triggered.connect(self._redo)
        self.redo_action.setEnabled(False)
        edit_menu.addAction(self.redo_action)
        
        edit_menu.addSeparator()
        
        add_channel_action = QAction("Добавить канал", self)
        add_channel_action.setShortcut(QKeySequence("Ctrl+A"))
        add_channel_action.triggered.connect(self._add_channel)
        edit_menu.addAction(add_channel_action)
        
        copy_channel_action = QAction("Копировать канал", self)
        copy_channel_action.setShortcut(QKeySequence("Ctrl+C"))
        copy_channel_action.triggered.connect(self._copy_channel)
        edit_menu.addAction(copy_channel_action)
        
        paste_channel_action = QAction("Вставить канал", self)
        paste_channel_action.setShortcut(QKeySequence("Ctrl+V"))
        paste_channel_action.triggered.connect(self._paste_channel)
        edit_menu.addAction(paste_channel_action)
        
        edit_menu.addSeparator()
        
        self.menu_move_up_action = QAction("Переместить вверх", self)
        self.menu_move_up_action.setShortcut(QKeySequence("Ctrl+Up"))
        self.menu_move_up_action.triggered.connect(self._move_channel_up)
        self.menu_move_up_action.setEnabled(False)
        edit_menu.addAction(self.menu_move_up_action)
        
        self.menu_move_down_action = QAction("Переместить вниз", self)
        self.menu_move_down_action.setShortcut(QKeySequence("Ctrl+Down"))
        self.menu_move_down_action.triggered.connect(self._move_channel_down)
        self.menu_move_down_action.setEnabled(False)
        edit_menu.addAction(self.menu_move_down_action)
        
        edit_menu.addSeparator()
        
        delete_selected_action = QAction("Удалить выбранные", self)
        delete_selected_action.setShortcut(QKeySequence("Ctrl+Shift+Delete"))
        delete_selected_action.triggered.connect(self._delete_selected_channels)
        delete_selected_action.setEnabled(False)
        edit_menu.addAction(delete_selected_action)
        
        move_selected_up_action = QAction("Переместить выбранные вверх", self)
        move_selected_up_action.setShortcut(QKeySequence("Ctrl+Shift+Up"))
        move_selected_up_action.triggered.connect(self._move_selected_up)
        move_selected_up_action.setEnabled(False)
        edit_menu.addAction(move_selected_up_action)
        
        move_selected_down_action = QAction("Переместить выбранные вниз", self)
        move_selected_down_action.setShortcut(QKeySequence("Ctrl+Shift+Down"))
        move_selected_down_action.triggered.connect(self._move_selected_down)
        move_selected_down_action.setEnabled(False)
        edit_menu.addAction(move_selected_down_action)
        
        edit_menu.addSeparator()
        
        merge_duplicates_action = QAction("Объединить дубликаты", self)
        merge_duplicates_action.triggered.connect(self._merge_duplicates)
        edit_menu.addAction(merge_duplicates_action)
        
        tools_menu = menubar.addMenu("Инструменты")
        
        # Управление заголовком плейлиста
        edit_playlist_header_action = QAction("Редактировать заголовок плейлиста...", self)
        edit_playlist_header_action.triggered.connect(self._edit_playlist_header)
        tools_menu.addAction(edit_playlist_header_action)
        
        # EPG функции
        manage_epg_action = QAction("Управление источниками EPG...", self)
        manage_epg_action.triggered.connect(self._manage_epg_sources)
        tools_menu.addAction(manage_epg_action)
        
        auto_fill_epg_action = QAction("Автозаполнение из EPG...", self)
        auto_fill_epg_action.triggered.connect(self._auto_fill_from_epg)
        tools_menu.addAction(auto_fill_epg_action)
        
        update_all_epg_action = QAction("Обновить все EPG", self)
        update_all_epg_action.triggered.connect(self._update_all_epg)
        tools_menu.addAction(update_all_epg_action)
        
        tools_menu.addSeparator()
        
        check_selected_urls_action = QAction("Проверить выбранные ссылки", self)
        check_selected_urls_action.triggered.connect(self._check_selected_urls)
        tools_menu.addAction(check_selected_urls_action)
        
        check_all_urls_action = QAction("Проверить все ссылки", self)
        check_all_urls_action.triggered.connect(self._check_all_urls)
        tools_menu.addAction(check_all_urls_action)
        
        remove_non_working_action = QAction("Удалить неработающие каналы", self)
        remove_non_working_action.triggered.connect(self._remove_non_working_channels)
        tools_menu.addAction(remove_non_working_action)
        
        delete_no_url_action = QAction("Удалить все каналы без ссылок", self)
        delete_no_url_action.triggered.connect(self._delete_channels_without_urls)
        tools_menu.addAction(delete_no_url_action)
        
        tools_menu.addSeparator()
        
        manage_blacklist_action = QAction("Управление чёрного списка...", self)
        manage_blacklist_action.triggered.connect(self._manage_blacklist)
        tools_menu.addAction(manage_blacklist_action)
        
        apply_blacklist_action = QAction("Применить чёрный список к текущему плейлисту", self)
        apply_blacklist_action.triggered.connect(self._apply_blacklist_to_current)
        tools_menu.addAction(apply_blacklist_action)
        
        apply_blacklist_all_action = QAction("Применить чёрный список ко всем плейлистам", self)
        apply_blacklist_all_action.triggered.connect(self._apply_blacklist_to_all_tabs)
        tools_menu.addAction(apply_blacklist_all_action)
        
        view_menu = menubar.addMenu("Вид")
        
        refresh_action = QAction("Обновить", self)
        refresh_action.setShortcut(QKeySequence("F5"))
        refresh_action.triggered.connect(self._refresh_view)
        view_menu.addAction(refresh_action)
        
        help_menu = menubar.addMenu("Справка")
        
        about_action = QAction("О программе", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _edit_playlist_header(self):
        """Редактирование заголовка плейлиста"""
        if not self.current_tab:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки с плейлистом")
            return
        
        dialog = PlaylistHeaderDialog(self.current_tab, self)
        dialog.exec()
    
    def _setup_toolbar(self):
        """Настройка панели инструментов с иконками"""
        toolbar = QToolBar("Панель инструментов")
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(toolbar)
        
        style = self.style()
        
        new_icon = style.standardIcon(style.StandardPixmap.SP_FileIcon)
        new_action = QAction(new_icon, "Создать новый плейлист", self)
        new_action.triggered.connect(self._create_new_playlist)
        toolbar.addAction(new_action)
        
        open_icon = style.standardIcon(style.StandardPixmap.SP_DialogOpenButton)
        open_action = QAction(open_icon, "Открыть существующий плейлист", self)
        open_action.triggered.connect(self._open_playlist)
        toolbar.addAction(open_action)
        
        save_icon = style.standardIcon(style.StandardPixmap.SP_DialogSaveButton)
        save_action = QAction(save_icon, "Сохранить текущий плейлист", self)
        save_action.triggered.connect(self._save_current)
        toolbar.addAction(save_action)
        
        toolbar.addSeparator()
        
        move_up_icon = style.standardIcon(style.StandardPixmap.SP_ArrowUp)
        move_up_action = QAction(move_up_icon, "Переместить канал вверх", self)
        move_up_action.triggered.connect(self._move_channel_up)
        move_up_action.setEnabled(False)
        toolbar.addAction(move_up_action)
        
        move_down_icon = style.standardIcon(style.StandardPixmap.SP_ArrowDown)
        move_down_action = QAction(move_down_icon, "Переместить канал вниз", self)
        move_down_action.triggered.connect(self._move_channel_down)
        move_down_action.setEnabled(False)
        toolbar.addAction(move_down_action)
        
        toolbar.addSeparator()
        
        undo_icon = style.standardIcon(style.StandardPixmap.SP_ArrowBack)
        undo_action = QAction(undo_icon, "Отменить последнее действие", self)
        undo_action.triggered.connect(self._undo)
        undo_action.setEnabled(False)
        toolbar.addAction(undo_action)
        
        redo_icon = style.standardIcon(style.StandardPixmap.SP_ArrowForward)
        redo_action = QAction(redo_icon, "Повторить отмененное действие", self)
        redo_action.triggered.connect(self._redo)
        redo_action.setEnabled(False)
        toolbar.addAction(redo_action)
        
        toolbar.addSeparator()
        
        check_url_icon = style.standardIcon(style.StandardPixmap.SP_DialogYesButton)
        self.toolbar_check_url_action = QAction(check_url_icon, "Проверить выбранные ссылки", self)
        self.toolbar_check_url_action.triggered.connect(self._check_selected_urls)
        self.toolbar_check_url_action.setEnabled(False)
        toolbar.addAction(self.toolbar_check_url_action)
        
        blacklist_icon = style.standardIcon(style.StandardPixmap.SP_DialogNoButton)
        blacklist_action = QAction(blacklist_icon, "Управление чёрного списка", self)
        blacklist_action.triggered.connect(self._manage_blacklist)
        toolbar.addAction(blacklist_action)
        
        refresh_icon = style.standardIcon(style.StandardPixmap.SP_BrowserReload)
        refresh_action = QAction(refresh_icon, "Обновить вид", self)
        refresh_action.triggered.connect(self._refresh_view)
        toolbar.addAction(refresh_action)
        
        toolbar.addSeparator()
        
        toolbar.addWidget(QLabel("Группа:"))
        
        self.group_combo = QComboBox()
        self.group_combo.addItem("Все группы")
        self.group_combo.setFixedWidth(150)
        self.group_combo.currentTextChanged.connect(self._filter_channels)
        toolbar.addWidget(self.group_combo)
        
        toolbar.addSeparator()
        
        toolbar.addWidget(QLabel("Поиск:"))
        
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Введите текст для поиска...")
        self.search_edit.setFixedWidth(200)
        self.search_edit.textChanged.connect(self._filter_channels)
        toolbar.addWidget(self.search_edit)
    
    def _update_undo_redo_buttons(self):
        """Обновление состояния кнопок отмены/повтора"""
        if self.current_tab:
            can_undo = self.current_tab.undo_manager.can_undo()
            can_redo = self.current_tab.undo_manager.can_redo()
            has_current_channel = self.current_tab.current_channel is not None
            has_selected_channels = len(self.current_tab.selected_channels) > 0
            
            undo_count = len(self.current_tab.undo_manager.undo_stack) - 1 if can_undo else 0
            redo_count = len(self.current_tab.undo_manager.redo_stack)
            self._update_status_undo_info(undo_count, redo_count)
            
            self._update_status_modified(self.current_tab.modified)
        else:
            can_undo = False
            can_redo = False
            has_current_channel = False
            has_selected_channels = False
            self._update_status_undo_info(0, 0)
            self._update_status_modified(False)
        
        if self.undo_action:
            self.undo_action.setEnabled(can_undo)
        
        if self.redo_action:
            self.redo_action.setEnabled(can_redo)
        
        if self.menu_move_up_action:
            self.menu_move_up_action.setEnabled(has_current_channel)
        
        if self.menu_move_down_action:
            self.menu_move_down_action.setEnabled(has_current_channel)
        
        # Обновляем действия для групповых операций
        for action in self.menuBar().actions():
            if action.text() in ["Удалить выбранные", "Переместить выбранные вверх", "Переместить выбранные вниз"]:
                action.setEnabled(has_selected_channels and len(self.current_tab.selected_channels) > 1)
        
        toolbar = self.findChild(QToolBar)
        if toolbar:
            actions = toolbar.actions()
            for action in actions:
                tooltip = action.toolTip()
                if tooltip == "Отменить последнее действие":
                    action.setEnabled(can_undo)
                elif tooltip == "Повторить отмененное действие":
                    action.setEnabled(can_redo)
                elif tooltip == "Переместить канал вверх":
                    action.setEnabled(has_current_channel)
                elif tooltip == "Переместить канал вниз":
                    action.setEnabled(has_current_channel)
                elif tooltip == "Проверить выбранные ссылки":
                    action.setEnabled(has_selected_channels)
    
    def _on_tab_info_changed(self, info_text: str):
        """Обработка изменения информации во вкладке"""
        self._update_status_info(info_text)
    
    def _on_tab_undo_state_changed(self, can_undo: bool, can_redo: bool):
        """Обработка изменения состояния отмены/повтора во вкладке"""
        sender = self.sender()
        if sender == self.current_tab:
            self._update_undo_redo_buttons()
    
    def _manage_epg_sources(self):
        """Управление источниками EPG"""
        dialog = EPGManagerDialog(self.epg_manager, self)
        dialog.exec()
    
    def _auto_fill_from_epg(self):
        """Автоматическое заполнение из EPG"""
        if not self.current_tab:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки с плейлистом")
            return
        
        enabled_sources = self.epg_manager.get_enabled_sources()
        if not enabled_sources:
            reply = QMessageBox.question(
                self, "Нет источников EPG",
                "Нет включенных источников EPG. Открыть менеджер EPG?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._manage_epg_sources()
            return
        
        dialog = EPGAutoFillDialog(self.epg_manager, self.current_tab, self)
        dialog.exec()
    
    def _update_all_epg(self):
        """Обновить все источники EPG"""
        enabled_sources = self.epg_manager.get_enabled_sources()
        if not enabled_sources:
            QMessageBox.information(self, "Информация", "Нет включенных источников EPG")
            return
        
        progress_dialog = QProgressDialog("Обновление источников EPG...", "Отмена", 0, len(enabled_sources), self)
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setAutoClose(True)
        
        success_count = 0
        for i, source in enumerate(enabled_sources):
            progress_dialog.setValue(i)
            progress_dialog.setLabelText(f"Обновление {source.name}... ({i+1}/{len(enabled_sources)})")
            QApplication.processEvents()
            
            if progress_dialog.wasCanceled():
                break
            
            if self.epg_manager.download_epg(source):
                success_count += 1
        
        progress_dialog.close()
        
        QMessageBox.information(self, "Готово", 
                              f"Обновлено {success_count} из {len(enabled_sources)} источников EPG")
    
    def _create_new_tab(self, filepath: str = None) -> PlaylistTab:
        """Создание новой вкладки с плейлистом"""
        if hasattr(self, 'welcome_widget'):
            self._remove_welcome_tab()
        
        empty_tabs = [tab for tab in self.tabs.values() if tab.is_empty()]
        
        if empty_tabs and len(self.tabs) == 1:
            tab = empty_tabs[0]
            if filepath and os.path.exists(filepath):
                tab.filepath = filepath
                tab._load_file(filepath)
        else:
            tab = PlaylistTab(filepath, self, self.blacklist_manager)
            widget = tab
            
            tab.undo_state_changed.connect(self._on_tab_undo_state_changed)
            tab.info_changed.connect(self._on_tab_info_changed)
            
            if filepath:
                tab_name = os.path.basename(filepath)
                if len(tab_name) > 15:
                    tab_name = tab_name[:13] + ".."
            else:
                tab_name = "Новый плейлист"
            
            index = self.tab_widget.addTab(widget, tab_name)
            self.tabs[widget] = tab
            self.tab_widget.setCurrentIndex(index)
        
        self.current_tab = tab
        
        self._update_group_filter()
        
        tab._update_info()
        
        self._update_undo_redo_buttons()
        
        return tab
    
    def _create_new_playlist(self):
        """Создание нового плейлиста"""
        self._create_new_tab()
        self._update_status_message("Создан новый плейлист", 3000)
    
    def _open_playlist(self):
        """Открытие плейлиста"""
        filepaths, _ = QFileDialog.getOpenFileNames(
            self, "Выберите файлы плейлистов", "",
            "M3U файлы (*.m3u *.m3u8);;Все файлы (*.*)"
        )
        
        if not filepaths:
            return
        
        for filepath in filepaths:
            if os.path.exists(filepath):
                self._create_new_tab(filepath)
                self._update_status_message(f"Открыт файл: {os.path.basename(filepath)}", 3000)
            else:
                QMessageBox.warning(self, "Предупреждение", f"Файл не найден: {filepath}")
    
    def _save_current(self):
        """Сохранение текущего плейлиста"""
        if not self.current_tab:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
            return
        
        if self.current_tab.filepath:
            if self.current_tab.save_to_file():
                self._update_status_message("Плейлист сохранен", 3000)
        else:
            self._save_as()
    
    def _save_as(self):
        """Сохранение как..."""
        if not self.current_tab:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
            return
        
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Сохранить файл", "",
            "M3U файлы (*.m3u *.m3u8);;Все файлы (*.*)"
        )
        
        if filepath:
            if self.current_tab.save_to_file(filepath):
                index = self.tab_widget.currentIndex()
                tab_name = os.path.basename(filepath)
                if len(tab_name) > 15:
                    tab_name = tab_name[:13] + ".."
                self.tab_widget.setTabText(index, tab_name)
                
                self._update_status_message(f"Сохранено как: {tab_name}", 3000)
    
    def _close_tab(self, index: int):
        """Закрытие вкладки"""
        widget = self.tab_widget.widget(index)
        
        if widget in self.tabs:
            tab = self.tabs[widget]
            
            if hasattr(tab, 'undo_state_changed'):
                tab.undo_state_changed.disconnect()
            if hasattr(tab, 'info_changed'):
                tab.info_changed.disconnect()
            
            if tab.modified:
                reply = QMessageBox.question(
                    self, "Подтверждение",
                    "Вкладка содержит несохраненные изменения. Закрыть без сохранения?",
                    QMessageBox.StandardButton.Yes |
                    QMessageBox.StandardButton.No |
                    QMessageBox.StandardButton.Cancel
                )
                
                if reply == QMessageBox.StandardButton.Cancel:
                    return
                elif reply == QMessageBox.StandardButton.Yes:
                    for tab in self.tabs.values():
                        if tab.modified:
                            if not tab.filepath:
                                filepath, _ = QFileDialog.getSaveFileName(
                                    self, f"Сохранить вкладку", "",
                                    "M3U файлы (*.m3u *.m3u8)"
                                )
                                if filepath:
                                    tab.save_to_file(filepath)
                                else:
                                    return
                            else:
                                tab.save_to_file()
            
            self.tab_widget.removeTab(index)
            del self.tabs[widget]
            
            if self.tab_widget.count() == 0:
                self._create_welcome_tab()
                self.current_tab = None
                self._update_undo_redo_buttons()
                self._update_status_info("Нет открытых плейлистов")
    
    def _on_tab_changed(self, index: int):
        """Обработка изменения текущей вкладки"""
        if index >= 0:
            widget = self.tab_widget.widget(index)
            
            if not hasattr(self, 'welcome_widget') or widget != self.welcome_widget:
                self.current_tab = self.tabs.get(widget)
            else:
                self.current_tab = None
        
        self._update_group_filter()
        self._filter_channels()
        
        if self.current_tab:
            self.current_tab._update_info()
        else:
            self._update_status_info("Нет открытых плейлистов")
        
        self._update_undo_redo_buttons()
    
    def _add_channel(self):
        """Добавление канала"""
        if self.current_tab:
            self.current_tab._new_channel()
            self._update_status_message("Готов к добавлению нового канала", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _copy_channel(self):
        """Копирование канала в буфер приложения"""
        if self.current_tab:
            self.current_tab._copy_channel()
    
    def _paste_channel(self):
        """Вставка канала из буфера приложения"""
        if self.current_tab:
            self.current_tab._paste_channel()
    
    def _move_channel_up(self):
        """Переместить выбранный канал вверх"""
        if self.current_tab and self.current_tab.current_channel:
            try:
                idx = self.current_tab.all_channels.index(self.current_tab.current_channel)
                self.current_tab._move_channel_up_in_list(idx)
                self._update_status_message("Канал перемещен вверх", 3000)
            except ValueError:
                pass
        else:
            QMessageBox.warning(self, "Предупреждение", "Выберите канал для перемещения")
    
    def _move_channel_down(self):
        """Переместить выбранный канал вниз"""
        if self.current_tab and self.current_tab.current_channel:
            try:
                idx = self.current_tab.all_channels.index(self.current_tab.current_channel)
                self.current_tab._move_channel_down_in_list(idx)
                self._update_status_message("Канал перемещен вниз", 3000)
            except ValueError:
                pass
        else:
            QMessageBox.warning(self, "Предупреждение", "Выберите канал для перемещения")
    
    def _move_selected_up(self):
        """Переместить выбранные каналы вверх"""
        if self.current_tab:
            self.current_tab._move_selected_up()
            self._update_status_message("Выбранные каналы перемещены вверх", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _move_selected_down(self):
        """Переместить выбранные каналы вниз"""
        if self.current_tab:
            self.current_tab._move_selected_down()
            self._update_status_message("Выбранные каналы перемещены вниз", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _delete_selected_channels(self):
        """Удалить выбранные каналы"""
        if self.current_tab:
            self.current_tab._delete_selected_channels()
            self._update_status_message("Выбранные каналы удалены", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _check_selected_urls(self):
        """Проверка выбранных URL"""
        if self.current_tab:
            self.current_tab.check_selected_urls()
            self._update_status_message("Проверка выбранных ссылок", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _check_all_urls(self):
        """Проверка всех URL"""
        if self.current_tab:
            self.current_tab.check_all_urls()
            self._update_status_message("Проверка всех ссылок", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _remove_non_working_channels(self):
        """Удаление неработающих каналов"""
        if self.current_tab:
            self.current_tab.remove_non_working_channels()
            self._update_status_message("Удаление неработающих каналов", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _delete_channels_without_urls(self):
        """Удаление всех каналов без ссылок"""
        if self.current_tab:
            self.current_tab.delete_channels_without_urls()
            self._update_status_message("Удаление каналов без ссылок", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _manage_blacklist(self):
        """Управление чёрным списком"""
        dialog = BlacklistDialog(self.blacklist_manager, self)
        dialog.exec()
    
    def _apply_blacklist_to_current(self):
        """Применить чёрный список к текущему плейлисту"""
        if self.current_tab:
            removed = self.current_tab.apply_blacklist()
            if removed > 0:
                self._update_status_message(f"Удалено {removed} каналов из текущего плейлиста", 3000)
            else:
                QMessageBox.information(self, "Информация", 
                                       "В текущем плейлисте нет каналов из чёрного списка")
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _apply_blacklist_to_all_tabs(self):
        """Применить чёрный список ко всем открытым плейлистам"""
        if not self.tabs:
            QMessageBox.information(self, "Информация", "Нет открытых плейлистов")
            return
        
        total_removed = 0
        
        for tab in self.tabs.values():
            removed = tab.apply_blacklist()
            total_removed += removed
        
        if total_removed > 0:
            self._update_status_message(f"Удалено {total_removed} каналов из всех плейлистов", 3000)
        else:
            QMessageBox.information(self, "Информация", 
                                   "В открытых плейлистах нет каналов из чёрного списка")
    
    def _import_channels(self):
        """Импорт каналов из файла"""
        if not self.current_tab:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
            return
        
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Импорт каналов из файла", "",
            "Текстовые файлы (*.txt);;CSV файлы (*.csv);;M3U файлы (*.m3u);;Все файлы (*.*)"
        )
        
        if not filepath:
            return
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            imported_count = 0
            
            if filepath.lower().endswith(('.m3u', '.m3u8')):
                self.current_tab._parse_m3u(content)
                imported_count = len(self.current_tab.all_channels)
            elif filepath.lower().endswith('.csv'):
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parts = line.split(';')
                        if len(parts) >= 2:
                            channel = ChannelData()
                            channel.name = parts[0].strip()
                            channel.url = parts[1].strip()
                            channel.has_url = bool(channel.url.strip())
                            
                            if len(parts) > 2:
                                channel.group = parts[2].strip()
                            else:
                                channel.group = "Импортированные"
                            
                            if len(parts) > 3:
                                channel.tvg_id = parts[3].strip()
                            if len(parts) > 4:
                                channel.tvg_logo = parts[4].strip()
                            
                            channel.update_extinf()
                            self.current_tab.all_channels.append(channel)
                            imported_count += 1
            else:
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parts = line.split('|')
                        if len(parts) >= 2:
                            channel = ChannelData()
                            channel.name = parts[0].strip()
                            channel.url = parts[1].strip()
                            channel.has_url = bool(channel.url.strip())
                            channel.group = "Импортированные"
                            
                            if len(parts) > 2:
                                channel.group = parts[2].strip()
                            
                            channel.update_extinf()
                            self.current_tab.all_channels.append(channel)
                            imported_count += 1
            
            self.current_tab._save_state("Импорт каналов")
            
            self._update_group_filter()
            self.current_tab._apply_filter()
            self.current_tab._update_info()
            self.current_tab.modified = True
            
            self._update_status_message(f"Импортировано {imported_count} каналов", 3000)
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось импортировать файл:\n{str(e)}")
    
    def _export_list(self):
        """Экспорт списка каналов"""
        if self.current_tab:
            self._export_channels()
    
    def _export_channels(self):
        """Экспорт каналов в файл"""
        if not self.current_tab or not self.current_tab.all_channels:
            QMessageBox.warning(self, "Предупреждение", "Нет каналов для экспорта")
            return
        
        filepath, selected_filter = QFileDialog.getSaveFileName(
            self, "Экспорт каналов", "",
            "Текстовые файлы (*.txt);;CSV файлы (*.csv);;M3U файлы (*.m3u);;Все файлы (*.*)"
        )
        
        if not filepath:
            return
        
        try:
            if filepath.lower().endswith('.csv'):
                self._export_to_csv(filepath)
            elif filepath.lower().endswith(('.m3u', '.m3u8')):
                self.current_tab.save_to_file(filepath)
            else:
                self._export_to_text(filepath)
            
            QMessageBox.information(self, "Успех", "Экспорт каналов завершен успешно!")
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать:\n{str(e)}")
    
    def _export_to_csv(self, filepath: str):
        """Экспорт в CSV"""
        with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
            f.write("Название;Группа;TVG-ID;Логотип;URL;Статус\n")
            for channel in self.current_tab.all_channels:
                status = channel.get_status_icon()
                f.write(f'{channel.name};{channel.group};{channel.tvg_id};{channel.tvg_logo};{channel.url};{status}\n')
    
    def _export_to_text(self, filepath: str):
        """Экспорт в текстовый формат"""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"Экспорт каналов из плейлиста\n")
            f.write(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Всего каналов: {len(self.current_tab.all_channels)}\n")
            f.write("="*80 + "\n\n")
            
            groups = {}
            for channel in self.current_tab.all_channels:
                if channel.group not in groups:
                    groups[channel.group] = []
                groups[channel.group].append(channel)
            
            for group in sorted(groups.keys()):
                f.write(f"\nГруппа: {group}\n")
                f.write("-"*40 + "\n")
                for idx, channel in enumerate(groups[group], 1):
                    status = channel.get_status_icon()
                    f.write(f"{idx:3}. {status} {channel.name}\n")
                    if channel.url:
                        display_url = channel.url[:50] + "..." if len(channel.url) > 50 else channel.url
                        f.write(f"     URL: {display_url}\n")
                    if channel.url_status is not None:
                        status_text = "Работает" if channel.url_status else "Не работает"
                        f.write(f"     Статус: {status_text}\n")
    
    def _merge_duplicates(self):
        """Объединение дубликатов"""
        if self.current_tab:
            self.current_tab._merge_duplicates()
            self._update_group_filter()
            self._filter_channels()
            self._update_status_message("Дубликаты объединены", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _refresh_view(self):
        """Обновление вида"""
        if self.current_tab:
            if self.search_edit:
                self.search_edit.clear()
            if self.group_combo:
                self.group_combo.setCurrentIndex(0)
            
            self._update_group_filter()
            self._filter_channels()
            self.current_tab._update_info()
            self._update_status_message("Вид обновлен", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _undo(self):
        """Отмена действия"""
        if self.current_tab:
            self.current_tab._undo()
            self._update_group_filter()
            self._filter_channels()
            
            self._update_undo_redo_buttons()
            
            self._update_status_message("Действие отменено", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _redo(self):
        """Повтор действия"""
        if self.current_tab:
            self.current_tab._redo()
            self._update_group_filter()
            self._filter_channels()
            
            self._update_undo_redo_buttons()
            
            self._update_status_message("Действие повторено", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _show_about(self):
        """Показать информацию о программе"""
        about_text = (
            "Редактор IPTV листов"
        )
        
        QMessageBox.about(self, "О программе", about_text)
    
    def _update_status_message(self, message: str, timeout: int = 0):
        """Обновление временного сообщения в статус баре"""
        self.status_bar.showMessage(message, timeout)
    
    def _reset_status_bar(self):
        """Сброс статус бара к значению по умолчанию"""
        self.status_bar.showMessage("")
    
    def closeEvent(self, event):
        """Обработка закрытия окна"""
        modified_tabs = [tab for tab in self.tabs.values() if tab.modified]
        
        if modified_tabs:
            reply = QMessageBox.question(
                self, "Подтверждение",
                f"Найдено {len(modified_tabs)} вкладок с несохраненными изменениями.\n"
                "Сохранить изменения перед выходом?",
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No |
                QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            elif reply == QMessageBox.StandardButton.Yes:
                for tab in modified_tabs:
                    if tab.modified:
                        if not tab.filepath:
                            filepath, _ = QFileDialog.getSaveFileName(
                                self, f"Сохранить вкладку", "",
                                "M3U файлы (*.m3u *.m3u8)"
                            )
                            if filepath:
                                tab.save_to_file(filepath)
                            else:
                                event.ignore()
                                return
                        else:
                            tab.save_to_file()
        
        event.accept()


def main():
    """Точка входа в приложение"""
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    
    if sys.platform == "linux" or sys.platform == "linux2":
        app.setStyle("Fusion")
    else:
        app.setStyle("Fusion")
    
    window = IPTVEditor()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
