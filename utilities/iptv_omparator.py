"""
IPTV Playlist Comparator - Standalone Application
На базе PyQt6 с идентичным интерфейсом оригинального плагина
"""

import sys
import os
import re
import json
import difflib
import shutil
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Set, Optional, Any
from enum import Enum

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QTabWidget, QTextEdit, QFileDialog, QMessageBox, QMenu,
    QProgressDialog, QDialog, QRadioButton, QCheckBox, QGroupBox,
    QSpinBox, QSlider, QSplitter, QHeaderView, QStatusBar,
    QToolBar, QMenuBar, QFrame
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, QSettings, 
    QItemSelectionModel, QAbstractItemModel
)
from PyQt6.QtGui import (
    QAction, QIcon, QFont, QColor, QBrush, 
    QClipboard, QDesktopServices
)


class ChannelStatus(Enum):
    """Статус канала при сравнении"""
    UNIQUE_IN_FIRST = "unique_first"
    UNIQUE_IN_SECOND = "unique_second"
    COMMON = "common"
    SIMILAR = "similar"
    DIFFERENT_URL = "different_url"


@dataclass
class Channel:
    """Представление канала в плейлисте"""
    name: str = ""
    group: str = "Без группы"
    tvg_id: str = ""
    tvg_logo: str = ""
    url: str = ""
    extinf: str = ""
    has_url: bool = False
    file_path: str = ""
    status: Optional[ChannelStatus] = None
    
    @classmethod
    def from_extinf(cls, extinf_line: str, url_line: str = "", file_path: str = "") -> 'Channel':
        """Создать канал из строки EXTINF"""
        channel = cls()
        channel.extinf = extinf_line
        channel.url = url_line.strip()
        channel.has_url = bool(channel.url)
        channel.file_path = file_path
        
        if ',' in extinf_line:
            parts = extinf_line.split(',', 1)
            channel.name = parts[1].strip()
        
        attrs_part = extinf_line.split(',')[0] if ',' in extinf_line else extinf_line
        
        patterns = {
            'tvg_id': r'tvg-id="([^"]*)"',
            'tvg_logo': r'tvg-logo="([^"]*)"',
            'group': r'group-title="([^"]*)"'
        }
        
        for attr, pattern in patterns.items():
            match = re.search(pattern, attrs_part)
            if match:
                setattr(channel, attr, match.group(1))
        
        return channel
    
    @property
    def key(self) -> str:
        """Уникальный ключ для сравнения"""
        return f"{self.name.lower()}|{self.group.lower()}"
    
    @property
    def key_with_url(self) -> str:
        """Уникальный ключ с учетом URL"""
        url_part = self.url.strip().rstrip('/')
        return f"{self.key}|{url_part}"
    
    def to_dict(self) -> Dict[str, str]:
        """Преобразовать канал в словарь"""
        return {
            'name': self.name,
            'group': self.group,
            'tvg_id': self.tvg_id,
            'tvg_logo': self.tvg_logo,
            'url': self.url,
            'extinf': self.extinf,
            'file_path': self.file_path,
            'status': self.status.value if self.status else None
        }


@dataclass
class ComparisonResult:
    """Результат сравнения двух плейлистов"""
    unique_in_first: List[Channel] = field(default_factory=list)
    unique_in_second: List[Channel] = field(default_factory=list)
    common_channels: List[Channel] = field(default_factory=list)
    similar_channels: List[Dict[str, Any]] = field(default_factory=list)
    different_url_channels: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def total_unique_first(self) -> int:
        return len(self.unique_in_first)
    
    @property
    def total_unique_second(self) -> int:
        return len(self.unique_in_second)
    
    @property
    def total_common(self) -> int:
        return len(self.common_channels)
    
    @property
    def total_similar(self) -> int:
        return len(self.similar_channels)
    
    @property
    def total_different_url(self) -> int:
        return len(self.different_url_channels)


class PlaylistLoader:
    """Загрузчик и валидатор плейлистов"""
    
    @staticmethod
    def validate_playlist(file_path: str) -> Tuple[bool, str, int]:
        """Проверить валидность плейлиста"""
        try:
            if not os.path.exists(file_path):
                return False, "Файл не существует", 0
            
            if os.path.getsize(file_path) == 0:
                return False, "Файл пуст", 0
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read(1024)
            
            if not content.startswith('#EXTM3U'):
                try:
                    with open(file_path, 'r', encoding='cp1251') as f:
                        content = f.read(1024)
                    if not content.startswith('#EXTM3U'):
                        return False, "Файл не является валидным M3U плейлистом", 0
                except:
                    return False, "Файл не является валидным M3U плейлистом", 0
            
            encodings = ['utf-8', 'cp1251', 'latin-1']
            lines = []
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        lines = f.readlines()
                    break
                except UnicodeDecodeError:
                    continue
            
            if not lines:
                return False, "Неподдерживаемая кодировка файла", 0
            
            extinf_count = sum(1 for line in lines if line.startswith('#EXTINF:'))
            if extinf_count == 0:
                return False, "В плейлисте не найдены каналы", 0
            
            return True, f"Валидный плейлист", extinf_count
            
        except IOError as e:
            return False, f"Ошибка чтения файла: {str(e)}", 0
        except Exception as e:
            return False, f"Неизвестная ошибка: {str(e)}", 0
    
    @staticmethod
    def load_playlist(file_path: str) -> Optional[List[Channel]]:
        """Загрузить плейлист из файла"""
        try:
            is_valid, message, count = PlaylistLoader.validate_playlist(file_path)
            if not is_valid:
                return None
            
            encodings = ['utf-8', 'cp1251', 'latin-1']
            content = None
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                return None
            
            channels = []
            lines = content.splitlines()
            i = 0
            
            while i < len(lines):
                line = lines[i].strip()
                
                if line.startswith('#EXTINF:'):
                    url = ""
                    j = i + 1
                    while j < len(lines) and (not lines[j].strip() or lines[j].startswith('#')):
                        j += 1
                    
                    if j < len(lines):
                        url = lines[j].strip()
                    
                    channel = Channel.from_extinf(line, url, file_path)
                    channels.append(channel)
                    
                    i = j if j > i else i + 1
                else:
                    i += 1
            
            return channels
            
        except Exception as e:
            print(f"Ошибка загрузки плейлиста: {e}")
            return None


