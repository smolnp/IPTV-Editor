import sys
import re
import csv
from pathlib import Path
from datetime import datetime
from PyQt6.QtWidgets import *
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QColor, QAction


class M3USorter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("M3USorter", "App")
        self.init_ui()
        self.setup_groups_order()
        
    def setup_groups_order(self):
        """Загрузка порядка групп из настроек"""
        saved_order = self.settings.value("groups_order")
        
        if saved_order:
            self.groups_order = saved_order
        else:
            # Порядок по умолчанию
            self.groups_order = [
                "Общественные",
                "Информационные", 
                "Христианские",
                "Детские",
                "Развлекательные",
                "Музыкальные",
                "Кино и сериалы",
                "Кинозалы",
                "Спортивные",
                "Познавательные",
                "Хобби и увлечения",
                "Региональные",
                "Радио"
            ]
        
    def init_ui(self):
        self.setWindowTitle("M3U Playlist Sorter")
        self.setGeometry(100, 100, 1000, 700)
        
        # Создаем меню
        menubar = self.menuBar()
        
        # Меню Файл
        file_menu = menubar.addMenu("Файл")
        
        open_action = QAction("Открыть M3U", self)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
        
        save_action = QAction("Сохранить", self)
        save_action.triggered.connect(self.save_file)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        export_stats_action = QAction("Экспорт статистики", self)
        export_stats_action.triggered.connect(self.export_stats)
        file_menu.addAction(export_stats_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Выход", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Меню Настройки
        settings_menu = menubar.addMenu("Настройки")
        
        edit_groups_action = QAction("Редактировать порядок групп", self)
        edit_groups_action.triggered.connect(self.edit_groups_order)
        settings_menu.addAction(edit_groups_action)
        
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Заголовок
        header_label = QLabel("Сортировщик M3U Плейлистов")
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = header_label.font()
        font.setPointSize(14)
        font.setBold(True)
        header_label.setFont(font)
        main_layout.addWidget(header_label)
        
        # Информация о файле
        info_layout = QHBoxLayout()
        self.file_info_label = QLabel("Файл не выбран")
        info_layout.addWidget(self.file_info_label)
        
        self.stats_label = QLabel("")
        info_layout.addWidget(self.stats_label)
        info_layout.addStretch()
        
        main_layout.addLayout(info_layout)
        
        # Кнопки управления
        button_layout = QHBoxLayout()
        
        self.btn_open = QPushButton("Открыть M3U файл")
        self.btn_open.clicked.connect(self.open_file)
        button_layout.addWidget(self.btn_open)
        
        self.btn_sort = QPushButton("Сортировать")
        self.btn_sort.clicked.connect(self.sort_playlist)
        self.btn_sort.setEnabled(False)
        button_layout.addWidget(self.btn_sort)
        
        self.btn_save = QPushButton("Сохранить")
        self.btn_save.clicked.connect(self.save_file)
        self.btn_save.setEnabled(False)
        button_layout.addWidget(self.btn_save)
        
        main_layout.addLayout(button_layout)
        
        # Поле поиска и фильтрации
        search_layout = QHBoxLayout()
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Поиск каналов...")
        self.search_input.textChanged.connect(self.filter_channels)
        search_layout.addWidget(QLabel("Поиск:"))
        search_layout.addWidget(self.search_input)
        
        # Кнопка сброса фильтра
        self.btn_reset_filter = QPushButton("Сбросить")
        self.btn_reset_filter.clicked.connect(self.reset_filter)
        search_layout.addWidget(self.btn_reset_filter)
        
        # Фильтр по группам
        self.group_filter = QComboBox()
        self.group_filter.addItem("Все группы")
        self.group_filter.currentTextChanged.connect(self.filter_channels)
        search_layout.addWidget(QLabel("Группа:"))
        search_layout.addWidget(self.group_filter)
        
        main_layout.addLayout(search_layout)
        
        # Область предпросмотра
        preview_label = QLabel("Содержимое плейлиста:")
        main_layout.addWidget(preview_label)
        
        # Таблица для отображения каналов
        self.channels_table = QTableWidget()
        self.channels_table.setColumnCount(6)  # Увеличили количество столбцов
        self.channels_table.setHorizontalHeaderLabels(["Новый №", "Старый №", "Название канала", "Группа", "Ссылка", "Изменение"])
        self.channels_table.horizontalHeader().setStretchLastSection(True)
        self.channels_table.setAlternatingRowColors(True)
        self.channels_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.channels_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        # Включаем контекстное меню
        self.channels_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.channels_table.customContextMenuRequested.connect(self.show_context_menu)
        
        main_layout.addWidget(self.channels_table)
        
        # Область логов
        log_label = QLabel("Лог операций:")
        main_layout.addWidget(log_label)
        
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(100)
        self.log_text.setReadOnly(True)
        main_layout.addWidget(self.log_text)
        
        # Статус бар
        self.statusBar().showMessage("Готов к работе")
        
        # Инициализация переменных
        self.current_file = None
        self.sorted_channels = None
        self.original_channels = None
        self.filtered_channels = None
        
        # Загружаем настройки
        self.load_settings()
        
    def load_settings(self):
        """Загрузка сохраненных настроек"""
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
            
    def save_settings(self):
        """Сохранение настроек"""
        self.settings.setValue("geometry", self.saveGeometry())
        
    def closeEvent(self, event):
        """Сохранение настроек при закрытии"""
        self.save_settings()
        event.accept()
        
    def log_message(self, message):
        """Добавление сообщения в лог"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        
    def open_file(self):
        """Открытие файла M3U"""
        last_dir = self.settings.value("last_dir", "")
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Открыть M3U файл", last_dir, 
            "M3U Files (*.m3u *.m3u8);;Все файлы (*.*)"
        )
        
        if file_path:
            self.settings.setValue("last_dir", str(Path(file_path).parent))
            self.current_file = Path(file_path)
            
            try:
                with open(self.current_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # Парсим каналы
                self.original_channels = self.parse_m3u(content)
                self.filtered_channels = self.original_channels.copy()
                
                # Обновляем информацию
                self.file_info_label.setText(f"Файл: {self.current_file.name}")
                groups_count = self.count_groups()
                
                # Считаем каналы с ссылками и без
                channels_with_url = sum(1 for ch in self.original_channels if ch.get('url'))
                channels_without_url = sum(1 for ch in self.original_channels if not ch.get('url'))
                
                self.stats_label.setText(
                    f"Каналов: {len(self.original_channels)} "
                    f"(с ссылкой: {channels_with_url}, без ссылки: {channels_without_url}) | "
                    f"Групп: {groups_count}"
                )
                
                # Обновляем фильтр групп
                self.update_group_filter(self.original_channels)
                
                # Показываем каналы в таблице
                self.show_channels_in_table(self.original_channels)
                
                self.btn_sort.setEnabled(True)
                self.statusBar().showMessage(f"Загружено {len(self.original_channels)} каналов")
                
                self.log_message(f"Открыт файл: {self.current_file.name}")
                self.log_message(f"Найдено каналов: {len(self.original_channels)}")
                self.log_message(f"Каналов с ссылкой: {channels_with_url}")
                self.log_message(f"Каналов без ссылки: {channels_without_url}")
                
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", 
                    f"Не удалось открыть файл:\n{str(e)}")
                self.log_message(f"Ошибка открытия файла: {str(e)}")
                
    def parse_m3u(self, content):
        """Улучшенный парсинг M3U файла - сохраняет ВСЕ каналы, включая без ссылок"""
        lines = content.strip().split('\n')
        channels = []
        current_channel = {}
        channel_number = 1
        waiting_for_url = False
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('#EXTINF'):
                # Если уже есть собранный канал, сохраняем его (даже без URL)
                if current_channel:
                    channels.append(current_channel.copy())
                    channel_number += 1
                
                current_channel = {'extinf': line}
                waiting_for_url = True
                
                # Извлекаем все параметры
                params_match = re.findall(r'([a-zA-Z-]+)="([^"]*)"', line)
                params = dict(params_match)
                
                # Получаем название (после последней запятой)
                name = line.split(',')[-1].strip()
                current_channel['name'] = name
                
                # Извлекаем группу
                current_channel['group'] = params.get('group-title', 'Без группы')
                
                # Сохраняем дополнительные параметры
                current_channel['tvg-id'] = params.get('tvg-id', '')
                current_channel['tvg-logo'] = params.get('tvg-logo', '')
                current_channel['tvg-name'] = params.get('tvg-name', '')
                
                # Сохраняем номер канала
                current_channel['original_number'] = channel_number
                
            elif line.startswith('#'):
                # Пропускаем другие комментарии
                continue
                
            elif waiting_for_url:
                # Это может быть URL или пустая строка после EXTINF
                if not line.startswith('http') and not line.startswith('rtp://') and not line.startswith('udp://'):
                    # Если это не URL, сохраняем канал без ссылки
                    current_channel['url'] = ''
                    channels.append(current_channel.copy())
                    channel_number += 1
                    current_channel = {}
                    waiting_for_url = False
                else:
                    # Это URL
                    current_channel['url'] = line
                    channels.append(current_channel.copy())
                    channel_number += 1
                    current_channel = {}
                    waiting_for_url = False
                    
        # Сохраняем последний канал, если он есть
        if current_channel:
            if 'url' not in current_channel:
                current_channel['url'] = ''
            channels.append(current_channel.copy())
        
        return channels
    
    def count_groups(self):
        """Подсчет количества уникальных групп"""
        if not self.original_channels:
            return 0
        groups = set(ch.get('group', 'Без группы') for ch in self.original_channels)
        return len(groups)
    
    def update_group_filter(self, channels):
        """Обновление списка групп для фильтрации"""
        self.group_filter.clear()
        self.group_filter.addItem("Все группы")
        
        groups = set(ch.get('group', 'Без группы') for ch in channels)
        for group in sorted(groups):
            self.group_filter.addItem(group)
    
    def show_channels_in_table(self, channels, show_sorted_info=False):
        """Отображение каналов в таблице"""
        if show_sorted_info:
            self.channels_table.setColumnCount(6)
            self.channels_table.setHorizontalHeaderLabels(["Новый №", "Старый №", "Название канала", "Группа", "Ссылка", "Изменение"])
        else:
            self.channels_table.setColumnCount(4)
            self.channels_table.setHorizontalHeaderLabels(["№", "Название канала", "Группа", "Ссылка"])
        
        self.channels_table.setRowCount(len(channels))
        
        for row, channel in enumerate(channels):
            if show_sorted_info:
                # Новый номер
                item_new_num = QTableWidgetItem(str(channel.get('new_number', '')))
                item_new_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.channels_table.setItem(row, 0, item_new_num)
                
                # Старый номер
                old_num = channel.get('original_number', '')
                item_old_num = QTableWidgetItem(str(old_num))
                item_old_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.channels_table.setItem(row, 1, item_old_num)
                
                # Название
                item_name = QTableWidgetItem(channel.get('name', ''))
                self.channels_table.setItem(row, 2, item_name)
                
                # Группа
                item_group = QTableWidgetItem(channel.get('group', ''))
                self.channels_table.setItem(row, 3, item_group)
                
                # Ссылка
                url = channel.get('url', '')
                item_url = QTableWidgetItem(url)
                if not url:
                    item_url.setText("Нет ссылки")
                    item_url.setForeground(QColor(255, 0, 0))  # Красный цвет для каналов без ссылки
                self.channels_table.setItem(row, 4, item_url)
                
                # Изменение позиции
                if 'new_number' in channel and 'original_number' in channel:
                    change = channel['new_number'] - channel['original_number']
                    item_change = QTableWidgetItem(f"{change:+d}")
                    item_change.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    
                    # Цветовое кодирование
                    if change > 0:
                        item_change.setBackground(QColor(255, 200, 200))  # Красный - опустился
                    elif change < 0:
                        item_change.setBackground(QColor(200, 255, 200))  # Зеленый - поднялся
                    
                    self.channels_table.setItem(row, 5, item_change)
            else:
                # Номер
                item_num = QTableWidgetItem(str(row + 1))
                item_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.channels_table.setItem(row, 0, item_num)
                
                # Название канала
                item_name = QTableWidgetItem(channel.get('name', 'Без названия'))
                self.channels_table.setItem(row, 1, item_name)
                
                # Группа
                group = channel.get('group', 'Без группы')
                item_group = QTableWidgetItem(group)
                self.channels_table.setItem(row, 2, item_group)
                
                # Ссылка
                url = channel.get('url', '')
                item_url = QTableWidgetItem(url)
                if not url:
                    item_url.setText("Нет ссылки")
                    item_url.setForeground(QColor(255, 0, 0))  # Красный цвет для каналов без ссылки
                self.channels_table.setItem(row, 3, item_url)
        
        # Автоматически подгоняем ширину столбцов
        self.channels_table.resizeColumnsToContents()
        
    def filter_channels(self):
        """Фильтрация каналов по поисковому запросу"""
        if not self.original_channels:
            return
            
        search_text = self.search_input.text().lower()
        selected_group = self.group_filter.currentText()
        
        filtered_channels = []
        for channel in self.original_channels:
            # Проверяем поиск по названию
            name_match = search_text in channel.get('name', '').lower()
            
            # Проверяем фильтр по группе
            group_match = (selected_group == "Все группы" or 
                          selected_group == channel.get('group', ''))
            
            if name_match and group_match:
                filtered_channels.append(channel)
        
        self.filtered_channels = filtered_channels
        self.show_channels_in_table(filtered_channels, show_sorted_info=False)
    
    def reset_filter(self):
        """Сброс фильтров"""
        self.search_input.clear()
        self.group_filter.setCurrentIndex(0)
        if self.original_channels:
            self.filtered_channels = self.original_channels.copy()
            self.show_channels_in_table(self.original_channels)
    
    def sort_playlist(self):
        """Улучшенная сортировка с сохранением исходных номеров"""
        if not self.original_channels:
            return
            
        try:
            # Создаем копию с сохранением исходных номеров
            for idx, channel in enumerate(self.original_channels):
                channel['original_number'] = idx + 1
        
            # Группируем каналы
            grouped_channels = {}
            for channel in self.original_channels:
                group = channel.get('group', 'Без группы')
                if group not in grouped_channels:
                    grouped_channels[group] = []
                grouped_channels[group].append(channel)
            
            # Сортируем внутри групп по названию
            for group in grouped_channels:
                grouped_channels[group].sort(key=lambda x: (
                    not x['name'].startswith('●'),  # Закрепленные каналы (с символом ●) вверху
                    x['name'].lower()
                ))
            
            # Собираем отсортированный список
            sorted_channels = []
            new_number = 1
            
            # Группы в указанном порядке
            for group_name in self.groups_order:
                if group_name in grouped_channels:
                    for channel in grouped_channels[group_name]:
                        channel['new_number'] = new_number
                        new_number += 1
                        sorted_channels.append(channel)
                    del grouped_channels[group_name]
            
            # Оставшиеся группы
            for group_name in sorted(grouped_channels.keys()):
                for channel in grouped_channels[group_name]:
                    channel['new_number'] = new_number
                    new_number += 1
                    sorted_channels.append(channel)
            
            self.sorted_channels = sorted_channels
            
            # Показываем результат
            self.show_channels_in_table(self.sorted_channels, show_sorted_info=True)
            
            self.btn_save.setEnabled(True)
            self.statusBar().showMessage("Сортировка завершена")
            
            # Статистика сортировки
            sorted_groups = set(ch.get('group', 'Без группы') for ch in self.sorted_channels)
            
            self.log_message(f"Сортировка завершена")
            self.log_message(f"Обработано групп: {len(sorted_groups)}")
            
            # Обновляем статистику
            self.update_sort_stats()
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", 
                f"Ошибка при сортировке:\n{str(e)}")
            self.log_message(f"Ошибка сортировки: {str(e)}")
    
    def update_sort_stats(self):
        """Обновление статистики после сортировки"""
        if not self.sorted_channels:
            return
            
        # Подсчитываем изменения позиций
        moved_up = 0
        moved_down = 0
        same_position = 0
        
        # Подсчитываем каналы с ссылками и без
        channels_with_url = 0
        channels_without_url = 0
        
        for channel in self.sorted_channels:
            change = channel['new_number'] - channel['original_number']
            if change < 0:
                moved_up += 1
            elif change > 0:
                moved_down += 1
            else:
                same_position += 1
            
            if channel.get('url'):
                channels_with_url += 1
            else:
                channels_without_url += 1
        
        stats_text = f"Каналов: {len(self.sorted_channels)} "
        stats_text += f"(с ссылкой: {channels_with_url}, без ссылки: {channels_without_url}) | "
        stats_text += f"Поднялось: {moved_up} | "
        stats_text += f"Опустилось: {moved_down} | "
        stats_text += f"Без изменений: {same_position}"
        
        self.stats_label.setText(stats_text)
    
    def save_file(self):
        """Сохранение отсортированного плейлиста"""
        if not self.sorted_channels:
            return
            
        last_dir = self.settings.value("last_dir", "")
        default_name = ""
        if self.current_file:
            default_name = f"sorted_{self.current_file.name}"
            
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить отсортированный M3U файл", 
            str(Path(last_dir) / default_name),
            "M3U Files (*.m3u *.m3u8);;Все файлы (*.*)"
        )
        
        if file_path:
            try:
                # Создаем содержимое файла
                content = ['#EXTM3U']
                
                for channel in self.sorted_channels:
                    # Сохраняем оригинальную строку EXTINF
                    content.append(channel['extinf'])
                    
                    # Добавляем URL, если он есть
                    url = channel.get('url', '')
                    if url:
                        content.append(url)
                    else:
                        # Если URL нет, добавляем пустую строку или комментарий
                        content.append('# NO_URL')
                
                # Сохраняем файл
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(content))
                
                # Обновляем информацию
                save_path = Path(file_path)
                self.statusBar().showMessage(f"Файл сохранен: {save_path}")
                
                self.log_message(f"Файл сохранен: {save_path.name}")
                
                QMessageBox.information(self, 'Сохранение завершено',
                    f'Файл успешно сохранен:\n{save_path}')
                
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", 
                    f"Не удалось сохранить файл:\n{str(e)}")
                self.log_message(f"Ошибка сохранения: {str(e)}")
    
    def export_stats(self):
        """Экспорт статистики сортировки в CSV"""
        if not self.sorted_channels:
            QMessageBox.warning(self, "Нет данных", "Нет данных для экспорта")
            return
            
        last_dir = self.settings.value("last_dir", "")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт статистики",
            str(Path(last_dir) / f"sorting_stats_{timestamp}.csv"),
            "CSV Files (*.csv);;All Files (*.*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    
                    # Заголовок
                    writer.writerow(['Статистика сортировки M3U плейлиста'])
                    writer.writerow(['Дата', datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                    writer.writerow(['Исходный файл', self.current_file.name if self.current_file else ''])
                    writer.writerow([])
                    
                    # Группировка по группам
                    groups_summary = {}
                    for channel in self.sorted_channels:
                        group = channel.get('group', 'Без группы')
                        if group not in groups_summary:
                            groups_summary[group] = {'total': 0, 'with_url': 0, 'without_url': 0}
                        
                        groups_summary[group]['total'] += 1
                        if channel.get('url'):
                            groups_summary[group]['with_url'] += 1
                        else:
                            groups_summary[group]['without_url'] += 1
                    
                    writer.writerow(['Группа', 'Всего каналов', 'С ссылкой', 'Без ссылки'])
                    for group, stats in sorted(groups_summary.items()):
                        writer.writerow([group, stats['total'], stats['with_url'], stats['without_url']])
                    
                    writer.writerow([])
                    writer.writerow(['Всего каналов:', len(self.sorted_channels)])
                    writer.writerow(['Каналов с ссылкой:', sum(1 for ch in self.sorted_channels if ch.get('url'))])
                    writer.writerow(['Каналов без ссылки:', sum(1 for ch in self.sorted_channels if not ch.get('url'))])
                    writer.writerow(['Всего групп:', len(groups_summary)])
                    
                self.log_message(f"Статистика экспортирована: {Path(file_path).name}")
                QMessageBox.information(self, "Экспорт завершен", 
                                      "Статистика успешно экспортирована")
                
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка экспорта: {str(e)}")
    
    def edit_groups_order(self):
        """Диалог редактирования порядка групп"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Редактирование порядка групп")
        dialog.resize(400, 500)
        
        layout = QVBoxLayout(dialog)
        
        list_widget = QListWidget()
        list_widget.addItems(self.groups_order)
        list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        layout.addWidget(list_widget)
        
        # Кнопки управления
        button_layout = QHBoxLayout()
        
        btn_up = QPushButton("↑ Вверх")
        btn_up.clicked.connect(lambda: self.move_list_item(list_widget, -1))
        button_layout.addWidget(btn_up)
        
        btn_down = QPushButton("↓ Вниз")
        btn_down.clicked.connect(lambda: self.move_list_item(list_widget, 1))
        button_layout.addWidget(btn_down)
        
        button_layout.addStretch()
        
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(dialog.accept)
        button_layout.addWidget(btn_ok)
        
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(dialog.reject)
        button_layout.addWidget(btn_cancel)
        
        layout.addLayout(button_layout)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Сохраняем новый порядок
            self.groups_order = []
            for i in range(list_widget.count()):
                self.groups_order.append(list_widget.item(i).text())
            
            self.settings.setValue("groups_order", self.groups_order)
            self.log_message("Порядок групп обновлен")
    
    def move_list_item(self, list_widget, direction):
        """Перемещение элемента в списке"""
        current_row = list_widget.currentRow()
        if current_row < 0:
            return
            
        new_row = current_row + direction
        if 0 <= new_row < list_widget.count():
            current_item = list_widget.takeItem(current_row)
            list_widget.insertItem(new_row, current_item)
            list_widget.setCurrentRow(new_row)
    
    def show_context_menu(self, position):
        """Показ контекстного меню"""
        selected_rows = self.channels_table.selectionModel().selectedRows()
        if not selected_rows:
            return
            
        menu = QMenu()
        
        copy_name_action = menu.addAction("Копировать название")
        copy_url_action = menu.addAction("Копировать URL")
        menu.addSeparator()
        edit_group_action = menu.addAction("Изменить группу")
        edit_url_action = menu.addAction("Изменить/добавить URL")
        
        action = menu.exec(self.channels_table.mapToGlobal(position))
        
        if action == copy_name_action:
            self.copy_cell_to_clipboard(2)  # Столбец с названием
        elif action == copy_url_action:
            if self.sorted_channels:
                self.copy_cell_to_clipboard(4)  # Столбец с URL для отсортированных
            else:
                self.copy_cell_to_clipboard(3)  # Столбец с URL для неотсортированных
        elif action == edit_group_action:
            self.edit_channel_group()
        elif action == edit_url_action:
            self.edit_channel_url()
    
    def copy_cell_to_clipboard(self, column):
        """Копирование ячейки в буфер обмена"""
        selected_items = self.channels_table.selectedItems()
        if selected_items:
            # Находим первую ячейку в выбранном столбце
            for item in selected_items:
                if item.column() == column:
                    text = item.text()
                    QApplication.clipboard().setText(text)
                    self.statusBar().showMessage("Скопировано в буфер обмена", 2000)
                    break
    
    def edit_channel_group(self):
        """Изменение группы выбранного канала"""
        selected_rows = self.channels_table.selectionModel().selectedRows()
        if not selected_rows:
            return
            
        row = selected_rows[0].row()
        
        # Определяем индекс столбца группы в зависимости от режима
        group_col = 3 if self.sorted_channels else 2
        
        # Получаем текущую группу
        current_group = self.channels_table.item(row, group_col).text()
        
        # Диалог изменения группы
        dialog = QDialog(self)
        dialog.setWindowTitle("Изменение группы")
        dialog.setModal(True)
        
        layout = QVBoxLayout(dialog)
        
        layout.addWidget(QLabel("Название группы:"))
        
        group_input = QLineEdit()
        group_input.setText(current_group)
        layout.addWidget(group_input)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | 
                                     QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_group = group_input.text().strip()
            if new_group and new_group != current_group:
                # Обновляем в таблице
                self.channels_table.item(row, group_col).setText(new_group)
                
                # Определяем, в каком списке обновлять
                channels_list = self.sorted_channels if self.sorted_channels else self.original_channels
                
                if channels_list and row < len(channels_list):
                    channels_list[row]['group'] = new_group
                    # Обновляем строку EXTINF
                    extinf = channels_list[row]['extinf']
                    if 'group-title=' in extinf:
                        # Заменяем старое значение группы
                        new_extinf = re.sub(r'group-title="[^"]*"', f'group-title="{new_group}"', extinf)
                        channels_list[row]['extinf'] = new_extinf
                    else:
                        # Добавляем параметр группы
                        self.sorted_channels[row]['extinf'] = extinf.replace('#EXTINF:', f'#EXTINF: group-title="{new_group}"')
                
                self.log_message(f"Группа канала изменена: {current_group} → {new_group}")
    
    def edit_channel_url(self):
        """Изменение или добавление URL выбранного канала"""
        selected_rows = self.channels_table.selectionModel().selectedRows()
        if not selected_rows:
            return
            
        row = selected_rows[0].row()
        
        # Определяем индекс столбца URL в зависимости от режима
        url_col = 4 if self.sorted_channels else 3
        
        # Получаем текущий URL
        current_url_item = self.channels_table.item(row, url_col)
        current_url = ""
        if current_url_item:
            current_url = current_url_item.text()
            if current_url == "Нет ссылки":
                current_url = ""
        
        # Диалог изменения URL
        dialog = QDialog(self)
        dialog.setWindowTitle("Изменение URL")
        dialog.setModal(True)
        dialog.resize(500, 200)
        
        layout = QVBoxLayout(dialog)
        
        layout.addWidget(QLabel("URL канала:"))
        
        url_input = QTextEdit()
        url_input.setText(current_url)
        url_input.setMaximumHeight(80)
        layout.addWidget(url_input)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | 
                                     QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_url = url_input.toPlainText().strip()
            
            # Обновляем в таблице
            if new_url:
                current_url_item.setText(new_url)
                current_url_item.setForeground(QColor(0, 0, 0))  # Черный цвет для каналов с ссылкой
            else:
                current_url_item.setText("Нет ссылки")
                current_url_item.setForeground(QColor(255, 0, 0))  # Красный цвет для каналов без ссылки
            
            # Определяем, в каком списке обновлять
            channels_list = self.sorted_channels if self.sorted_channels else self.original_channels
            
            if channels_list and row < len(channels_list):
                channels_list[row]['url'] = new_url
            
            self.log_message(f"URL канала обновлен")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("M3U Playlist Sorter")
    app.setOrganizationName("M3USorter")
    
    window = M3USorter()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
