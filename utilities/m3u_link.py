import sys
import os
import re
import threading
import concurrent.futures
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
import requests
from urllib.parse import urlparse
import time
from collections import defaultdict
import sqlite3
import hashlib
from datetime import datetime
import traceback
import queue
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
import warnings
import urllib3

# Отключаем предупреждения о небезопасных HTTPS запросах
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class EPGManager:
    """Менеджер для работы с EPG данными"""
    
    def __init__(self):
        self.epg_url = "http://epg.one/epg.xml"
        self.epg_data = {}  # {epg_id: {'names': [], 'icon': '', 'group': ''}}
        self.name_to_epg_id = {}  # {normalized_name: epg_id}
        self.loaded = False
        self.last_update = None
        self.cache_file = 'epg_cache.xml'
        self.cache_days = 7
        
    def load_epg_data(self):
        """Загружает данные EPG из интернета или кэша"""
        try:
            # Пробуем загрузить из кэша, если он актуален
            if self.try_load_from_cache():
                print(f"Загружено {len(self.epg_data)} каналов из кэша")
                self.loaded = True
                return True
            
            # Загружаем из интернета
            print(f"Загрузка EPG из {self.epg_url}...")
            response = requests.get(self.epg_url, timeout=15, verify=False)
            response.raise_for_status()
            
            # Парсим XML
            root = ET.fromstring(response.content)
            self.parse_epg_xml(root)
            
            # Сохраняем в кэш
            self.save_to_cache(response.content)
            
            self.loaded = True
            self.last_update = datetime.now()
            print(f"Успешно загружено {len(self.epg_data)} каналов из EPG")
            return True
            
        except Exception as e:
            print(f"Ошибка загрузки EPG: {e}")
            # Пробуем загрузить из кэша даже если он старый
            if os.path.exists(self.cache_file):
                try:
                    tree = ET.parse(self.cache_file)
                    self.parse_epg_xml(tree.getroot())
                    self.loaded = True
                    print(f"Загружено {len(self.epg_data)} каналов из старого кэша")
                    return True
                except Exception as cache_error:
                    print(f"Ошибка загрузки из кэша: {cache_error}")
            
            return False
    
    def try_load_from_cache(self):
        """Пробует загрузить данные из кэша, если он актуален"""
        if not os.path.exists(self.cache_file):
            return False
            
        try:
            cache_time = os.path.getmtime(self.cache_file)
            cache_age = (datetime.now() - datetime.fromtimestamp(cache_time)).days
            
            if cache_age <= self.cache_days:
                tree = ET.parse(self.cache_file)
                self.parse_epg_xml(tree.getroot())
                self.last_update = datetime.fromtimestamp(cache_time)
                return True
        except Exception as e:
            print(f"Ошибка чтения кэша: {e}")
            
        return False
    
    def save_to_cache(self, xml_content):
        """Сохраняет EPG данные в кэш"""
        try:
            with open(self.cache_file, 'wb') as f:
                f.write(xml_content)
        except Exception as e:
            print(f"Ошибка сохранения кэша: {e}")
    
    def parse_epg_xml(self, root):
        """Парсит XML структуру EPG"""
        self.epg_data.clear()
        self.name_to_epg_id.clear()
        
        # Обрабатываем каналы
        for channel in root.findall('.//channel'):
            channel_id = channel.get('id')
            if not channel_id:
                continue
                
            channel_info = {
                'names': [],
                'icon': '',
                'group': '',
                'original_id': channel_id
            }
            
            # Собираем все варианты названий
            for display_name in channel.findall('display-name'):
                name = display_name.text.strip()
                if name:
                    channel_info['names'].append(name)
                    # Нормализуем и добавляем в словарь для поиска
                    normalized = self.normalize_epg_name(name)
                    self.name_to_epg_id[normalized] = channel_id
            
            # Иконка канала
            icon_elem = channel.find('icon')
            if icon_elem is not None and 'src' in icon_elem.attrib:
                channel_info['icon'] = icon_elem.get('src')
            
            self.epg_data[channel_id] = channel_info
    
    def normalize_epg_name(self, name):
        """Нормализует название для поиска в EPG"""
        # Приводим к нижнему регистру, убираем лишние символы
        name = name.lower()
        name = re.sub(r'[^\w\s]', ' ', name)  # Заменяем все не-буквенные символы на пробелы
        name = re.sub(r'\s+', ' ', name).strip()
        
        # Удаляем common words
        stop_words = {'hd', 'full hd', 'fhd', '4k', 'uhd', 'live', 'stream', 
                     'tv', 'channel', 'россия', 'russia', 'телеканал', 'канал'}
        words = [word for word in name.split() if word not in stop_words]
        
        return ' '.join(words)
    
    def find_epg_id(self, channel_name):
        """Находит EPG ID для названия канала"""
        if not self.loaded:
            return None
            
        normalized = self.normalize_epg_name(channel_name)
        
        # Прямой поиск
        if normalized in self.name_to_epg_id:
            return self.name_to_epg_id[normalized]
        
        # Нечеткий поиск по похожим названиям
        best_match = None
        best_ratio = 0.7  # Порог сходства
        
        for epg_name, epg_id in self.name_to_epg_id.items():
            if not epg_name or len(epg_name) < 3:
                continue
                
            ratio = SequenceMatcher(None, normalized, epg_name).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = epg_id
        
        return best_match
    
    def get_channel_info(self, epg_id):
        """Возвращает информацию о канале по EPG ID"""
        return self.epg_data.get(epg_id)
    
    def get_all_names(self, epg_id):
        """Возвращает все варианты названий для канала"""
        info = self.get_channel_info(epg_id)
        return info['names'] if info else []

class VLCParamsExtractor:
    """Класс для извлечения параметров VLC из плейлиста"""
    
    @staticmethod
    def extract_vlc_params(lines, url_line_index):
        """Извлекает параметры VLC (#EXTVLCOPT) для указанной URL строки"""
        params = {}
        
        # Ищем параметры перед URL строкой
        i = url_line_index - 1
        while i >= 0 and lines[i].strip().startswith('#EXTVLCOPT:'):
            line = lines[i].strip()
            if ':=' in line:
                # Формат: #EXTVLCOPT:ключ=значение
                key_value = line.split(':', 1)[1].strip()
                if '=' in key_value:
                    key, value = key_value.split('=', 1)
                    params[key.strip()] = value.strip()
            elif ':' in line:
                # Формат: #EXTVLCOPT:http-user-agent=значение
                key_value = line.split(':', 1)[1].strip()
                if '=' in key_value:
                    key, value = key_value.split('=', 1)
                    params[key.strip()] = value.strip()
            i -= 1
        
        return params
    
    @staticmethod
    def format_vlc_params(params):
        """Форматирует параметы VLC в строки для записи в M3U"""
        lines = []
        for key, value in params.items():
            lines.append(f"#EXTVLCOPT:{key}={value}")
        return lines