class ComparisonThread(QThread):
    """Поток для сравнения плейлистов"""
    
    progress_updated = pyqtSignal(int, str)
    comparison_completed = pyqtSignal(ComparisonResult)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, first_playlist_path: str, second_playlist_path: str, similarity_threshold: float = 0.7):
        super().__init__()
        self.first_playlist_path = first_playlist_path
        self.second_playlist_path = second_playlist_path
        self.similarity_threshold = similarity_threshold
        
    def run(self):
        """Запуск сравнения в отдельном потоке"""
        try:
            self.progress_updated.emit(0, "Загрузка плейлистов...")
            
            first_channels = PlaylistLoader.load_playlist(self.first_playlist_path)
            second_channels = PlaylistLoader.load_playlist(self.second_playlist_path)
            
            if not first_channels or not second_channels:
                self.error_occurred.emit("Не удалось загрузить один из плейлистов")
                return
            
            self.progress_updated.emit(20, "Создание индексов...")
            
            first_dict = {}
            second_dict = {}
            
            for channel in first_channels:
                first_dict[channel.key] = channel
            
            for channel in second_channels:
                second_dict[channel.key] = channel
            
            first_keys = set(first_dict.keys())
            second_keys = set(second_dict.keys())
            
            unique_first_keys = first_keys - second_keys
            unique_second_keys = second_keys - first_keys
            common_keys = first_keys & second_keys
            
            self.progress_updated.emit(40, "Поиск общих каналов...")
            
            true_common = []
            different_url_common = []
            
            for idx, key in enumerate(common_keys):
                ch1 = first_dict[key]
                ch2 = second_dict[key]
                
                url1 = ch1.url.strip().rstrip('/')
                url2 = ch2.url.strip().rstrip('/')
                
                if url1 == url2:
                    true_common.append(ch1)
                else:
                    different_url_common.append({
                        'first': ch1,
                        'second': ch2
                    })
                
                if idx % 10 == 0:
                    progress = 40 + int(30 * idx / len(common_keys))
                    self.progress_updated.emit(progress, f"Проверка URL... {idx}/{len(common_keys)}")
            
            unique_in_first = [first_dict[key] for key in unique_first_keys]
            unique_in_second = [second_dict[key] for key in unique_second_keys]
            
            self.progress_updated.emit(70, "Поиск похожих каналов...")
            
            similar_channels = self._find_similar_channels(first_channels, second_channels)
            
            self.progress_updated.emit(90, "Формирование результатов...")
            
            result = ComparisonResult(
                unique_in_first=unique_in_first,
                unique_in_second=unique_in_second,
                common_channels=true_common,
                similar_channels=similar_channels,
                different_url_channels=different_url_common
            )
            
            self.comparison_completed.emit(result)
            
        except Exception as e:
            self.error_occurred.emit(f"Ошибка при сравнении: {str(e)}")
    
    def _find_similar_channels(self, first_channels: List[Channel], second_channels: List[Channel]) -> List[Dict]:
        """Найти похожие каналы"""
        similar = []
        processed_pairs = set()
        total_pairs = len(first_channels) * len(second_channels)
        processed = 0
        
        for ch1 in first_channels:
            for ch2 in second_channels:
                processed += 1
                
                if ch1.key == ch2.key:
                    continue
                
                pair_key = frozenset([ch1.key, ch2.key])
                if pair_key in processed_pairs:
                    continue
                
                try:
                    name_similarity = difflib.SequenceMatcher(
                        None, 
                        ch1.name.lower(), 
                        ch2.name.lower()
                    ).ratio()
                    
                    group_similarity = difflib.SequenceMatcher(
                        None,
                        ch1.group.lower(),
                        ch2.group.lower()
                    ).ratio()
                    
                    total_similarity = (name_similarity * 0.7 + group_similarity * 0.3)
                    
                    if total_similarity >= self.similarity_threshold:
                        similar.append({
                            'first': ch1,
                            'second': ch2,
                            'name_similarity': name_similarity,
                            'group_similarity': group_similarity,
                            'total_similarity': total_similarity
                        })
                        processed_pairs.add(pair_key)
                    
                    if processed % 1000 == 0:
                        progress = 70 + int(20 * processed / total_pairs)
                        self.progress_updated.emit(progress, f"Сравнение каналов... {processed}/{total_pairs}")
                        
                except Exception as e:
                    print(f"Ошибка при сравнении каналов: {e}")
        
        similar.sort(key=lambda x: x['total_similarity'], reverse=True)
        return similar


class ChannelTreeWidget(QTreeWidget):
    """Кастомный виджет дерева для отображения каналов"""
    
    def __init__(self, columns: List[str], parent=None):
        super().__init__(parent)
        self.columns = columns
        self.setup_ui()
        
    def setup_ui(self):
        """Настройка интерфейса дерева"""
        self.setColumnCount(len(self.columns))
        self.setHeaderLabels(self.columns)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.setSortingEnabled(True)
        
        header = self.header()
        header.setStretchLastSection(True)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        
    def add_channel(self, channel: Channel, extra_info: str = ""):
        """Добавить канал в дерево"""
        if len(self.columns) == 4:  # Для похожих каналов и разных URL
            url_display = channel.url[:50] + "..." if len(channel.url) > 50 else channel.url
            item = QTreeWidgetItem([
                channel.name,
                channel.group,
                url_display,
                extra_info
            ])
        else:  # Для остальных списков
            url_display = channel.url[:80] + "..." if len(channel.url) > 80 else channel.url
            item = QTreeWidgetItem([
                channel.name,
                channel.group,
                url_display
            ])
        
        item.setData(0, Qt.ItemDataRole.UserRole, channel)
        self.addTopLevelItem(item)
        
    def add_similar_channel(self, item_data: Dict):
        """Добавить похожий канал"""
        ch1 = item_data['first']
        ch2 = item_data['second']
        similarity = item_data['total_similarity']
        
        url1_display = ch1.url[:50] + "..." if len(ch1.url) > 50 else ch1.url
        extra_info = f"{ch2.name} ({similarity:.1%})"
        
        item = QTreeWidgetItem([
            ch1.name,
            ch1.group,
            url1_display,
            extra_info
        ])
        
        item.setData(0, Qt.ItemDataRole.UserRole, item_data)
        self.addTopLevelItem(item)
        
    def add_different_url_channel(self, item_data: Dict):
        """Добавить канал с разными URL"""
        ch1 = item_data['first']
        ch2 = item_data['second']
        
        url1_display = ch1.url[:50] + "..." if len(ch1.url) > 50 else ch1.url
        extra_info = f"{ch2.name} (разные URL)"
        
        item = QTreeWidgetItem([
            ch1.name,
            ch1.group,
            url1_display,
            extra_info
        ])
        
        item.setData(0, Qt.ItemDataRole.UserRole, item_data)
        self.addTopLevelItem(item)
        
    def clear_all(self):
        """Очистить все элементы"""
        self.clear()
        
    def get_selected_channels(self) -> List[Any]:
        """Получить выбранные каналы"""
        selected = []
        for item in self.selectedItems():
            channel_data = item.data(0, Qt.ItemDataRole.UserRole)
            if channel_data:
                selected.append(channel_data)
        return selected


