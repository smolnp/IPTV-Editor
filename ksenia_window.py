import sys
import os
import json
import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from PyQt6.QtGui import (
    QAction, QKeySequence, QColor, QFont, QIcon,
    QTextCursor, QClipboard, QDesktopServices, QPalette,
    QContextMenuEvent, QShortcut, QTextCharFormat, QSyntaxHighlighter,
    QFontMetrics, QPainter, QBrush
)
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTabWidget, QTableWidget, QTableWidgetItem, QGroupBox,
    QFormLayout, QLineEdit, QPushButton, QComboBox, QLabel,
    QMenuBar, QMenu, QStatusBar, QToolBar, QFileDialog,
    QMessageBox, QDialog, QDialogButtonBox, QTreeWidget,
    QTreeWidgetItem, QHeaderView, QAbstractItemView, QListWidget,
    QListWidgetItem, QScrollArea, QGridLayout, QInputDialog,
    QToolButton, QTextEdit, QCheckBox, QRadioButton, QProgressBar,
    QProgressDialog, QFrame, QPlainTextEdit, QSpacerItem,
    QSizePolicy, QSlider, QApplication
)
from PyQt6.QtCore import (
    QSettings, Qt, pyqtSignal, QTimer, QModelIndex,
    Qt, QTimer, QSize, QPoint, QStringListModel, QEvent,
    pyqtSignal
)
from PyQt6.QtGui import (
    QAction, QKeySequence, QColor, QFont, QIcon,
    QTextCursor, QClipboard, QDesktopServices, QPalette,
    QContextMenuEvent, QShortcut, QTextCharFormat, QSyntaxHighlighter,
    QFontMetrics, QPainter, QBrush
)

from models.channel_data import ChannelData
from playlist_tab import PlaylistTab
from widgets.channel_table import ChannelTableWidget
from utilities.system_theme_manager import SystemThemeManager
from utilities.blacklist_manager import BlacklistManager
from dialogs.url_check import URLCheckDialog
from dialogs.playlist_header import PlaylistHeaderDialog
from dialogs.copy_metadata import CopyMetadataDialog
from dialogs.edit_groups_order import EditGroupsOrderDialog
from dialogs.remove_metadata import RemoveMetadataDialog
import logging

logger = logging.getLogger(__name__)


class IPTVEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # self.theme_manager = SystemThemeManager()
        self.blacklist_manager = BlacklistManager()
        
        self.tabs: Dict[QWidget, PlaylistTab] = {}
        self.current_tab: Optional[PlaylistTab] = None
        self.copied_channel: Optional[ChannelData] = None
        self.copied_channels: List[ChannelData] = []
        self.copied_metadata: Optional[ChannelData] = None
        self.copied_metadata_list: List[ChannelData] = []
        
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
        
        self._apply_system_settings()
        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_status_bar()
        
        self._create_welcome_tab()
    
    def _apply_system_settings(self):
        self.setWindowTitle("Редактор IPTV листов")
        self.resize(1200, 700)
        self.setMinimumSize(800, 600)
        self._center_window()
        
        if sys.platform in ["linux", "linux2"]:
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
        screen_geometry = self.screen().geometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)
    
    def _setup_ui(self):
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
        self.status_label = QLabel("Готов")
        self.status_bar.addWidget(self.status_label)
    
    def _create_welcome_tab(self):
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
        
        manage_blacklist_btn = QPushButton("Управление чёрным списком")
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
        if hasattr(self, 'welcome_widget'):
            index = self.tab_widget.indexOf(self.welcome_widget)
            if index >= 0:
                self.tab_widget.removeTab(index)
            self.tab_widget.setTabsClosable(True)
            del self.welcome_widget
    
    def _setup_menu(self):
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
        
        copy_metadata_action = QAction("Копировать метаданные", self)
        copy_metadata_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        copy_metadata_action.triggered.connect(self._copy_metadata)
        edit_menu.addAction(copy_metadata_action)
        
        paste_metadata_action = QAction("Вставить метаданные", self)
        paste_metadata_action.setShortcut(QKeySequence("Ctrl+Shift+V"))
        paste_metadata_action.triggered.connect(self._paste_metadata)
        edit_menu.addAction(paste_metadata_action)
        
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
        
        find_duplicate_urls_action = QAction("Найти дубликаты по URL", self)
        find_duplicate_urls_action.triggered.connect(self._find_duplicate_urls)
        edit_menu.addAction(find_duplicate_urls_action)
        
        remove_duplicate_urls_action = QAction("Удалить дубликаты по URL", self)
        remove_duplicate_urls_action.triggered.connect(self._remove_duplicate_urls)
        edit_menu.addAction(remove_duplicate_urls_action)
        
        edit_menu.addSeparator()
        
        merge_duplicates_action = QAction("Объединить дубликаты по названию", self)
        merge_duplicates_action.triggered.connect(self._merge_duplicates)
        edit_menu.addAction(merge_duplicates_action)
        
        edit_menu.addSeparator()
        
        remove_all_urls_action = QAction("Удалить все ссылки из каналов", self)
        remove_all_urls_action.triggered.connect(self._remove_all_urls)
        edit_menu.addAction(remove_all_urls_action)
        
        remove_metadata_action = QAction("Удалить метаданные из каналов...", self)
        remove_metadata_action.triggered.connect(self._remove_metadata_dialog)
        edit_menu.addAction(remove_metadata_action)
        
        delete_channels_without_metadata_action = QAction("Удалить каналы без метаданных", self)
        delete_channels_without_metadata_action.triggered.connect(self._delete_channels_without_metadata)
        edit_menu.addAction(delete_channels_without_metadata_action)
        
        playlist_menu = menubar.addMenu("Плейлист")
        
        edit_header_action = QAction("Редактировать заголовок плейлиста", self)
        edit_header_action.triggered.connect(self._edit_playlist_header)
        playlist_menu.addAction(edit_header_action)
        
        check_all_urls_action = QAction("Проверить все ссылки", self)
        check_all_urls_action.triggered.connect(self._check_all_urls)
        playlist_menu.addAction(check_all_urls_action)
        
        delete_no_url_action = QAction("Удалить все каналы без ссылок", self)
        delete_no_url_action.triggered.connect(self._delete_channels_without_urls)
        playlist_menu.addAction(delete_no_url_action)
        
        playlist_menu.addSeparator()
        
        sort_by_groups_action = QAction("Сортировать по группам", self)
        sort_by_groups_action.triggered.connect(self._sort_playlist_by_groups)
        playlist_menu.addAction(sort_by_groups_action)
        
        sort_with_changes_action = QAction("Сортировать (с отображением изменений)", self)
        sort_with_changes_action.triggered.connect(self._sort_playlist_with_changes)
        playlist_menu.addAction(sort_with_changes_action)
        
        reset_sort_view_action = QAction("Сбросить вид сортировки", self)
        reset_sort_view_action.triggered.connect(self._reset_sort_view)
        reset_sort_view_action.setEnabled(False)
        playlist_menu.addAction(reset_sort_view_action)
        
        edit_groups_order_action = QAction("Редактировать порядок групп...", self)
        edit_groups_order_action.triggered.connect(self._edit_groups_order)
        playlist_menu.addAction(edit_groups_order_action)
        
        export_sorting_stats_action = QAction("Экспорт статистики сортировки...", self)
        export_sorting_stats_action.triggered.connect(self._export_sorting_stats)
        playlist_menu.addAction(export_sorting_stats_action)
        
        tools_menu = menubar.addMenu("Инструменты")
        
        copy_metadata_between_action = QAction("Копировать метаданные между плейлистами...", self)
        copy_metadata_between_action.triggered.connect(self._copy_metadata_between_playlists)
        tools_menu.addAction(copy_metadata_between_action)
        
        tools_menu.addSeparator()
        
        check_selected_urls_action = QAction("Проверить выбранные ссылки", self)
        check_selected_urls_action.triggered.connect(self._check_selected_urls)
        tools_menu.addAction(check_selected_urls_action)
        
        tools_menu.addSeparator()
        
        manage_blacklist_action = QAction("Управление чёрным списком...", self)
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
    
    def _setup_toolbar(self):
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
        blacklist_action = QAction(blacklist_icon, "Управление чёрным списком", self)
        blacklist_action.triggered.connect(self._manage_blacklist)
        toolbar.addAction(blacklist_action)
        
        header_icon = style.standardIcon(style.StandardPixmap.SP_FileDialogInfoView)
        header_action = QAction(header_icon, "Редактировать заголовок плейлиста", self)
        header_action.triggered.connect(self._edit_playlist_header)
        toolbar.addAction(header_action)
        
        refresh_icon = style.standardIcon(style.StandardPixmap.SP_BrowserReload)
        refresh_action = QAction(refresh_icon, "Обновить вид", self)
        refresh_action.triggered.connect(self._refresh_view)
        toolbar.addAction(refresh_action)
        
        toolbar.addSeparator()
        
        sort_icon = style.standardIcon(style.StandardPixmap.SP_FileDialogListView)
        sort_action = QAction(sort_icon, "Сортировать по группам", self)
        sort_action.triggered.connect(self._sort_playlist_by_groups)
        toolbar.addAction(sort_action)
        
        reset_sort_icon = style.standardIcon(style.StandardPixmap.SP_FileDialogBack)
        reset_sort_action = QAction(reset_sort_icon, "Сбросить вид сортировки", self)
        reset_sort_action.triggered.connect(self._reset_sort_view)
        reset_sort_action.setEnabled(False)
        toolbar.addAction(reset_sort_action)
        
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
    
    def _create_new_tab(self, filepath: str = None) -> PlaylistTab:
        if hasattr(self, 'welcome_widget'):
            self._remove_welcome_tab()
        
        empty_tabs = [tab for tab in self.tabs.values() if tab and tab.is_empty()]
        
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
        
        QTimer.singleShot(10, self._delayed_filter_update)
        
        return tab
    
    def _delayed_filter_update(self):
        if self.current_tab:
            self._update_group_filter()
            self._filter_channels()
            self.current_tab._update_info()
            self._update_undo_redo_buttons()
    
    def _create_new_playlist(self):
        self._create_new_tab()
        self.status_bar.showMessage("Создан новый плейлист", 3000)
    
    def _open_playlist(self):
        filepaths, _ = QFileDialog.getOpenFileNames(
            self, "Выберите файлы плейлистов", "",
            "M3U файлы (*.m3u *.m3u8);;Все файлы (*.*)"
        )
        
        if not filepaths:
            return
        
        for filepath in filepaths:
            if os.path.exists(filepath):
                self._create_new_tab(filepath)
                self.status_bar.showMessage(f"Открыт файл: {os.path.basename(filepath)}", 3000)
            else:
                QMessageBox.warning(self, "Предупреждение", f"Файл не найден: {filepath}")
    
    def _save_current(self):
        if not self.current_tab:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
            return
        
        if self.current_tab.filepath:
            if self.current_tab.save_to_file():
                self.status_bar.showMessage("Плейлист сохранен", 3000)
            else:
                self.status_bar.showMessage("Ошибка сохранения", 3000)
        else:
            self._save_as()
    
    def _save_as(self):
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
                
                self.status_bar.showMessage(f"Сохранено как: {tab_name}", 3000)
            else:
                self.status_bar.showMessage("Ошибка сохранения", 3000)
    
    def _close_tab(self, index: int):
        widget = self.tab_widget.widget(index)
        
        if widget in self.tabs:
            tab = self.tabs[widget]
            
            if tab is None:
                self.tab_widget.removeTab(index)
                del self.tabs[widget]
                
                if self.tab_widget.count() == 0:
                    self._create_welcome_tab()
                    self.current_tab = None
                    self._update_undo_redo_buttons()
                    self.status_label.setText("Готов")
                return
            
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
                    pass
                elif reply == QMessageBox.StandardButton.No:
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
                self.status_label.setText("Готов")
    
    def _on_tab_changed(self, index: int):
        if index >= 0:
            widget = self.tab_widget.widget(index)
            
            if widget in self.tabs:
                self.current_tab = self.tabs.get(widget)
            elif not hasattr(self, 'welcome_widget') or widget != self.welcome_widget:
                self.current_tab = None
            else:
                self.current_tab = None
        
        QTimer.singleShot(10, self._delayed_filter_update)
    
    def _on_tab_info_changed(self, info_text: str):
        self.status_label.setText(info_text)
    
    def _on_tab_undo_state_changed(self, can_undo: bool, can_redo: bool):
        self._update_undo_redo_buttons()
    
    def _update_undo_redo_buttons(self):
        if self.current_tab and hasattr(self.current_tab, 'undo_manager'):
            can_undo = self.current_tab.undo_manager.can_undo()
            can_redo = self.current_tab.undo_manager.can_redo()
            has_current_channel = self.current_tab.current_channel is not None
            has_selected_channels = len(self.current_tab.selected_channels) > 0
            is_sorted_mode = self.current_tab.is_sorted_mode
        else:
            can_undo = False
            can_redo = False
            has_current_channel = False
            has_selected_channels = False
            is_sorted_mode = False
        
        if self.undo_action:
            self.undo_action.setEnabled(can_undo)
        
        if self.redo_action:
            self.redo_action.setEnabled(can_redo)
        
        if self.menu_move_up_action:
            self.menu_move_up_action.setEnabled(has_current_channel)
        
        if self.menu_move_down_action:
            self.menu_move_down_action.setEnabled(has_current_channel)
        
        menu_bar = self.menuBar()
        if menu_bar and has_current_channel:
            for action in menu_bar.actions():
                if action.text() in ["Удалить выбранные", "Переместить выбранные вверх", "Переместить выбранные вниз"]:
                    action.setEnabled(has_selected_channels and len(self.current_tab.selected_channels) > 1)
                
                if action.text() == "Сбросить вид сортировки":
                    action.setEnabled(is_sorted_mode)
        
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
                elif tooltip == "Сбросить вид сортировки":
                    action.setEnabled(is_sorted_mode)
    
    def _add_channel(self):
        if self.current_tab:
            self.current_tab._new_channel()
            self.status_bar.showMessage("Готов к добавлению нового канала", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _copy_channel(self):
        if self.current_tab:
            self.current_tab._copy_channel()
    
    def _copy_selected_channels(self):
        if self.current_tab:
            self.current_tab._copy_selected_channels()
    
    def _copy_metadata(self):
        if self.current_tab:
            self.current_tab._copy_metadata()
    
    def _copy_selected_metadata(self):
        if self.current_tab:
            self.current_tab._copy_selected_metadata()
    
    def _paste_channel(self):
        if self.current_tab:
            self.current_tab._paste_channel()
    
    def _paste_selected_channels(self):
        if self.current_tab:
            self.current_tab._paste_selected_channels()
    
    def _paste_metadata(self):
        if self.current_tab:
            self.current_tab._paste_metadata()
    
    def _paste_selected_metadata(self):
        if self.current_tab:
            self.current_tab._paste_selected_metadata()
    
    def _rename_groups(self):
        if self.current_tab:
            self.current_tab._rename_groups()
    
    def _move_channel_up(self):
        if self.current_tab and self.current_tab.current_channel:
            try:
                idx = self.current_tab.all_channels.index(self.current_tab.current_channel)
                self.current_tab._move_channel_up_in_list(idx)
                self.status_bar.showMessage("Канал перемещен вверх", 3000)
            except ValueError:
                pass
        else:
            QMessageBox.warning(self, "Предупреждение", "Выберите канал для перемещения")
    
    def _move_channel_down(self):
        if self.current_tab and self.current_tab.current_channel:
            try:
                idx = self.current_tab.all_channels.index(self.current_tab.current_channel)
                self.current_tab._move_channel_down_in_list(idx)
                self.status_bar.showMessage("Канал перемещен вниз", 3000)
            except ValueError:
                pass
        else:
            QMessageBox.warning(self, "Предупреждение", "Выберите канал для перемещения")
    
    def _move_selected_up(self):
        if self.current_tab:
            self.current_tab._move_selected_up()
            self.status_bar.showMessage("Выбранные каналы перемещены вверх", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _move_selected_down(self):
        if self.current_tab:
            self.current_tab._move_selected_down()
            self.status_bar.showMessage("Выбранные каналы перемещены вниз", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _delete_selected_channels(self):
        if self.current_tab:
            self.current_tab._delete_selected_channels()
            self.status_bar.showMessage("Выбранные каналы удалены", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _check_selected_urls(self):
        if self.current_tab:
            self.current_tab.check_selected_urls()
            self.status_bar.showMessage("Проверка выбранных ссылок", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _check_all_urls(self):
        if self.current_tab:
            self.current_tab.check_all_urls()
            self.status_bar.showMessage("Проверка всех ссылок", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _delete_channels_without_urls(self):
        if self.current_tab:
            self.current_tab.delete_channels_without_urls()
            self.status_bar.showMessage("Удаление каналов без ссылок", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _manage_blacklist(self):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton, QLabel, QLineEdit, QCheckBox, QGroupBox, QFileDialog, QMessageBox, QDialogButtonBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Управление чёрным списком")
        dialog.resize(800, 500)
        
        layout = QVBoxLayout(dialog)
        
        add_group = QGroupBox("Добавить в чёрный список")
        add_layout = QFormLayout(add_group)
        
        name_edit = QLineEdit()
        name_edit.setPlaceholderText("Название канала (частичное совпадение)")
        
        tvg_id_edit = QLineEdit()
        tvg_id_edit.setPlaceholderText("TVG-ID (точное совпадение)")
        
        add_layout.addRow("Название:", name_edit)
        add_layout.addRow("TVG-ID:", tvg_id_edit)
        
        add_btn = QPushButton("Добавить")
        add_btn.clicked.connect(lambda: self._add_to_blacklist_dialog(dialog, name_edit, tvg_id_edit))
        add_layout.addRow("", add_btn)
        
        layout.addWidget(add_group)
        
        list_group = QGroupBox("Чёрный список")
        list_layout = QVBoxLayout(list_group)
        
        blacklist_table = QTableWidget()
        blacklist_table.setColumnCount(3)
        blacklist_table.setHorizontalHeaderLabels(["Название", "TVG-ID", "Дата добавления"])
        
        blacklist_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        blacklist_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        
        header = blacklist_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        
        list_layout.addWidget(blacklist_table)
        
        btn_layout = QHBoxLayout()
        
        remove_btn = QPushButton("Удалить выбранное")
        remove_btn.clicked.connect(lambda: self._remove_from_blacklist_dialog(dialog, blacklist_table))
        
        clear_btn = QPushButton("Очистить список")
        clear_btn.clicked.connect(lambda: self._clear_blacklist_dialog(dialog))
        
        import_btn = QPushButton("Импорт из файла")
        import_btn.clicked.connect(lambda: self._import_blacklist_dialog(dialog))
        
        export_btn = QPushButton("Экспорт в файл")
        export_btn.clicked.connect(lambda: self._export_blacklist_dialog(dialog))
        
        btn_layout.addWidget(remove_btn)
        btn_layout.addWidget(clear_btn)
        btn_layout.addWidget(import_btn)
        btn_layout.addWidget(export_btn)
        
        list_layout.addLayout(btn_layout)
        
        layout.addWidget(list_group)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        self._load_blacklist_to_table(blacklist_table)
        dialog.exec()
    
    def _add_to_blacklist_dialog(self, dialog, name_edit, tvg_id_edit):
        name = name_edit.text().strip()
        tvg_id = tvg_id_edit.text().strip()
        
        if not name and not tvg_id:
            QMessageBox.warning(dialog, "Предупреждение", "Укажите название канала или TVG-ID")
            return
        
        if self.blacklist_manager.add_channel(name, tvg_id):
            self._load_blacklist_to_table(dialog.findChild(QTableWidget))
            name_edit.clear()
            tvg_id_edit.clear()
            
            self._apply_blacklist_to_all_tabs()
            
            QMessageBox.information(dialog, "Успех", "Канал добавлен в чёрный список")
        else:
            QMessageBox.warning(dialog, "Предупреждение", "Канал уже есть в чёрном списке")
    
    def _load_blacklist_to_table(self, table):
        blacklist = self.blacklist_manager.get_all()
        table.setRowCount(len(blacklist))
        
        for i, item in enumerate(blacklist):
            table.setItem(i, 0, QTableWidgetItem(item.get('name', '')))
            table.setItem(i, 1, QTableWidgetItem(item.get('tvg_id', '')))
            table.setItem(i, 2, QTableWidgetItem(item.get('added_date', '')))
    
    def _remove_from_blacklist_dialog(self, dialog, table):
        selected_rows = set()
        for item in table.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            return
        
        for row in sorted(selected_rows, reverse=True):
            name_item = table.item(row, 0)
            tvg_id_item = table.item(row, 1)
            
            if name_item and tvg_id_item:
                name = name_item.text()
                tvg_id = tvg_id_item.text()
                self.blacklist_manager.remove_channel(name, tvg_id)
        
        self._load_blacklist_to_table(table)
        self._apply_blacklist_to_all_tabs()
    
    def _clear_blacklist_dialog(self, dialog):
        reply = QMessageBox.question(
            dialog, "Подтверждение",
            "Вы уверены, что хотите очистить весь чёрный список?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.blacklist_manager.clear()
            self._load_blacklist_to_table(dialog.findChild(QTableWidget))
            self._apply_blacklist_to_all_tabs()
            QMessageBox.information(dialog, "Успех", "Чёрный список очищен")
    
    def _import_blacklist_dialog(self, dialog):
        filepath, _ = QFileDialog.getOpenFileName(
            dialog, "Импорт чёрного списка", "",
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
                            if name or tvg_id:
                                self.blacklist_manager.add_channel(name, tvg_id)
                                imported += 1
                    
                    self._load_blacklist_to_table(dialog.findChild(QTableWidget))
                    self._apply_blacklist_to_all_tabs()
                    
                    QMessageBox.information(dialog, "Успех", f"Импортировано {imported} записей")
                else:
                    QMessageBox.warning(dialog, "Ошибка", "Некорректный формат JSON файла")
            
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
                            self.blacklist_manager.add_channel(name, tvg_id)
                            imported += 1
                
                self._load_blacklist_to_table(dialog.findChild(QTableWidget))
                self._apply_blacklist_to_all_tabs()
                
                QMessageBox.information(dialog, "Успех", f"Импортировано {imported} записей")
        
        except Exception as e:
            QMessageBox.critical(dialog, "Ошибка", f"Не удалось импортировать файл:\n{str(e)}")
    
    def _export_blacklist_dialog(self, dialog):
        filepath, _ = QFileDialog.getSaveFileName(
            dialog, "Экспорт чёрного списка", "blacklist.json",
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
                    f.write("# Формат: название|tvg-id\n")
                    
                    for item in self.blacklist_manager.get_all():
                        name = item.get('name', '')
                        tvg_id = item.get('tvg_id', '')
                        f.write(f"{name}|{tvg_id}\n")
            
            QMessageBox.information(dialog, "Успех", "Чёрный список экспортирован")
        
        except Exception as e:
            QMessageBox.critical(dialog, "Ошибка", f"Не удалось экспортировать файл:\n{str(e)}")
    
    def _apply_blacklist_to_current(self):
        if self.current_tab:
            removed = self.current_tab.apply_blacklist()
            if removed > 0:
                self.status_bar.showMessage(f"Удалено {removed} каналов из текущего плейлиста", 3000)
            else:
                QMessageBox.information(self, "Информация", 
                                       "В текущем плейлисте нет каналов из чёрного списка")
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _apply_blacklist_to_all_tabs(self):
        if not self.tabs:
            QMessageBox.information(self, "Информация", "Нет открытых плейлистов")
            return
        
        total_removed = 0
        
        for tab in self.tabs.values():
            if tab:
                removed = tab.apply_blacklist()
                total_removed += removed
        
        if total_removed > 0:
            self.status_bar.showMessage(f"Удалено {total_removed} каналов из всех плейлистов", 3000)
        else:
            QMessageBox.information(self, "Информация", 
                                   "В открытых плейлистах нет каналов из чёрного списка")
    
    def _import_channels(self):
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
            
            self.status_bar.showMessage(f"Импортировано {imported_count} каналов", 3000)
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось импортировать файл:\n{str(e)}")
    
    def _export_list(self):
        if self.current_tab:
            self._export_channels()
    
    def _export_channels(self):
        if not self.current_tab or not self.current_tab.all_channels:
            QMessageBox.warning(self, "Предупреждение", "Нет каналов для экспорта")
            return
        
        filepath, selected_filter = QFileDialog.getSaveFileName(
            self, "Экспорт каналов", "",
            "Текстовые файлы (*.txt);;CSV файлы (*.csv);;M3У файлы (*.m3u);;Все файлы (*.*)"
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
        with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
            f.write("Название;Группа;TVG-ID;Логотип;URL;Статус\n")
            for channel in self.current_tab.all_channels:
                status = channel.get_status_icon()
                f.write(f'{channel.name};{channel.group};{channel.tvg_id};{channel.tvg_logo};{channel.url};{status}\n')
    
    def _export_to_text(self, filepath: str):
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
        if self.current_tab:
            self.current_tab._merge_duplicates()
            self._update_group_filter()
            self._filter_channels()
            self.status_bar.showMessage("Дубликаты по названию объединены", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _find_duplicate_urls(self):
        if not self.current_tab:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки с плейлистом")
            return
        
        self.current_tab.find_duplicate_urls()
    
    def _remove_duplicate_urls(self):
        if not self.current_tab:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки с плейлистом")
            return
        
        self.current_tab.remove_duplicate_urls()
        self.status_bar.showMessage("Дубликаты по URL удалены", 3000)
    
    def _remove_all_urls(self):
        if not self.current_tab:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки с плейлистом")
            return
        
        self.current_tab.remove_all_urls()
        self.status_bar.showMessage("Все ссылки удалены из каналов", 3000)
    
    def _remove_metadata_dialog(self):
        if not self.current_tab:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки с плейлистом")
            return
        
        dialog = RemoveMetadataDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            metadata_options = dialog.get_metadata_options()
            selection_scope = dialog.get_selection_scope()
            
            if selection_scope == "current" and self.current_tab.current_channel:
                self.current_tab._save_state("Удаление метаданных из текущего канала")
                
                channel = self.current_tab.current_channel
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
                    import re
                    extinf_line = channel.extinf
                    extinf_line = re.sub(r'catchup="[^"]*"', '', extinf_line)
                    extinf_line = re.sub(r'catchup-days="[^"]*"', '', extinf_line)
                    extinf_line = re.sub(r'catchup-source="[^"]*"', '', extinf_line)
                    extinf_line = re.sub(r'\s+', ' ', extinf_line).strip()
                    channel.extinf = extinf_line
                
                channel.update_extinf()
                self.current_tab._apply_filter()
                self.current_tab.modified = True
                self.current_tab._update_modified_status()
                
                self.status_bar.showMessage("Метаданные удалены из текущего канала", 3000)
                
            elif selection_scope == "selected" and self.current_tab.selected_channels:
                self.current_tab._save_state("Удаление метаданных из выбранных каналов")
                
                for channel in self.current_tab.selected_channels:
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
                        import re
                        extinf_line = channel.extinf
                        extinf_line = re.sub(r'catchup="[^"]*"', '', extinf_line)
                        extinf_line = re.sub(r'catchup-days="[^"]*"', '', extinf_line)
                        extinf_line = re.sub(r'catchup-source="[^"]*"', '', extinf_line)
                        extinf_line = re.sub(r'\s+', ' ', extinf_line).strip()
                        channel.extinf = extinf_line
                    
                    channel.update_extinf()
                
                self.current_tab._apply_filter()
                self.current_tab.modified = True
                self.current_tab._update_modified_status()
                
                self.status_bar.showMessage(f"Метаданные удалены из {len(self.current_tab.selected_channels)} каналов", 3000)
                
            elif selection_scope == "all":
                self.current_tab.remove_metadata(metadata_options)
                self.status_bar.showMessage("Метаданные удалены из всех каналов", 3000)
            else:
                QMessageBox.warning(self, "Предупреждение", "Нет каналов для обработки")
    
    def _delete_channels_without_metadata(self):
        if not self.current_tab:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки с плейлистом")
            return
        
        self.current_tab.delete_channels_without_metadata()
        self.status_bar.showMessage("Каналы без метаданных удалены", 3000)
    
    def _refresh_view(self):
        if self.current_tab:
            if self.search_edit:
                self.search_edit.clear()
            if self.group_combo:
                self.group_combo.setCurrentIndex(0)
            
            self._update_group_filter()
            self._filter_channels()
            self.current_tab._update_info()
            self.status_bar.showMessage("Вид обновлен", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _undo(self):
        if self.current_tab:
            self.current_tab._undo()
            self._update_group_filter()
            self._filter_channels()
            
            self._update_undo_redo_buttons()
            
            self.status_bar.showMessage("Действие отменено", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _redo(self):
        if self.current_tab:
            self.current_tab._redo()
            self._update_group_filter()
            self._filter_channels()
            
            self._update_undo_redo_buttons()
            
            self.status_bar.showMessage("Действие повторено", 3000)
        else:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
    
    def _edit_playlist_header(self):
        if not self.current_tab:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки с плейлистом")
            return
        
        self.current_tab.edit_playlist_header()
    
    def _copy_metadata_between_playlists(self):
        dialog = CopyMetadataDialog(self, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_selected_data()
            if data:
                self._apply_metadata_copy(data)
    
    def _apply_metadata_copy(self, data: Dict[str, Any]):
        source_tab_index = data['source_tab_index']
        target_tab_index = data['target_tab_index']
        
        if source_tab_index == target_tab_index:
            QMessageBox.warning(self, "Предупреждение", "Нельзя копировать метаданные в тот же плейлист")
            return
        
        source_widget = self.tab_widget.widget(source_tab_index)
        target_widget = self.tab_widget.widget(target_tab_index)
        
        if source_widget not in self.tabs or target_widget not in self.tabs:
            return
        
        source_tab = self.tabs[source_widget]
        target_tab = self.tabs[target_widget]
        
        if source_tab is None or target_tab is None:
            return
        
        source_channels = data['source_channels']
        target_channels = data['target_channels']
        
        if not source_channels or not target_channels:
            return
        
        if data['match_by_name']:
            match_func = lambda s, t: s.match_by_name(t)
        else:
            match_func = lambda s, t: s.match_by_name_and_group(t)
        
        updated_count = 0
        for target_channel in target_channels:
            source_channel = None
            for src_ch in source_channels:
                if match_func(src_ch, target_channel):
                    source_channel = src_ch
                    break
            
            if source_channel:
                metadata_channel = ChannelData()
                metadata_channel.tvg_id = source_channel.tvg_id if data['copy_tvg_id'] else ""
                metadata_channel.tvg_logo = source_channel.tvg_logo if data['copy_logo'] else ""
                metadata_channel.group = source_channel.group if data['copy_group'] else target_channel.group
                metadata_channel.user_agent = source_channel.user_agent if data['copy_user_agent'] else ""
                
                if data['copy_headers']:
                    metadata_channel.extvlcopt_lines = source_channel.extvlcopt_lines.copy()
                    metadata_channel.extra_headers = source_channel.extra_headers.copy()
                    metadata_channel.parse_extvlcopt_headers()
                else:
                    if data['copy_user_agent'] and source_channel.user_agent:
                        metadata_channel.user_agent = source_channel.user_agent
                        metadata_channel.extra_headers['User-Agent'] = source_channel.user_agent
                        metadata_channel.update_extvlcopt_from_headers()
                
                target_channel.update_metadata_from(metadata_channel)
                updated_count += 1
        
        if updated_count > 0:
            target_tab._save_state(f"Копирование метаданных из '{self.tab_widget.tabText(source_tab_index)}'")
            target_tab._apply_filter()
            target_tab.modified = True
            target_tab._update_modified_status()
            
            self.status_bar.showMessage(f"Обновлены метаданные {updated_count} каналов", 3000)
            QMessageBox.information(self, "Успех", f"Метаданные успешно обновлены для {updated_count} каналов")
        else:
            QMessageBox.information(self, "Информация", "Не найдено соответствующих каналов для обновления метаданных")
    
    def _sort_playlist_by_groups(self):
        if not self.current_tab:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
            return
        
        self.current_tab.sort_playlist_by_groups(show_change_column=True)
        self._update_undo_redo_buttons()
    
    def _sort_playlist_with_changes(self):
        if not self.current_tab:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
            return
        
        self.current_tab.sort_playlist_by_groups(show_change_column=True)
        self._update_undo_redo_buttons()
    
    def _reset_sort_view(self):
        if not self.current_tab:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
            return
        
        self.current_tab.reset_sort_view()
        self._update_undo_redo_buttons()
    
    def _edit_groups_order(self):
        if not self.current_tab:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
            return
        
        self.current_tab.edit_groups_order()
    
    def _export_sorting_stats(self):
        if not self.current_tab:
            QMessageBox.warning(self, "Предупреждение", "Нет активной вкладки")
            return
        
        self.current_tab.export_sorting_stats()
    
    def _filter_channels(self):
        if self.current_tab and hasattr(self.current_tab, '_apply_filter'):
            try:
                self.current_tab._apply_filter()
            except Exception as e:
                logger.error(f"Ошибка при фильтрации: {e}")
    
    def _update_group_filter(self):
        if (not self.current_tab or 
            not hasattr(self.current_tab, 'all_channels') or 
            not self.group_combo):
            return
        
        current = self.group_combo.currentText()
        
        self.group_combo.blockSignals(True)
        
        try:
            self.group_combo.clear()
            self.group_combo.addItem("Все группы")
            
            groups = []
            if hasattr(self.current_tab, 'all_channels'):
                try:
                    groups = sorted({ch.group for ch in self.current_tab.all_channels if ch.group and isinstance(ch.group, str)})
                except Exception as e:
                    logger.error(f"Ошибка получения групп: {e}")
                    groups = []
            
            for group in groups:
                self.group_combo.addItem(group)
            
            if current in groups:
                self.group_combo.setCurrentText(current)
            elif current == "Все группы":
                self.group_combo.setCurrentIndex(0)
                
        finally:
            self.group_combo.blockSignals(False)
    
    def _show_about(self):
        about_text = (
            "Редактор IPTV листов\n"
            "Разработчик: SmolNP\n"
        )
        
        QMessageBox.about(self, "О программе", about_text)
    
    def _reset_status_bar(self):
        self.status_bar.clearMessage()
    
    def closeEvent(self, event):
        modified_tabs = [tab for tab in self.tabs.values() if tab and tab.modified]
        
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