class M3UAnalyzer(QMainWindow):
    epg_loaded = pyqtSignal(bool)  # Сигнал для завершения загрузки EPG
    
    def __init__(self):
        super().__init__()
        self.current_playlist = None
        self.sources = []
        self.channel_database = defaultdict(list)
        self.link_analyzer = LinkAnalyzer()
        self.epg_manager = EPGManager()
        self.vlc_extractor = VLCParamsExtractor()
        
        # Подключаем сигналы
        self.epg_loaded.connect(self.on_epg_loaded_signal)
        
        self.initUI()
        self.init_database()
        self.load_saved_sources()
        self.load_epg_data()
        
    def initUI(self):
        self.setWindowTitle('IPTV M3U Link Restorer Pro + EPG Sync + VLC Params')
        self.setGeometry(100, 100, 1200, 800)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        toolbar = QToolBar()
        self.addToolBar(toolbar)
        
        open_act = QAction('📂 Открыть M3U', self)
        open_act.triggered.connect(self.open_playlist)
        toolbar.addAction(open_act)
        
        save_act = QAction('💾 Сохранить M3U', self)
        save_act.triggered.connect(self.save_playlist)
        toolbar.addAction(save_act)
        
        toolbar.addSeparator()
        
        sources_act = QAction('🔧 Управление источниками', self)
        sources_act.triggered.connect(self.manage_sources)
        toolbar.addAction(sources_act)
        
        analyze_act = QAction('📊 Анализировать каналы', self)
        analyze_act.triggered.connect(self.analyze_playlist)
        toolbar.addAction(analyze_act)
        
        fix_act = QAction('🔄 Исправить ссылки', self)
        fix_act.triggered.connect(self.fix_links)
        toolbar.addAction(fix_act)
        
        # НОВАЯ КНОПКА: Восстановить отсутствующие ссылки
        fix_missing_links_act = QAction('🔗 Восстановить отсутствующие ссылки', self)
        fix_missing_links_act.triggered.connect(self.fix_missing_links)
        toolbar.addAction(fix_missing_links_act)
        
        # НОВАЯ КНОПКА: Проверить отсутствующие ссылки
        check_missing_act = QAction('🔍 Проверить отсутствующие ссылки', self)
        check_missing_act.triggered.connect(self.check_missing_links)
        toolbar.addAction(check_missing_act)
        
        toolbar.addSeparator()
        
        scan_sources_act = QAction('🔍 Сканировать источники', self)
        scan_sources_act.triggered.connect(self.scan_sources)
        toolbar.addAction(scan_sources_act)
        
        epg_act = QAction('📡 Обновить EPG', self)
        epg_act.triggered.connect(self.update_epg_data)
        toolbar.addAction(epg_act)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        self.playlist_label = QLabel('Текущий плейлист: Не выбран')
        left_layout.addWidget(self.playlist_label)
        
        # Статус EPG
        self.epg_status_label = QLabel('EPG: не загружен')
        self.epg_status_label.setStyleSheet("color: gray; font-style: italic;")
        left_layout.addWidget(self.epg_status_label)
        
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Фильтр:"))
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Фильтр каналов...")
        self.filter_input.textChanged.connect(self.filter_channels)
        filter_layout.addWidget(self.filter_input)
        
        clear_filter_btn = QPushButton("✕")
        clear_filter_btn.clicked.connect(lambda: self.filter_input.clear())
        clear_filter_btn.setMaximumWidth(30)
        filter_layout.addWidget(clear_filter_btn)
        
        left_layout.addLayout(filter_layout)
        
        self.channel_list = QListWidget()
        self.channel_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.channel_list.itemClicked.connect(self.show_channel_info)
        # Добавляем контекстное меню
        self.channel_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.channel_list.customContextMenuRequested.connect(self.show_channel_context_menu)
        left_layout.addWidget(self.channel_list)
        
        self.stats_label = QLabel('Каналов: 0')
        left_layout.addWidget(self.stats_label)
        
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        self.tab_widget = QTabWidget()
        
        info_tab = QWidget()
        info_layout = QVBoxLayout(info_tab)
        
        self.channel_info = QTextEdit()
        self.channel_info.setReadOnly(True)
        info_layout.addWidget(QLabel('Информация о канале:'))
        info_layout.addWidget(self.channel_info)
        
        channel_buttons = QHBoxLayout()
        test_btn = QPushButton("Проверить")
        test_btn.clicked.connect(self.test_selected_channel)
        channel_buttons.addWidget(test_btn)
        
        manual_btn = QPushButton("Ручная замена")
        manual_btn.clicked.connect(self.manual_fix_channel)
        channel_buttons.addWidget(manual_btn)
        
        copy_btn = QPushButton("Копировать URL")
        copy_btn.clicked.connect(self.copy_channel_url)
        channel_buttons.addWidget(copy_btn)
        
        info_layout.addLayout(channel_buttons)
        
        sources_tab = QWidget()
        sources_layout = QVBoxLayout(sources_tab)
        
        self.sources_list = QListWidget()
        sources_layout.addWidget(QLabel('Источники ссылок:'))
        sources_layout.addWidget(self.sources_list)
        
        source_buttons = QHBoxLayout()
        add_source_btn = QPushButton('➕ Добавить')
        add_source_btn.clicked.connect(self.add_source_playlist)
        add_online_btn = QPushButton('🌐 Добавить онлайн')
        add_online_btn.clicked.connect(self.add_online_source)
        remove_source_btn = QPushButton('🗑 Удалить')
        remove_source_btn.clicked.connect(self.remove_source_playlist)
        scan_sources_btn = QPushButton('🔍 Сканировать все')
        scan_sources_btn.clicked.connect(self.scan_sources)
        
        source_buttons.addWidget(add_source_btn)
        source_buttons.addWidget(add_online_btn)
        source_buttons.addWidget(remove_source_btn)
        source_buttons.addWidget(scan_sources_btn)
        sources_layout.addLayout(source_buttons)
        
        stats_tab = QWidget()
        stats_layout = QVBoxLayout(stats_tab)
        
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        stats_layout.addWidget(QLabel('Статистика:'))
        stats_layout.addWidget(self.stats_text)
        
        refresh_stats_btn = QPushButton("Обновить статистику")
        refresh_stats_btn.clicked.connect(self.update_statistics_display)
        stats_layout.addWidget(refresh_stats_btn)
        
        # Новая вкладка EPG
        epg_tab = QWidget()
        epg_layout = QVBoxLayout(epg_tab)
        
        epg_group = QGroupBox("EPG синхронизация")
        epg_group_layout = QVBoxLayout()
        
        self.use_epg_for_matching = QCheckBox('Использовать EPG для сопоставления каналов')
        self.use_epg_for_matching.setChecked(True)
        self.use_epg_for_matching.stateChanged.connect(self.on_epg_toggle)
        epg_group_layout.addWidget(self.use_epg_for_matching)
        
        self.epg_match_threshold = QSlider(Qt.Orientation.Horizontal)
        self.epg_match_threshold.setMinimum(50)
        self.epg_match_threshold.setMaximum(100)
        self.epg_match_threshold.setValue(70)
        self.epg_match_threshold.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.epg_match_threshold.setTickInterval(10)
        epg_group_layout.addWidget(QLabel("Порог совпадения по EPG (%):"))
        epg_group_layout.addWidget(self.epg_match_threshold)
        
        self.epg_threshold_label = QLabel(f"Текущий порог: 70%")
        epg_group_layout.addWidget(self.epg_threshold_label)
        self.epg_match_threshold.valueChanged.connect(
            lambda v: self.epg_threshold_label.setText(f"Текущий порог: {v}%")
        )
        
        epg_status_layout = QHBoxLayout()
        epg_status_layout.addWidget(QLabel("Статус EPG:"))
        self.epg_status_indicator = QLabel("○")
        self.epg_status_indicator.setStyleSheet("color: red; font-weight: bold;")
        epg_status_layout.addWidget(self.epg_status_indicator)
        epg_status_layout.addStretch()
        epg_group_layout.addLayout(epg_status_layout)
        
        epg_buttons = QHBoxLayout()
        update_epg_btn = QPushButton("🔄 Обновить EPG")
        update_epg_btn.clicked.connect(self.update_epg_data)
        epg_buttons.addWidget(update_epg_btn)
        
        show_epg_info_btn = QPushButton("📊 Показать статистику EPG")
        show_epg_info_btn.clicked.connect(self.show_epg_stats)
        epg_buttons.addWidget(show_epg_info_btn)
        
        epg_group_layout.addLayout(epg_buttons)
        
        epg_group.setLayout(epg_group_layout)
        epg_layout.addWidget(epg_group)
        
        test_epg_layout = QHBoxLayout()
        self.epg_test_input = QLineEdit()
        self.epg_test_input.setPlaceholderText("Введите название канала для проверки EPG...")
        test_epg_layout.addWidget(self.epg_test_input)
        
        test_epg_btn = QPushButton("🔍 Проверить")
        test_epg_btn.clicked.connect(self.test_epg_matching)
        test_epg_layout.addWidget(test_epg_btn)
        epg_layout.addLayout(test_epg_layout)
        
        self.epg_test_result = QTextEdit()
        self.epg_test_result.setReadOnly(True)
        self.epg_test_result.setMaximumHeight(150)
        epg_layout.addWidget(self.epg_test_result)
        
        epg_layout.addStretch()
        epg_tab.setLayout(epg_layout)
        
        # Новая вкладка для настроек VLC параметров
        vlc_tab = QWidget()
        vlc_layout = QVBoxLayout(vlc_tab)
        
        vlc_group = QGroupBox("Параметры VLC (#EXTVLCOPT)")
        vlc_group_layout = QVBoxLayout()
        
        self.preserve_vlc_params = QCheckBox('Сохранять параметры VLC при восстановлении ссылок')
        self.preserve_vlc_params.setChecked(True)
        self.preserve_vlc_params.stateChanged.connect(self.on_vlc_params_toggle)
        vlc_group_layout.addWidget(self.preserve_vlc_params)
        
        self.auto_detect_ua = QCheckBox('Автоматически определять User-Agent из источников')
        self.auto_detect_ua.setChecked(True)
        vlc_group_layout.addWidget(self.auto_detect_ua)
        
        vlc_group_layout.addWidget(QLabel("Общий User-Agent для всех каналов (опционально):"))
        self.global_user_agent = QLineEdit()
        self.global_user_agent.setPlaceholderText("Например: WINK/1.40.1 (AndroidTV/9) HlsWinkPlayer")
        vlc_group_layout.addWidget(self.global_user_agent)
        
        vlc_group.setLayout(vlc_group_layout)
        vlc_layout.addWidget(vlc_group)
        
        test_vlc_layout = QHBoxLayout()
        self.vlc_test_url = QLineEdit()
        self.vlc_test_url.setPlaceholderText("Введите URL для проверки с User-Agent...")
        test_vlc_layout.addWidget(self.vlc_test_url)
        
        test_vlc_btn = QPushButton("🔍 Проверить")
        test_vlc_btn.clicked.connect(self.test_vlc_url)
        test_vlc_layout.addWidget(test_vlc_btn)
        vlc_layout.addLayout(test_vlc_layout)
        
        self.vlc_test_result = QTextEdit()
        self.vlc_test_result.setReadOnly(True)
        self.vlc_test_result.setMaximumHeight(100)
        vlc_layout.addWidget(self.vlc_test_result)
        
        vlc_layout.addStretch()
        vlc_tab.setLayout(vlc_layout)
        
        # Новая вкладка для настроек безопасности
        security_tab = QWidget()
        security_layout = QVBoxLayout(security_tab)
        
        security_group = QGroupBox("Настройки безопасности")
        security_group_layout = QVBoxLayout()
        
        self.verify_ssl = QCheckBox('Проверять SSL сертификаты')
        self.verify_ssl.setChecked(False)  # По умолчанию выключено для IPTV
        self.verify_ssl.stateChanged.connect(self.on_ssl_toggle)
        security_group_layout.addWidget(self.verify_ssl)
        
        self.show_warnings = QCheckBox('Показывать предупреждения безопасности')
        self.show_warnings.setChecked(False)  # По умолчанию выключено
        self.show_warnings.stateChanged.connect(self.on_warnings_toggle)
        security_group_layout.addWidget(self.show_warnings)
        
        security_group_layout.addWidget(QLabel("Настройки прокси (опционально):"))
        
        proxy_layout = QHBoxLayout()
        proxy_layout.addWidget(QLabel("HTTP:"))
        self.http_proxy = QLineEdit()
        self.http_proxy.setPlaceholderText("http://proxy:8080")
        proxy_layout.addWidget(self.http_proxy)
        security_group_layout.addLayout(proxy_layout)
        
        https_proxy_layout = QHBoxLayout()
        https_proxy_layout.addWidget(QLabel("HTTPS:"))
        self.https_proxy = QLineEdit()
        self.https_proxy.setPlaceholderText("https://proxy:8080")
        https_proxy_layout.addWidget(self.https_proxy)
        security_group_layout.addLayout(https_proxy_layout)
        
        security_group.setLayout(security_group_layout)
        security_layout.addWidget(security_group)
        
        # Группа для настройки таймаутов
        timeout_group = QGroupBox("Настройки таймаутов")
        timeout_layout = QVBoxLayout()
        
        timeout_layout.addWidget(QLabel('Таймаут проверки (сек):'))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 30)
        self.timeout_spin.setValue(5)
        timeout_layout.addWidget(self.timeout_spin)
        
        timeout_layout.addWidget(QLabel('Максимальное количество потоков:'))
        self.max_threads_spin = QSpinBox()
        self.max_threads_spin.setRange(1, 20)
        self.max_threads_spin.setValue(10)
        timeout_layout.addWidget(self.max_threads_spin)
        
        self.retry_check = QCheckBox('Повторная проверка при ошибке')
        self.retry_check.setChecked(True)
        timeout_layout.addWidget(self.retry_check)
        
        self.retry_count = QSpinBox()
        self.retry_count.setRange(1, 5)
        self.retry_count.setValue(2)
        timeout_layout.addWidget(QLabel('Количество попыток:'))
        timeout_layout.addWidget(self.retry_count)
        
        timeout_group.setLayout(timeout_layout)
        security_layout.addWidget(timeout_group)
        
        security_layout.addStretch()
        
        settings_tab = QWidget()
        settings_layout = QVBoxLayout(settings_tab)
        
        settings_layout.addWidget(QLabel('Метод проверки:'))
        self.check_method = QComboBox()
        self.check_method.addItems(['HEAD запрос (быстро)', 'GET запрос (точнее)', 'Только проверка формата'])
        settings_layout.addWidget(self.check_method)
        
        settings_layout.addWidget(QLabel('Тип поиска:'))
        self.match_type = QComboBox()
        self.match_type.addItems(['Точное совпадение', 'Частичное совпадение', 'По ключевым словам'])
        settings_layout.addWidget(self.match_type)
        
        self.use_regex = QCheckBox('Использовать регулярные выражения')
        settings_layout.addWidget(self.use_regex)
        
        self.remove_duplicates = QCheckBox('Удалять дубликаты каналов')
        self.remove_duplicates.setChecked(True)
        settings_layout.addWidget(self.remove_duplicates)
        
        self.auto_fix = QCheckBox('Автоматически исправлять при анализе')
        settings_layout.addWidget(self.auto_fix)
        
        filter_group = QGroupBox("Фильтрация ссылок")
        filter_group_layout = QVBoxLayout()
        
        self.filter_temporary = QCheckBox('Фильтровать временные ссылки')
        self.filter_temporary.setChecked(True)
        filter_group_layout.addWidget(self.filter_temporary)
        
        self.filter_unsafe = QCheckBox('Фильтровать небезопасные ссылки')
        self.filter_unsafe.setChecked(True)
        filter_group_layout.addWidget(self.filter_unsafe)
        
        self.prioritize_https = QCheckBox('Приоритет HTTPS ссылок')
        self.prioritize_https.setChecked(True)
        filter_group_layout.addWidget(self.prioritize_https)
        
        filter_group.setLayout(filter_group_layout)
        settings_layout.addWidget(filter_group)
        
        settings_layout.addStretch()
        
        self.tab_widget.addTab(info_tab, "Информация")
        self.tab_widget.addTab(sources_tab, "Источники")
        self.tab_widget.addTab(stats_tab, "Статистика")
        self.tab_widget.addTab(epg_tab, "EPG Синхронизация")
        self.tab_widget.addTab(vlc_tab, "VLC Параметры")
        self.tab_widget.addTab(security_tab, "Безопасность")
        self.tab_widget.addTab(settings_tab, "Настройки")
        
        right_layout.addWidget(self.tab_widget)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)
        
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([400, 800])
        
        layout.addWidget(splitter)
        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
    
    # НОВЫЙ МЕТОД: Контекстное меню для каналов
    def show_channel_context_menu(self, position):
        """Показывает контекстное меню для канала"""
        item = self.channel_list.itemAt(position)
        if not item:
            return
        
        channel = item.data(Qt.ItemDataRole.UserRole)
        if not channel:
            return
        
        menu = QMenu()
        
        # Проверяем, есть ли у канала ссылка
        if not channel['url'] or channel['url'].strip() == '' or channel['status'] == 'no_url':
            fix_action = menu.addAction("🔄 Найти и вставить ссылку")
            fix_action.triggered.connect(lambda: self.fix_single_channel(channel, item))
        
        # Проверить ссылку (если есть)
        if channel['url'] and channel['url'].strip() != '':
            test_action = menu.addAction("🔍 Проверить ссылку")
            test_action.triggered.connect(lambda: self.test_selected_channel())
        
        menu.addSeparator()
        
        # Копировать название
        copy_name_action = menu.addAction("📋 Копировать название")
        copy_name_action.triggered.connect(lambda: self.copy_channel_name(channel))
        
        # Копировать URL (если есть)
        if channel['url'] and channel['url'].strip() != '':
            copy_url_action = menu.addAction("🔗 Копировать URL")
            copy_url_action.triggered.connect(lambda: self.copy_channel_url())
        
        menu.exec(self.channel_list.mapToGlobal(position))
    
    def fix_single_channel(self, channel, item):
        """Восстанавливает ссылку для одного канала"""
        if not channel:
            return
        
        print(f"Восстановление ссылки для канала: {channel['name']}")
        
        if not self.channel_database:
            QMessageBox.warning(self, 'Предупреждение', 'Сначала просканируйте источники')
            return
        
        # Показываем прогресс
        self.status_bar.showMessage(f"Поиск замены для: {channel['name'][:30]}...")
        
        # Ищем замену
        replacement = self.find_best_replacement(channel['name'])
        
        if replacement:
            # Обновляем канал
            channel['url'] = replacement['url']
            channel['status'] = 'fixed'
            channel['replacement_source'] = replacement['source']
            
            if replacement.get('epg_id'):
                channel['epg_id'] = replacement['epg_id']
            
            # Обновляем отображение
            self.update_channel_display(item, 'fixed')
            
            QMessageBox.information(self, 'Успех', 
                                  f"Найдена ссылка для канала:\n{channel['name']}\n\n"
                                  f"Источник: {replacement['source']}")
            self.status_bar.showMessage(f"Ссылка восстановлена для: {channel['name'][:30]}")
        else:
            QMessageBox.warning(self, 'Не найдено', 
                              f"Не удалось найти подходящую ссылку для канала:\n{channel['name']}")
            self.status_bar.showMessage(f"Замена не найдена для: {channel['name'][:30]}")
    
    def copy_channel_name(self, channel):
        """Копирует название канала в буфер обмена"""
        if channel:
            clipboard = QApplication.clipboard()
            clipboard.setText(channel['name'])
            self.status_bar.showMessage("Название канала скопировано", 2000)
    
    # НОВЫЙ МЕТОД: Проверка каналов без ссылок
    def check_missing_links(self):
        """Проверяет и показывает каналы без ссылок"""
        if not self.current_playlist:
            QMessageBox.warning(self, 'Предупреждение', 'Сначала откройте плейлист')
            return
        
        # Находим все каналы без ссылок
        channels_without_links = []
        channels_with_links = 0
        
        for channel in self.current_playlist['channels']:
            if not channel['url'] or channel['url'].strip() == '':
                channels_without_links.append(channel['name'])
                channel['status'] = 'no_url'
            else:
                channels_with_links += 1
        
        # Обновляем отображение
        self.update_channel_list()
        
        # Показываем статистику
        total_channels = len(self.current_playlist['channels'])
        missing_count = len(channels_without_links)
        
        if missing_count > 0:
            message = f"Найдено каналов без ссылок: {missing_count} из {total_channels}\n"
            message += f"Каналов с ссылками: {channels_with_links}\n\n"
            message += "Примеры каналов без ссылок:\n"
            
            # Показываем до 10 примеров
            for i, name in enumerate(channels_without_links[:10]):
                message += f"{i+1}. {name}\n"
            
            if missing_count > 10:
                message += f"... и еще {missing_count - 10} каналов\n"
            
            message += "\nИспользуйте функцию 'Восстановить отсутствующие ссылки' для поиска замен."
            
            QMessageBox.information(self, 'Каналы без ссылок', message)
            self.status_bar.showMessage(f'Найдено {missing_count} каналов без ссылок', 5000)
        else:
            QMessageBox.information(self, 'Информация', 'Все каналы имеют ссылки')
    
    # НОВЫЙ МЕТОД: Восстановление отсутствующих ссылок
    def fix_missing_links(self):
        """Специальная функция для восстановления каналов без ссылок"""
        if not self.current_playlist:
            QMessageBox.warning(self, 'Предупреждение', 'Сначала откройте плейлист')
            return
        
        if not self.channel_database:
            QMessageBox.warning(self, 'Предупреждение', 'Сначала просканируйте источники')
            return
        
        # Находим каналы без ссылок
        channels_without_url = []
        for i, channel in enumerate(self.current_playlist['channels']):
            # Проверяем, есть ли вообще ссылка
            if not channel['url'] or channel['url'].strip() == '':
                channels_without_url.append((i, channel))
            # Также проверяем каналы со статусом 'no_url'
            elif channel['status'] == 'no_url':
                channels_without_url.append((i, channel))
        
        if not channels_without_url:
            QMessageBox.information(self, 'Информация', 'Все каналы уже имеют ссылки')
            return
        
        reply = QMessageBox.question(
            self, 'Подтверждение',
            f'Найдено {len(channels_without_url)} каналов без ссылок.\n'
            'Попробовать найти ссылки в источниках?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        self.progress_bar.setMaximum(len(channels_without_url))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        
        fixed_count = 0
        not_found = []
        
        for idx, (channel_idx, channel) in enumerate(channels_without_url):
            print(f"Ищем замену для канала: {channel['name']}")
            
            # Используем улучшенный поиск
            replacement = self.find_best_replacement(channel['name'])
            if replacement:
                print(f"Найдена замена: {replacement['name']} из {replacement['source']}")
                
                # Сохраняем оригинальные VLC параметры
                original_vlc_params = channel.get('vlc_params', {})
                
                # Обновляем ссылку
                old_url = channel.get('url', '')
                channel['url'] = replacement['url']
                channel['status'] = 'fixed'
                channel['replacement_source'] = replacement['source']
                
                # Сохраняем EPG ID из замены
                if replacement.get('epg_id'):
                    channel['epg_id'] = replacement['epg_id']
                
                # Сохраняем VLC параметры
                if self.preserve_vlc_params.isChecked():
                    if replacement.get('vlc_params'):
                        channel['vlc_params'] = replacement['vlc_params']
                    elif original_vlc_params:
                        channel['vlc_params'] = original_vlc_params
                
                # Обновляем EXTINF строку с EPG ID, если нужно
                if replacement.get('epg_id') and 'tvg-id=' not in channel['extinf'].lower():
                    extinf_line = channel['extinf']
                    if ' tvg-' in extinf_line:
                        pos = extinf_line.lower().find(' tvg-')
                        channel['extinf'] = extinf_line[:pos] + f' tvg-id="{replacement["epg_id"]}"' + extinf_line[pos:]
                    else:
                        channel['extinf'] = extinf_line.rstrip('"') + f'" tvg-id="{replacement["epg_id"]}"'
                
                fixed_count += 1
                self.update_channel_display_by_index(channel_idx, 'fixed')
                
                print(f"Канал '{channel['name']}' обновлен: {old_url} -> {channel['url'][:50]}...")
            else:
                not_found.append(channel['name'])
                print(f"Не найдена замена для: {channel['name']}")
            
            self.progress_bar.setValue(idx + 1)
            QApplication.processEvents()
        
        self.progress_bar.setVisible(False)
        
        # Показывать результаты
        result_message = f'Восстановлено {fixed_count} из {len(channels_without_url)} ссылок'
        if not_found:
            result_message += f'\n\nНе найдены ссылки для:\n'
            for name in not_found[:10]:  # Показываем первые 10
                result_message += f'• {name}\n'
            if len(not_found) > 10:
                result_message += f'... и еще {len(not_found) - 10} каналов'
        
        QMessageBox.information(self, 'Результат', result_message)
        self.status_bar.showMessage(f'Восстановлено {fixed_count} ссылок')
        self.update_statistics_display()
    
    # НОВЫЙ МЕТОД: Поиск лучшей замены
    def find_best_replacement(self, channel_name):
        """Находит лучшую замену для канала без ссылки"""
        if not self.channel_database:
            return None
        
        # Нормализуем название для поиска
        normalized_name = self.normalize_channel_name(channel_name)
        print(f"Поиск замены для: '{channel_name}' (нормализовано: '{normalized_name}')")
        
        best_match = None
        best_score = 0
        
        # 1. Сначала ищем точное совпадение по названию
        if normalized_name in self.channel_database:
            print(f"Найдено точное совпадение: {normalized_name}")
            channels = self.channel_database[normalized_name]
            # Выбираем лучший вариант по оценке
            for channel in channels:
                score = self.calculate_replacement_score(channel)
                if score > best_score:
                    best_score = score
                    best_match = channel
        
        # 2. Если нет точного совпадения, ищем частичные
        if not best_match:
            for db_name, channels in self.channel_database.items():
                # Проверяем различные варианты совпадения
                if (normalized_name in db_name or 
                    db_name in normalized_name or
                    SequenceMatcher(None, normalized_name, db_name).ratio() > 0.7):
                    
                    print(f"Найдено частичное совпадение: {db_name}")
                    for channel in channels:
                        score = self.calculate_replacement_score(channel)
                        # Дополнительные баллы за схожесть названий
                        similarity = SequenceMatcher(None, normalized_name, db_name).ratio()
                        score += int(similarity * 50)
                        
                        if score > best_score:
                            best_score = score
                            best_match = channel
        
        # 3. Используем EPG для поиска, если доступно
        if not best_match and self.epg_manager.loaded and self.use_epg_for_matching.isChecked():
            print("Пробуем поиск через EPG...")
            epg_id = self.epg_manager.find_epg_id(channel_name)
            if epg_id:
                print(f"Найден EPG ID: {epg_id}")
                # Ищем каналы с таким же EPG ID в базе
                for db_name, channels in self.channel_database.items():
                    for channel in channels:
                        if channel.get('epg_id') == epg_id:
                            score = self.calculate_replacement_score(channel)
                            score += 100  # Большой бонус за совпадение EPG
                            
                            if score > best_score:
                                best_score = score
                                best_match = channel
                        
                        # Также проверяем через поиск EPG ID по названию
                        channel_epg_id = self.epg_manager.find_epg_id(channel['name'])
                        if channel_epg_id == epg_id:
                            score = self.calculate_replacement_score(channel)
                            score += 80  # Бонус за совпадение через поиск EPG
                            
                            if score > best_score:
                                best_score = score
                                best_match = channel
        
        if best_match:
            print(f"Лучшая замена: {best_match['name']} (оценка: {best_score})")
        else:
            print(f"Замена не найдена для: {channel_name}")
        
        return best_match
    
    # НОВЫЙ МЕТОД: Расчет оценки замены
    def calculate_replacement_score(self, candidate):
        """Рассчитывает оценку кандидата на замену"""
        score = 0
        
        # Проверяем, работает ли ссылка
        if candidate.get('analysis', {}).get('is_stable', False):
            score += 30
        
        # Предпочитаем HTTPS
        if candidate.get('analysis', {}).get('is_https', False):
            score += 20
        
        # Предпочитаем безопасные ссылки
        if candidate.get('analysis', {}).get('is_safe', False):
            score += 15
        
        # Бонус за наличие EPG ID
        if candidate.get('epg_id'):
            score += 25
        
        # Бонус за VLC параметры
        if candidate.get('vlc_params'):
            score += 20
        
        # Предпочитаем быстрые ссылки
        response_time = candidate.get('response_time', 10)
        if response_time < 2:
            score += 15
        elif response_time < 5:
            score += 10
        
        # Предпочитаем официальные источники
        source_name = candidate.get('source', '').lower()
        if any(word in source_name for word in ['official', 'stable', 'main', 'primary']):
            score += 25
        
        return score
    
    def on_ssl_toggle(self, state):
        """Обработчик изменения состояния чекбокса SSL"""
        if state == Qt.CheckState.Checked.value:
            warnings.filterwarnings('default')  # Включаем предупреждения
            self.status_bar.showMessage("Проверка SSL включена", 2000)
        else:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            warnings.filterwarnings('ignore')
            self.status_bar.showMessage("Проверка SSL выключена", 2000)
    
    def on_warnings_toggle(self, state):
        """Обработчик изменения состояния чекбокса предупреждений"""
        if state == Qt.CheckState.Checked.value:
            warnings.filterwarnings('default')
            self.status_bar.showMessage("Предупреждения включены", 2000)
        else:
            warnings.filterwarnings('ignore')
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            self.status_bar.showMessage("Предупреждения выключены", 2000)
    
    def load_epg_data(self):
        """Загружает данные EPG в фоновом режиме"""
        self.status_bar.showMessage("Загрузка EPG данных...")
        
        def load_epg_thread():
            try:
                success = self.epg_manager.load_epg_data()
                # Используем сигнал вместо QMetaObject.invokeMethod
                self.epg_loaded.emit(success)
            except Exception as e:
                print(f"Ошибка в потоке загрузки EPG: {e}")
                self.epg_loaded.emit(False)
        
        thread = threading.Thread(target=load_epg_thread, daemon=True)
        thread.start()
    
    def on_epg_loaded_signal(self, success):
        """Обработчик сигнала завершения загрузки EPG"""
        self.on_epg_loaded(success)
    
    def on_epg_loaded(self, success):
        """Обработчик завершения загрузки EPG"""
        if success:
            self.epg_status_label.setText(f"EPG: загружено {len(self.epg_manager.epg_data)} каналов")
            self.epg_status_label.setStyleSheet("color: green;")
            self.epg_status_indicator.setText("●")
            self.epg_status_indicator.setStyleSheet("color: green; font-weight: bold;")
            self.status_bar.showMessage(f"EPG загружен: {len(self.epg_manager.epg_data)} каналов", 3000)
        else:
            self.epg_status_label.setText("EPG: не загружен")
            self.epg_status_label.setStyleSheet("color: red;")
            self.epg_status_indicator.setText("○")
            self.epg_status_indicator.setStyleSheet("color: red; font-weight: bold;")
            self.status_bar.showMessage("Ошибка загрузки EPG", 3000)
    
    def update_epg_data(self):
        """Обновляет данные EPG"""
        reply = QMessageBox.question(
            self, 'Обновление EPG',
            'Обновить данные EPG? Это может занять некоторое время.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.load_epg_data()
    
    def on_epg_toggle(self, state):
        """Обработчик изменения состояния чекбокса EPG"""
        if state == Qt.CheckState.Checked.value:
            self.status_bar.showMessage("Использование EPG включено", 2000)
        else:
            self.status_bar.showMessage("Использование EPG выключено", 2000)
    
    def on_vlc_params_toggle(self, state):
        """Обработчик изменения состояния чекбокса VLC параметров"""
        if state == Qt.CheckState.Checked.value:
            self.status_bar.showMessage("Сохранение VLC параметров включено", 2000)
        else:
            self.status_bar.showMessage("Сохранение VLC параметров выключено", 2000)
    
    def show_epg_stats(self):
        """Показывает статистику EPG"""
        if not self.epg_manager.loaded:
            QMessageBox.information(self, "Статистика EPG", "EPG данные не загружены")
            return
        
        stats = f"=== СТАТИСТИКА EPG ===\n\n"
        stats += f"Всего каналов в EPG: {len(self.epg_manager.epg_data)}\n"
        stats += f"Вариантов названий: {len(self.epg_manager.name_to_epg_id)}\n"
        
        if self.epg_manager.last_update:
            stats += f"Последнее обновление: {self.epg_manager.last_update.strftime('%Y-%m-%d %H:%M')}\n"
        
        # Подсчитываем каналы с иконками
        channels_with_icon = sum(1 for info in self.epg_manager.epg_data.values() if info['icon'])
        stats += f"Каналов с иконками: {channels_with_icon}\n\n"
        
        # Показываем несколько примеров
        stats += "Примеры каналов:\n"
        for i, (epg_id, info) in enumerate(list(self.epg_manager.epg_data.items())[:10]):
            stats += f"{i+1}. {info['names'][0] if info['names'] else 'Без названия'} (ID: {epg_id})\n"
            if len(info['names']) > 1:
                stats += f"   Варианты: {', '.join(info['names'][1:3])}"
                if len(info['names']) > 3:
                    stats += f"... (+{len(info['names'])-3})"
                stats += "\n"
        
        QMessageBox.information(self, "Статистика EPG", stats)
    
    def test_epg_matching(self):
        """Тестирует сопоставление названия канала с EPG"""
        channel_name = self.epg_test_input.text().strip()
        if not channel_name:
            QMessageBox.warning(self, "Предупреждение", "Введите название канала")
            return
        
        if not self.epg_manager.loaded:
            QMessageBox.warning(self, "Предупреждение", "EPG данные не загружены")
            return
        
        epg_id = self.epg_manager.find_epg_id(channel_name)
        
        result_text = f"Тестирование EPG сопоставления:\n"
        result_text += f"Исходное название: {channel_name}\n"
        result_text += f"Нормализованное: {self.epg_manager.normalize_epg_name(channel_name)}\n\n"
        
        if epg_id:
            channel_info = self.epg_manager.get_channel_info(epg_id)
            result_text += f"✅ Найден EPG ID: {epg_id}\n"
            result_text += f"Официальное название: {channel_info['names'][0] if channel_info['names'] else 'Нет'}\n"
            result_text += f"Все варианты названий:\n"
            for name in channel_info['names']:
                result_text += f"  • {name}\n"
            
            # Проверяем, есть ли этот канал в базе источников
            normalized_search = self.normalize_channel_name(channel_name)
            matches = []
            for db_name, channels in self.channel_database.items():
                db_epg_id = self.epg_manager.find_epg_id(db_name)
                if db_epg_id == epg_id:
                    for channel in channels:
                        matches.append({
                            'name': channel['name'],
                            'source': channel['source'],
                            'url': channel['url'][:50] + '...' if len(channel['url']) > 50 else channel['url'],
                            'vlc_params': channel.get('vlc_params', {})
                        })
            
            if matches:
                result_text += f"\n📡 Найдено в источниках: {len(matches)} совпадений\n"
                for match in matches[:5]:  # Показываем первые 5
                    result_text += f"  • {match['name']} ({match['source']})\n"
                    if match.get('vlc_params'):
                        result_text += f"    VLC параметры: {match['vlc_params']}\n"
                if len(matches) > 5:
                    result_text += f"  ... и еще {len(matches)-5}\n"
        else:
            result_text += f"❌ EPG ID не найден\n\n"
            result_text += f"Ближайшие совпадения:\n"
            
            # Ищем похожие названия
            normalized = self.epg_manager.normalize_epg_name(channel_name)
            similar = []
            for epg_name, epg_id in self.epg_manager.name_to_epg_id.items():
                if len(epg_name) < 3:
                    continue
                ratio = SequenceMatcher(None, normalized, epg_name).ratio()
                if ratio > 0.5:
                    similar.append((epg_name, epg_id, ratio))
            
            similar.sort(key=lambda x: x[2], reverse=True)
            for epg_name, epg_id, ratio in similar[:5]:
                result_text += f"  • {epg_name} (ID: {epg_id}, сходство: {ratio:.1%})\n"
        
        self.epg_test_result.setText(result_text)
    
    def test_vlc_url(self):
        """Тестирует URL с User-Agent"""
        url = self.vlc_test_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Предупреждение", "Введите URL для проверки")
            return
        
        user_agent = self.global_user_agent.text().strip()
        if not user_agent:
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        
        self.vlc_test_result.setText(f"Проверяем URL с User-Agent: {user_agent[:50]}...\n")
        
        def test_thread():
            try:
                session = requests.Session()
                session.headers.update({
                    'User-Agent': user_agent
                })
                
                # Настраиваем прокси, если указаны
                proxies = {}
                if self.http_proxy.text().strip():
                    proxies['http'] = self.http_proxy.text().strip()
                if self.https_proxy.text().strip():
                    proxies['https'] = self.https_proxy.text().strip()
                
                verify_ssl = self.verify_ssl.isChecked()
                
                response = session.head(url, timeout=10, allow_redirects=True, 
                                      verify=verify_ssl, proxies=proxies if proxies else None)
                status = response.status_code
                
                result_text = f"Результат проверки:\n"
                result_text += f"URL: {url}\n"
                result_text += f"User-Agent: {user_agent[:80]}...\n"
                result_text += f"SSL проверка: {'Включена' if verify_ssl else 'Выключена'}\n"
                result_text += f"Статус: {status}\n"
                
                if status < 400:
                    result_text += "✅ URL доступен с указанным User-Agent\n"
                else:
                    result_text += f"⚠️ URL недоступен (статус: {status})\n"
                
                # Используем сигнал для обновления UI из потока
                self.vlc_test_result.setText(result_text)
                
            except Exception as e:
                self.vlc_test_result.setText(f"❌ Ошибка проверки: {str(e)}")
        
        thread = threading.Thread(target=test_thread, daemon=True)
        thread.start()
    
    def init_database(self):
        try:
            self.db_conn = sqlite3.connect('iptv_cache.db', check_same_thread=False)
            self.db_cursor = self.db_conn.cursor()
            
            self.db_cursor.execute('''
                CREATE TABLE IF NOT EXISTS saved_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    url TEXT,
                    path TEXT,
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            self.db_cursor.execute('''
                CREATE TABLE IF NOT EXISTS cache (
                    url_hash TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    status TEXT,
                    status_code INTEGER,
                    check_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            self.db_cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_cache_date ON cache(check_date)
            ''')
            
            # Добавляем таблицу для EPG сопоставлений
            self.db_cursor.execute('''
                CREATE TABLE IF NOT EXISTS epg_mappings (
                    channel_name TEXT PRIMARY KEY,
                    epg_id TEXT,
                    match_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            self.db_conn.commit()
        except Exception as e:
            print(f"Ошибка инициализации БД: {e}")
            
    def load_saved_sources(self):
        try:
            self.db_cursor.execute('SELECT type, name, url, path FROM saved_sources ORDER BY added_date')
            saved_sources = self.db_cursor.fetchall()
            
            for source_type, name, url, path in saved_sources:
                if source_type == 'online':
                    self.sources.append({
                        'type': 'online',
                        'name': name,
                        'url': url,
                        'path': '',
                        'status': 'не сканирован',
                        'channels': 0,
                        'last_checked': None
                    })
                elif source_type == 'local' and os.path.exists(path):
                    self.sources.append({
                        'type': 'local',
                        'name': name,
                        'url': '',
                        'path': path,
                        'status': 'не сканирован',
                        'channels': 0,
                        'last_checked': None
                    })
            
            self.update_sources_display()
            
        except Exception as e:
            print(f"Ошибка загрузки источников: {e}")
    
    def save_source_to_db(self, source):
        try:
            if source['type'] == 'online':
                self.db_cursor.execute('''
                    INSERT OR REPLACE INTO saved_sources (type, name, url)
                    VALUES (?, ?, ?)
                ''', ('online', source['name'], source['url']))
            elif source['type'] == 'local':
                self.db_cursor.execute('''
                    INSERT OR REPLACE INTO saved_sources (type, name, path)
                    VALUES (?, ?, ?)
                ''', ('local', source['name'], source['path']))
            
            self.db_conn.commit()
        except Exception as e:
            print(f"Ошибка сохранения источника: {e}")
    
    def manage_sources(self):
        dialog = SourceManager(self)
        dialog.set_sources(self.sources)
        
        if dialog.exec():
            new_sources = dialog.get_sources()
            self.sources = new_sources
            
            for source in self.sources:
                self.save_source_to_db(source)
            
            self.update_sources_display()
            self.status_bar.showMessage(f"Загружено {len(self.sources)} источников")
    
    def update_sources_display(self):
        self.sources_list.clear()
        
        for source in self.sources:
            icon = "📁" if source['type'] == 'local' else "🌐"
            status_text = ""
            
            if source['channels'] > 0:
                status_text = f" ({source['channels']} каналов)"
            elif source['last_checked']:
                status_text = f" [{source['last_checked']}]"
            
            item_text = f"{icon} {source['name']}{status_text}"
            item = QListWidgetItem(item_text)
            
            if 'сканирован' in str(source.get('status', '')):
                item.setForeground(QColor(0, 128, 0))
            elif 'ошибка' in str(source.get('status', '')) or 'недоступен' in str(source.get('status', '')):
                item.setForeground(QColor(255, 0, 0))
            
            self.sources_list.addItem(item)
    
    def add_source_playlist(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, 'Добавить источники M3U', '', 
            'M3U Files (*.m3u *.m3u8);;All Files (*)'
        )
        
        for file_path in file_paths:
            source_info = {
                'type': 'local',
                'name': os.path.basename(file_path),
                'url': '',
                'path': file_path,
                'status': 'не сканирован',
                'channels': 0,
                'last_checked': None
            }
            
            is_duplicate = False
            for source in self.sources:
                if source['type'] == 'local' and source['path'] == file_path:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                self.sources.append(source_info)
                self.save_source_to_db(source_info)
                self.sources_list.addItem(f"📁 {source_info['name']}")
        
        if file_paths:
            self.status_bar.showMessage(f"Добавлено {len(file_paths)} источников")
    
    def add_online_source(self):
        dialog = OnlineSourceDialog(self)
        if dialog.exec():
            url = dialog.get_url()
            name = dialog.get_name()
            
            if url and name:
                source_info = {
                    'type': 'online',
                    'name': name,
                    'url': url,
                    'path': '',
                    'status': 'не сканирован',
                    'channels': 0,
                    'last_checked': None
                }
                
                is_duplicate = False
                for source in self.sources:
                    if source['type'] == 'online' and source['url'] == url:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    self.sources.append(source_info)
                    self.save_source_to_db(source_info)
                    self.sources_list.addItem(f"🌐 {name}")
                    self.status_bar.showMessage(f"Добавлен онлайн источник: {name}")
    
    def remove_source_playlist(self):
        current_item = self.sources_list.currentItem()
        if not current_item:
            return
        
        row = self.sources_list.row(current_item)
        if row < len(self.sources):
            source = self.sources[row]
            
            reply = QMessageBox.question(
                self, 'Подтверждение',
                f'Удалить источник "{source["name"]}"?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    if source['type'] == 'online':
                        self.db_cursor.execute('DELETE FROM saved_sources WHERE url = ?', (source['url'],))
                    else:
                        self.db_cursor.execute('DELETE FROM saved_sources WHERE path = ?', (source['path'],))
                    self.db_conn.commit()
                except Exception as e:
                    print(f"Ошибка удаления из БД: {e}")
                
                self.sources.pop(row)
                self.sources_list.takeItem(row)
                self.status_bar.showMessage(f"Источник удален")
    
    def scan_sources(self):
        if not self.sources:
            QMessageBox.warning(self, 'Предупреждение', 'Нет источников для сканирования')
            return
        
        self.channel_database.clear()
        
        self.progress_bar.setMaximum(len(self.sources))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        
        total_channels = 0
        
        for i, source in enumerate(self.sources):
            try:
                if source['type'] == 'local':
                    if not os.path.exists(source['path']):
                        self.progress_bar.setValue(i + 1)
                        continue
                    
                    with open(source['path'], 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    response_time = 0
                else:
                    try:
                        start_time = time.time()
                        # Настраиваем прокси и SSL проверку
                        proxies = {}
                        if self.http_proxy.text().strip():
                            proxies['http'] = self.http_proxy.text().strip()
                        if self.https_proxy.text().strip():
                            proxies['https'] = self.https_proxy.text().strip()
                        
                        verify_ssl = self.verify_ssl.isChecked()
                        
                        response = requests.get(source['url'], timeout=15, 
                                              verify=verify_ssl, 
                                              proxies=proxies if proxies else None)
                        response_time = time.time() - start_time
                        
                        if response.status_code == 200:
                            content = response.text
                        else:
                            self.progress_bar.setValue(i + 1)
                            continue
                    except:
                        self.progress_bar.setValue(i + 1)
                        continue
                
                # Парсим с учетом VLC параметров
                channels = self.parse_m3u_with_vlc_params(content)
                added_channels = 0
                
                for channel in channels:
                    if channel['url']:
                        analysis = self.link_analyzer.analyze_url(channel['url'])
                        
                        if self.filter_temporary.isChecked() and any(temp in channel['url'].lower() 
                                                                   for temp in LinkAnalyzer.TEMPORARY_DOMAINS):
                            continue
                        if self.filter_unsafe.isChecked() and any(unsafe in channel['url'].lower() 
                                                                for unsafe in LinkAnalyzer.SHORTENER_DOMAINS):
                            continue
                        
                        normalized_name = self.normalize_channel_name(channel['name'])
                        
                        # Добавляем EPG ID, если доступно
                        epg_id = None
                        if self.epg_manager.loaded and self.use_epg_for_matching.isChecked():
                            epg_id = self.epg_manager.find_epg_id(channel['name'])
                        
                        self.channel_database[normalized_name].append({
                            'name': channel['name'],
                            'url': channel['url'],
                            'source': source['name'],
                            'type': source['type'],
                            'analysis': analysis,
                            'response_time': response_time,
                            'epg_id': epg_id,
                            'vlc_params': channel.get('vlc_params', {})  # Сохраняем VLC параметры
                        })
                        added_channels += 1
                
                total_channels += added_channels
                source['channels'] = added_channels
                source['last_checked'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                source['status'] = 'сканирован'
                
                if source['type'] == 'local':
                    self.sources_list.item(i).setText(f"📁 {source['name']} ({added_channels} каналов)")
                else:
                    self.sources_list.item(i).setText(f"🌐 {source['name']} ({added_channels} каналов)")
                
                self.progress_bar.setValue(i + 1)
                QApplication.processEvents()
                
            except Exception as e:
                print(f"Ошибка при сканировании {source['name']}: {e}")
                source['status'] = 'ошибка'
        
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f'Просканировано {len(self.sources)} источников. Найдено {total_channels} каналов')
        self.update_statistics_display()
    
    def normalize_channel_name(self, name):
        """Нормализует название канала для поиска"""
        name = name.lower()
        name = re.sub(r'[^\w\s]', '', name)
        name = re.sub(r'\s+', ' ', name).strip()
        
        common_words = ['hd', 'full hd', 'fhd', '4k', 'uhd', 'live', 'stream', 'tv', 'channel']
        words = name.split()
        filtered_words = [word for word in words if word not in common_words]
        
        return ' '.join(filtered_words) if filtered_words else name
    
    def parse_m3u(self, content):
        """Старый метод парсинга (для обратной совместимости)"""
        return self.parse_m3u_with_vlc_params(content)
    
    def parse_m3u_with_vlc_params(self, content):
        """Парсит M3U с извлечением VLC параметров"""
        channels = []
        lines = content.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if line.startswith('#EXTINF:'):
                extinf = line
                name = self.extract_channel_name(line)
                
                # Пытаемся извлечь EPG ID из атрибутов EXTINF
                epg_id = None
                epg_match = re.search(r'tvg-id="([^"]+)"', line, re.IGNORECASE)
                if epg_match:
                    epg_id = epg_match.group(1)
                
                # Ищем URL
                j = i + 1
                url = ""
                url_line_index = -1
                
                while j < len(lines):
                    next_line = lines[j].strip()
                    if next_line and not next_line.startswith('#'):
                        url = next_line
                        url_line_index = j
                        break
                    j += 1
                
                # Извлекаем VLC параметры, если они есть
                vlc_params = {}
                if url_line_index != -1 and self.preserve_vlc_params.isChecked():
                    vlc_params = self.vlc_extractor.extract_vlc_params(lines, url_line_index)
                
                channels.append({
                    'extinf': extinf,
                    'url': url,
                    'name': name,
                    'original_url': url,
                    'status': 'no_url' if not url else 'pending',
                    'last_checked': None,
                    'check_count': 0,
                    'epg_id': epg_id,
                    'vlc_params': vlc_params,  # Сохраняем VLC параметры
                    'original_lines': lines[i:url_line_index+1] if url_line_index != -1 else [extinf]
                })
                
                i = url_line_index + 1 if url else i + 1
            else:
                i += 1
        
        return channels
    
    def extract_channel_name(self, extinf_line):
        name_match = re.search(r'tvg-name="([^"]+)"', extinf_line, re.IGNORECASE)
        if name_match:
            return name_match.group(1)
        
        parts = extinf_line.split(',')
        if len(parts) > 1:
            name = parts[-1].strip()
            name = re.sub(r'\s*\([^)]*\)\s*$', '', name)
            name = re.sub(r'^\d+\s*[\.\-\:]\s*', '', name)
            name = re.sub(r'^\d+\s+', '', name)
            if name:
                return name
        
        return "Без названия"
    
    def open_playlist(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 'Открыть M3U плейлист', '', 'M3U Files (*.m3u *.m3u8);;All Files (*)'
        )
        if file_path:
            self.load_playlist(file_path)
    
    def load_playlist(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            channels = self.parse_m3u_with_vlc_params(content)
            
            self.current_playlist = {
                'path': file_path,
                'content': content,
                'channels': channels,
                'file_size': os.path.getsize(file_path)
            }
            
            self.playlist_label.setText(f'Текущий плейлист: {os.path.basename(file_path)}')
            self.stats_label.setText(f'Каналов: {len(channels)}')
            self.update_channel_list()
            self.status_bar.showMessage(f'Загружено {len(channels)} каналов из {file_path}')
            
            self.update_statistics_display()
            
        except Exception as e:
            QMessageBox.critical(self, 'Ошибка', f'Не удалось загрузить плейлист: {str(e)}')
    
    def update_channel_list(self):
        self.channel_list.clear()
        if self.current_playlist:
            for channel in self.current_playlist['channels']:
                self.add_channel_to_list(channel)
    
    def add_channel_to_list(self, channel):
        status_icon = {
            'pending': '⏳',
            'working': '✅',
            'broken': '❌',
            'fixed': '🔄',
            'no_url': '🚫',  # Специальная иконка для каналов без ссылок
            'checking': '🔍'
        }.get(channel.get('status', 'pending'), '❓')
        
        # Добавляем иконку EPG, если есть EPG ID
        epg_icon = '📡' if channel.get('epg_id') or (self.epg_manager.loaded and 
                    self.epg_manager.find_epg_id(channel['name'])) else ''
        
        # Добавляем иконку VLC, если есть параметры
        vlc_icon = '🔧' if channel.get('vlc_params') else ''
        
        url_status = ""
        if not channel['url'] or channel['url'].strip() == '':
            url_status = " (НЕТ ССЫЛКИ!)"
            # Устанавливаем статус 'no_url' если ссылки нет
            channel['status'] = 'no_url'
        elif channel['status'] == 'broken':
            url_status = " (битая ссылка)"
        
        display_name = channel['name']
        if len(display_name) > 60:
            display_name = display_name[:57] + "..."
        
        item = QListWidgetItem(f"{vlc_icon}{epg_icon}{status_icon} {display_name}{url_status}")
        item.setData(Qt.ItemDataRole.UserRole, channel)
        
        # Устанавливаем красный цвет для каналов без ссылок
        if not channel['url'] or channel['url'].strip() == '' or channel.get('status') == 'no_url':
            item.setForeground(QColor(255, 0, 0))  # Красный цвет
            item.setFont(QFont("Arial", 9, QFont.Weight.Bold))  # Жирный шрифт
            # Добавляем подсказку
            item.setToolTip("Канал без ссылки. Используйте 'Восстановить отсутствующие ссылки'")
        elif channel.get('status') == 'working':
            item.setForeground(QColor(0, 128, 0))
        elif channel.get('status') == 'broken':
            item.setForeground(QColor(255, 0, 0))
        elif channel.get('status') == 'fixed':
            item.setForeground(QColor(0, 0, 255))
        elif channel.get('status') == 'checking':
            item.setForeground(QColor(255, 165, 0))
        else:
            item.setForeground(QColor(128, 128, 128))
            
        self.channel_list.addItem(item)
    
    def filter_channels(self, text):
        if not self.current_playlist:
            return
            
        search_text = text.lower()
        for i in range(self.channel_list.count()):
            item = self.channel_list.item(i)
            channel = item.data(Qt.ItemDataRole.UserRole)
            if channel and search_text in channel['name'].lower():
                item.setHidden(False)
            else:
                item.setHidden(True)
    
    def analyze_playlist(self):
        if not self.current_playlist:
            QMessageBox.warning(self, 'Предупреждение', 'Сначала откройте плейлист')
            return
        
        channels_to_check = []
        for i, channel in enumerate(self.current_playlist['channels']):
            if channel['url'] and channel['url'].strip() != '':
                channels_to_check.append((i, channel))
            else:
                channel['status'] = 'no_url'
                self.update_channel_display_by_index(i, 'no_url')
        
        if not channels_to_check:
            QMessageBox.information(self, 'Информация', 'Нет каналов с ссылками для проверки')
            return
        
        self.progress_bar.setMaximum(len(channels_to_check))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_threads_spin.value()) as executor:
            futures = []
            for i, channel in channels_to_check:
                future = executor.submit(self.check_channel_status_with_vlc, channel, i)
                futures.append(future)
            
            for i, future in enumerate(concurrent.futures.as_completed(futures)):
                try:
                    idx, status, details = future.result(timeout=self.timeout_spin.value() + 5)
                    self.current_playlist['channels'][idx]['status'] = status
                    self.current_playlist['channels'][idx]['last_checked'] = datetime.now()
                    self.current_playlist['channels'][idx]['check_details'] = details
                    self.update_channel_display_by_index(idx, status)
                except concurrent.futures.TimeoutError:
                    if i < len(channels_to_check):
                        idx = channels_to_check[i][0]
                        self.current_playlist['channels'][idx]['status'] = 'broken'
                        self.current_playlist['channels'][idx]['check_details'] = 'Таймаут'
                        self.update_channel_display_by_index(idx, 'broken')
                except Exception as e:
                    print(f"Ошибка проверки: {e}")
                
                self.progress_bar.setValue(i + 1)
                QApplication.processEvents()
        
        self.progress_bar.setVisible(False)
        
        stats = self.calculate_statistics()
        self.status_bar.showMessage(
            f'Анализ завершен: ✅ {stats["working"]} | ❌ {stats["broken"]} | 🚫 {stats["no_url"]}'
        )
        
        if self.auto_fix.isChecked():
            self.fix_links()
    
    def check_channel_status_with_vlc(self, channel, index):
        """Проверяет статус канала с учетом VLC параметров"""
        try:
            if not channel['url'] or channel['url'].strip() == '':
                return (index, 'no_url', 'Нет ссылки')
            
            url = channel['url']
            check_method = self.check_method.currentText()
            details = []
            
            # Создаем сессию с правильными заголовками
            session = requests.Session()
            
            # Настраиваем прокси, если указаны
            proxies = {}
            if self.http_proxy.text().strip():
                proxies['http'] = self.http_proxy.text().strip()
            if self.https_proxy.text().strip():
                proxies['https'] = self.https_proxy.text().strip()
            
            # Добавляем User-Agent из VLC параметров, если есть
            user_agent = None
            if channel.get('vlc_params') and 'http-user-agent' in channel['vlc_params']:
                user_agent = channel['vlc_params']['http-user-agent']
                session.headers.update({'User-Agent': user_agent})
                details.append(f"Используется User-Agent из источника")
            else:
                # Используем стандартный User-Agent
                session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
            
            verify_ssl = self.verify_ssl.isChecked()
            
            if check_method == 'Только проверка формата':
                parsed = urlparse(url)
                if parsed.scheme and parsed.netloc:
                    return (index, 'working', 'Формат URL корректен')
                else:
                    return (index, 'broken', 'Неверный формат URL')
            
            # Пробуем разные методы проверки
            for attempt in range(self.retry_count.value() if self.retry_check.isChecked() else 1):
                try:
                    if check_method == 'HEAD запрос (быстро)':
                        response = session.head(
                            url,
                            timeout=self.timeout_spin.value(),
                            allow_redirects=True,
                            verify=verify_ssl,
                            stream=True,
                            proxies=proxies if proxies else None
                        )
                        
                        if response.status_code in [200, 301, 302, 307, 308]:
                            details.append(f"HEAD: {response.status_code}")
                            return (index, 'working', ' | '.join(details))
                        elif response.status_code == 403:
                            details.append(f"HEAD заблокирован (403), пробуем GET")
                        else:
                            details.append(f"HEAD: {response.status_code}")
                    
                    response = session.get(
                        url,
                        timeout=self.timeout_spin.value(),
                        allow_redirects=True,
                        verify=verify_ssl,
                        stream=True,
                        proxies=proxies if proxies else None
                    )
                    
                    if response.status_code in [200, 301, 302, 307, 308]:
                        if url.endswith('.m3u8') or 'm3u8' in url:
                            try:
                                content_start = response.raw.read(1024)
                                if b'#EXTM3U' in content_start or b'#EXTINF' in content_start:
                                    details.append(f"GET: {response.status_code}, M3U8 формат")
                                    response.close()
                                    return (index, 'working', ' | '.join(details))
                                else:
                                    details.append(f"GET: {response.status_code}, не M3U8 формат")
                                    response.close()
                            except:
                                details.append(f"GET: {response.status_code}, ошибка чтения")
                                response.close()
                        else:
                            response.close()
                            details.append(f"GET: {response.status_code}")
                            return (index, 'working', ' | '.join(details))
                    else:
                        details.append(f"GET: {response.status_code}")
                        response.close()
                    
                    if attempt < (self.retry_count.value() - 1):
                        time.sleep(0.5)
                        
                except requests.exceptions.SSLError:
                    details.append("SSL ошибка")
                    # Пробуем без проверки SSL
                    if verify_ssl:
                        try:
                            response = session.get(
                                url,
                                timeout=self.timeout_spin.value(),
                                allow_redirects=True,
                                verify=False,
                                proxies=proxies if proxies else None
                            )
                            if response.status_code < 400:
                                details.append(f"Без SSL: {response.status_code}")
                                return (index, 'working', ' | '.join(details))
                        except:
                            pass
                except requests.exceptions.Timeout:
                    details.append(f"Таймаут (попытка {attempt + 1})")
                except requests.exceptions.ConnectionError:
                    details.append(f"Ошибка соединения (попытка {attempt + 1})")
                except requests.exceptions.TooManyRedirects:
                    details.append("Слишком много редиректов")
                    return (index, 'broken', ' | '.join(details))
                except Exception as e:
                    details.append(f"Ошибка: {str(e)[:50]}")
            
            if len(details) == 0:
                details.append("Неизвестная ошибка")
            
            return (index, 'broken', ' | '.join(details))
                
        except Exception as e:
            return (index, 'broken', f'Ошибка проверки: {str(e)[:100]}')
    
    def update_channel_display_by_index(self, idx, status):
        if not self.current_playlist or idx >= len(self.current_playlist['channels']):
            return
            
        channel = self.current_playlist['channels'][idx]
        channel['status'] = status
        
        for j in range(self.channel_list.count()):
            item = self.channel_list.item(j)
            item_channel = item.data(Qt.ItemDataRole.UserRole)
            
            if (item_channel['name'] == channel['name'] and 
                item_channel['url'] == channel['url']):
                
                status_icon = {
                    'pending': '⏳',
                    'working': '✅',
                    'broken': '❌',
                    'fixed': '🔄',
                    'no_url': '🚫',
                    'checking': '🔍'
                }.get(status, '❓')
                
                # Добавляем иконку EPG, если есть EPG ID
                epg_icon = '📡' if channel.get('epg_id') or (self.epg_manager.loaded and 
                            self.epg_manager.find_epg_id(channel['name'])) else ''
                
                # Добавляем иконку VLC, если есть параметры
                vlc_icon = '🔧' if channel.get('vlc_params') else ''
                
                url_status = ""
                if not channel['url'] or channel['url'].strip() == '':
                    url_status = " (НЕТ ССЫЛКИ!)"
                elif status == 'broken':
                    url_status = " (битая ссылка)"
                
                display_name = channel['name']
                if len(display_name) > 60:
                    display_name = display_name[:57] + "..."
                
                item.setText(f"{vlc_icon}{epg_icon}{status_icon} {display_name}{url_status}")
                
                # Устанавливаем красный цвет для каналов без ссылок
                if not channel['url'] or channel['url'].strip() == '' or channel.get('status') == 'no_url':
                    item.setForeground(QColor(255, 0, 0))  # Красный цвет
                    item.setFont(QFont("Arial", 9, QFont.Weight.Bold))  # Жирный шрифт
                elif status == 'working':
                    item.setForeground(QColor(0, 128, 0))
                elif status == 'broken':
                    item.setForeground(QColor(255, 0, 0))
                elif status == 'fixed':
                    item.setForeground(QColor(0, 0, 255))
                elif status == 'checking':
                    item.setForeground(QColor(255, 165, 0))
                else:
                    item.setForeground(QColor(128, 128, 128))
                    
                item.setData(Qt.ItemDataRole.UserRole, channel)
                break
    
    def calculate_statistics(self):
        stats = {
            'working': 0,
            'broken': 0,
            'pending': 0,
            'fixed': 0,
            'no_url': 0,
            'checking': 0,
            'total': 0,
            'with_epg': 0,
            'with_vlc_params': 0  # Добавляем статистику по VLC параметрам
        }
        
        if not self.current_playlist:
            return stats
        
        for channel in self.current_playlist['channels']:
            stats[channel['status']] = stats.get(channel['status'], 0) + 1
            
            if channel.get('epg_id') or (self.epg_manager.loaded and 
                self.epg_manager.find_epg_id(channel['name'])):
                stats['with_epg'] += 1
            
            if channel.get('vlc_params'):
                stats['with_vlc_params'] += 1
        
        stats['total'] = len(self.current_playlist['channels'])
        
        return stats
    
    def update_statistics_display(self):
        if not self.current_playlist:
            self.stats_text.setText("Статистика недоступна")
            return
        
        stats = self.calculate_statistics()
        
        text = "=== СТАТИСТИКА ПЛЕЙЛИСТА ===\n\n"
        text += f"📊 Всего каналов: {stats['total']}\n"
        text += f"✅ Рабочих: {stats['working']}\n"
        text += f"❌ Битых: {stats['broken']}\n"
        text += f"🚫 Без ссылки: {stats['no_url']}\n"
        text += f"🔄 Исправленных: {stats['fixed']}\n"
        text += f"⏳ Ожидают проверки: {stats['pending']}\n"
        text += f"📡 С EPG: {stats['with_epg']}\n"
        text += f"🔧 С VLC параметрами: {stats['with_vlc_params']}\n\n"
        
        if stats['total'] > 0:
            working_percent = (stats['working'] / stats['total']) * 100
            epg_percent = (stats['with_epg'] / stats['total']) * 100
            vlc_percent = (stats['with_vlc_params'] / stats['total']) * 100
            text += f"📈 Работоспособность: {working_percent:.1f}%\n"
            text += f"📡 Каналов с EPG: {epg_percent:.1f}%\n"
            text += f"🔧 Каналов с VLC параметрами: {vlc_percent:.1f}%\n\n"
        
        text += "=== ИСТОЧНИКИ ===\n\n"
        if self.sources:
            for source in self.sources:
                text += f"• {source['name']} ({source['type']}): {source['channels']} каналов\n"
        else:
            text += "Источники не добавлены\n"
        
        text += f"\n=== БАЗА ДАННЫХ ===\n\n"
        text += f"Уникальных каналов: {len(self.channel_database)}\n"
        
        total_urls = sum(len(channels) for channels in self.channel_database.values())
        text += f"Всего ссылок: {total_urls}\n"
        
        # Статистика VLC параметров в базе данных
        vlc_channels = 0
        for channels in self.channel_database.values():
            for channel in channels:
                if channel.get('vlc_params'):
                    vlc_channels += 1
        
        text += f"Каналов с VLC параметрами в БД: {vlc_channels}\n"
        
        # Статистика EPG
        if self.epg_manager.loaded:
            text += f"\n=== EPG ДАННЫЕ ===\n\n"
            text += f"Загружено каналов: {len(self.epg_manager.epg_data)}\n"
            text += f"Вариантов названий: {len(self.epg_manager.name_to_epg_id)}\n"
            if self.epg_manager.last_update:
                text += f"Последнее обновление: {self.epg_manager.last_update.strftime('%Y-%m-%d %H:%M')}\n"
        
        self.stats_text.setText(text)
    
    def show_channel_info(self, item):
        channel = item.data(Qt.ItemDataRole.UserRole)
        if not channel:
            return
            
        info = f"📺 Название: {channel['name']}\n"
        info += f"📡 Статус: {channel['status']}\n"
        
        # Информация об EPG
        if self.epg_manager.loaded:
            epg_id = channel.get('epg_id') or self.epg_manager.find_epg_id(channel['name'])
            if epg_id:
                channel_info = self.epg_manager.get_channel_info(epg_id)
                info += f"📡 EPG ID: {epg_id}\n"
                if channel_info and channel_info['names']:
                    info += f"📡 Официальное название: {channel_info['names'][0]}\n"
                    if len(channel_info['names']) > 1:
                        info += f"📡 Другие названия: {', '.join(channel_info['names'][1:])}\n"
        
        # Информация о VLC параметрах
        if channel.get('vlc_params'):
            info += f"🔧 VLC параметры:\n"
            for key, value in channel['vlc_params'].items():
                info += f"   • {key}: {value}\n"
        
        if channel.get('check_details'):
            info += f"🔍 Детали проверки: {channel['check_details']}\n"
        
        if channel['url'] and channel['url'].strip() != '':
            analysis = self.link_analyzer.analyze_url(channel['url'])
            
            url_display = channel['url']
            if len(url_display) > 80:
                url_display = url_display[:77] + "..."
            info += f"🔗 Ссылка: {url_display}\n"
            
            info += f"🔒 Безопасность: {analysis['score']}/100\n"
            if analysis['is_https']:
                info += "   • HTTPS: Да ✅\n"
            else:
                info += "   • HTTPS: Нет ❌\n"
            
            if analysis['issues']:
                info += "   • Проблемы:\n"
                for issue in analysis['issues']:
                    info += f"     - {issue}\n"
        else:
            info += f"🔗 Ссылка: НЕТ ССЫЛКИ\n"
        
        if channel.get('replacement_source'):
            info += f"🔄 Источник замены: {channel['replacement_source']}\n"
        
        if channel.get('last_checked'):
            info += f"⏰ Последняя проверка: {channel['last_checked']}\n"
        
        if channel.get('check_count', 0) > 0:
            info += f"🔢 Количество проверок: {channel['check_count']}\n"
        
        self.channel_info.setText(info)
    
    def test_selected_channel(self):
        selected_items = self.channel_list.selectedItems()
        if not selected_items:
            return
            
        item = selected_items[0]
        channel = item.data(Qt.ItemDataRole.UserRole)
        
        if not channel['url'] or channel['url'].strip() == '':
            QMessageBox.information(self, "Информация", "У канала нет ссылки для проверки")
            return
        
        channel['status'] = 'checking'
        self.update_channel_display(item, 'checking')
        
        def check_thread():
            try:
                session = requests.Session()
                
                # Настраиваем прокси, если указаны
                proxies = {}
                if self.http_proxy.text().strip():
                    proxies['http'] = self.http_proxy.text().strip()
                if self.https_proxy.text().strip():
                    proxies['https'] = self.https_proxy.text().strip()
                
                # Используем User-Agent из VLC параметров, если есть
                if channel.get('vlc_params') and 'http-user-agent' in channel['vlc_params']:
                    user_agent = channel['vlc_params']['http-user-agent']
                    session.headers.update({'User-Agent': user_agent})
                else:
                    session.headers.update({
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    })
                
                verify_ssl = self.verify_ssl.isChecked()
                
                try:
                    response = session.get(
                        channel['url'],
                        timeout=self.timeout_spin.value(),
                        allow_redirects=True,
                        verify=verify_ssl,
                        stream=True,
                        proxies=proxies if proxies else None
                    )
                    
                    if response.status_code < 400:
                        status = 'working'
                        details = f"GET: {response.status_code}"
                    else:
                        status = 'broken'
                        details = f"GET: {response.status_code}"
                    
                    response.close()
                except:
                    status = 'broken'
                    details = "Ошибка соединения"
                
                channel['status'] = status
                channel['check_details'] = details
                channel['last_checked'] = datetime.now()
                
                self.update_channel_display(item, status)
                
            except Exception as e:
                print(f"Ошибка проверки канала: {e}")
        
        thread = threading.Thread(target=check_thread, daemon=True)
        thread.start()
    
    def update_channel_display(self, item, status):
        channel = item.data(Qt.ItemDataRole.UserRole)
        if not channel:
            return
            
        channel['status'] = status
        channel['last_checked'] = datetime.now()
        
        status_icon = {
            'pending': '⏳',
            'working': '✅',
            'broken': '❌',
            'fixed': '🔄',
            'no_url': '🚫',
            'checking': '🔍'
        }.get(status, '❓')
        
        # Добавляем иконку EPG, если есть EPG ID
        epg_icon = '📡' if channel.get('epg_id') or (self.epg_manager.loaded and 
                    self.epg_manager.find_epg_id(channel['name'])) else ''
        
        # Добавляем иконку VLC, если есть параметры
        vlc_icon = '🔧' if channel.get('vlc_params') else ''
        
        url_status = ""
        if not channel['url'] or channel['url'].strip() == '':
            url_status = " (НЕТ ССЫЛКИ!)"
        elif status == 'broken':
            url_status = " (битая ссылка)"
        
        display_name = channel['name']
        if len(display_name) > 60:
            display_name = display_name[:57] + "..."
        
        item.setText(f"{vlc_icon}{epg_icon}{status_icon} {display_name}{url_status}")
        
        # Устанавливаем красный цвет для каналов без ссылок
        if not channel['url'] or channel['url'].strip() == '' or channel.get('status') == 'no_url':
            item.setForeground(QColor(255, 0, 0))  # Красный цвет
            item.setFont(QFont("Arial", 9, QFont.Weight.Bold))  # Жирный шрифт
        elif status == 'working':
            item.setForeground(QColor(0, 128, 0))
        elif status == 'broken':
            item.setForeground(QColor(255, 0, 0))
        elif status == 'fixed':
            item.setForeground(QColor(0, 0, 255))
        elif status == 'checking':
            item.setForeground(QColor(255, 165, 0))
        else:
            item.setForeground(QColor(0, 0, 0))
        
        self.show_channel_info(item)
    
    def copy_channel_url(self):
        selected_items = self.channel_list.selectedItems()
        if selected_items:
            item = selected_items[0]
            channel = item.data(Qt.ItemDataRole.UserRole)
            
            if channel['url'] and channel['url'].strip() != '':
                clipboard = QApplication.clipboard()
                clipboard.setText(channel['url'])
                self.status_bar.showMessage("Ссылка скопирована в буфер обмена", 2000)
            else:
                QMessageBox.information(self, "Информация", "У канала нет ссылки для копирования")
    
    def fix_links(self):
        if not self.current_playlist:
            return
        
        if not self.channel_database:
            QMessageBox.warning(self, 'Предупреждение', 'Сначала просканируйте источники')
            return
        
        fixed_count = 0
        self.progress_bar.setMaximum(len(self.current_playlist['channels']))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        
        for i, channel in enumerate(self.current_playlist['channels']):
            # ВАЖНОЕ ИЗМЕНЕНИЕ: Обрабатываем все каналы со статусом 'broken', 'no_url', 'pending'
            if channel['status'] in ['broken', 'no_url', 'pending']:
                replacement = self.find_replacement(channel['name'], channel['url'])
                if replacement:
                    # Сохраняем оригинальные VLC параметры, если включена опция
                    original_vlc_params = channel.get('vlc_params', {})
                    
                    channel['url'] = replacement['url']
                    channel['status'] = 'fixed'
                    channel['replacement_source'] = replacement['source']
                    
                    # Сохраняем EPG ID из замены, если есть
                    if replacement.get('epg_id'):
                        channel['epg_id'] = replacement['epg_id']
                    
                    # Сохраняем VLC параметры
                    if self.preserve_vlc_params.isChecked():
                        # Если в замене есть VLC параметры, используем их
                        if replacement.get('vlc_params'):
                            channel['vlc_params'] = replacement['vlc_params']
                        # Иначе сохраняем оригинальные параметры
                        elif original_vlc_params:
                            channel['vlc_params'] = original_vlc_params
                    
                    fixed_count += 1
                    self.update_channel_display_by_index(i, 'fixed')
            
            self.progress_bar.setValue(i + 1)
            QApplication.processEvents()
        
        self.progress_bar.setVisible(False)
        
        if fixed_count > 0:
            QMessageBox.information(self, 'Готово', f'Исправлено {fixed_count} ссылок')
            self.status_bar.showMessage(f'Исправлено {fixed_count} ссылок')
            self.update_statistics_display()
        else:
            QMessageBox.information(self, 'Информация', 'Не найдено подходящих замен для битых ссылок')
    
    def find_replacement(self, channel_name, current_url):
        """Находит замену для канала с использованием EPG для точного сопоставления"""
        use_epg = self.use_epg_for_matching.isChecked() and self.epg_manager.loaded
        
        # Получаем EPG ID для искомого канала
        target_epg_id = None
        if use_epg:
            target_epg_id = self.epg_manager.find_epg_id(channel_name)
        
        best_candidate = None
        highest_score = -1
        
        # Проходим по всем каналам в базе данных
        for db_name, channels in self.channel_database.items():
            # Получаем EPG ID для канала из базы данных
            candidate_epg_id = None
            if use_epg:
                # Пробуем найти EPG ID для канала из базы
                for channel in channels:
                    if channel.get('epg_id'):
                        candidate_epg_id = channel['epg_id']
                        break
                if not candidate_epg_id:
                    candidate_epg_id = self.epg_manager.find_epg_id(db_name)
            
            # Сравниваем EPG ID, если доступны
            if use_epg and target_epg_id and candidate_epg_id:
                if target_epg_id == candidate_epg_id:
                    # Совпадение по EPG ID! Это наилучшее совпадение
                    for channel in channels:
                        score = self.calculate_candidate_score(channel, db_name, target_epg_id=True)
                        if score > highest_score:
                            highest_score = score
                            best_candidate = channel
                    # Если нашли совпадение по EPG ID, можно прекратить поиск
                    if best_candidate:
                        break
            else:
                # Используем старый алгоритм сравнения названий
                if self.is_match(self.normalize_channel_name(channel_name), db_name, channel_name):
                    for channel in channels:
                        score = self.calculate_candidate_score(channel, db_name)
                        if score > highest_score:
                            highest_score = score
                            best_candidate = channel
        
        return best_candidate
    
    def calculate_candidate_score(self, candidate, search_name=None, target_epg_id=False):
        """Рассчитывает оценку кандидата на замену"""
        score = 0
        
        # Если это совпадение по EPG ID, даем максимальный базовый балл
        if target_epg_id:
            score += 100
        
        # Проверяем, работает ли ссылка кандидата
        if candidate.get('status', 'unknown') == 'working':
            score += 40
        elif candidate.get('last_checked'):
            # Если недавно проверяли и была рабочей, даем баллы
            score += 20
        
        if search_name:
            candidate_name = self.normalize_channel_name(candidate['name'])
            if search_name == candidate_name:
                score += 50
            elif search_name in candidate_name or candidate_name in search_name:
                score += 30
            else:
                # Частичное совпадение слов
                search_words = set(search_name.split())
                candidate_words = set(candidate_name.split())
                common_words = search_words.intersection(candidate_words)
                if common_words:
                    score += len(common_words) * 10
        
        analysis = candidate.get('analysis', {})
        if analysis.get('is_https', False) and self.prioritize_https.isChecked():
            score += 20
        if analysis.get('is_stable', False):
            score += 15
        if analysis.get('is_safe', False):
            score += 10
        
        response_time = candidate.get('response_time', 10)
        if response_time < 2:
            score += 10
        elif response_time < 5:
            score += 5
        
        # Бонус за наличие EPG ID
        if candidate.get('epg_id'):
            score += 25
        
        # Бонус за наличие VLC параметров
        if candidate.get('vlc_params'):
            score += 30
        
        # Бонус за стабильный источник
        source_name = candidate.get('source', '')
        if 'official' in source_name.lower() or 'stable' in source_name.lower():
            score += 20
        
        return score
    
    def is_match(self, search_name, db_name, original_name):
        match_type = self.match_type.currentText()
        
        if self.use_regex.isChecked():
            try:
                return bool(re.search(search_name, db_name, re.IGNORECASE))
            except:
                return False
        
        if match_type == 'Точное совпадение':
            return search_name == db_name
        elif match_type == 'Частичное совпадение':
            return search_name in db_name or db_name in search_name
        else:
            search_words = set(search_name.split())
            db_words = set(db_name.split())
            return len(search_words.intersection(db_words)) > 0
    
    def save_playlist(self):
        if not self.current_playlist:
            QMessageBox.warning(self, 'Предупреждение', 'Нет открытого плейлиста')
            return
        
        default_name = os.path.basename(self.current_playlist['path'])
        if default_name.endswith('.m3u'):
            default_name = default_name.replace('.m3u', '_fixed.m3u')
        elif default_name.endswith('.m3u8'):
            default_name = default_name.replace('.m3u8', '_fixed.m3u8')
        else:
            default_name = 'playlist_fixed.m3u'
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, 'Сохранить M3U плейлист', 
            default_name, 
            'M3U Files (*.m3u *.m3u8);;All Files (*)'
        )
        
        if file_path:
            try:
                if not file_path.endswith(('.m3u', '.m3u8')):
                    file_path += '.m3u'
                
                content = '#EXTM3U\n'
                for channel in self.current_playlist['channels']:
                    # Добавляем EPG ID в атрибуты EXTINF, если он есть
                    extinf_line = channel['extinf']
                    
                    # Если у канала есть EPG ID, добавляем его как tvg-id
                    epg_id = channel.get('epg_id')
                    if not epg_id and self.epg_manager.loaded:
                        epg_id = self.epg_manager.find_epg_id(channel['name'])
                    
                    if epg_id and 'tvg-id=' not in extinf_line.lower():
                        # Добавляем tvg-id в конец строки перед параметрами
                        if ' tvg-' in extinf_line:
                            # Вставляем перед первым tvg- параметром
                            pos = extinf_line.lower().find(' tvg-')
                            extinf_line = extinf_line[:pos] + f' tvg-id="{epg_id}"' + extinf_line[pos:]
                        else:
                            # Добавляем в конец перед закрывающей кавычкой
                            extinf_line = extinf_line.rstrip('"') + f'" tvg-id="{epg_id}"'
                    
                    content += extinf_line + '\n'
                    
                    # Добавляем VLC параметры, если они есть и включена опция
                    if channel.get('vlc_params') and self.preserve_vlc_params.isChecked():
                        vlc_lines = self.vlc_extractor.format_vlc_params(channel['vlc_params'])
                        for vlc_line in vlc_lines:
                            content += vlc_line + '\n'
                    
                    if channel['url'] and channel['url'].strip() != '':
                        content += channel['url'] + '\n'
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                self.status_bar.showMessage(f'Плейлист сохранен: {file_path}')
                
            except Exception as e:
                QMessageBox.critical(self, 'Ошибка', f'Ошибка при сохранении: {str(e)}')
    
    def manual_fix_channel(self):
        selected_items = self.channel_list.selectedItems()
        if not selected_items:
            return
            
        item = selected_items[0]
        channel = item.data(Qt.ItemDataRole.UserRole)
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Ручная замена ссылки")
        dialog.setGeometry(300, 200, 600, 400)
        
        layout = QVBoxLayout(dialog)
        
        layout.addWidget(QLabel(f"Канал: {channel['name']}"))
        
        # Поле для EPG ID
        epg_layout = QHBoxLayout()
        epg_layout.addWidget(QLabel("EPG ID:"))
        epg_input = QLineEdit()
        epg_input.setPlaceholderText("Введите EPG ID...")
        epg_id = channel.get('epg_id')
        if not epg_id and self.epg_manager.loaded:
            epg_id = self.epg_manager.find_epg_id(channel['name'])
        epg_input.setText(epg_id or "")
        epg_layout.addWidget(epg_input)
        
        find_epg_btn = QPushButton("Найти")
        def find_epg():
            epg_id = self.epg_manager.find_epg_id(channel['name'])
            if epg_id:
                epg_input.setText(epg_id)
                channel_info = self.epg_manager.get_channel_info(epg_id)
                if channel_info:
                    QMessageBox.information(dialog, "Найден EPG", 
                                          f"EPG ID: {epg_id}\nНазвания: {', '.join(channel_info['names'][:3])}")
            else:
                QMessageBox.warning(dialog, "Не найдено", "EPG ID не найден")
        find_epg_btn.clicked.connect(find_epg)
        epg_layout.addWidget(find_epg_btn)
        
        layout.addLayout(epg_layout)
        
        # Поля для VLC параметров
        vlc_group = QGroupBox("VLC параметры")
        vlc_layout = QVBoxLayout()
        
        user_agent_layout = QHBoxLayout()
        user_agent_layout.addWidget(QLabel("User-Agent:"))
        user_agent_input = QLineEdit()
        user_agent_input.setPlaceholderText("WINK/1.40.1 (AndroidTV/9) HlsWinkPlayer")
        if channel.get('vlc_params') and 'http-user-agent' in channel['vlc_params']:
            user_agent_input.setText(channel['vlc_params']['http-user-agent'])
        user_agent_layout.addWidget(user_agent_input)
        vlc_layout.addLayout(user_agent_layout)
        
        referer_layout = QHBoxLayout()
        referer_layout.addWidget(QLabel("Referer:"))
        referer_input = QLineEdit()
        referer_input.setPlaceholderText("https://example.com/")
        if channel.get('vlc_params') and 'http-referrer' in channel['vlc_params']:
            referer_input.setText(channel['vlc_params']['http-referrer'])
        referer_layout.addWidget(referer_input)
        vlc_layout.addLayout(referer_layout)
        
        vlc_group.setLayout(vlc_layout)
        layout.addWidget(vlc_group)
        
        url_input = QLineEdit()
        url_input.setPlaceholderText("Введите новую ссылку...")
        url_input.setText(channel['url'] if channel['url'] else "")
        layout.addWidget(url_input)
        
        button_layout = QHBoxLayout()
        
        test_btn = QPushButton("Проверить")
        def test_url():
            url = url_input.text()
            if not url:
                QMessageBox.warning(dialog, "Предупреждение", "Введите ссылку для проверки")
                return
            
            # Используем User-Agent из формы, если указан
            user_agent = user_agent_input.text().strip()
            if not user_agent:
                user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            
            dialog.setCursor(Qt.CursorShape.WaitCursor)
            try:
                session = requests.Session()
                session.headers.update({'User-Agent': user_agent})
                
                verify_ssl = self.verify_ssl.isChecked()
                
                response = session.get(url, timeout=5, allow_redirects=True, 
                                     verify=verify_ssl, stream=True)
                if response.status_code < 400:
                    QMessageBox.information(dialog, "Успех", "Ссылка работает!")
                else:
                    QMessageBox.warning(dialog, "Предупреждение", f"Ссылка не работает. Код: {response.status_code}")
                response.close()
            except Exception as e:
                QMessageBox.critical(dialog, "Ошибка", f"Ошибка проверки: {str(e)}")
            finally:
                dialog.unsetCursor()
        test_btn.clicked.connect(test_url)
        button_layout.addWidget(test_btn)
        
        button_layout.addStretch()
        
        ok_btn = QPushButton("Применить")
        def apply_url():
            new_url = url_input.text()
            new_epg_id = epg_input.text().strip() or None
            
            # Собираем VLC параметры
            vlc_params = {}
            user_agent = user_agent_input.text().strip()
            referer = referer_input.text().strip()
            
            if user_agent:
                vlc_params['http-user-agent'] = user_agent
            if referer:
                vlc_params['http-referrer'] = referer
            
            old_url = channel['url']
            channel['url'] = new_url
            channel['epg_id'] = new_epg_id
            
            if vlc_params:
                channel['vlc_params'] = vlc_params
            
            if new_url and new_url.strip() != '':
                try:
                    session = requests.Session()
                    if user_agent:
                        session.headers.update({'User-Agent': user_agent})
                    
                    verify_ssl = self.verify_ssl.isChecked()
                    
                    response = session.get(new_url, timeout=5, allow_redirects=True, 
                                         verify=verify_ssl, stream=True)
                    if response.status_code < 400:
                        channel['status'] = 'working'
                    else:
                        channel['status'] = 'broken'
                    response.close()
                except:
                    channel['status'] = 'broken'
                
                if new_url != old_url:
                    channel['replacement_source'] = 'ручная замена'
            else:
                channel['status'] = 'no_url'
            
            # Обновляем EXTINF строку с новым EPG ID
            if new_epg_id and 'tvg-id=' not in channel['extinf'].lower():
                extinf_line = channel['extinf']
                if ' tvg-' in extinf_line:
                    pos = extinf_line.lower().find(' tvg-')
                    channel['extinf'] = extinf_line[:pos] + f' tvg-id="{new_epg_id}"' + extinf_line[pos:]
                else:
                    channel['extinf'] = extinf_line.rstrip('"') + f'" tvg-id="{new_epg_id}"'
            
            self.update_channel_display(item, channel['status'])
            dialog.accept()
        ok_btn.clicked.connect(apply_url)
        button_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        dialog.exec()
    
    def closeEvent(self, event):
        try:
            if hasattr(self, 'db_conn'):
                self.db_conn.close()
        except:
            pass
        
        event.accept()

# Добавляем недостающие классы
class LinkAnalyzer:
    TEMPORARY_DOMAINS = {
        'pastebin.com', 'file.io', 'transfer.sh', 'tmp.link',
        '0x0.st', 'catbox.moe', 'rentry.co', 'gist.github.com'
    }
    
    SHORTENER_DOMAINS = {
        'bit.ly', 'tinyurl.com', 'shorturl.at', 'cutt.ly',
        'ow.ly', 'is.gd', 'adf.ly', 'shorte.st', 'ouo.io',
        'tiny.cc', 'short.link', 'rb.gy', 't.ly'
    }
    
    STABLE_DOMAINS = {
        'akamai.net', 'cloudfront.net', 'hwcdn.net', 'cdn77.org',
        'm3u8', 'stream', 'live', 'tv', 'channel'
    }
    
    @staticmethod
    def analyze_url(url: str) -> dict:
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            score = 100
            
            issues = []
            positive = []
            
            for temp in LinkAnalyzer.TEMPORARY_DOMAINS:
                if temp in domain:
                    score -= 40
                    issues.append(f"Временный домен: {temp}")
                    break
            
            for shortener in LinkAnalyzer.SHORTENER_DOMAINS:
                if shortener in domain:
                    score -= 35
                    issues.append(f"Сокращатель: {shortener}")
                    break
            
            for stable in LinkAnalyzer.STABLE_DOMAINS:
                if stable in domain:
                    score += 20
                    positive.append(f"Стабильный: {stable}")
                    break
            
            if parsed.scheme == 'https':
                score += 15
                positive.append("HTTPS")
            else:
                score -= 10
                issues.append("HTTP")
            
            if len(url) > 500:
                score -= 20
                issues.append("Слишком длинный URL")
            
            if re.search(r'[\s<>"\'{}|\\^`]', url):
                score -= 25
                issues.append("Странные символы в URL")
            
            score = max(0, min(100, score))
            
            return {
                'score': score,
                'issues': issues,
                'positive': positive,
                'is_https': parsed.scheme == 'https',
                'is_stable': score >= 70,
                'is_safe': score >= 50,
                'domain': domain
            }
            
        except Exception as e:
            return {
                'score': 0,
                'issues': [f'Ошибка анализа: {str(e)}'],
                'positive': [],
                'is_https': False,
                'is_stable': False,
                'is_safe': False,
                'domain': ''
            }

class SourceManager(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Управление источниками")
        self.setGeometry(200, 200, 800, 500)
        self.sources = []
        self.initUI()
        
    def initUI(self):
        layout = QVBoxLayout(self)
        
        # Таблица источников
        self.sources_table = QTableWidget()
        self.sources_table.setColumnCount(5)
        self.sources_table.setHorizontalHeaderLabels(["Тип", "Имя", "URL/Путь", "Статус", "Каналы"])
        self.sources_table.horizontalHeader().setStretchLastSection(True)
        
        self.sources_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.sources_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.sources_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        layout.addWidget(self.sources_table)
        
        # Кнопки управления
        button_layout = QHBoxLayout()
        
        add_local_btn = QPushButton("➕ Добавить локальный")
        add_local_btn.clicked.connect(self.add_local_source)
        button_layout.addWidget(add_local_btn)
        
        add_online_btn = QPushButton("🌐 Добавить онлайн")
        add_online_btn.clicked.connect(self.add_online_source)
        button_layout.addWidget(add_online_btn)
        
        remove_btn = QPushButton("🗑 Удалить")
        remove_btn.clicked.connect(self.remove_source)
        button_layout.addWidget(remove_btn)
        
        refresh_btn = QPushButton("🔄 Обновить статус")
        refresh_btn.clicked.connect(self.refresh_status)
        button_layout.addWidget(refresh_btn)
        
        scan_btn = QPushButton("🔍 Сканировать")
        scan_btn.clicked.connect(self.scan_selected)
        button_layout.addWidget(scan_btn)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Кнопки закрытия
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
    def add_local_source(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, 'Добавить локальные источники', '', 
            'M3U Files (*.m3u *.m3u8);;All Files (*)'
        )
        for file_path in file_paths:
            is_duplicate = False
            for source in self.sources:
                if source['type'] == 'local' and source['path'] == file_path:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                self.sources.append({
                    'type': 'local',
                    'name': os.path.basename(file_path),
                    'path': file_path,
                    'url': '',
                    'status': 'не сканирован',
                    'channels': 0,
                    'last_checked': None
                })
        self.update_table()
        
    def add_online_source(self):
        dialog = OnlineSourceDialog(self)
        if dialog.exec():
            url = dialog.get_url()
            name = dialog.get_name()
            if url and name:
                is_duplicate = False
                for source in self.sources:
                    if source['type'] == 'online' and source['url'] == url:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    self.sources.append({
                        'type': 'online',
                        'name': name,
                        'url': url,
                        'path': '',
                        'status': 'не сканирован',
                        'channels': 0,
                        'last_checked': None
                    })
                    self.update_table()
                
    def remove_source(self):
        row = self.sources_table.currentRow()
        if row >= 0 and row < len(self.sources):
            source = self.sources[row]
            
            reply = QMessageBox.question(
                self, 'Подтверждение',
                f'Удалить источник "{source["name"]}"?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                del self.sources[row]
                self.update_table()
                
    def refresh_status(self):
        for i, source in enumerate(self.sources):
            try:
                if source['type'] == 'online':
                    try:
                        response = requests.head(source['url'], timeout=5, allow_redirects=True, verify=False)
                        if response.status_code == 200:
                            source['status'] = 'доступен'
                        else:
                            source['status'] = f'ошибка {response.status_code}'
                    except Exception as e:
                        source['status'] = 'недоступен'
                else:
                    if os.path.exists(source['path']):
                        source['status'] = 'файл существует'
                    else:
                        source['status'] = 'файл не найден'
            except Exception as e:
                source['status'] = f'ошибка: {str(e)[:30]}'
        
        self.update_table()
        
    def scan_selected(self):
        row = self.sources_table.currentRow()
        if row >= 0 and row < len(self.sources):
            source = self.sources[row]
            
            def scan_thread():
                try:
                    if source['type'] == 'local':
                        if not os.path.exists(source['path']):
                            source['status'] = 'файл не найден'
                            self.update_table()
                            return
                        
                        with open(source['path'], 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                    else:
                        try:
                            response = requests.get(source['url'], timeout=10, verify=False)
                            
                            if response.status_code == 200:
                                content = response.text
                                source['status'] = 'сканирован'
                            else:
                                source['status'] = f'ошибка {response.status_code}'
                                self.update_table()
                                return
                        except Exception as e:
                            source['status'] = f'ошибка: {str(e)[:30]}'
                            self.update_table()
                            return
                    
                    lines = content.split('\n')
                    channel_count = 0
                    url_count = 0
                    
                    i = 0
                    while i < len(lines):
                        line = lines[i].strip()
                        if line.startswith('#EXTINF:'):
                            channel_count += 1
                            j = i + 1
                            while j < len(lines):
                                next_line = lines[j].strip()
                                if next_line and not next_line.startswith('#'):
                                    if next_line.startswith('http'):
                                        url_count += 1
                                    break
                                j += 1
                            i = j + 1
                        else:
                            i += 1
                    
                    source['channels'] = channel_count
                    source['last_checked'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                    source['status'] = f'сканирован ({url_count}/{channel_count} ссылок)'
                    
                    QMetaObject.invokeMethod(self, "update_table", 
                                           Qt.ConnectionType.QueuedConnection)
                    
                except Exception as e:
                    source['status'] = f'ошибка сканирования: {str(e)[:30]}'
                    QMetaObject.invokeMethod(self, "update_table", 
                                           Qt.ConnectionType.QueuedConnection)
            
            source['status'] = 'сканируется...'
            self.update_table()
            
            thread = threading.Thread(target=scan_thread, daemon=True)
            thread.start()
            
    def update_table(self):
        self.sources_table.setRowCount(len(self.sources))
        for i, source in enumerate(self.sources):
            type_item = QTableWidgetItem()
            if source['type'] == 'local':
                type_item.setText('📁 Локальный')
            else:
                type_item.setText('🌐 Онлайн')
            self.sources_table.setItem(i, 0, type_item)
            
            name_item = QTableWidgetItem(source['name'])
            self.sources_table.setItem(i, 1, name_item)
            
            if source['type'] == 'local':
                path_text = source['path']
                if len(path_text) > 50:
                    path_text = '...' + path_text[-47:]
                path_item = QTableWidgetItem(path_text)
                path_item.setToolTip(source['path'])
            else:
                url_text = source['url']
                if len(url_text) > 50:
                    url_text = url_text[:47] + '...'
                url_item = QTableWidgetItem(url_text)
                url_item.setToolTip(source['url'])
            self.sources_table.setItem(i, 2, path_item if source['type'] == 'local' else url_item)
            
            status_item = QTableWidgetItem(source['status'])
            
            if 'сканирован' in source['status']:
                status_item.setForeground(QColor(0, 128, 0))
            elif 'ошибка' in source['status'] or 'недоступен' in source['status']:
                status_item.setForeground(QColor(255, 0, 0))
            elif 'сканируется' in source['status']:
                status_item.setForeground(QColor(255, 165, 0))
            
            self.sources_table.setItem(i, 3, status_item)
            
            channels_item = QTableWidgetItem(str(source['channels']))
            self.sources_table.setItem(i, 4, channels_item)
        
        self.sources_table.resizeColumnsToContents()
            
    def get_sources(self):
        return self.sources
        
    def set_sources(self, sources):
        self.sources = sources
        self.update_table()

class OnlineSourceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добавить онлайн источник")
        self.setGeometry(300, 300, 500, 250)
        self.initUI()
        
    def initUI(self):
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("Имя источника:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Введите имя источника")
        layout.addWidget(self.name_input)
        
        layout.addWidget(QLabel("URL источника:"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com/playlist.m3u")
        layout.addWidget(self.url_input)
        
        settings_group = QGroupBox("Настройки")
        settings_layout = QVBoxLayout()
        
        self.auto_check = QCheckBox("Автоматически проверять доступность")
        self.auto_check.setChecked(True)
        settings_layout.addWidget(self.auto_check)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        button_layout = QHBoxLayout()
        
        test_btn = QPushButton("🔍 Проверить")
        test_btn.clicked.connect(self.test_url)
        button_layout.addWidget(test_btn)
        
        button_layout.addStretch()
        
        ok_btn = QPushButton("✅ OK")
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("❌ Отмена")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
    def test_url(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Ошибка", "Введите URL")
            return
            
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
            self.url_input.setText(url)
            
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            response = requests.head(url, timeout=10, allow_redirects=True, verify=False)
            if response.status_code == 200:
                QMessageBox.information(self, "Успех", "URL доступен")
                
                if not self.name_input.text():
                    parsed = urlparse(url)
                    name = parsed.netloc
                    if name.startswith('www.'):
                        name = name[4:]
                    self.name_input.setText(f"Источник {name}")
            else:
                QMessageBox.warning(self, "Предупреждение", 
                                  f"URL недоступен. Код: {response.status_code}")
        except requests.exceptions.Timeout:
            QMessageBox.warning(self, "Предупреждение", 
                              "Таймаут при проверке URL. Сайт может быть недоступен.")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", 
                               f"Не удалось проверить URL: {str(e)}")
        finally:
            QApplication.restoreOverrideCursor()
            
    def get_url(self):
        return self.url_input.text().strip()
        
    def get_name(self):
        name = self.name_input.text().strip()
        if not name:
            name = f"Источник {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return name

def main():
    app = QApplication(sys.argv)
    
    app.setStyle('Fusion')
    
    window = M3UAnalyzer()
    window.show()
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