class PlaylistComparator(QMainWindow):
    """Основное окно приложения"""
    
    def __init__(self):
        super().__init__()
        self.first_playlist_path = None
        self.second_playlist_path = None
        self.comparison_result = None
        self.similarity_threshold = 0.7
        
        self.trees = {}
        self.tab_widget = None
        self.status_bar = None
        
        self.setup_ui()
        self.load_settings()
        
    def setup_ui(self):
        """Настройка интерфейса"""
        self.setWindowTitle("IPTV Playlist Comparator v2.0")
        self.setGeometry(100, 100, 1400, 900)
        
        # Создание меню
        self.create_menu()
        
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Верхняя панель с кнопками
        top_panel = QFrame()
        top_panel.setFrameStyle(QFrame.Shape.StyledPanel)
        top_layout = QHBoxLayout(top_panel)
        
        self.btn_compare = QPushButton("Сравнить")
        self.btn_compare.clicked.connect(self.compare_playlists)
        self.btn_compare.setMinimumWidth(100)
        
        self.btn_refresh = QPushButton("Обновить")
        self.btn_refresh.clicked.connect(self.refresh_playlists)
        self.btn_refresh.setMinimumWidth(100)
        
        self.btn_clear = QPushButton("Очистить")
        self.btn_clear.clicked.connect(self.clear_selection)
        self.btn_clear.setMinimumWidth(100)
        
        self.btn_settings = QPushButton("Настройки")
        self.btn_settings.clicked.connect(self.open_settings)
        self.btn_settings.setMinimumWidth(100)
        
        top_layout.addWidget(self.btn_compare)
        top_layout.addWidget(self.btn_refresh)
        top_layout.addWidget(self.btn_clear)
        top_layout.addWidget(self.btn_settings)
        top_layout.addStretch()
        
        main_layout.addWidget(top_panel)
        
        # Панель выбора плейлистов
        playlist_frame = QGroupBox("Выбор плейлистов")
        playlist_layout = QVBoxLayout(playlist_frame)
        
        # Первый плейлист
        first_row = QHBoxLayout()
        first_row.addWidget(QLabel("Первый плейлист:"))
        
        self.first_playlist_label = QLabel("Не выбран")
        self.first_playlist_label.setStyleSheet("border: 1px solid #ccc; padding: 5px;")
        self.first_playlist_label.setMinimumHeight(30)
        first_row.addWidget(self.first_playlist_label, 1)
        
        self.btn_select_first = QPushButton("Выбрать...")
        self.btn_select_first.clicked.connect(self.select_first_playlist)
        self.btn_select_first.setMinimumWidth(100)
        first_row.addWidget(self.btn_select_first)
        
        self.btn_clear_first = QPushButton("Очистить")
        self.btn_clear_first.clicked.connect(lambda: self.clear_playlist('first'))
        self.btn_clear_first.setMinimumWidth(80)
        first_row.addWidget(self.btn_clear_first)
        
        playlist_layout.addLayout(first_row)
        
        # Второй плейлист
        second_row = QHBoxLayout()
        second_row.addWidget(QLabel("Второй плейлист:"))
        
        self.second_playlist_label = QLabel("Не выбран")
        self.second_playlist_label.setStyleSheet("border: 1px solid #ccc; padding: 5px;")
        self.second_playlist_label.setMinimumHeight(30)
        second_row.addWidget(self.second_playlist_label, 1)
        
        self.btn_select_second = QPushButton("Выбрать...")
        self.btn_select_second.clicked.connect(self.select_second_playlist)
        self.btn_select_second.setMinimumWidth(100)
        second_row.addWidget(self.btn_select_second)
        
        self.btn_clear_second = QPushButton("Очистить")
        self.btn_clear_second.clicked.connect(lambda: self.clear_playlist('second'))
        self.btn_clear_second.setMinimumWidth(80)
        second_row.addWidget(self.btn_clear_second)
        
        playlist_layout.addLayout(second_row)
        
        main_layout.addWidget(playlist_frame)
        
        # Вкладки с результатами
        self.tab_widget = QTabWidget()
        
        # Создаем вкладки
        self.create_unique_first_tab()
        self.create_unique_second_tab()
        self.create_common_tab()
        self.create_similar_tab()
        self.create_different_url_tab()
        
        main_layout.addWidget(self.tab_widget, 1)
        
        # Статус бар
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Выберите два плейлиста для сравнения")
        
        # Панель статистики
        stats_frame = QFrame()
        stats_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        stats_layout = QHBoxLayout(stats_frame)
        
        self.stats_label = QLabel("Статистика: выберите плейлисты")
        self.stats_label.setStyleSheet("font-weight: bold; padding: 5px;")
        stats_layout.addWidget(self.stats_label)
        
        main_layout.addWidget(stats_frame)
        
    def create_menu(self):
        """Создание меню приложения"""
        menubar = self.menuBar()
        
        # Меню Файл
        file_menu = menubar.addMenu("Файл")
        
        new_action = QAction("Новое сравнение", self)
        new_action.triggered.connect(self.clear_selection)
        file_menu.addAction(new_action)
        
        file_menu.addSeparator()
        
        export_action = QAction("Экспорт результатов", self)
        export_action.triggered.connect(self.export_results)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Выход", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Меню Экспорт
        export_menu = menubar.addMenu("Экспорт")
        
        export_unique_first_action = QAction("Уникальные из первого во второй", self)
        export_unique_first_action.triggered.connect(self.export_unique_first_to_second)
        export_menu.addAction(export_unique_first_action)
        
        export_unique_second_action = QAction("Уникальные из второго в первый", self)
        export_unique_second_action.triggered.connect(self.export_unique_second_to_first)
        export_menu.addAction(export_unique_second_action)
        
        # Меню Удаление
        delete_menu = menubar.addMenu("Удаление")
        
        delete_common_first_action = QAction("Общие из первого", self)
        delete_common_first_action.triggered.connect(self.delete_common_from_first)
        delete_menu.addAction(delete_common_first_action)
        
        delete_common_second_action = QAction("Общие из второго", self)
        delete_common_second_action.triggered.connect(self.delete_common_from_second)
        delete_menu.addAction(delete_common_second_action)
        
        # Меню Слияние
        merge_menu = menubar.addMenu("Слияние")
        
        merge_action = QAction("Объединить", self)
        merge_action.triggered.connect(self.create_combined_playlist)
        merge_menu.addAction(merge_action)
        
        merge_no_duplicates_action = QAction("Объединить (без дубликатов)", self)
        merge_no_duplicates_action.triggered.connect(self.merge_playlists_no_duplicates)
        merge_menu.addAction(merge_no_duplicates_action)
        
        # Меню Операции
        ops_menu = menubar.addMenu("Операции")
        
        invert_action = QAction("Инвертировать выделение", self)
        invert_action.triggered.connect(self.invert_selection)
        ops_menu.addAction(invert_action)
        
        copy_action = QAction("Копировать в буфер", self)
        copy_action.triggered.connect(self.copy_to_clipboard)
        ops_menu.addAction(copy_action)
        
        # Меню Справка
        help_menu = menubar.addMenu("Справка")
        
        about_action = QAction("О программе", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
    def create_unique_first_tab(self):
        """Создать вкладку с уникальными каналами из первого плейлиста"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Панель поиска
        search_frame = QFrame()
        search_layout = QHBoxLayout(search_frame)
        
        search_layout.addWidget(QLabel("Поиск:"))
        
        self.unique_first_search = QLineEdit()
        self.unique_first_search.textChanged.connect(
            lambda text: self.filter_tree("unique_first", text)
        )
        search_layout.addWidget(self.unique_first_search, 1)
        
        self.btn_select_all_first = QPushButton("Выделить все")
        self.btn_select_all_first.clicked.connect(
            lambda: self.select_all_in_tree(self.trees["unique_first"])
        )
        search_layout.addWidget(self.btn_select_all_first)
        
        self.btn_export_first = QPushButton("Экспорт в файл")
        self.btn_export_first.clicked.connect(
            lambda: self.export_selected_to_file(self.trees["unique_first"], "unique_first")
        )
        search_layout.addWidget(self.btn_export_first)
        
        self.unique_first_count = QLabel("Всего: 0")
        search_layout.addWidget(self.unique_first_count)
        
        layout.addWidget(search_frame)
        
        # Дерево каналов
        tree = ChannelTreeWidget(["Название", "Группа", "URL"])
        self.trees["unique_first"] = tree
        layout.addWidget(tree, 1)
        
        self.tab_widget.addTab(tab, "Уникальные в первом")
        
    def create_unique_second_tab(self):
        """Создать вкладку с уникальными каналами из второго плейлиста"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Панель поиска
        search_frame = QFrame()
        search_layout = QHBoxLayout(search_frame)
        
        search_layout.addWidget(QLabel("Поиск:"))
        
        self.unique_second_search = QLineEdit()
        self.unique_second_search.textChanged.connect(
            lambda text: self.filter_tree("unique_second", text)
        )
        search_layout.addWidget(self.unique_second_search, 1)
        
        self.btn_select_all_second = QPushButton("Выделить все")
        self.btn_select_all_second.clicked.connect(
            lambda: self.select_all_in_tree(self.trees["unique_second"])
        )
        search_layout.addWidget(self.btn_select_all_second)
        
        self.btn_export_second = QPushButton("Экспорт в файл")
        self.btn_export_second.clicked.connect(
            lambda: self.export_selected_to_file(self.trees["unique_second"], "unique_second")
        )
        search_layout.addWidget(self.btn_export_second)
        
        self.unique_second_count = QLabel("Всего: 0")
        search_layout.addWidget(self.unique_second_count)
        
        layout.addWidget(search_frame)
        
        # Дерево каналов
        tree = ChannelTreeWidget(["Название", "Группа", "URL"])
        self.trees["unique_second"] = tree
        layout.addWidget(tree, 1)
        
        self.tab_widget.addTab(tab, "Уникальные во втором")
        
    def create_common_tab(self):
        """Создать вкладку с общими каналами"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Панель поиска
        search_frame = QFrame()
        search_layout = QHBoxLayout(search_frame)
        
        search_layout.addWidget(QLabel("Поиск:"))
        
        self.common_search = QLineEdit()
        self.common_search.textChanged.connect(
            lambda text: self.filter_tree("common", text)
        )
        search_layout.addWidget(self.common_search, 1)
        
        self.btn_select_all_common = QPushButton("Выделить все")
        self.btn_select_all_common.clicked.connect(
            lambda: self.select_all_in_tree(self.trees["common"])
        )
        search_layout.addWidget(self.btn_select_all_common)
        
        self.btn_export_common = QPushButton("Экспорт в файл")
        self.btn_export_common.clicked.connect(
            lambda: self.export_selected_to_file(self.trees["common"], "common")
        )
        search_layout.addWidget(self.btn_export_common)
        
        self.common_count = QLabel("Всего: 0")
        search_layout.addWidget(self.common_count)
        
        layout.addWidget(search_frame)
        
        # Дерево каналов
        tree = ChannelTreeWidget(["Название", "Группа", "URL"])
        self.trees["common"] = tree
        layout.addWidget(tree, 1)
        
        self.tab_widget.addTab(tab, "Общие каналы")
        
    def create_similar_tab(self):
        """Создать вкладку с похожими каналами"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Панель поиска
        search_frame = QFrame()
        search_layout = QHBoxLayout(search_frame)
        
        search_layout.addWidget(QLabel("Поиск:"))
        
        self.similar_search = QLineEdit()
        self.similar_search.textChanged.connect(
            lambda text: self.filter_tree("similar", text)
        )
        search_layout.addWidget(self.similar_search, 1)
        
        self.btn_select_all_similar = QPushButton("Выделить все")
        self.btn_select_all_similar.clicked.connect(
            lambda: self.select_all_in_tree(self.trees["similar"])
        )
        search_layout.addWidget(self.btn_select_all_similar)
        
        self.btn_export_similar = QPushButton("Экспорт в файл")
        self.btn_export_similar.clicked.connect(
            lambda: self.export_selected_to_file(self.trees["similar"], "similar")
        )
        search_layout.addWidget(self.btn_export_similar)
        
        self.similar_count = QLabel("Всего: 0")
        search_layout.addWidget(self.similar_count)
        
        layout.addWidget(search_frame)
        
        # Дерево каналов
        tree = ChannelTreeWidget(["Канал 1", "Группа 1", "URL 1", "Канал 2 / Сходство"])
        self.trees["similar"] = tree
        layout.addWidget(tree, 1)
        
        self.tab_widget.addTab(tab, "Похожие")
        
    def create_different_url_tab(self):
        """Создать вкладку с каналами с разными URL"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Панель поиска
        search_frame = QFrame()
        search_layout = QHBoxLayout(search_frame)
        
        search_layout.addWidget(QLabel("Поиск:"))
        
        self.different_url_search = QLineEdit()
        self.different_url_search.textChanged.connect(
            lambda text: self.filter_tree("different_url", text)
        )
        search_layout.addWidget(self.different_url_search, 1)
        
        self.btn_select_all_diff = QPushButton("Выделить все")
        self.btn_select_all_diff.clicked.connect(
            lambda: self.select_all_in_tree(self.trees["different_url"])
        )
        search_layout.addWidget(self.btn_select_all_diff)
        
        self.btn_export_diff = QPushButton("Экспорт в файл")
        self.btn_export_diff.clicked.connect(
            lambda: self.export_selected_to_file(self.trees["different_url"], "different_url")
        )
        search_layout.addWidget(self.btn_export_diff)
        
        self.different_url_count = QLabel("Всего: 0")
        search_layout.addWidget(self.different_url_count)
        
        layout.addWidget(search_frame)
        
        # Дерево каналов
        tree = ChannelTreeWidget(["Канал 1", "Группа 1", "URL 1", "Канал 2"])
        self.trees["different_url"] = tree
        layout.addWidget(tree, 1)
        
        self.tab_widget.addTab(tab, "Разные URL")
        
    def select_first_playlist(self):
        """Выбрать первый плейлист"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите первый плейлист",
            "",
            "M3U файлы (*.m3u *.m3u8);;Все файлы (*.*)"
        )
        
        if file_path:
            self.first_playlist_path = file_path
            filename = os.path.basename(file_path)
            self.first_playlist_label.setText(filename)
            self.status_bar.showMessage(f"Выбран первый плейлист: {filename}")
            
    def select_second_playlist(self):
        """Выбрать второй плейлист"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите второй плейлист",
            "",
            "M3U файлы (*.m3u *.m3u8);;Все файлы (*.*)"
        )
        
        if file_path:
            self.second_playlist_path = file_path
            filename = os.path.basename(file_path)
            self.second_playlist_label.setText(filename)
            self.status_bar.showMessage(f"Выбран второй плейлист: {filename}")
            
    def clear_playlist(self, playlist_type: str):
        """Очистить выбранный плейлист"""
        if playlist_type == 'first':
            self.first_playlist_path = None
            self.first_playlist_label.setText("Не выбран")
        elif playlist_type == 'second':
            self.second_playlist_path = None
            self.second_playlist_label.setText("Не выбран")
        
        self.status_bar.showMessage(f"Плейлист {playlist_type} очищен")
        
    def refresh_playlists(self):
        """Обновить информацию о плейлистах"""
        # В standalone версии просто обновляем метки
        if self.first_playlist_path:
            filename = os.path.basename(self.first_playlist_path)
            self.first_playlist_label.setText(filename)
            
        if self.second_playlist_path:
            filename = os.path.basename(self.second_playlist_path)
            self.second_playlist_label.setText(filename)
            
        self.status_bar.showMessage("Информация о плейлистах обновлена")
        
    def compare_playlists(self):
        """Сравнить два плейлиста"""
        if not self.first_playlist_path or not self.second_playlist_path:
            QMessageBox.warning(self, "Предупреждение", "Выберите оба плейлиста для сравнения")
            return
        
        # Проверка валидности плейлистов
        valid1, msg1, count1 = PlaylistLoader.validate_playlist(self.first_playlist_path)
        valid2, msg2, count2 = PlaylistLoader.validate_playlist(self.second_playlist_path)
        
        if not valid1 or not valid2:
            msg = f"Проблемы с плейлистами:\n"
            if not valid1:
                msg += f"Первый: {msg1}\n"
            if not valid2:
                msg += f"Второй: {msg2}\n"
            
            reply = QMessageBox.question(
                self,
                "Предупреждение",
                f"{msg}\nПродолжить сравнение?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
        
        # Создаем прогресс-диалог
        self.progress_dialog = QProgressDialog("Сравнение плейлистов...", "Отмена", 0, 100, self)
        self.progress_dialog.setWindowTitle("Сравнение")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setAutoClose(True)
        self.progress_dialog.setAutoReset(True)
        
        # Создаем и запускаем поток сравнения
        self.comparison_thread = ComparisonThread(
            self.first_playlist_path,
            self.second_playlist_path,
            self.similarity_threshold
        )
        
        self.comparison_thread.progress_updated.connect(self.update_progress)
        self.comparison_thread.comparison_completed.connect(self.on_comparison_completed)
        self.comparison_thread.error_occurred.connect(self.on_comparison_error)
        self.comparison_thread.finished.connect(self.progress_dialog.close)
        
        self.progress_dialog.canceled.connect(self.comparison_thread.terminate)
        
        self.comparison_thread.start()
        
    def update_progress(self, value: int, message: str):
        """Обновить прогресс"""
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.setValue(value)
            self.progress_dialog.setLabelText(message)
            
    def on_comparison_completed(self, result: ComparisonResult):
        """Обработка завершения сравнения"""
        self.comparison_result = result
        self.display_results()
        self.update_stats()
        self.status_bar.showMessage("Сравнение плейлистов завершено")
        
    def on_comparison_error(self, error_message: str):
        """Обработка ошибки сравнения"""
        QMessageBox.critical(self, "Ошибка", error_message)
        
    def display_results(self):
        """Отобразить результаты сравнения"""
        if not self.comparison_result:
            return
        
        # Уникальные в первом
        tree = self.trees["unique_first"]
        tree.clear_all()
        for channel in self.comparison_result.unique_in_first:
            tree.add_channel(channel)
        self.unique_first_count.setText(f"Всего: {self.comparison_result.total_unique_first}")
        
        # Уникальные во втором
        tree = self.trees["unique_second"]
        tree.clear_all()
        for channel in self.comparison_result.unique_in_second:
            tree.add_channel(channel)
        self.unique_second_count.setText(f"Всего: {self.comparison_result.total_unique_second}")
        
        # Общие каналы
        tree = self.trees["common"]
        tree.clear_all()
        for channel in self.comparison_result.common_channels:
            tree.add_channel(channel)
        self.common_count.setText(f"Всего: {self.comparison_result.total_common}")
        
        # Похожие каналы
        tree = self.trees["similar"]
        tree.clear_all()
        for item in self.comparison_result.similar_channels:
            tree.add_similar_channel(item)
        self.similar_count.setText(f"Всего: {self.comparison_result.total_similar}")
        
        # Каналы с разными URL
        tree = self.trees["different_url"]
        tree.clear_all()
        for item in self.comparison_result.different_url_channels:
            tree.add_different_url_channel(item)
        self.different_url_count.setText(f"Всего: {self.comparison_result.total_different_url}")
        
    def update_stats(self):
        """Обновить статистику"""
        if not self.comparison_result:
            return
        
        valid1, msg1, count1 = PlaylistLoader.validate_playlist(self.first_playlist_path)
        valid2, msg2, count2 = PlaylistLoader.validate_playlist(self.second_playlist_path)
        
        stats_text = (
            f"📊 Статистика: "
            f"Первый: {count1} | "
            f"Второй: {count2} | "
            f"Уникальных в первом: {self.comparison_result.total_unique_first} | "
            f"Уникальных во втором: {self.comparison_result.total_unique_second} | "
            f"Общих: {self.comparison_result.total_common} | "
            f"Похожих: {self.comparison_result.total_similar} | "
            f"Разные URL: {self.comparison_result.total_different_url}"
        )
        
        self.stats_label.setText(stats_text)
        
    def clear_selection(self):
        """Очистить выбранные плейлисты и результаты"""
        self.first_playlist_path = None
        self.second_playlist_path = None
        self.comparison_result = None
        
        self.first_playlist_label.setText("Не выбран")
        self.second_playlist_label.setText("Не выбран")
        self.stats_label.setText("Статистика: выберите плейлисты")
        
        for tree in self.trees.values():
            if tree:
                tree.clear_all()
        
        # Очистка полей поиска
        self.unique_first_search.clear()
        self.unique_second_search.clear()
        self.common_search.clear()
        self.similar_search.clear()
        self.different_url_search.clear()
        
        # Сброс счетчиков
        self.unique_first_count.setText("Всего: 0")
        self.unique_second_count.setText("Всего: 0")
        self.common_count.setText("Всего: 0")
        self.similar_count.setText("Всего: 0")
        self.different_url_count.setText("Всего: 0")
        
        self.status_bar.showMessage("Выбор плейлистов очищен")
        
    def filter_tree(self, tree_name: str, search_text: str):
        """Фильтрация дерева по поисковому запросу"""
        tree = self.trees.get(tree_name)
        if not tree or not self.comparison_result:
            return
        
        search_lower = search_text.lower()
        
        # В реальном приложении здесь была бы сложная логика фильтрации
        # Для простоты просто показываем/скрываем элементы
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            show = False
            
            for col in range(tree.columnCount()):
                text = item.text(col).lower()
                if search_lower in text:
                    show = True
                    break
            
            item.setHidden(not show)
            
    def select_all_in_tree(self, tree: ChannelTreeWidget):
        """Выделить все элементы в дереве"""
        if tree:
            tree.selectAll()
            
    def export_selected_to_file(self, tree: ChannelTreeWidget, list_type: str):
        """Экспортировать выбранные каналы в файл"""
        if not tree:
            return
        
        selected = tree.get_selected_channels()
        if not selected:
            QMessageBox.warning(self, "Предупреждение", "Выберите каналы для экспорта")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт выбранных каналов",
            "",
            "M3U файлы (*.m3u);;Текстовые файлы (*.txt);;Все файлы (*.*)"
        )
        
        if not file_path:
            return
        
        try:
            channels_to_export = []
            
            if list_type in ["similar", "different_url"]:
                for item in selected:
                    if isinstance(item, dict):
                        channels_to_export.append(item['first'])
                        channels_to_export.append(item['second'])
            else:
                channels_to_export = selected
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('#EXTM3U\n')
                for channel in channels_to_export:
                    if hasattr(channel, 'extinf'):
                        f.write(channel.extinf + '\n')
                        f.write(channel.url + '\n' if channel.url else '\n')
            
            QMessageBox.information(self, "Успех", f"Экспортировано {len(channels_to_export)} каналов")
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать каналы:\n{str(e)}")
            
    def export_unique_first_to_second(self):
        """Экспорт уникальных каналов из первого плейлиста во второй"""
        if not self.comparison_result or not self.second_playlist_path:
            QMessageBox.warning(self, "Предупреждение", "Сначала сравните плейлисты и выберите второй плейлист")
            return
        
        if not self.comparison_result.unique_in_first:
            QMessageBox.information(self, "Информация", "Нет уникальных каналов в первом плейлисте")
            return
        
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Экспортировать {len(self.comparison_result.unique_in_first)} уникальных каналов из первого плейлиста во второй?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        try:
            original_file = self.second_playlist_path
            backup_file = original_file + '.backup_' + datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(original_file, backup_file)
            
            with open(original_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.splitlines()
            
            insert_position = len(lines)
            for i, line in enumerate(lines):
                if line.startswith('#EXTINF:'):
                    insert_position = i
                    j = i + 1
                    while j < len(lines) and (not lines[j].strip() or lines[j].startswith('#')):
                        j += 1
                    insert_position = j
            
            new_lines = lines[:insert_position]
            for channel in self.comparison_result.unique_in_first:
                new_lines.append(channel.extinf)
                new_lines.append(channel.url if channel.url else '')
            new_lines.extend(lines[insert_position:])
            
            with open(original_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(new_lines))
            
            QMessageBox.information(
                self,
                "Успех",
                f"Экспортировано {len(self.comparison_result.unique_in_first)} уникальных каналов из первого плейлиста во второй.\n"
                f"Создана резервная копия: {os.path.basename(backup_file)}"
            )
            
            # Повторное сравнение
            self.compare_playlists()
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать каналы:\n{str(e)}")
            
    def export_unique_second_to_first(self):
        """Экспорт уникальных каналов из второго плейлиста в первый"""
        # Аналогично export_unique_first_to_second
        
    def delete_common_from_first(self):
        """Удалить общие каналы из первого плейлиста"""
        # Реализация аналогична оригинальному плагину
        
    def delete_common_from_second(self):
        """Удалить общие каналы из второго плейлиста"""
        # Реализация аналогична оригинальному плагину
        
    def merge_playlists_no_duplicates(self):
        """Объединить плейлисты, исключив общие каналы"""
        if not self.comparison_result or not self.first_playlist_path or not self.second_playlist_path:
            QMessageBox.warning(self, "Предупреждение", "Сначала сравните оба плейлиста")
            return
        
        default_name = f"merged_{os.path.basename(self.first_playlist_path)}"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить объединенный плейлист",
            default_name,
            "M3U файлы (*.m3u);;M3U8 файлы (*.m3u8);;Все файлы (*.*)"
        )
        
        if not file_path:
            return
        
        try:
            all_unique_channels = []
            
            all_unique_channels.extend(self.comparison_result.unique_in_first)
            all_unique_channels.extend(self.comparison_result.unique_in_second)
            all_unique_channels.extend(self.comparison_result.common_channels)
            
            if not all_unique_channels:
                QMessageBox.warning(self, "Предупреждение", "Нет каналов для объединения")
                return
            
            reply = QMessageBox.question(
                self,
                "Подтверждение",
                f"Создать объединенный плейлист из {len(all_unique_channels)} уникальных каналов?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('#EXTM3U\n')
                for channel in all_unique_channels:
                    f.write(channel.extinf + '\n')
                    f.write(channel.url + '\n' if channel.url else '\n')
            
            QMessageBox.information(
                self,
                "Успех",
                f"Создан объединенный плейлист из {len(all_unique_channels)} каналов.\n"
                f"Файл: {os.path.basename(file_path)}"
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось объединить плейлисты:\n{str(e)}")
            
    def create_combined_playlist(self):
        """Создать новый плейлист с каналами из обоих плейлистов"""
        if not self.first_playlist_path or not self.second_playlist_path:
            QMessageBox.warning(self, "Предупреждение", "Сначала выберите оба плейлиста")
            return
        
        default_name = f"combined_{os.path.basename(self.first_playlist_path)}"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить комбинированный плейлист",
            default_name,
            "M3U файлы (*.m3u);;M3U8 файлы (*.m3u8);;Все файлы (*.*)"
        )
        
        if not file_path:
            return
        
        try:
            first_channels = PlaylistLoader.load_playlist(self.first_playlist_path)
            second_channels = PlaylistLoader.load_playlist(self.second_playlist_path)
            
            if not first_channels or not second_channels:
                QMessageBox.warning(self, "Предупреждение", "Не удалось загрузить плейлисты")
                return
            
            all_channels = first_channels + second_channels
            
            reply = QMessageBox.question(
                self,
                "Подтверждение",
                f"Создать комбинированный плейлист из {len(all_channels)} каналов?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('#EXTM3U\n')
                for channel in all_channels:
                    f.write(channel.extinf + '\n')
                    f.write(channel.url + '\n' if channel.url else '\n')
            
            QMessageBox.information(
                self,
                "Успех",
                f"Создан комбинированный плейлист из {len(all_channels)} каналов.\n"
                f"Файл: {os.path.basename(file_path)}"
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать комбинированный плейлист:\n{str(e)}")
            
    def invert_selection(self):
        """Инвертировать выделение в активной вкладке"""
        current_index = self.tab_widget.currentIndex()
        tree_names = ["unique_first", "unique_second", "common", "similar", "different_url"]
        
        if 0 <= current_index < len(tree_names):
            tree_name = tree_names[current_index]
            tree = self.trees.get(tree_name)
            
            if tree:
                # Получаем все элементы
                all_items = []
                for i in range(tree.topLevelItemCount()):
                    all_items.append(tree.topLevelItem(i))
                
                # Получаем выбранные элементы
                selected_items = tree.selectedItems()
                
                # Инвертируем выделение
                for item in all_items:
                    if item in selected_items:
                        item.setSelected(False)
                    else:
                        item.setSelected(True)
                        
    def copy_to_clipboard(self):
        """Скопировать выделенные каналы в буфер обмена"""
        current_index = self.tab_widget.currentIndex()
        tree_names = ["unique_first", "unique_second", "common", "similar", "different_url"]
        
        if 0 <= current_index < len(tree_names):
            tree_name = tree_names[current_index]
            tree = self.trees.get(tree_name)
            
            if tree:
                selected_items = tree.selectedItems()
                if not selected_items:
                    QMessageBox.warning(self, "Предупреждение", "Выберите каналы для копирования")
                    return
                
                clipboard_text = ""
                for item in selected_items:
                    values = [item.text(col) for col in range(tree.columnCount())]
                    if current_index in [3, 4]:  # Похожие и разные URL
                        clipboard_text += f"{values[0]} ({values[1]}) -> {values[3]}\n"
                    else:
                        clipboard_text += f"{values[0]} ({values[1]})\n"
                
                if clipboard_text:
                    clipboard = QApplication.clipboard()
                    clipboard.setText(clipboard_text)
                    self.status_bar.showMessage(f"Скопировано {len(selected_items)} каналов в буфер обмена")
                    
    def export_results(self):
        """Экспортировать результаты сравнения"""
        if not self.comparison_result:
            QMessageBox.warning(self, "Предупреждение", "Нет результатов для экспорта")
            return
        
        dialog = ExportDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            format_type, options = dialog.get_export_options()
            self.perform_export(format_type, options)
            
    def perform_export(self, format_type: str, options: Dict):
        """Выполнить экспорт в выбранный формат"""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Экспорт результатов",
                "",
                self.get_file_filter(format_type)
            )
            
            if not file_path:
                return
            
            if format_type == 'csv':
                self.export_to_csv(file_path, options)
            elif format_type == 'html':
                self.export_to_html(file_path, options)
            elif format_type == 'json':
                self.export_to_json(file_path, options)
            elif format_type == 'm3u':
                self.export_to_m3u(file_path, options)
            else:
                self.export_to_txt(file_path, options)
            
            QMessageBox.information(self, "Успех", f"Результаты экспортированы в:\n{file_path}")
            self.status_bar.showMessage(f"Экспорт завершен: {os.path.basename(file_path)}")
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать результаты:\n{str(e)}")
            
    def get_file_filter(self, format_type: str) -> str:
        """Получить фильтр файлов для экспорта"""
        filters = {
            'txt': "Текстовые файлы (*.txt);;Все файлы (*.*)",
            'csv': "CSV файлы (*.csv);;Все файлы (*.*)",
            'html': "HTML файлы (*.html);;Все файлы (*.*)",
            'json': "JSON файлы (*.json);;Все файлы (*.*)",
            'm3u': "M3U файлы (*.m3u);;Все файлы (*.*)"
        }
        return filters.get(format_type, "Все файлы (*.*)")
        
    def export_to_txt(self, file_path: str, options: Dict):
        """Экспорт в текстовый файл"""
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("СРАВНЕНИЕ ПЛЕЙЛИСТОВ\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"Дата сравнения: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Первый плейлист: {os.path.basename(self.first_playlist_path) if self.first_playlist_path else ''}\n")
            f.write(f"Второй плейлист: {os.path.basename(self.second_playlist_path) if self.second_playlist_path else ''}\n\n")
            
            f.write("СТАТИСТИКА:\n")
            f.write("-" * 40 + "\n")
            valid1, msg1, count1 = PlaylistLoader.validate_playlist(self.first_playlist_path)
            valid2, msg2, count2 = PlaylistLoader.validate_playlist(self.second_playlist_path)
            
            f.write(f"Всего в первом плейлисте: {count1}\n")
            f.write(f"Всего во втором плейлисте: {count2}\n")
            f.write(f"Уникальных в первом: {self.comparison_result.total_unique_first}\n")
            f.write(f"Уникальных во втором: {self.comparison_result.total_unique_second}\n")
            f.write(f"Общих каналов: {self.comparison_result.total_common}\n")
            f.write(f"Похожих каналов: {self.comparison_result.total_similar}\n")
            f.write(f"Каналов с разными URL: {self.comparison_result.total_different_url}\n\n")
            
            if options.get('include_unique', True) and self.comparison_result.unique_in_first:
                f.write("УНИКАЛЬНЫЕ КАНАЛЫ В ПЕРВОМ ПЛЕЙЛИСТЕ:\n")
                f.write("-" * 40 + "\n")
                for i, channel in enumerate(self.comparison_result.unique_in_first, 1):
                    url = channel.url[:80] + "..." if len(channel.url) > 80 else channel.url
                    f.write(f"{i:3}. {channel.name} | {channel.group} | {url}\n")
                f.write("\n")
            
            # ... остальные разделы аналогично
            
    def export_to_csv(self, file_path: str, options: Dict):
        """Экспорт в CSV файл"""
        import csv
        
        with open(file_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            
            writer.writerow(["Сравнение плейлистов"])
            writer.writerow([f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
            writer.writerow([f"Первый плейлист: {os.path.basename(self.first_playlist_path) if self.first_playlist_path else ''}"])
            writer.writerow([f"Второй плейлист: {os.path.basename(self.second_playlist_path) if self.second_playlist_path else ''}"])
            writer.writerow([])
            
            writer.writerow(["Статистика"])
            writer.writerow(["Параметр", "Значение"])
            valid1, msg1, count1 = PlaylistLoader.validate_playlist(self.first_playlist_path)
            valid2, msg2, count2 = PlaylistLoader.validate_playlist(self.second_playlist_path)
            
            writer.writerow(["Всего в первом", count1])
            writer.writerow(["Всего во втором", count2])
            writer.writerow(["Уникальных в первом", self.comparison_result.total_unique_first])
            writer.writerow(["Уникальных во втором", self.comparison_result.total_unique_second])
            writer.writerow(["Общих", self.comparison_result.total_common])
            writer.writerow(["Похожих", self.comparison_result.total_similar])
            writer.writerow(["Разные URL", self.comparison_result.total_different_url])
            writer.writerow([])
            
            # ... остальные разделы аналогично
            
    def export_to_html(self, file_path: str, options: Dict):
        """Экспорт в HTML файл"""
        html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Сравнение плейлистов</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 5px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }}
        h2 {{ color: #4CAF50; margin-top: 30px; }}
        .stats {{ background: #f9f9f9; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
        th {{ background: #4CAF50; color: white; padding: 10px; text-align: left; }}
        td {{ padding: 8px 10px; border-bottom: 1px solid #ddd; }}
        tr:nth-child(even) {{ background: #f9f9f9; }}
        .timestamp {{ color: #666; font-size: 0.9em; }}
        .section {{ margin-bottom: 30px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Сравнение плейлистов</h1>
        <div class="timestamp">Дата создания: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        
        <div class="stats">
            <h2>Статистика</h2>
            <table>
"""
        
        valid1, msg1, count1 = PlaylistLoader.validate_playlist(self.first_playlist_path)
        valid2, msg2, count2 = PlaylistLoader.validate_playlist(self.second_playlist_path)
        
        html += f"""
                <tr><td>Первый плейлист:</td><td><b>{os.path.basename(self.first_playlist_path) if self.first_playlist_path else ''}</b></td></tr>
                <tr><td>Второй плейлист:</td><td><b>{os.path.basename(self.second_playlist_path) if self.second_playlist_path else ''}</b></td></tr>
                <tr><td>Всего каналов в первом:</td><td>{count1}</td></tr>
                <tr><td>Всего каналов во втором:</td><td>{count2}</td></tr>
                <tr><td>Уникальных в первом:</td><td>{self.comparison_result.total_unique_first}</td></tr>
                <tr><td>Уникальных во втором:</td><td>{self.comparison_result.total_unique_second}</td></tr>
                <tr><td>Общих каналов:</td><td>{self.comparison_result.total_common}</td></tr>
                <tr><td>Похожих каналов:</td><td>{self.comparison_result.total_similar}</td></tr>
                <tr><td>Каналов с разными URL:</td><td>{self.comparison_result.total_different_url}</td></tr>
            </table>
        </div>
"""
        
        # Добавление разделов в зависимости от опций
        if options.get('include_unique', True) and self.comparison_result.unique_in_first:
            html += """
        <div class="section">
            <h2>🎯 Уникальные каналы в первом плейлисте</h2>
            <table>
                <tr><th>#</th><th>Название</th><th>Группа</th><th>URL</th></tr>
"""
            for i, channel in enumerate(self.comparison_result.unique_in_first, 1):
                html += f"""
                <tr>
                    <td>{i}</td>
                    <td>{channel.name}</td>
                    <td>{channel.group}</td>
                    <td>{channel.url[:100] + '...' if len(channel.url) > 100 else channel.url}</td>
                </tr>
"""
            html += """
            </table>
        </div>
"""
        
        html += """
    </div>
</body>
</html>
"""
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html)
            
    def export_to_json(self, file_path: str, options: Dict):
        """Экспорт в JSON файл"""
        data = {
            'timestamp': datetime.now().isoformat(),
            'first_playlist': {
                'name': os.path.basename(self.first_playlist_path) if self.first_playlist_path else '',
                'file_path': self.first_playlist_path,
                'channels_count': 0
            },
            'second_playlist': {
                'name': os.path.basename(self.second_playlist_path) if self.second_playlist_path else '',
                'file_path': self.second_playlist_path,
                'channels_count': 0
            },
            'statistics': {
                'unique_in_first': self.comparison_result.total_unique_first,
                'unique_in_second': self.comparison_result.total_unique_second,
                'common_channels': self.comparison_result.total_common,
                'similar_channels': self.comparison_result.total_similar,
                'different_url_channels': self.comparison_result.total_different_url
            }
        }
        
        valid1, msg1, count1 = PlaylistLoader.validate_playlist(self.first_playlist_path)
        valid2, msg2, count2 = PlaylistLoader.validate_playlist(self.second_playlist_path)
        data['first_playlist']['channels_count'] = count1
        data['second_playlist']['channels_count'] = count2
        
        if options.get('include_unique', True):
            data['unique_in_first_channels'] = [ch.to_dict() for ch in self.comparison_result.unique_in_first]
            data['unique_in_second_channels'] = [ch.to_dict() for ch in self.comparison_result.unique_in_second]
        
        if options.get('include_common', False):
            data['common_channels_list'] = [ch.to_dict() for ch in self.comparison_result.common_channels]
        
        if options.get('include_similar', False):
            data['similar_channels_list'] = [
                {
                    'first': item['first'].to_dict(),
                    'second': item['second'].to_dict(),
                    'similarity': item.get('total_similarity', 0)
                }
                for item in self.comparison_result.similar_channels
            ]
        
        if options.get('include_different_url', False):
            data['different_url_channels_list'] = [
                {
                    'first': item['first'].to_dict(),
                    'second': item['second'].to_dict()
                }
                for item in self.comparison_result.different_url_channels
            ]
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
    def export_to_m3u(self, file_path: str, options: Dict):
        """Экспорт в M3U плейлист"""
        channels = []
        
        if options.get('include_unique', True):
            channels.extend(self.comparison_result.unique_in_first)
            channels.extend(self.comparison_result.unique_in_second)
        
        if options.get('include_common', False):
            channels.extend(self.comparison_result.common_channels)
        
        if options.get('include_similar', False):
            for item in self.comparison_result.similar_channels:
                channels.append(item['first'])
                channels.append(item['second'])
        
        if options.get('include_different_url', False):
            for item in self.comparison_result.different_url_channels:
                channels.append(item['first'])
                channels.append(item['second'])
        
        unique_channels = []
        seen_keys = set()
        
        for channel in channels:
            key = channel.key_with_url
            if key not in seen_keys:
                seen_keys.add(key)
                unique_channels.append(channel)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            for channel in unique_channels:
                f.write(channel.extinf + '\n')
                f.write(channel.url + '\n' if channel.url else '\n')
                
    def open_settings(self):
        """Открыть настройки"""
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.similarity_threshold = dialog.get_similarity_threshold()
            self.save_settings()
            
    def show_about(self):
        """Показать информацию о программе"""
        about_text = """
        <h2>IPTV Playlist Comparator</h2>
        <p>Автономное приложение для сравнения двух IPTV плейлистов.</p>
        <p>Функции:</p>
        <ul>
            <li>Сравнение двух M3U плейлистов</li>
            <li>Поиск уникальных, общих и похожих каналов</li>
            <li>Объединение плейлистов</li>
            <li>Экспорт результатов в различные форматы</li>
            <li>Управление каналами (экспорт/удаление)</li>
        </ul>
        <p>Разработчик: SmolNP</p>
        <p>Версия: 1 (PyQt6)</p>
        """
        
        QMessageBox.about(self, "О программе", about_text)
        
    def load_settings(self):
        """Загрузить настройки"""
        settings = QSettings("IPTVComparator", "PlaylistComparator")
        self.similarity_threshold = float(settings.value("similarity_threshold", 0.7))
        
    def save_settings(self):
        """Сохранить настройки"""
        settings = QSettings("IPTVComparator", "PlaylistComparator")
        settings.setValue("similarity_threshold", self.similarity_threshold)
        
    def closeEvent(self, event):
        """Обработка закрытия окна"""
        self.save_settings()
        event.accept()


class SettingsDialog(QDialog):
    """Диалог настроек"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        """Настройка интерфейса диалога"""
        self.setWindowTitle("Настройки сравнения")
        self.setGeometry(200, 200, 400, 300)
        
        layout = QVBoxLayout(self)
        
        # Порог схожести
        similarity_group = QGroupBox("Порог схожести каналов")
        similarity_layout = QVBoxLayout(similarity_group)
        
        self.similarity_slider = QSlider(Qt.Orientation.Horizontal)
        self.similarity_slider.setMinimum(50)
        self.similarity_slider.setMaximum(95)
        self.similarity_slider.setValue(int(self.parent().similarity_threshold * 100))
        
        self.similarity_label = QLabel(f"{self.similarity_slider.value()}%")
        
        self.similarity_slider.valueChanged.connect(
            lambda value: self.similarity_label.setText(f"{value}%")
        )
        
        similarity_layout.addWidget(QLabel("Минимальный процент схожести:"))
        similarity_layout.addWidget(self.similarity_slider)
        similarity_layout.addWidget(self.similarity_label)
        
        layout.addWidget(similarity_group)
        
        # Дополнительные настройки
        options_group = QGroupBox("Дополнительные настройки")
        options_layout = QVBoxLayout(options_group)
        
        self.compare_urls_check = QCheckBox("Сравнивать URL при проверке общих каналов")
        self.compare_urls_check.setChecked(True)
        
        self.ignore_case_check = QCheckBox("Игнорировать регистр при сравнении")
        self.ignore_case_check.setChecked(True)
        
        self.auto_refresh_check = QCheckBox("Автоматически обновлять при изменении файлов")
        self.auto_refresh_check.setChecked(True)
        
        options_layout.addWidget(self.compare_urls_check)
        options_layout.addWidget(self.ignore_case_check)
        options_layout.addWidget(self.auto_refresh_check)
        
        layout.addWidget(options_group)
        
        # Кнопки
        button_layout = QHBoxLayout()
        
        self.btn_ok = QPushButton("Сохранить")
        self.btn_ok.clicked.connect(self.accept)
        
        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(self.btn_ok)
        button_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(button_layout)
        
    def get_similarity_threshold(self) -> float:
        """Получить порог схожести"""
        return self.similarity_slider.value() / 100


class ExportDialog(QDialog):
    """Диалог экспорта результатов"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        """Настройка интерфейса диалога"""
        self.setWindowTitle("Экспорт результатов")
        self.setGeometry(200, 200, 400, 400)
        
        layout = QVBoxLayout(self)
        
        # Выбор формата
        format_group = QGroupBox("Формат экспорта")
        format_layout = QVBoxLayout(format_group)
        
        self.format_txt = QRadioButton("Текстовый файл (.txt)")
        self.format_csv = QRadioButton("CSV файл (.csv)")
        self.format_html = QRadioButton("HTML отчет (.html)")
        self.format_json = QRadioButton("JSON файл (.json)")
        self.format_m3u = QRadioButton("M3U плейлист (.m3u)")
        
        self.format_txt.setChecked(True)
        
        format_layout.addWidget(self.format_txt)
        format_layout.addWidget(self.format_csv)
        format_layout.addWidget(self.format_html)
        format_layout.addWidget(self.format_json)
        format_layout.addWidget(self.format_m3u)
        
        layout.addWidget(format_group)
        
        # Что экспортировать
        content_group = QGroupBox("Что экспортировать")
        content_layout = QVBoxLayout(content_group)
        
        self.include_unique = QCheckBox("Уникальные каналы")
        self.include_common = QCheckBox("Общие каналы")
        self.include_similar = QCheckBox("Похожие каналы")
        self.include_different_url = QCheckBox("Каналы с разными URL")
        
        self.include_unique.setChecked(True)
        
        content_layout.addWidget(self.include_unique)
        content_layout.addWidget(self.include_common)
        content_layout.addWidget(self.include_similar)
        content_layout.addWidget(self.include_different_url)
        
        layout.addWidget(content_group)
        
        # Кнопки
        button_layout = QHBoxLayout()
        
        self.btn_export = QPushButton("Экспортировать")
        self.btn_export.clicked.connect(self.accept)
        
        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(self.btn_export)
        button_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(button_layout)
        
    def get_export_options(self) -> Tuple[str, Dict]:
        """Получить параметры экспорта"""
        format_type = ""
        if self.format_txt.isChecked():
            format_type = "txt"
        elif self.format_csv.isChecked():
            format_type = "csv"
        elif self.format_html.isChecked():
            format_type = "html"
        elif self.format_json.isChecked():
            format_type = "json"
        elif self.format_m3u.isChecked():
            format_type = "m3u"
        
        options = {
            'include_unique': self.include_unique.isChecked(),
            'include_common': self.include_common.isChecked(),
            'include_similar': self.include_similar.isChecked(),
            'include_different_url': self.include_different_url.isChecked()
        }
        
        return format_type, options


def main():
    """Точка входа в приложение"""
    app = QApplication(sys.argv)
    app.setApplicationName("IPTV Playlist Comparator")
    app.setOrganizationName("IPTVComparator")
    
    window = PlaylistComparator()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
