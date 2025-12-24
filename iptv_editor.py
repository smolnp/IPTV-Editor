"""
Редактор IPTV листов
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, Menu
import os
import re
from pathlib import Path
import json
from typing import List, Dict, Optional, Set, Tuple
import ctypes
import sys
import winreg
import webbrowser
from urllib.parse import urlparse
import threading
import logging
from logging.handlers import RotatingFileHandler
import time
import hashlib
import io
import base64
import warnings
import urllib3
import shutil

# Отключаем предупреждения urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Проверяем наличие дополнительных библиотек
REQUESTS_AVAILABLE = False
PIL_AVAILABLE = False
TKDND_AVAILABLE = False

try:
    import requests
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
    REQUESTS_AVAILABLE = True
except ImportError:
    pass

try:
    from PIL import Image, ImageTk, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    pass

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    TKDND_AVAILABLE = True
except ImportError:
    try:
        import tkinterdnd2
        from tkinterdnd2 import DND_FILES, TkinterDnD
        TKDND_AVAILABLE = True
    except ImportError:
        pass


class AppLogger:
    """Класс для настройки логирования приложения"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._setup_logging()
        return cls._instance
    
    def _setup_logging(self):
        """Настройка системы логирования"""
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        self.logger = logging.getLogger("IPTVEditor")
        self.logger.setLevel(logging.INFO)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "iptv_editor.log"),
            maxBytes=5*1024*1024,
            backupCount=3,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        self.logger.info("Логирование инициализировано")
    
    def get_logger(self):
        """Получить экземпляр логгера"""
        return self.logger


try:
    logger = AppLogger().get_logger()
except:
    logging.basicConfig(level=logging.WARNING, 
                       format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger("IPTVEditor")


class ChannelData:
    """Структура данных канала"""
    def __init__(self):
        self.name = ""
        self.group = ""
        self.tvg_id = ""
        self.tvg_logo = ""
        self.url = ""
        self.extinf = ""
        self.has_url = True
        self.url_status = None
        self.url_check_time = None
        self._hash = None
        self.logo_image = None
    
    def __hash__(self):
        if self._hash is None:
            self._hash = hash((self.name, self.url, self.group))
        return self._hash
    
    def __eq__(self, other):
        if not isinstance(other, ChannelData):
            return False
        return (self.name == other.name and 
                self.url == other.url and 
                self.group == other.group)


class ImageManager:
    """Менеджер для загрузки и кэширования изображений логотипов"""
    
    def __init__(self, max_cache_size=48):
        self.max_cache_size = max_cache_size
        self.image_cache = {}
        self.access_times = {}
        self.default_logo = None
        self._create_default_logo()
    
    def _create_default_logo(self):
        """Создание логотипа по умолчанию"""
        try:
            img = Image.new('RGB', (48, 48), color='lightgray')
            draw = ImageDraw.Draw(img)
            draw.rectangle([2, 2, 46, 46], outline='gray', width=2)
            draw.text((24, 24), "TV", fill='darkgray', anchor='mm')
            self.default_logo = ImageTk.PhotoImage(img)
        except:
            self.default_logo = None
    
    def load_logo(self, url, max_size=(48, 48)):
        """Загрузка логотипа из URL с кэшированием"""
        if not url or not url.strip():
            return self.default_logo
        
        cache_key = f"{url}_{max_size[0]}x{max_size[1]}"
        
        if cache_key in self.image_cache:
            self.access_times[cache_key] = time.time()
            return self.image_cache[cache_key]
        
        try:
            if len(self.image_cache) >= self.max_cache_size:
                oldest_key = min(self.access_times, key=self.access_times.get)
                del self.image_cache[oldest_key]
                del self.access_times[oldest_key]
            
            if PIL_AVAILABLE:
                if url.startswith(('http://', 'https://')):
                    if REQUESTS_AVAILABLE:
                        response = requests.get(url, timeout=3, stream=True, verify=False)
                        response.raise_for_status()
                        img_data = response.content
                    else:
                        return self.default_logo
                elif url.startswith('data:image'):
                    header, data = url.split(',', 1)
                    img_data = base64.b64decode(data)
                else:
                    with open(url, 'rb') as f:
                        img_data = f.read()
                
                img = Image.open(io.BytesIO(img_data))
                
                if img.mode == 'RGBA':
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3])
                    img = background
                
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                
                self.image_cache[cache_key] = photo
                self.access_times[cache_key] = time.time()
                
                return photo
                
        except Exception as e:
            logger.debug(f"Ошибка загрузки логотипа {url}: {e}")
        
        return self.default_logo
    
    def clear_cache(self):
        """Очистка кэша изображений"""
        self.image_cache.clear()
        self.access_times.clear()
        logger.info("Кэш изображений очищен")


class DragDropManager:
    """Менеджер для обработки Drag & Drop"""
    
    def __init__(self, root, callback):
        self.root = root
        self.callback = callback
        self.drop_targets = []
        
        if TKDND_AVAILABLE:
            self._setup_drag_drop()
    
    def _setup_drag_drop(self):
        """Настройка обработки Drag & Drop"""
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind('<<Drop>>', self._on_drop)
        self.root.dnd_bind('<<DropEnter>>', self._on_drop_enter)
        self.root.dnd_bind('<<DropLeave>>', self._on_drop_leave)
    
    def add_drop_target(self, widget, callback=None):
        """Добавление виджета как цели для drop"""
        if not TKDND_AVAILABLE:
            return
        
        widget.drop_target_register(DND_FILES)
        
        def handle_drop(event):
            files = self._parse_drop_data(event.data)
            if files and (callback or self.callback):
                target_callback = callback or self.callback
                target_callback(files)
        
        widget.dnd_bind('<<Drop>>', handle_drop)
        self.drop_targets.append(widget)
    
    def _parse_drop_data(self, data):
        """Парсинг данных из drop события"""
        files = []
        if isinstance(data, str):
            data = data.strip('{}')
            file_list = data.split('} {')
            files = [f.strip() for f in file_list if f.strip()]
        elif isinstance(data, list):
            files = data
        return files
    
    def _on_drop(self, event):
        """Обработка drop на главном окне"""
        files = self._parse_drop_data(event.data)
        if files and self.callback:
            self.callback(files)
    
    def _on_drop_enter(self, event):
        """Визуальная обратная связь при входе в зону drop"""
        self.root.config(cursor='hand2')
    
    def _on_drop_leave(self, event):
        """Визуальная обратная связь при выходе из зоны drop"""
        self.root.config(cursor='')


class ColumnManager:
    """Менеджер для управления колонками таблицы"""
    
    DEFAULT_COLUMNS = [
        ("number", "№", 50, True),
        ("name", "Название", 300, True),
        ("group", "Группа", 150, True),
        ("url", "URL", 500, True)
    ]
    
    def __init__(self):
        self.columns = self.load_columns()
        self.column_order = [col[0] for col in self.columns if col[3]]
    
    def load_columns(self):
        """Загрузка настроек колонок из файла"""
        config_file = "column_settings.json"
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    saved_columns = json.load(f)
                    valid_columns = []
                    for col in saved_columns:
                        if len(col) >= 4:
                            valid_columns.append(tuple(col))
                    if valid_columns:
                        return valid_columns
            except Exception as e:
                logger.error(f"Ошибка загрузки настроек колонок: {e}")
        
        return self.DEFAULT_COLUMNS.copy()
    
    def save_columns(self):
        """Сохранение настроек колонок в файл"""
        try:
            with open("column_settings.json", 'w', encoding='utf-8') as f:
                json.dump(self.columns, f, ensure_ascii=False)
            logger.info("Настройки колонок сохранены")
        except Exception as e:
            logger.error(f"Ошибка сохранения настроек колонок: {e}")
    
    def get_visible_columns(self):
        """Получение видимых колонок"""
        return [col for col in self.columns if col[3]]
    
    def set_column_visibility(self, column_id, visible):
        """Установка видимости колонки"""
        for i, col in enumerate(self.columns):
            if col[0] == column_id:
                self.columns[i] = (col[0], col[1], col[2], visible)
                break
        
        self.column_order = [col[0] for col in self.columns if col[3]]
        self.save_columns()
    
    def reset_to_default(self):
        """Сброс к настройкам по умолчанию"""
        self.columns = self.DEFAULT_COLUMNS.copy()
        self.column_order = [col[0] for col in self.columns if col[3]]
        self.save_columns()
        logger.info("Настройки колонок сброшены на заводские")


class SmartCacheManager:
    """Умный кэш-менеджер с TTL и LRU политикой"""
    
    def __init__(self, max_size=1000, default_ttl=300):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache = {}
        self._access_times = {}
        self._creation_times = {}
    
    def get(self, key):
        """Получение значения с проверкой TTL"""
        if key in self._cache:
            if time.time() - self._creation_times[key] > self._cache[key].get('ttl', self.default_ttl):
                self.delete(key)
                return None
            
            self._access_times[key] = time.time()
            return self._cache[key]['value']
        return None
    
    def set(self, key, value, ttl=None):
        """Установка значения с TTL"""
        self._cleanup_expired()
        
        if len(self._cache) >= self.max_size:
            self._evict_lru()
        
        self._cache[key] = {
            'value': value,
            'ttl': ttl or self.default_ttl
        }
        self._access_times[key] = time.time()
        self._creation_times[key] = time.time()
    
    def delete(self, key):
        """Удаление значения из кэша"""
        if key in self._cache:
            del self._cache[key]
            del self._access_times[key]
            del self._creation_times[key]
    
    def _cleanup_expired(self):
        """Очистка просроченных записей"""
        current_time = time.time()
        expired_keys = []
        
        for key, cache_item in self._cache.items():
            if current_time - self._creation_times[key] > cache_item['ttl']:
                expired_keys.append(key)
        
        for key in expired_keys:
            self.delete(key)
    
    def _evict_lru(self):
        """Удаление наименее используемых записей"""
        if not self._access_times:
            return
        
        lru_count = max(1, len(self._cache) // 10)
        sorted_keys = sorted(self._access_times.items(), key=lambda x: x[1])
        
        for key, _ in sorted_keys[:lru_count]:
            self.delete(key)
    
    def clear(self):
        """Очистить кэш"""
        self._cache.clear()
        self._access_times.clear()
        self._creation_times.clear()
        logger.info("Кэш очищен")
    
    def size(self):
        """Получить размер кэша"""
        return len(self._cache)


class BulkOperations:
    """Класс для групповых операций с каналами"""
    
    def __init__(self, playlist_tab):
        self.tab = playlist_tab
        self.manager = playlist_tab.manager
    
    def show_bulk_operations_dialog(self):
        """Диалог групповых операций"""
        dialog = tk.Toplevel(self.manager.root)
        dialog.title("Групповые операции")
        dialog.geometry("500x600")
        dialog.transient(self.manager.root)
        dialog.grab_set()
        
        font_settings = self.manager.font_settings
        
        main_frame = ttk.Frame(dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main_frame, text="Групповые операции", 
                 font=font_settings['title_font']).pack(pady=(0, 15))
        
        selected_count = len(self.tab.tree.selection())
        total_count = len(self.tab.filtered_data)
        
        stats_text = f"Выбрано: {selected_count} из {total_count} каналов"
        stats_label = ttk.Label(main_frame, text=stats_text, 
                               font=font_settings['caption_font'])
        stats_label.pack(pady=10)
        
        operations_frame = ttk.LabelFrame(main_frame, text="Операции", padding="15")
        operations_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        group_frame = ttk.Frame(operations_frame)
        group_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(group_frame, text="Изменить группу на:", 
                 font=font_settings['small_font']).pack(side=tk.LEFT, padx=(0, 10))
        
        new_group_var = tk.StringVar()
        group_entry = ttk.Entry(group_frame, textvariable=new_group_var, width=20)
        group_entry.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(group_frame, text="Применить", 
                  command=lambda: self.bulk_change_group(new_group_var.get(), dialog),
                  style="Small.TButton").pack(side=tk.LEFT)
        
        name_frame = ttk.Frame(operations_frame)
        name_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(name_frame, text="Изменить названия:", 
                 font=font_settings['small_font']).pack(anchor='w')
        
        prefix_frame = ttk.Frame(name_frame)
        prefix_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(prefix_frame, text="Префикс:", 
                 font=font_settings['small_font']).pack(side=tk.LEFT, padx=(0, 10))
        
        prefix_var = tk.StringVar()
        prefix_entry = ttk.Entry(prefix_frame, textvariable=prefix_var, width=15)
        prefix_entry.pack(side=tk.LEFT, padx=(0, 20))
        
        ttk.Label(prefix_frame, text="Суффикс:", 
                 font=font_settings['small_font']).pack(side=tk.LEFT, padx=(0, 10))
        
        suffix_var = tk.StringVar()
        suffix_entry = ttk.Entry(prefix_frame, textvariable=suffix_var, width=15)
        suffix_entry.pack(side=tk.LEFT)
        
        ttk.Button(prefix_frame, text="Применить", 
                  command=lambda: self.bulk_change_names(prefix_var.get(), suffix_var.get(), dialog),
                  style="Small.TButton").pack(side=tk.RIGHT)
        
        copy_frame = ttk.Frame(operations_frame)
        copy_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(copy_frame, text="Копировать из первого выбранного:", 
                 font=font_settings['small_font']).pack(anchor='w')
        
        copy_btn_frame = ttk.Frame(copy_frame)
        copy_btn_frame.pack(pady=5)
        
        ttk.Button(copy_btn_frame, text="TVG-ID", 
                  command=lambda: self.bulk_copy_field('tvg_id', dialog),
                  style="Small.TButton").pack(side=tk.LEFT, padx=5)
        
        ttk.Button(copy_btn_frame, text="Логотип", 
                  command=lambda: self.bulk_copy_field('tvg_logo', dialog),
                  style="Small.TButton").pack(side=tk.LEFT, padx=5)
        
        comment_frame = ttk.Frame(operations_frame)
        comment_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(comment_frame, text="Включить/выключить каналы:", 
                 font=font_settings['small_font']).pack(anchor='w')
        
        comment_btn_frame = ttk.Frame(comment_frame)
        comment_btn_frame.pack(pady=5)
        
        ttk.Button(comment_btn_frame, text="Включить", 
                  command=lambda: self.bulk_toggle_channels(True, dialog),
                  style="Small.TButton").pack(side=tk.LEFT, padx=5)
        
        ttk.Button(comment_btn_frame, text="Выключить", 
                  command=lambda: self.bulk_toggle_channels(False, dialog),
                  style="Small.TButton").pack(side=tk.LEFT, padx=5)
        
        delete_frame = ttk.Frame(operations_frame)
        delete_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(delete_frame, text="🗑️ Удалить выбранные", 
                  command=lambda: self.bulk_delete_channels(dialog),
                  style="Large.TButton").pack()
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=20)
        
        ttk.Button(button_frame, text="Выбрать все", 
                  command=self.select_all_channels,
                  style="Medium.TButton").pack(side=tk.LEFT, padx=10)
        
        ttk.Button(button_frame, text="Снять выделение", 
                  command=self.deselect_all_channels,
                  style="Medium.TButton").pack(side=tk.LEFT, padx=10)
        
        ttk.Button(button_frame, text="Закрыть", 
                  command=dialog.destroy,
                  style="Medium.TButton").pack(side=tk.LEFT, padx=10)
    
    def get_selected_channels(self):
        """Получение выбранных каналов"""
        selected_items = self.tab.tree.selection()
        channels = []
        
        for item in selected_items:
            channel = self.tab.get_channel_for_item(item)
            if channel:
                channels.append(channel)
        
        return channels
    
    def bulk_change_group(self, new_group, dialog):
        """Групповое изменение группы"""
        selected_channels = self.get_selected_channels()
        if not selected_channels:
            messagebox.showwarning("Предупреждение", "Выберите каналы для изменения")
            return
        
        if not new_group.strip():
            messagebox.showwarning("Предупреждение", "Введите название группы")
            return
        
        action = self.tab.history.start_action(
            "bulk_change_group", 
            f"Групповое изменение группы на '{new_group}' для {len(selected_channels)} каналов"
        )
        
        for channel in selected_channels:
            old_group = channel.group
            channel.group = new_group
            self._update_extinf(channel)
            self.tab.history.add_change(
                "group_change",
                old_group,
                new_group,
                channel.name
            )
        
        self.tab.history.commit_action()
        self.tab._group_cache = None
        self.tab._search_cache = {}
        self.tab.filter_channels()
        
        dialog.destroy()
        self.manager.update_status(f"✅ Группа изменена для {len(selected_channels)} каналов")
    
    def bulk_change_names(self, prefix, suffix, dialog):
        """Групповое изменение названий"""
        selected_channels = self.get_selected_channels()
        if not selected_channels:
            messagebox.showwarning("Предупреждение", "Выберите каналы для изменения")
            return
        
        if not prefix and not suffix:
            messagebox.showwarning("Предупреждение", "Введите префикс и/или суффикс")
            return
        
        action = self.tab.history.start_action(
            "bulk_change_names", 
            f"Групповое изменение названий для {len(selected_channels)} каналов"
        )
        
        for channel in selected_channels:
            old_name = channel.name
            new_name = channel.name
            if prefix:
                new_name = prefix + new_name
            if suffix:
                new_name = new_name + suffix
            
            channel.name = new_name
            self._update_extinf(channel)
            self.tab.history.add_change(
                "name_change",
                old_name,
                new_name,
                f"{old_name} -> {new_name}"
            )
        
        self.tab.history.commit_action()
        self.tab.filter_channels()
        
        dialog.destroy()
        self.manager.update_status(f"✅ Названия изменены для {len(selected_channels)} каналов")
    
    def bulk_copy_field(self, field_name, dialog):
        """Копирование поля из первого выбранного канала в остальные"""
        selected_channels = self.get_selected_channels()
        if len(selected_channels) < 2:
            messagebox.showwarning("Предупреждение", "Выберите минимум 2 канала")
            return
        
        source_channel = selected_channels[0]
        source_value = getattr(source_channel, field_name)
        
        action = self.tab.history.start_action(
            f"bulk_copy_{field_name}", 
            f"Копирование {field_name} для {len(selected_channels)-1} каналов"
        )
        
        for channel in selected_channels[1:]:
            old_value = getattr(channel, field_name)
            setattr(channel, field_name, source_value)
            
            if field_name in ['tvg_id', 'tvg_logo']:
                self._update_extinf(channel)
            
            self.tab.history.add_change(
                f"{field_name}_change",
                old_value,
                source_value,
                channel.name
            )
        
        self.tab.history.commit_action()
        self.tab.filter_channels()
        
        dialog.destroy()
        self.manager.update_status(f"✅ {field_name} скопирован для {len(selected_channels)-1} каналов")
    
    def bulk_toggle_channels(self, enable, dialog):
        """Включение/выключение каналов через комментарии"""
        selected_channels = self.get_selected_channels()
        if not selected_channels:
            messagebox.showwarning("Предупреждение", "Выберите каналы для изменения")
            return
        
        action_name = "Включение" if enable else "Выключение"
        
        action = self.tab.history.start_action(
            "bulk_toggle_channels", 
            f"{action_name} {len(selected_channels)} каналов"
        )
        
        for channel in selected_channels:
            old_extinf = channel.extinf
            
            if enable:
                if channel.extinf.startswith('#'):
                    channel.extinf = channel.extinf[1:]
            else:
                if not channel.extinf.startswith('#'):
                    channel.extinf = '#' + channel.extinf
            
            if old_extinf != channel.extinf:
                self.tab.history.add_change(
                    "toggle_channel",
                    old_extinf,
                    channel.extinf,
                    channel.name
                )
        
        self.tab.history.commit_action()
        self.tab.filter_channels()
        
        dialog.destroy()
        self.manager.update_status(f"✅ {action_name} {len(selected_channels)} каналов")
    
    def bulk_delete_channels(self, dialog):
        """Удаление выбранных каналов"""
        selected_channels = self.get_selected_channels()
        if not selected_channels:
            messagebox.showwarning("Предупреждение", "Выберите каналы для удаления")
            return
        
        if not messagebox.askyesno("Подтверждение", 
                                 f"Удалить {len(selected_channels)} выбранных каналов?"):
            return
        
        action = self.tab.history.start_action(
            "bulk_delete_channels", 
            f"Удаление {len(selected_channels)} каналов"
        )
        
        for channel in selected_channels:
            if channel in self.tab.playlist_data:
                self.tab.playlist_data.remove(channel)
            
            self.tab.history.add_change(
                "channel_delete",
                channel,
                None,
                f"{channel.name} ({channel.group})"
            )
        
        self.tab.history.commit_action()
        self.tab._group_cache = None
        self.tab._search_cache = {}
        self.tab.filter_channels()
        
        dialog.destroy()
        self.manager.update_status(f"✅ Удалено {len(selected_channels)} каналов")
    
    def select_all_channels(self):
        """Выделение всех каналов в таблице"""
        items = self.tab.tree.get_children()
        self.tab.tree.selection_set(items)
        
        for item in items:
            channel = self.tab.get_channel_for_item(item)
            if not channel:
                self.tab.tree.selection_remove(item)
    
    def deselect_all_channels(self):
        """Снятие выделения со всех каналов"""
        self.tab.tree.selection_remove(self.tab.tree.selection())
    
    def _update_extinf(self, channel):
        """Обновление строки EXTINF для канала"""
        extinf_parts = ["#EXTINF:-1"]
        if channel.tvg_id:
            extinf_parts.append(f'tvg-id="{channel.tvg_id}"')
        if channel.tvg_logo:
            extinf_parts.append(f'tvg-logo="{channel.tvg_logo}"')
        if channel.group:
            extinf_parts.append(f'group-title="{channel.group}"')
        extinf_parts.append(f',{channel.name}')
        channel.extinf = ' '.join(extinf_parts)


class HistoryManager:
    """Менеджер истории изменений"""
    
    def __init__(self, max_history=50):
        self.history = []
        self.redo_stack = []
        self.max_history = max_history
        self.current_action = None
    
    def start_action(self, action_type, description):
        """Начало нового действия"""
        self.current_action = {
            'type': action_type,
            'description': description,
            'timestamp': time.time(),
            'data': {},
            'changes': []
        }
        return self.current_action
    
    def add_change(self, change_type, old_value, new_value, target=None):
        """Добавление изменения в текущее действие"""
        if self.current_action:
            change = {
                'type': change_type,
                'old_value': old_value,
                'new_value': new_value,
                'target': target,
                'timestamp': time.time()
            }
            self.current_action['changes'].append(change)
    
    def commit_action(self):
        """Завершение и сохранение действия"""
        if self.current_action and self.current_action['changes']:
            self.history.append(self.current_action)
            self.redo_stack.clear()
            
            if len(self.history) > self.max_history:
                self.history.pop(0)
            
            action = self.current_action
            logger.info(f"История: {action['description']} - {len(action['changes'])} изменений")
            
        self.current_action = None
    
    def cancel_action(self):
        """Отмена текущего действия"""
        self.current_action = None
    
    def undo(self):
        """Отмена последнего действия"""
        if not self.history:
            return None
        
        action = self.history.pop()
        self.redo_stack.append(action)
        
        logger.info(f"Отменено: {action['description']}")
        return action
    
    def redo(self):
        """Повтор последнего отмененного действия"""
        if not self.redo_stack:
            return None
        
        action = self.redo_stack.pop()
        self.history.append(action)
        
        logger.info(f"Повторено: {action['description']}")
        return action
    
    def clear(self):
        """Очистка истории"""
        self.history.clear()
        self.redo_stack.clear()
        logger.info("История очищена")


class WindowsFontSettings:
    """Класс для получения настроек шрифтов из реестра Windows"""
    
    @staticmethod
    def get_system_font_settings():
        """Получение настроек системных шрифтов из реестра"""
        settings = {
            'caption_font': ('Segoe UI', 10),
            'menu_font': ('Segoe UI', 10),
            'message_font': ('Segoe UI', 10),
            'status_font': ('Segoe UI', 10),
            'icon_font': ('Segoe UI', 10)
        }
        
        try:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                                  r"Control Panel\Desktop", 
                                  0, winreg.KEY_READ) as key:
                    try:
                        log_pixels, _ = winreg.QueryValueEx(key, "LogPixels")
                        base_size = 10
                        if log_pixels > 96:
                            base_size = int(base_size * (log_pixels / 96))
                        settings['base_size'] = base_size
                    except:
                        settings['base_size'] = 11
            except:
                settings['base_size'] = 11
            
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                                  r"Software\Microsoft\Windows NT\CurrentVersion\Fonts", 
                                  0, winreg.KEY_READ) as key:
                    try:
                        value, _ = winreg.QueryValueEx(key, "Segoe UI (TrueType)")
                        font_family = "Segoe UI" if value else "Tahoma"
                    except:
                        font_family = "Segoe UI"
            except:
                font_family = "Segoe UI"
            
            base_size = settings.get('base_size', 11)
            
            settings.update({
                'caption_font': (font_family, base_size),
                'menu_font': (font_family, base_size),
                'message_font': (font_family, base_size),
                'status_font': (font_family, base_size),
                'icon_font': (font_family, base_size),
                'title_font': (font_family, base_size + 1, 'bold'),
                'heading_font': (font_family, base_size, 'bold'),
                'tree_font': (font_family, base_size),
                'tree_heading_font': (font_family, base_size, 'bold'),
                'dialog_font': (font_family, base_size),
                'small_font': (font_family, base_size - 1),
            })
            
        except Exception as e:
            logger.error(f"Ошибка получения настроек шрифтов: {e}")
            settings.update({
                'caption_font': ('Segoe UI', 12),
                'menu_font': ('Segoe UI', 12),
                'message_font': ('Segoe UI', 12),
                'status_font': ('Segoe UI', 12),
                'icon_font': ('Segoe UI', 12),
                'title_font': ('Segoe UI', 13, 'bold'),
                'heading_font': ('Segoe UI', 12, 'bold'),
                'tree_font': ('Segoe UI', 12),
                'tree_heading_font': ('Segoe UI', 12, 'bold'),
                'dialog_font': ('Segoe UI', 12),
                'small_font': ('Segoe UI', 11),
                'base_size': 12
            })
        
        return settings


class PlaylistValidator:
    """Класс для валидации плейлистов"""
    
    @staticmethod
    def validate_playlist(playlist_data):
        """Валидация всего плейлиста"""
        errors = []
        warnings = []
        stats = {
            'total_channels': len(playlist_data),
            'channels_with_url': 0,
            'channels_without_url': 0,
            'duplicate_urls': 0,
            'duplicate_names': 0,
            'long_names': 0,
            'invalid_urls': 0,
            'empty_groups': 0
        }
        
        seen_urls = set()
        seen_names = set()
        
        for channel in playlist_data:
            if channel.has_url:
                stats['channels_with_url'] += 1
            else:
                stats['channels_without_url'] += 1
                warnings.append(f"Канал '{channel.name}' не имеет URL")
            
            if channel.url and channel.url in seen_urls:
                stats['duplicate_urls'] += 1
                warnings.append(f"Дубликат URL: '{channel.url[:50]}...' в канале '{channel.name}'")
            elif channel.url:
                seen_urls.add(channel.url)
            
            if channel.name in seen_names:
                stats['duplicate_names'] += 1
                warnings.append(f"Дубликат имени: '{channel.name}'")
            else:
                seen_names.add(channel.name)
            
            if len(channel.name) > 100:
                stats['long_names'] += 1
                warnings.append(f"Слишком длинное имя: '{channel.name[:50]}...'")
            
            if channel.url and not PlaylistValidator.validate_url(channel.url):
                stats['invalid_urls'] += 1
                errors.append(f"Неверный URL: '{channel.url[:50]}...' в канале '{channel.name}'")
            
            if not channel.group or channel.group.strip() == "":
                stats['empty_groups'] += 1
                warnings.append(f"Пустая группа у канала: '{channel.name}'")
        
        return {
            'errors': errors,
            'warnings': warnings,
            'stats': stats,
            'is_valid': len(errors) == 0
        }
    
    @staticmethod
    def validate_url(url):
        """Валидация одного URL"""
        if not url or not url.strip():
            return True
        
        patterns = [
            r'^(http|https|rtmp|rtsp|udp)://',
            r'^file://',
            r'^/[\w/.-]+$',
            r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+',
            r'^[a-zA-Z0-9.-]+:\d+',
        ]
        
        for pattern in patterns:
            if re.match(pattern, url):
                return True
        
        return False


class TextFieldContextMenu:
    """Универсальное контекстное меню для текстовых полей"""
    
    @staticmethod
    def create_context_menu(widget):
        menu = Menu(widget, tearoff=0)
        
        menu.add_command(label="Выделить всё", 
                        command=lambda: widget.select_range(0, tk.END))
        menu.add_separator()
        menu.add_command(label="Копировать", 
                        command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Вырезать", 
                        command=lambda: widget.event_generate("<<Cut>>"))
        menu.add_command(label="Вставить", 
                        command=lambda: widget.event_generate("<<Paste>>"))
        menu.add_command(label="Удалить", 
                        command=lambda: widget.delete(tk.SEL_FIRST, tk.SEL_LAST))
        menu.add_separator()
        menu.add_command(label="Отменить", 
                        command=lambda: widget.event_generate("<<Undo>>"))
        menu.add_command(label="Повторить", 
                        command=lambda: widget.event_generate("<<Redo>>"))
        
        return menu
    
    @staticmethod
    def bind_context_menu(widget):
        menu = TextFieldContextMenu.create_context_menu(widget)
        
        def show_menu(event):
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
        
        widget.bind("<Button-3>", show_menu)


class LinkChecker:
    """Класс для проверки ссылок на доступность"""
    
    def __init__(self, max_workers=5, timeout=3):
        self.max_workers = max_workers
        self.timeout = timeout
        if REQUESTS_AVAILABLE:
            self.session = requests.Session()
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            self.session.verify = False
        else:
            self.session = None
        self.cache = SmartCacheManager(max_size=500)
    
    def check_single_url(self, url):
        """Проверка одной ссылки"""
        if not url or not url.strip():
            return False, "Пустой URL"
        
        cache_key = f"url_check_{hashlib.md5(url.encode()).hexdigest()}"
        cached_result = self.cache.get(cache_key)
        if cached_result:
            return cached_result
        
        try:
            if url.startswith('file://') or '://' not in url:
                result = (True, "Локальный файл")
                self.cache.set(cache_key, result)
                return result
            
            if url.startswith(('rtmp://', 'rtsp://', 'udp://')):
                result = (True, "Потоковый протокол")
                self.cache.set(cache_key, result)
                return result
            
            if REQUESTS_AVAILABLE and self.session:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", InsecureRequestWarning)
                    response = self.session.head(
                        url, 
                        timeout=self.timeout,
                        allow_redirects=True,
                        verify=False
                    )
                
                if response.status_code < 400:
                    result = (True, f"Статус: {response.status_code}")
                else:
                    result = (False, f"Ошибка: {response.status_code}")
                
                self.cache.set(cache_key, result)
                return result
            else:
                result = (True, "Проверка формата")
                self.cache.set(cache_key, result)
                return result
                
        except Exception as e:
            result = (False, f"Ошибка: {str(e)}")
            self.cache.set(cache_key, result)
            return result


class AutoSaveManager:
    """Менеджер автоматического сохранения"""
    
    def __init__(self, tab, interval=300):
        self.tab = tab
        self.interval = interval * 1000
        self._save_job = None
        self.enabled = True
    
    def start(self):
        """Запуск автоматического сохранения"""
        self._schedule_save()
    
    def stop(self):
        """Остановка автоматического сохранения"""
        if self._save_job:
            self.tab.tab_frame.after_cancel(self._save_job)
            self._save_job = None
    
    def _schedule_save(self):
        """Планирование следующего сохранения"""
        if not self.enabled:
            return
        
        self._save_job = self.tab.tab_frame.after(
            self.interval, 
            self._perform_autosave
        )
    
    def _perform_autosave(self):
        """Выполнение автоматического сохранения"""
        try:
            if self.tab.file_path and not self.tab.file_path.startswith(('http://', 'https://')):
                if self.tab.has_unsaved_changes():
                    self.tab.save_to_file()
                    logger.info(f"Автосохранение: {self.tab.file_path}")
        
        except Exception as e:
            logger.error(f"Ошибка автосохранения: {e}")
        
        finally:
            if self.enabled:
                self._schedule_save()
    
    def has_unsaved_changes(self):
        """Проверка наличия несохраненных изменений"""
        return True


class PlaylistTab:
    """Класс для хранения данных вкладки"""
    
    def __init__(self, parent, manager, file_path=None):
        self.manager = manager
        self.parent = parent
        self.file_path = file_path
        self.playlist_data = []
        self.filtered_data = []
        self.epg_data = []
        self.history = HistoryManager()
        self._group_cache = None
        self._search_cache = {}
        self._row_to_channel = {}
        
        self.image_manager = ImageManager()
        self.bulk_ops = BulkOperations(self)
        self.column_manager = manager.column_manager
        self.current_channel = None
        self.auto_save_manager = AutoSaveManager(self)
        
        self.is_loading = False
        self.loading_thread = None
        self.loading_complete = False
        self.loading_error = None
        
        self._update_lock = threading.Lock()
        self._is_updating = False
        
        self.tab_frame = ttk.Frame(parent)
        self._create_interface()
        
        if file_path and os.path.exists(file_path):
            self.load_from_file_async(file_path)
        elif file_path and file_path.startswith(('http://', 'https://')):
            self.load_from_url_async(file_path)
        
        tab_name = self._get_tab_name(file_path)
        parent.add(self.tab_frame, text=tab_name)
        parent.select(self.tab_frame)
        
        if TKDND_AVAILABLE and hasattr(manager, 'drag_drop_manager'):
            manager.drag_drop_manager.add_drop_target(
                self.tab_frame, 
                self.handle_dropped_files
            )
        
        self.auto_save_manager.start()
    
    def handle_dropped_files(self, files):
        """Обработка перетащенных файлов"""
        if not files:
            return
        
        for file_path in files:
            if file_path.lower().endswith(('.m3u', '.m3u8')):
                self.load_from_file_async(file_path)
                self.manager.update_status(f"⏳ Загрузка файла: {os.path.basename(file_path)}...")
            elif file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp')):
                self._handle_dropped_image(file_path)
    
    def _handle_dropped_image(self, image_path):
        """Обработка перетащенного изображения"""
        if not self.current_channel:
            messagebox.showinfo("Информация", 
                              "Выберите канал для установки логотипа")
            return
        
        self.tvg_logo_var.set(image_path)
    
    def save_to_file(self, file_path=None):
        """Сохранение плейлиста в файл"""
        if file_path:
            self.file_path = file_path
        
        if not self.file_path:
            return False
        
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                f.write('#EXTM3U\n')
                for channel in self.playlist_data:
                    f.write(channel.extinf + '\n')
                    if channel.url:
                        f.write(channel.url + '\n')
                    else:
                        f.write('\n')
            
            tab_name = self._get_tab_name(self.file_path)
            index = self.parent.index(self.tab_frame)
            self.parent.tab(index, text=tab_name)
            
            logger.info(f"Плейлист сохранен в: {self.file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка сохранения файла {self.file_path}: {e}")
            messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{str(e)}")
            return False
    
    def _get_tab_name(self, file_path):
        if file_path:
            if file_path.startswith(('http://', 'https://')):
                parsed = urlparse(file_path)
                name = parsed.netloc
            else:
                name = os.path.basename(file_path)
        else:
            name = "Новый плейлист"
        
        if len(name) > 20:
            name = "..." + name[-17:]
        
        return name
    
    def _create_interface(self):
        font_settings = self.manager.font_settings
        
        self.control_frame = ttk.Frame(self.tab_frame)
        self.control_frame.pack(fill=tk.X, padx=5, pady=5)
        
        left_frame = ttk.Frame(self.control_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Label(left_frame, text="Поиск:", 
                 font=font_settings['caption_font']).pack(side=tk.LEFT, padx=(0, 5))
        
        self.search_var = tk.StringVar()
        self._search_debounce_id = None
        search_entry = ttk.Entry(left_frame, textvariable=self.search_var, 
                                width=40, font=font_settings['caption_font'])
        search_entry.pack(side=tk.LEFT, padx=(0, 20))
        search_entry.bind('<KeyRelease>', self._debounced_filter_channels)
        TextFieldContextMenu.bind_context_menu(search_entry)
        
        ttk.Label(left_frame, text="Группа:", 
                 font=font_settings['caption_font']).pack(side=tk.LEFT, padx=(0, 5))
        
        self.group_var = tk.StringVar()
        self.group_combo = ttk.Combobox(left_frame, textvariable=self.group_var, 
                                       width=20, state='readonly',
                                       font=font_settings['caption_font'])
        self.group_combo.pack(side=tk.LEFT)
        self.group_combo.set("Все группы")
        self.group_combo.bind('<<ComboboxSelected>>', lambda e: self.filter_channels())
        
        right_frame = ttk.Frame(self.control_frame)
        right_frame.pack(side=tk.RIGHT)
        
        self.loading_label = ttk.Label(right_frame, text="", 
                                      font=font_settings['small_font'])
        self.loading_label.pack(side=tk.RIGHT, padx=5)
        
        self.progress_bar = ttk.Progressbar(right_frame, mode='indeterminate', 
                                           length=100)
        self.progress_bar.pack(side=tk.RIGHT, padx=5)
        self.progress_bar.pack_forget()
        
        main_container = ttk.Frame(self.tab_frame)
        main_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        table_frame = ttk.Frame(main_container)
        table_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self._create_table(table_frame, font_settings)
        self._create_side_panel(main_container, font_settings)
        
        self.tree.bind("<ButtonRelease-1>", self.on_single_click)
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Button-3>", self.show_context_menu)
        
        if TKDND_AVAILABLE:
            self._setup_table_drag_drop()
    
    def _create_side_panel(self, parent, font_settings):
        """Создание боковой панели справа"""
        side_panel = ttk.Frame(parent, width=400, relief=tk.RAISED, borderwidth=1)
        side_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        side_panel.pack_propagate(False)
        
        title_label = ttk.Label(side_panel, text="Управление каналом", 
                               font=font_settings['title_font'])
        title_label.pack(pady=15, padx=10)
        
        ttk.Separator(side_panel, orient='horizontal').pack(fill=tk.X, padx=10, pady=5)
        self._create_channel_editor_section(side_panel, font_settings)
        ttk.Separator(side_panel, orient='horizontal').pack(fill=tk.X, padx=10, pady=5)
        
        if PIL_AVAILABLE:
            self._create_logo_section(side_panel, font_settings)
            ttk.Separator(side_panel, orient='horizontal').pack(fill=tk.X, padx=10, pady=5)
        
        self._create_playlist_info_section(side_panel, font_settings)
    
    def _create_channel_editor_section(self, parent, font_settings):
        """Создание секции редактирования канала"""
        editor_frame = ttk.LabelFrame(parent, text="Править канал", padding="10")
        editor_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.name_var = tk.StringVar()
        self.group_var_editor = tk.StringVar()
        self.tvg_id_var = tk.StringVar()
        self.tvg_logo_var = tk.StringVar()
        self.url_var = tk.StringVar()
        
        fields = [
            ("Название канала*:", self.name_var),
            ("Группа:", self.group_var_editor),
            ("TVG-ID:", self.tvg_id_var),
            ("Логотип URL:", self.tvg_logo_var),
            ("URL потока:", self.url_var)
        ]
        
        for label, var in fields:
            frame = ttk.Frame(editor_frame)
            frame.pack(fill=tk.X, pady=2)
            
            ttk.Label(frame, text=label, 
                     font=font_settings['small_font'], width=15).pack(side=tk.LEFT, anchor='w')
            
            entry = ttk.Entry(frame, textvariable=var, width=25)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
            TextFieldContextMenu.bind_context_menu(entry)
        
        button_frame = ttk.Frame(editor_frame)
        button_frame.pack(pady=10)
        
        ttk.Button(button_frame, text="➕ Новый", 
                  command=self._clear_editor_for_new,
                  style="Medium.TButton").pack(side=tk.LEFT, padx=2)
        
        self.save_button = ttk.Button(button_frame, text="💾 Сохранить", 
                                     command=self._save_channel_from_editor,
                                     style="Medium.TButton")
        self.save_button.pack(side=tk.LEFT, padx=2)
        
        self.delete_button = ttk.Button(button_frame, text="🗑️ Удалить", 
                                       command=self._delete_current_channel,
                                       style="Medium.TButton")
        self.delete_button.pack(side=tk.LEFT, padx=2)
        
        ttk.Button(button_frame, text="❌ Отмена", 
                  command=self._cancel_edit,
                  style="Medium.TButton").pack(side=tk.LEFT, padx=2)
        
        self._update_editor_buttons_state(False)
    
    def _create_logo_section(self, parent, font_settings):
        """Создание секции отображения логотипа"""
        logo_frame = ttk.LabelFrame(parent, text="Логотип канала", padding="10")
        logo_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.logo_preview_label = ttk.Label(logo_frame, text="Нет логотипа", 
                                           font=font_settings['caption_font'])
        self.logo_preview_label.pack(pady=10)
    
    def _create_playlist_info_section(self, parent, font_settings):
        """Создание секции информации о плейлисте"""
        info_frame = ttk.LabelFrame(parent, text="Информация о плейлисте", padding="10")
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.total_channels_label = ttk.Label(info_frame, text="Всего каналов: 0", 
                                             font=font_settings['small_font'])
        self.total_channels_label.pack(anchor='w', pady=2)
        
        self.with_url_label = ttk.Label(info_frame, text="С URL: 0", 
                                       font=font_settings['small_font'])
        self.with_url_label.pack(anchor='w', pady=2)
        
        self.without_url_label = ttk.Label(info_frame, text="Без URL: 0", 
                                          font=font_settings['small_font'])
        self.without_url_label.pack(anchor='w', pady=2)
        
        self.file_info_label = ttk.Label(info_frame, text="Файл: не сохранен", 
                                        font=font_settings['small_font'])
        self.file_info_label.pack(anchor='w', pady=2)
    
    def _create_table(self, parent, font_settings):
        """Создание таблицы Treeview"""
        table_container = ttk.Frame(parent)
        table_container.pack(fill=tk.BOTH, expand=True)
        
        vsb = ttk.Scrollbar(table_container, orient="vertical")
        hsb = ttk.Scrollbar(table_container, orient="horizontal")
        
        visible_columns = self.column_manager.get_visible_columns()
        column_ids = [col[0] for col in visible_columns]
        
        self.tree = ttk.Treeview(
            table_container,
            columns=column_ids,
            show="headings",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set,
            height=25,
            selectmode='browse'
        )
        
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)
        
        style = ttk.Style()
        style.configure("Treeview", 
                       font=font_settings['small_font'])
        style.configure("Treeview.Heading",
                       font=font_settings['caption_font'])
        
        for col_id, heading, width, visible in visible_columns:
            self.tree.heading(col_id, text=heading, anchor=tk.W)
            self.tree.column(col_id, width=width, anchor=tk.W, stretch=False)
        
        self.tree.grid(row=0, column=0, sticky="nsew", in_=table_container)
        vsb.grid(row=0, column=1, sticky="ns", in_=table_container)
        hsb.grid(row=1, column=0, sticky="ew", columnspan=2, in_=table_container)
        
        table_container.grid_rowconfigure(0, weight=1)
        table_container.grid_columnconfigure(0, weight=1)
    
    def _debounced_filter_channels(self, event=None):
        if self._search_debounce_id:
            self.tab_frame.after_cancel(self._search_debounce_id)
        
        self._search_debounce_id = self.tab_frame.after(300, self.filter_channels)
    
    def _fast_parse_m3u_threaded(self, content):
        """Парсинг M3U с использованием регулярных выражений для ускорения"""
        self.playlist_data = []
        
        extinf_pattern = re.compile(
            r'#EXTINF:-1\s+(.*?),\s*(.+)',
            re.DOTALL
        )
        
        lines = content.splitlines()
        total_lines = len(lines)
        i = 0
        
        while i < total_lines:
            line = lines[i].strip()
            
            if line.startswith('#EXTINF:'):
                match = extinf_pattern.search(line)
                if match:
                    channel = ChannelData()
                    channel.extinf = line
                    channel.name = match.group(2)
                    
                    attrs = match.group(1)
                    tvg_id_match = re.search(r'tvg-id="([^"]+)"', attrs)
                    if tvg_id_match:
                        channel.tvg_id = tvg_id_match.group(1)
                    
                    tvg_logo_match = re.search(r'tvg-logo="([^"]+)"', attrs)
                    if tvg_logo_match:
                        channel.tvg_logo = tvg_logo_match.group(1)
                    
                    group_match = re.search(r'group-title="([^"]+)"', attrs)
                    if group_match:
                        channel.group = group_match.group(1)
                    else:
                        channel.group = "Без группы"
                    
                    j = i + 1
                    while j < total_lines and (not lines[j].strip() or lines[j].startswith('#')):
                        j += 1
                    
                    if j < total_lines:
                        channel.url = lines[j].strip()
                        channel.has_url = bool(channel.url.strip())
                        i = j
                    
                    self.playlist_data.append(channel)
            
            i += 1
        
        self.loading_complete = True
    
    def load_from_file_async(self, file_path):
        """Асинхронная загрузка файла плейлиста"""
        if self.is_loading:
            messagebox.showinfo("Информация", "Загрузка уже выполняется")
            return
        
        self.is_loading = True
        self.file_path = file_path
        self.loading_complete = False
        self.loading_error = None
        
        self.loading_label.config(text="Загрузка...")
        self.progress_bar.pack(side=tk.RIGHT, padx=5)
        self.progress_bar.start()
        
        self.loading_thread = threading.Thread(
            target=self._load_from_file_thread,
            args=(file_path,),
            daemon=True
        )
        self.loading_thread.start()
        self._check_loading_complete()
    
    def load_from_url_async(self, url):
        """Асинхронная загрузка плейлиста по URL"""
        if self.is_loading:
            messagebox.showinfo("Информация", "Загрузка уже выполняется")
            return
        
        self.is_loading = True
        self.file_path = url
        self.loading_complete = False
        self.loading_error = None
        
        self.loading_label.config(text="Загрузка URL...")
        self.progress_bar.pack(side=tk.RIGHT, padx=5)
        self.progress_bar.start()
        
        self.loading_thread = threading.Thread(
            target=self._load_from_url_thread,
            args=(url,),
            daemon=True
        )
        self.loading_thread.start()
        self._check_loading_complete()
    
    def _load_from_file_thread(self, file_path):
        """Загрузка файла в отдельном потоке"""
        try:
            logger.info(f"Асинхронная загрузка файла: {file_path}")
            
            with open(file_path, 'rb') as f:
                content_bytes = f.read()
            
            encodings = ['utf-8', 'cp1251', 'windows-1251', 'latin-1']
            content = None
            
            for encoding in encodings:
                try:
                    content = content_bytes.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                content = content_bytes.decode('utf-8', errors='ignore')
            
            self._fast_parse_m3u_threaded(content)
            
        except Exception as e:
            logger.error(f"Ошибка загрузки файла {file_path}: {e}")
            self.loading_error = str(e)
    
    def _load_from_url_thread(self, url):
        """Загрузка плейлиста по URL в отдельном потоке"""
        try:
            logger.info(f"Асинхронная загрузка URL: {url}")
            
            import urllib.request
            
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            
            with urllib.request.urlopen(req, timeout=30) as response:
                content_bytes = response.read()
            
            encodings = ['utf-8', 'cp1251', 'windows-1251', 'latin-1']
            content = None
            
            for encoding in encodings:
                try:
                    content = content_bytes.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                content = content_bytes.decode('utf-8', errors='ignore')
            
            self._fast_parse_m3u_threaded(content)
            
        except Exception as e:
            logger.error(f"Ошибка загрузки URL {url}: {e}")
            self.loading_error = str(e)
    
    def _check_loading_complete(self):
        """Проверка завершения загрузки"""
        if self.loading_complete:
            self.is_loading = False
            self.progress_bar.stop()
            self.progress_bar.pack_forget()
            self.loading_label.config(text="")
            
            self.filtered_data = self.playlist_data[:]
            self.update_table()
            self.update_group_filter()
            self.update_playlist_info()
            
            tab_name = self._get_tab_name(self.file_path)
            index = self.parent.index(self.tab_frame)
            self.parent.tab(index, text=tab_name)
            
            self.manager.update_status(f"✅ Загружено: {len(self.playlist_data)} каналов")
            logger.info(f"Файл загружен успешно. Каналов: {len(self.playlist_data)}")
            
        elif self.loading_error is not None:
            self.is_loading = False
            self.progress_bar.stop()
            self.progress_bar.pack_forget()
            self.loading_label.config(text="")
            
            logger.error(f"Ошибка загрузки: {self.loading_error}")
            messagebox.showerror("Ошибка", f"Не удалось загрузить файл:\n{self.loading_error}")
            self.manager.update_status("❌ Ошибка загрузки")
            self.loading_error = None
            
        elif self.loading_thread and not self.loading_thread.is_alive():
            self.is_loading = False
            self.progress_bar.stop()
            self.progress_bar.pack_forget()
            self.loading_label.config(text="")
            
            if not self.playlist_data:
                logger.warning("Загрузка завершена, но данных нет")
                self.manager.update_status("⚠️ Загружено 0 каналов")
                self.filtered_data = []
                self.update_table()
                self.update_playlist_info()
        else:
            self.tab_frame.after(100, self._check_loading_complete)
    
    def update_table(self):
        """Обновление таблицы с упрощенными колонками"""
        if self._is_updating:
            return
        
        with self._update_lock:
            self._is_updating = True
            try:
                for item in self.tree.get_children():
                    self.tree.delete(item)
                
                self._row_to_channel = {}
                visible_columns = self.column_manager.get_visible_columns()
                
                if not self.filtered_data:
                    info_values = [""] * len(visible_columns)
                    info_item = self.tree.insert('', 'end', values=info_values, tags=('info',))
                    
                    for col_id, heading, width, visible in visible_columns:
                        if col_id == 'name':
                            self.tree.set(info_item, col_id, "Нет данных для отображения")
                            break
                    
                    self.tree.tag_configure('info', background='#f0f0f0', foreground='#666')
                    self._row_to_channel[info_item] = {'is_info': True}
                    return
                
                column_order = [col[0] for col in visible_columns]
                
                for idx, channel in enumerate(self.filtered_data):
                    display_idx = idx + 1
                    
                    values = {}
                    for col_id, heading, width, visible in visible_columns:
                        if col_id == 'number':
                            values[col_id] = str(display_idx)
                        elif col_id == 'name':
                            values[col_id] = channel.name
                        elif col_id == 'group':
                            values[col_id] = channel.group
                        elif col_id == 'url':
                            url_display = channel.url
                            if url_display and len(url_display) > 50:
                                url_display = channel.url[:50] + "..."
                            values[col_id] = url_display or ""
                        else:
                            values[col_id] = ""
                    
                    row_values = [values[col_id] for col_id in column_order]
                    
                    tags = ()
                    if not channel.has_url:
                        tags = ('no_url',)
                    elif channel.url_status is False:
                        tags = ('bad_url',)
                    elif channel.url_status is True:
                        tags = ('good_url',)
                    
                    item_id = self.tree.insert('', 'end', values=row_values, tags=tags)
                    
                    self._row_to_channel[item_id] = {
                        'channel': channel,
                        'original_index': self.playlist_data.index(channel) if channel in self.playlist_data else -1,
                        'display_index': idx
                    }
                
                self.tree.tag_configure('no_url', background='#ffe6e6')
                self.tree.tag_configure('bad_url', background='#fff0e6')
                self.tree.tag_configure('good_url', background='#e6ffe6')
                
                self.update_info()
                
            finally:
                self._is_updating = False
    
    def update_group_filter(self):
        if self._group_cache is None:
            groups = sorted(set(ch.group for ch in self.playlist_data if ch.group))
            groups.insert(0, "Все группы")
            self._group_cache = groups
        
        self.group_combo['values'] = self._group_cache
        if self.group_var.get() not in self._group_cache:
            self.group_combo.set("Все группы")
    
    def update_info(self):
        """Обновление информации в панели управления"""
        total = len(self.playlist_data)
        filtered = len(self.filtered_data)
        
        no_url_count = sum(1 for ch in self.playlist_data if not ch.has_url)
        
        info_text = f"Всего: {total} | Отфильтровано: {filtered} | Без URL: {no_url_count}"
        
        if not hasattr(self, 'info_label'):
            self.info_label = ttk.Label(self.control_frame, text=info_text,
                                      font=self.manager.font_settings['small_font'])
            self.info_label.pack(side=tk.LEFT, padx=(20, 0))
        else:
            self.info_label.config(text=info_text)
    
    def update_playlist_info(self):
        """Обновление информации о плейлисте в боковой панели"""
        total = len(self.playlist_data)
        with_url = sum(1 for ch in self.playlist_data if ch.has_url)
        without_url = sum(1 for ch in self.playlist_data if not ch.has_url)
        
        self.total_channels_label.config(text=f"Всего каналов: {total}")
        self.with_url_label.config(text=f"С URL: {with_url}")
        self.without_url_label.config(text=f"Без URL: {without_url}")
        
        if self.file_path:
            if self.file_path.startswith(('http://', 'https://')):
                self.file_info_label.config(text=f"URL: {self.file_path[:30]}...")
            else:
                file_name = os.path.basename(self.file_path)
                if len(file_name) > 30:
                    file_name = "..." + file_name[-27:]
                self.file_info_label.config(text=f"Файл: {file_name}")
        else:
            self.file_info_label.config(text="Файл: не сохранен")
    
    def filter_channels(self, event=None):
        search_text = self.search_var.get().lower()
        group_filter = self.group_var.get()
        
        self._row_to_channel = {}
        
        cache_key = f"{search_text}_{group_filter}"
        if cache_key in self._search_cache and len(self._search_cache) < 100:
            self.filtered_data = self._search_cache[cache_key]
        else:
            if group_filter == "Все группы":
                if search_text:
                    self.filtered_data = [
                        ch for ch in self.playlist_data
                        if search_text in ch.name.lower() or search_text in ch.group.lower()
                    ]
                else:
                    self.filtered_data = self.playlist_data[:]
            else:
                if search_text:
                    self.filtered_data = [
                        ch for ch in self.playlist_data
                        if ch.group == group_filter and 
                        (search_text in ch.name.lower() or search_text in ch.group.lower())
                    ]
                else:
                    self.filtered_data = [
                        ch for ch in self.playlist_data
                        if ch.group == group_filter
                    ]
            
            if len(self._search_cache) >= 100:
                self._search_cache.clear()
            self._search_cache[cache_key] = self.filtered_data
        
        self.update_table()
        self.update_info()
    
    def get_channel_for_item(self, item_id):
        if not hasattr(self, '_row_to_channel'):
            self._row_to_channel = {}
        
        if item_id in self._row_to_channel:
            mapping = self._row_to_channel[item_id]
            if 'is_info' in mapping:
                return None
            return mapping.get('channel')
        return None
    
    def on_single_click(self, event):
        """Обработка одиночного клика для выделения канала"""
        item = self.tree.identify_row(event.y)
        if not item:
            return
        
        self.tree.selection_set(item)
        channel = self.get_channel_for_item(item)
        if channel:
            self._load_channel_to_editor(channel)
    
    def on_double_click(self, event):
        """Обработка двойного клика для редактирования"""
        item = self.tree.identify_row(event.y)
        if not item:
            return
        
        self.tree.selection_set(item)
        channel = self.get_channel_for_item(item)
        if channel:
            self._load_channel_to_editor(channel)
    
    def show_context_menu(self, event):
        """Показать контекстное меню для выбранного канала"""
        item = self.tree.identify_row(event.y)
        if not item:
            return
        
        self.tree.selection_set(item)
        channel = self.get_channel_for_item(item)
        if not channel:
            return
        
        menu = Menu(self.manager.root, tearoff=0,
                   font=self.manager.font_settings['menu_font'])
        
        menu.add_command(label="Править",
                        command=lambda: self._load_channel_to_editor(channel))
        
        menu.add_command(label="Удалить",
                        command=lambda: self.delete_selected_channel(item))
        menu.add_separator()
        
        menu.add_command(label="Удалить пустые каналы",
                        command=self.delete_empty_channels)
        
        menu.add_separator()
        menu.add_command(label="Групповые операции...",
                        command=self.bulk_ops.show_bulk_operations_dialog)
        
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
    
    def _load_channel_to_editor(self, channel):
        """Загрузка данных канала в редактор боковой панели"""
        self.current_channel = channel
        
        self.name_var.set(channel.name)
        self.group_var_editor.set(channel.group)
        self.tvg_id_var.set(channel.tvg_id)
        self.tvg_logo_var.set(channel.tvg_logo)
        self.url_var.set(channel.url)
        
        self._update_logo_preview()
        self._update_editor_buttons_state(True)
        
        for item in self.tree.get_children():
            item_channel = self.get_channel_for_item(item)
            if item_channel == channel:
                self.tree.see(item)
                self.tree.selection_set(item)
                break
    
    def _update_logo_preview(self):
        """Обновление превью логотипа"""
        if hasattr(self, 'logo_preview_label'):
            logo_url = self.tvg_logo_var.get()
            if logo_url:
                try:
                    photo = self.image_manager.load_logo(logo_url, max_size=(150, 150))
                    if photo:
                        self.logo_preview_label.config(image=photo)
                        self.logo_preview_label.image = photo
                        self.logo_preview_label.config(text="")
                    else:
                        self.logo_preview_label.config(image='', text="Логотип не загружен")
                except:
                    self.logo_preview_label.config(image='', text="Ошибка загрузки логотипа")
            else:
                self.logo_preview_label.config(image='', text="Логотип не установлен")
    
    def _clear_editor_for_new(self):
        """Очистка редактора для создания нового канала"""
        self.current_channel = None
        
        self.name_var.set("")
        self.group_var_editor.set("Без группы")
        self.tvg_id_var.set("")
        self.tvg_logo_var.set("")
        self.url_var.set("")
        
        if hasattr(self, 'logo_preview_label'):
            self.logo_preview_label.config(image='', text="Нет логотипа")
        
        self.tree.selection_remove(self.tree.selection())
        self._update_editor_buttons_state(False)
    
    def _save_channel_from_editor(self):
        """Сохранение канала из редактора"""
        if not self.name_var.get().strip():
            messagebox.showwarning("Предупреждение", "Заполните название канала")
            return
        
        url = self.url_var.get().strip()
        if url and not PlaylistValidator.validate_url(url):
            messagebox.showwarning("Предупреждение", 
                                 "Некорректный URL. URL должен начинаться с http://, https://, rtmp:// или быть в формате ip:port")
            return
        
        if self.current_channel:
            action_type = "edit_channel"
            action_description = f"Редактирование канала: {self.current_channel.name}"
        else:
            action_type = "add_channel"
            action_description = "Добавление нового канала"
        
        action = self.history.start_action(action_type, action_description)
        
        if self.current_channel:
            old_values = {
                'name': self.current_channel.name,
                'group': self.current_channel.group,
                'tvg_id': self.current_channel.tvg_id,
                'tvg_logo': self.current_channel.tvg_logo,
                'url': self.current_channel.url,
                'has_url': self.current_channel.has_url
            }
            
            self.current_channel.name = self.name_var.get().strip()
            self.current_channel.group = self.group_var_editor.get().strip() or "Без группы"
            self.current_channel.tvg_id = self.tvg_id_var.get().strip()
            self.current_channel.tvg_logo = self.tvg_logo_var.get().strip()
            self.current_channel.url = url
            self.current_channel.has_url = bool(url)
            self.current_channel.url_status = None
            self.current_channel._hash = None
            
            self._update_channel_extinf(self.current_channel)
            
            new_values = {
                'name': self.current_channel.name,
                'group': self.current_channel.group,
                'tvg_id': self.current_channel.tvg_id,
                'tvg_logo': self.current_channel.tvg_logo,
                'url': self.current_channel.url,
                'has_url': self.current_channel.has_url
            }
            
            for key in old_values:
                if old_values[key] != new_values[key]:
                    self.history.add_change(
                        f"change_{key}",
                        old_values[key],
                        new_values[key],
                        f"{self.current_channel.name} ({key})"
                    )
            
        else:
            channel = ChannelData()
            channel.name = self.name_var.get().strip()
            channel.group = self.group_var_editor.get().strip() or "Без группы"
            channel.tvg_id = self.tvg_id_var.get().strip()
            channel.tvg_logo = self.tvg_logo_var.get().strip()
            channel.url = url
            channel.has_url = bool(url)
            
            self._update_channel_extinf(channel)
            
            if url:
                for existing_channel in self.playlist_data:
                    if existing_channel.url == url:
                        if not messagebox.askyesno("Предупреждение", 
                                                 f"Канал с URL '{url[:50]}...' уже существует.\nДобавить дубликат?"):
                            self.history.cancel_action()
                            return
            
            self.history.add_change(
                "channel_add",
                None,
                channel,
                f"{channel.name} ({channel.group})"
            )
            
            self.playlist_data.append(channel)
            self.current_channel = channel
        
        self.history.commit_action()
        self._group_cache = None
        self._search_cache = {}
        self.filter_channels()
        self.update_playlist_info()
        
        if self.current_channel:
            for item in self.tree.get_children():
                item_channel = self.get_channel_for_item(item)
                if item_channel == self.current_channel:
                    self.tree.see(item)
                    self.tree.selection_set(item)
                    break
        
        self.manager.update_status("✅ Канал сохранен")
        logger.info(f"Канал сохранен: {self.current_channel.name if self.current_channel else 'новый'}")
    
    def _delete_current_channel(self):
        """Удаление текущего канала"""
        if not self.current_channel:
            messagebox.showwarning("Предупреждение", "Нет выбранного канала для удаления")
            return
        
        if not messagebox.askyesno("Подтверждение", 
                                 f"Удалить канал '{self.current_channel.name}'?"):
            return
        
        action = self.history.start_action("delete_channel", 
                                         f"Удаление канала: {self.current_channel.name}")
        
        for i, ch in enumerate(self.playlist_data):
            if ch == self.current_channel:
                self.history.add_change(
                    "channel_delete",
                    ch,
                    None,
                    f"{ch.name} ({ch.group})"
                )
                
                del self.playlist_data[i]
                break
        
        self.history.commit_action()
        self._clear_editor_for_new()
        self._group_cache = None
        self._search_cache = {}
        self.filter_channels()
        self.update_playlist_info()
        
        self.manager.update_status("✅ Канал удален")
    
    def _cancel_edit(self):
        """Отмена редактирования"""
        if self.current_channel:
            self._load_channel_to_editor(self.current_channel)
        else:
            self._clear_editor_for_new()
    
    def _update_editor_buttons_state(self, has_channel):
        """Обновление состояния кнопок редактора"""
        if has_channel:
            self.save_button.config(text="💾 Сохранить", state='normal')
            self.delete_button.config(state='normal')
        else:
            self.save_button.config(text="💾 Добавить", state='normal')
            self.delete_button.config(state='disabled')
    
    def _update_channel_extinf(self, channel):
        """Обновление строки EXTINF для канала"""
        extinf_parts = ["#EXTINF:-1"]
        if channel.tvg_id:
            extinf_parts.append(f'tvg-id="{channel.tvg_id}"')
        if channel.tvg_logo:
            extinf_parts.append(f'tvg-logo="{channel.tvg_logo}"')
        if channel.group:
            extinf_parts.append(f'group-title="{channel.group}"')
        extinf_parts.append(f',{channel.name}')
        channel.extinf = ' '.join(extinf_parts)
    
    def delete_selected_channel(self, item_id):
        channel = self.get_channel_for_item(item_id)
        if not channel:
            return
        
        if not messagebox.askyesno("Подтверждение", f"Удалить канал '{channel.name}'?"):
            return
        
        if self.current_channel == channel:
            self._clear_editor_for_new()
        
        action = self.history.start_action("delete_channel", f"Удаление канала: {channel.name}")
        
        for i, ch in enumerate(self.playlist_data):
            if ch == channel:
                self.history.add_change(
                    "channel_delete",
                    ch,
                    None,
                    f"{ch.name} ({ch.group})"
                )
                
                del self.playlist_data[i]
                break
        
        self.history.commit_action()
        self._group_cache = None
        self._search_cache = {}
        self.filter_channels()
        self.update_playlist_info()
        self.manager.update_status("✅ Канал удален")
    
    def delete_empty_channels(self):
        empty_channels = [ch for ch in self.playlist_data if not ch.has_url]
        
        if not empty_channels:
            messagebox.showinfo("Информация", "Каналы без URL не найдены")
            return
        
        if not messagebox.askyesno("Подтверждение", 
                                 f"Найдено {len(empty_channels)} каналов без URL.\nУдалить их?"):
            return
        
        action = self.history.start_action(
            "delete_empty_channels", 
            f"Удаление {len(empty_channels)} каналов без URL"
        )
        
        channels_to_keep = []
        for channel in self.playlist_data:
            if channel.has_url:
                channels_to_keep.append(channel)
            else:
                self.history.add_change(
                    "channel_delete",
                    channel,
                    None,
                    f"{channel.name} ({channel.group})"
                )
        
        self.playlist_data = channels_to_keep
        
        if self.current_channel and not self.current_channel.has_url:
            self._clear_editor_for_new()
        
        self.history.commit_action()
        self._group_cache = None
        self._search_cache = {}
        self.filter_channels()
        self.update_playlist_info()
        self.manager.update_status(f"✅ Удалено {len(empty_channels)} каналов без URL")
        logger.info(f"Удалено {len(empty_channels)} каналов без URL")
    
    def validate_playlist_dialog(self):
        """Диалог валидации плейлиста"""
        results = PlaylistValidator.validate_playlist(self.playlist_data)
        
        dialog = tk.Toplevel(self.manager.root)
        dialog.title("Результаты валидации")
        dialog.geometry("600x500")
        dialog.transient(self.manager.root)
        dialog.grab_set()
        
        notebook = ttk.Notebook(dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        stats_frame = ttk.Frame(notebook)
        notebook.add(stats_frame, text="Статистика")
        
        stats_text = f"""
        Общая статистика:
        • Всего каналов: {results['stats']['total_channels']}
        • Каналов с URL: {results['stats']['channels_with_url']}
        • Каналов без URL: {results['stats']['channels_without_url']}
        • Дубликатов URL: {results['stats']['duplicate_urls']}
        • Дубликатов имен: {results['stats']['duplicate_names']}
        • Слишком длинных имен: {results['stats']['long_names']}
        • Неверных URL: {results['stats']['invalid_urls']}
        • Пустых групп: {results['stats']['empty_groups']}
        """
        
        ttk.Label(stats_frame, text=stats_text, justify=tk.LEFT,
                 font=self.manager.font_settings['dialog_font']).pack(pady=20, padx=20)
        
        if results['errors']:
            errors_frame = ttk.Frame(notebook)
            notebook.add(errors_frame, text=f"Ошибки ({len(results['errors'])})")
            
            text_widget = tk.Text(errors_frame, wrap=tk.WORD)
            scrollbar = ttk.Scrollbar(errors_frame, command=text_widget.yview)
            text_widget.configure(yscrollcommand=scrollbar.set)
            
            for error in results['errors']:
                text_widget.insert(tk.END, f"• {error}\n")
            
            text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        if results['warnings']:
            warnings_frame = ttk.Frame(notebook)
            notebook.add(warnings_frame, text=f"Предупреждения ({len(results['warnings'])})")
            
            text_widget = tk.Text(warnings_frame, wrap=tk.WORD)
            scrollbar = ttk.Scrollbar(warnings_frame, command=text_widget.yview)
            text_widget.configure(yscrollcommand=scrollbar.set)
            
            for warning in results['warnings']:
                text_widget.insert(tk.END, f"• {warning}\n")
            
            text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)
        
        ttk.Button(button_frame, text="Закрыть", 
                  command=dialog.destroy,
                  style="Large.TButton").pack()
    
    def _setup_table_drag_drop(self):
        """Настройка Drag & Drop внутри таблицы для переупорядочивания"""
        if not TKDND_AVAILABLE:
            return
        
        self._drag_data = {'x': 0, 'y': 0, 'item': None}
        
        def start_drag(event):
            item = self.tree.identify_row(event.y)
            if item:
                self._drag_data['item'] = item
                self._drag_data['x'] = event.x
                self._drag_data['y'] = event.y
        
        def do_drag(event):
            if self._drag_data['item']:
                self.tree.config(cursor='hand2')
        
        def stop_drag(event):
            if self._drag_data['item']:
                target_item = self.tree.identify_row(event.y)
                if target_item and target_item != self._drag_data['item']:
                    self.tree.move(self._drag_data['item'], '', self.tree.index(target_item))
                    self._reorder_channels(self._drag_data['item'], target_item)
                
                self.tree.config(cursor='')
                self._drag_data['item'] = None
        
        self.tree.bind('<ButtonPress-1>', start_drag)
        self.tree.bind('<B1-Motion>', do_drag)
        self.tree.bind('<ButtonRelease-1>', stop_drag)
    
    def _reorder_channels(self, source_item, target_item):
        """Переупорядочивание каналов после Drag & Drop"""
        source_channel = self.get_channel_for_item(source_item)
        target_channel = self.get_channel_for_item(target_item)
        
        if not source_channel or not target_channel:
            return
        
        source_idx = None
        target_idx = None
        
        for i, channel in enumerate(self.filtered_data):
            if channel == source_channel:
                source_idx = i
            if channel == target_channel:
                target_idx = i
        
        if source_idx is not None and target_idx is not None:
            channel = self.filtered_data.pop(source_idx)
            
            if target_idx < source_idx:
                insert_idx = target_idx
            else:
                insert_idx = target_idx
            
            self.filtered_data.insert(insert_idx, channel)
            self.update_table()
            self.manager.update_status("✅ Порядок каналов изменен")
    
    def has_unsaved_changes(self):
        """Проверка наличия несохраненных изменений"""
        if self.history.history:
            return True
        
        if self.history.current_action:
            return True
        
        return True


class IPTVManager:
    """Основной класс приложения"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Редактор IPTV листов")
        
        sys.excepthook = self._handle_exception
        self.font_settings = WindowsFontSettings.get_system_font_settings()
        self._setup_dpi_awareness()
        
        self.tabs = {}
        self.auto_save = False
        self.auto_save_interval = 300000
        
        self.column_manager = ColumnManager()
        self.drag_drop_manager = None
        if TKDND_AVAILABLE:
            self.drag_drop_manager = DragDropManager(root, self.handle_dropped_files)
        
        self._setup_styles()
        self._create_menu()
        self._create_toolbar()
        self._create_notebook()
        self._create_status_bar()
        self._setup_hotkeys()
        
        self.create_new_tab()
        self._center_window()
        self.root.minsize(1100, 700)
        
        logger.info("Приложение инициализировано")
    
    def _handle_exception(self, exc_type, exc_value, exc_traceback):
        """Обработчик необработанных исключений"""
        logger.error("Необработанное исключение", 
                    exc_info=(exc_type, exc_value, exc_traceback))
        messagebox.showerror("Критическая ошибка", 
                           f"Произошла ошибка:\n{exc_type.__name__}: {exc_value}")
    
    def handle_dropped_files(self, files):
        """Обработка перетащенных файлов на главное окно"""
        if not files:
            return
        
        for file_path in files:
            if file_path.lower().endswith(('.m3u', '.m3u8')):
                for tab in self.tabs.values():
                    if tab.file_path and os.path.abspath(tab.file_path) == os.path.abspath(file_path):
                        self.notebook.select(tab.tab_frame)
                        self.update_status(f"✅ Файл уже открыт: {os.path.basename(file_path)}")
                        return
            
                tab = self.create_new_tab()
                tab.load_from_file_async(file_path)
                self.update_status(f"⏳ Загрузка файла: {os.path.basename(file_path)}...")
    
    def _setup_dpi_awareness(self):
        if sys.platform == "win32":
            try:
                awareness = ctypes.c_int()
                ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(awareness))
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except:
                    pass
    
    def _setup_styles(self):
        style = ttk.Style()
        
        default_font = self.font_settings['caption_font']
        dialog_font = self.font_settings['dialog_font']
        
        self.root.option_add('*Font', default_font)
        self.root.option_add('*Dialog.msg.font', dialog_font)
        self.root.option_add('*Menu.Font', default_font)
        
        style.configure('TLabel', font=default_font)
        style.configure('Small.TButton', font=default_font, padding=4)
        style.configure('Medium.TButton', font=default_font, padding=6)
        style.configure('Large.TButton', font=default_font, padding=8)
        style.configure('TEntry', font=dialog_font)
        style.configure('TCombobox', font=dialog_font)
        style.configure('TNotebook', font=default_font)
        style.configure('TNotebook.Tab', font=default_font, padding=[10, 4])
        
        style.configure('Treeview', 
                       rowheight=25,
                       font=self.font_settings['small_font'])
        style.configure('Treeview.Heading',
                       font=self.font_settings['caption_font'])
    
    def _center_window(self):
        width = 1200
        height = 700
        
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def _create_menu(self):
        menubar = Menu(self.root, font=self.font_settings['menu_font'])
        self.root.config(menu=menubar)
        
        file_menu = Menu(menubar, tearoff=0, font=self.font_settings['menu_font'])
        menubar.add_cascade(label="Файл", menu=file_menu)
        
        file_menu.add_command(label="Создать плейлист", command=self.create_new_playlist)
        file_menu.add_command(label="Открыть плейлист", command=self.open_playlist)
        file_menu.add_command(label="Открыть по URL", command=self.open_url_playlist)
        file_menu.add_separator()
        file_menu.add_command(label="Сохранить", command=self.save_current)
        file_menu.add_command(label="Сохранить как...", command=self.save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Сбросить настройки", command=self.reset_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.root.quit)
        
        operations_menu = Menu(menubar, tearoff=0, font=self.font_settings['menu_font'])
        menubar.add_cascade(label="Операции", menu=operations_menu)
        if REQUESTS_AVAILABLE:
            operations_menu.add_command(label="Проверить ссылки", 
                                       command=self.check_urls)
        operations_menu.add_command(label="Валидация плейлиста",
                                   command=self.validate_current_playlist)
        operations_menu.add_command(label="Удалить пустые каналы",
                                   command=self.delete_empty_channels)
        operations_menu.add_separator()
        operations_menu.add_command(label="Групповые операции",
                                   command=self.bulk_operations)
        
        help_menu = Menu(menubar, tearoff=0, font=self.font_settings['menu_font'])
        menubar.add_cascade(label="Справка", menu=help_menu)
        help_menu.add_command(label="О программе", command=self.show_about)
        help_menu.add_command(label="Горячие клавиши", command=self.show_hotkeys)
        help_menu.add_command(label="Просмотреть логи", command=self.view_logs)
        help_menu.add_command(label="Сброс настроек...", command=self.reset_settings_dialog)
    
    def _create_toolbar(self):
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(toolbar, text="📄", 
                  command=self.create_new_playlist,
                  style="Medium.TButton").pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="📂", 
                  command=self.open_playlist,
                  style="Medium.TButton").pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="💾", 
                  command=self.save_current,
                  style="Medium.TButton").pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient='vertical').pack(side=tk.LEFT, padx=8, fill=tk.Y)
        
        if REQUESTS_AVAILABLE:
            ttk.Button(toolbar, text="🔗 Проверить", 
                      command=self.check_urls,
                      style="Medium.TButton").pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="✓ Валидация", 
                  command=self.validate_current_playlist,
                  style="Medium.TButton").pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient='vertical').pack(side=tk.LEFT, padx=8, fill=tk.Y)
        
        ttk.Button(toolbar, text="📊 Групповые", 
                  command=self.bulk_operations,
                  style="Medium.TButton").pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient='vertical').pack(side=tk.LEFT, padx=8, fill=tk.Y)
        
        ttk.Button(toolbar, text="✕ Закрыть", 
                  command=self.close_current_tab,
                  style="Medium.TButton").pack(side=tk.LEFT, padx=2)
        
        self.tab_info = ttk.Label(toolbar, text="Вкладок: 1", 
                                 font=self.font_settings['small_font'])
        self.tab_info.pack(side=tk.RIGHT, padx=10)
    
    def _create_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
    
    def _create_status_bar(self):
        self.status_frame = ttk.Frame(self.root, height=30)
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_frame.pack_propagate(False)
        
        self.status_label = ttk.Label(self.status_frame, text="Готов", 
                                     font=self.font_settings['small_font'])
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        self.file_label = ttk.Label(self.status_frame, text="Нет открытых файлов", 
                                   font=self.font_settings['small_font'])
        self.file_label.pack(side=tk.RIGHT, padx=10)
        
        if TKDND_AVAILABLE:
            self.dnd_indicator = ttk.Label(self.status_frame, text="📁 Drag & Drop доступен", 
                                          font=self.font_settings['small_font'],
                                          foreground='green')
            self.dnd_indicator.pack(side=tk.RIGHT, padx=10)
    
    def _setup_hotkeys(self):
        self.root.bind('<Control-n>', lambda e: self.create_new_playlist())
        self.root.bind('<Control-o>', lambda e: self.open_playlist())
        self.root.bind('<Control-s>', lambda e: self.save_current())
        self.root.bind('<Control-Shift-S>', lambda e: self.save_as())
        if REQUESTS_AVAILABLE:
            self.root.bind('<Control-l>', lambda e: self.check_urls())
        self.root.bind('<Control-v>', lambda e: self.validate_current_playlist())
        self.root.bind('<Delete>', lambda e: self.delete_selected_channel())
        self.root.bind('<Insert>', lambda e: self.add_channel())
        self.root.bind('<Control-w>', lambda e: self.close_current_tab())
        self.root.bind('<Control-g>', lambda e: self.bulk_operations())
        self.root.bind('<Control-R>', lambda e: self.reset_settings_dialog())
    
    def get_current_tab(self):
        current_index = self.notebook.index(self.notebook.select())
        if current_index >= 0:
            tab_frame = self.notebook.winfo_children()[current_index]
            return self.tabs.get(tab_frame)
        return None
    
    def create_new_tab(self, file_path=None):
        tab = PlaylistTab(self.notebook, self, file_path)
        self.tabs[tab.tab_frame] = tab
        self.update_tab_info()
        return tab
    
    def bulk_operations(self):
        """Вызов групповых операций"""
        tab = self.get_current_tab()
        if not tab:
            messagebox.showwarning("Предупреждение", "Нет активной вкладки")
            return
        
        tab.bulk_ops.show_bulk_operations_dialog()
    
    def close_current_tab(self):
        tab = self.get_current_tab()
        if not tab:
            messagebox.showwarning("Предупреждение", "Нет активной вкладки")
            return
        
        if len(self.tabs) <= 1:
            messagebox.showwarning("Предупреждение", "Нельзя закрыть последнюю вкладку")
            return
        
        tab_name = os.path.basename(tab.file_path) if tab.file_path else "Новый плейлист"
        if not messagebox.askyesno("Закрыть вкладку", f"Закрыть вкладку '{tab_name}'?"):
            return
        
        if hasattr(tab, 'auto_save_manager'):
            tab.auto_save_manager.stop()
        
        self.notebook.forget(tab.tab_frame)
        
        if tab.tab_frame in self.tabs:
            del self.tabs[tab.tab_frame]
        
        self.update_tab_info()
        self.update_status(f"✅ Вкладка '{tab_name}' закрыта")
        logger.info(f"Закрыта вкладка: {tab_name}")
        
        if self.tabs:
            current_tab = self.get_current_tab()
            if current_tab and current_tab.file_path:
                tab_name = os.path.basename(current_tab.file_path)
                if len(tab_name) > 30:
                    tab_name = "..." + tab_name[-27:]
                self.file_label.config(text=f"Файл: {tab_name}")
            else:
                self.file_label.config(text="Нет открытых файлов")
    
    def create_new_playlist(self):
        self.create_new_tab()
        self.update_status("✅ Создан новый плейлист")
        logger.info("Создан новый плейлист")
    
    def open_playlist(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("M3U файлы", "*.m3u *.m3u8"), ("Все файлы", "*.*")]
        )
        
        if file_path:
            for tab in self.tabs.values():
                if tab.file_path and os.path.abspath(tab.file_path) == os.path.abspath(file_path):
                    self.notebook.select(tab.tab_frame)
                    self.update_status(f"✅ Файл уже открыт: {os.path.basename(file_path)}")
                    return
            
            tab = self.create_new_tab()
            tab.load_from_file_async(file_path)
            self.update_status(f"⏳ Загрузка файла: {os.path.basename(file_path)}...")
            logger.info(f"Открыт файл: {file_path}")
    
    def open_url_playlist(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Открыть плейлист по URL")
        dialog.geometry("550x380")
        dialog.transient(self.root)
        dialog.grab_set()
        
        dialog_font = self.font_settings['dialog_font']
        label_font = self.font_settings['caption_font']
        
        main_frame = ttk.Frame(dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main_frame, text="Введите URL плейлиста:", 
                 font=label_font).pack(pady=(0, 10))
        
        url_var = tk.StringVar()
        url_entry = ttk.Entry(main_frame, textvariable=url_var, width=50, font=dialog_font)
        url_entry.pack(pady=10, padx=20, fill=tk.X)
        
        TextFieldContextMenu.bind_context_menu(url_entry)
        
        def open_url():
            url = url_var.get().strip()
            if not url:
                messagebox.showwarning("Предупреждение", "Введите URL")
                return
            
            if not url.startswith(('http://', 'https://')):
                messagebox.showwarning("Предупреждение", "URL должен начинаться с http:// или https://")
                return
            
            dialog.destroy()
            
            for tab in self.tabs.values():
                if tab.file_path and tab.file_path == url:
                    self.notebook.select(tab.tab_frame)
                    self.update_status(f"✅ URL уже открыт: {url}")
                    return
            
            tab = self.create_new_tab()
            tab.load_from_url_async(url)
            self.update_status(f"⏳ Загрузка URL: {url}...")
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=20)
        
        ttk.Button(button_frame, text="Открыть", command=open_url,
                  style="Large.TButton").pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame, text="Отмена", command=dialog.destroy,
                  style="Large.TButton").pack(side=tk.LEFT, padx=10)
        
        url_entry.focus_set()
    
    def save_current(self):
        tab = self.get_current_tab()
        if not tab:
            messagebox.showwarning("Предупреждение", "Нет активной вкладки")
            return
        
        if tab.file_path and not tab.file_path.startswith(('http://', 'https://')):
            if tab.save_to_file():
                self.update_status("✅ Плейлист сохранен")
        else:
            self.save_as()
    
    def save_as(self):
        tab = self.get_current_tab()
        if not tab:
            messagebox.showwarning("Предупреждение", "Нет активной вкладки")
            return
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".m3u",
            filetypes=[("M3U файлы", "*.m3u"), ("M3U8 файлы", "*.m3u8")]
        )
        
        if file_path:
            if tab.save_to_file(file_path):
                self.update_status(f"✅ Плейлист сохранен как: {os.path.basename(file_path)}")
                logger.info(f"Плейлист сохранен как: {file_path}")
    
    def check_urls(self):
        tab = self.get_current_tab()
        if not tab:
            messagebox.showwarning("Предупреждение", "Нет активной вкладки")
            return
        
        messagebox.showinfo("Информация", "Функция проверки ссылок доступна в меню Операции")
    
    def validate_current_playlist(self):
        tab = self.get_current_tab()
        if not tab:
            messagebox.showwarning("Предупреждение", "Нет активной вкладки")
            return
        
        tab.validate_playlist_dialog()
    
    def add_channel(self):
        tab = self.get_current_tab()
        if tab:
            tab._clear_editor_for_new()
        else:
            messagebox.showwarning("Предупреждение", "Нет активной вкладки")
    
    def delete_selected_channel(self):
        tab = self.get_current_tab()
        if tab:
            selection = tab.tree.selection()
            if selection:
                for item in selection:
                    tab.delete_selected_channel(item)
            else:
                messagebox.showwarning("Предупреждение", "Выберите канал для удаления")
        else:
            messagebox.showwarning("Предупреждение", "Нет активной вкладки")
    
    def delete_empty_channels(self):
        tab = self.get_current_tab()
        if tab:
            tab.delete_empty_channels()
        else:
            messagebox.showwarning("Предупреждение", "Нет активной вкладки")
    
    def update_status(self, text):
        self.status_label.config(text=text)
    
    def update_tab_info(self):
        count = len(self.tabs)
        self.tab_info.config(text=f"Вкладок: {count}")
    
    def on_tab_changed(self, event):
        tab = self.get_current_tab()
        if tab and tab.file_path:
            if tab.file_path.startswith(('http://', 'https://')):
                self.file_label.config(text=f"URL: {tab.file_path[:30]}...")
            else:
                tab_name = os.path.basename(tab.file_path)
                if len(tab_name) > 30:
                    tab_name = "..." + tab_name[-27:]
                self.file_label.config(text=f"Файл: {tab_name}")
        else:
            self.file_label.config(text="Нет открытых файлов")
    
    def show_about(self):
        messagebox.showinfo("О программе", 
                          "Редактор IPTV листов\n"
                          "Версия 0.5\n\n"
                          "Управление IPTV плейлистами\n"
                          "© 2025\n\n")
    
    def show_hotkeys(self):
        hotkeys = """
        Горячие клавиши:
        
        Ctrl+N - Создать новый плейлист
        Ctrl+O - Открыть плейлист (файл)
        Ctrl+S - Сохранить текущий
        Ctrl+Shift+S - Сохранить как
        Ctrl+V - Валидация плейлиста
        Ctrl+G - Групповые операции
        Ctrl+R - Сброс настроек
        """
        
        if REQUESTS_AVAILABLE:
            hotkeys += "Ctrl+L - Проверить ссылки\n"
        
        hotkeys += """
        Insert - Добавить канал
        Delete - Удалить канал
        Ctrl+W - Закрыть текущую вкладку
        
        Двойной клик - Править канал
        Правый клик - Контекстное меню
        
        Перетаскивание файлов в окно - Открыть плейлист
        Перетаскивание внутри таблицы - Изменить порядок каналов
        """
        messagebox.showinfo("Горячие клавиши", hotkeys)
    
    def view_logs(self):
        log_file = "logs/iptv_editor.log"
        if not os.path.exists(log_file):
            messagebox.showinfo("Логи", "Файл логов не найден")
            return
        
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()
            
            log_window = tk.Toplevel(self.root)
            log_window.title("Просмотр логов")
            log_window.geometry("800x600")
            
            text_frame = ttk.Frame(log_window)
            text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            text_widget = tk.Text(text_frame, wrap=tk.WORD, 
                                 font=('Consolas', 9))
            scrollbar = ttk.Scrollbar(text_frame, command=text_widget.yview)
            text_widget.configure(yscrollcommand=scrollbar.set)
            
            text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            text_widget.insert(1.0, log_content)
            text_widget.configure(state='disabled')
            
            button_frame = ttk.Frame(log_window)
            button_frame.pack(pady=10)
            
            ttk.Button(button_frame, text="Обновить", 
                      command=lambda: self.refresh_logs(text_widget, log_file),
                      style="Medium.TButton").pack(side=tk.LEFT, padx=10)
            
            ttk.Button(button_frame, text="Очистить логи", 
                      command=lambda: self.clear_logs(log_file, text_widget),
                      style="Medium.TButton").pack(side=tk.LEFT, padx=10)
            
            ttk.Button(button_frame, text="Закрыть", 
                      command=log_window.destroy,
                      style="Medium.TButton").pack(side=tk.LEFT, padx=10)
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать файл логов:\n{str(e)}")
            logger.error(f"Ошибка чтения логов: {e}")
    
    def refresh_logs(self, text_widget, log_file):
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()
            
            text_widget.configure(state='normal')
            text_widget.delete(1.0, tk.END)
            text_widget.insert(1.0, log_content)
            text_widget.configure(state='disabled')
            text_widget.see(tk.END)
            
        except Exception as e:
            logger.error(f"Ошибка обновления логов: {e}")
    
    def clear_logs(self, log_file, text_widget):
        if not messagebox.askyesno("Подтверждение", "Очистить все логи?"):
            return
        
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write("")
            
            text_widget.configure(state='normal')
            text_widget.delete(1.0, tk.END)
            text_widget.configure(state='disabled')
            
            logger.info("Логи очищены пользователем")
            messagebox.showinfo("Успех", "Логи очищены")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось очистить логи:\n{str(e)}")
            logger.error(f"Ошибка очистки логов: {e}")
    
    def reset_settings_dialog(self):
        """Диалог сброса настроек"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Сброс настроек")
        dialog.geometry("500x400")
        dialog.transient(self.root)
        dialog.grab_set()
        
        main_frame = ttk.Frame(dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main_frame, text="Сброс настроек приложения", 
                 font=self.font_settings['title_font']).pack(pady=(0, 20))
        
        ttk.Label(main_frame, text="Выберите, какие настройки сбросить:", 
                 font=self.font_settings['caption_font']).pack(pady=(0, 10))
        
        settings_frame = ttk.LabelFrame(main_frame, text="Настройки для сброса", padding="15")
        settings_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.reset_cols_var = tk.BooleanVar(value=True)
        self.reset_ui_var = tk.BooleanVar(value=True)
        self.reset_cache_var = tk.BooleanVar(value=True)
        self.reset_logs_var = tk.BooleanVar(value=False)
        
        ttk.Checkbutton(settings_frame, text="Настройки колонок таблицы", 
                       variable=self.reset_cols_var).pack(anchor='w', pady=5)
        ttk.Checkbutton(settings_frame, text="Настройки интерфейса", 
                       variable=self.reset_ui_var).pack(anchor='w', pady=5)
        ttk.Checkbutton(settings_frame, text="Кэш изображений и URL", 
                       variable=self.reset_cache_var).pack(anchor='w', pady=5)
        ttk.Checkbutton(settings_frame, text="Файлы логов", 
                       variable=self.reset_logs_var).pack(anchor='w', pady=5)
        
        warning_frame = ttk.Frame(main_frame)
        warning_frame.pack(fill=tk.X, pady=10)
        
        warning_label = ttk.Label(warning_frame, 
                                 text="⚠️ Внимание: Это действие нельзя отменить!",
                                 font=self.font_settings['small_font'],
                                 foreground='red')
        warning_label.pack()
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=20)
        
        ttk.Button(button_frame, text="✅ Сбросить выбранные", 
                  command=lambda: self._perform_reset(dialog),
                  style="Large.TButton").pack(side=tk.LEFT, padx=10)
        
        ttk.Button(button_frame, text="❌ Отмена", 
                  command=dialog.destroy,
                  style="Large.TButton").pack(side=tk.LEFT, padx=10)
    
    def reset_settings(self):
        """Сброс всех настроек на заводские (быстрый сброс из меню)"""
        if not messagebox.askyesno("Подтверждение", 
                                 "Сбросить ВСЕ настройки приложения на заводские?\n\n"
                                 "Это действие удалит:\n"
                                 "• Настройки колонок таблицы\n"
                                 "• Настройки интерфейса\n"
                                 "• Кэш изображений и URL\n"
                                 "\n"
                                 "Действие нельзя отменить!"):
            return
        
        self._reset_settings_impl(reset_cols=True, reset_ui=True, reset_cache=True, reset_logs=False)
    
    def _perform_reset(self, dialog):
        """Выполнение сброса настроек"""
        if not messagebox.askyesno("Последнее подтверждение", 
                                 "Вы уверены, что хотите сбросить выбранные настройки?\n\n"
                                 "Это действие нельзя отменить!"):
            return
        
        dialog.destroy()
        
        reset_cols = self.reset_cols_var.get()
        reset_ui = self.reset_ui_var.get()
        reset_cache = self.reset_cache_var.get()
        reset_logs = self.reset_logs_var.get()
        
        self._reset_settings_impl(reset_cols, reset_ui, reset_cache, reset_logs)
    
    def _reset_settings_impl(self, reset_cols, reset_ui, reset_cache, reset_logs):
        """Реализация сброса настроек"""
        reset_items = []
        
        try:
            if reset_cols:
                try:
                    if os.path.exists("column_settings.json"):
                        backup_file = f"column_settings.json.backup_{int(time.time())}"
                        shutil.copy2("column_settings.json", backup_file)
                        os.remove("column_settings.json")
                        reset_items.append("Настройки колонок")
                        logger.info("Настройки колонок сброшены")
                except Exception as e:
                    logger.error(f"Ошибка сброса настроек колонок: {e}")
            
            if reset_ui:
                reset_items.append("Настройки интерфейса")
                logger.info("Настройки интерфейса сброшены")
            
            if reset_cache:
                try:
                    for tab in self.tabs.values():
                        if hasattr(tab, 'image_manager'):
                            tab.image_manager.clear_cache()
                    
                    if hasattr(self, 'link_checker'):
                        self.link_checker.cache.clear()
                    
                    reset_items.append("Кэш изображений и URL")
                    logger.info("Кэш очищен")
                except Exception as e:
                    logger.error(f"Ошибка очистки кэша: {e}")
            
            if reset_logs:
                try:
                    log_dir = "logs"
                    if os.path.exists(log_dir):
                        for file in os.listdir(log_dir):
                            if file.endswith('.log'):
                                os.remove(os.path.join(log_dir, file))
                        reset_items.append("Файлы логов")
                        logger.info("Логи очищены")
                except Exception as e:
                    logger.error(f"Ошибка очистки логов: {e}")
            
            if reset_cols:
                self.column_manager = ColumnManager()
                
                for tab in self.tabs.values():
                    tab.column_manager = self.column_manager
                    tab.update_table()
            
            if reset_items:
                message = "Сброшены следующие настройки:\n\n"
                for item in reset_items:
                    message += f"• {item}\n"
                message += "\nДля применения некоторых изменений может потребоваться перезапуск приложения."
                messagebox.showinfo("Сброс настроек", message)
                self.update_status("✅ Настройки сброшены")
            else:
                messagebox.showinfo("Сброс настроек", "Ничего не было сброшено.")
            
        except Exception as e:
            logger.error(f"Ошибка при сбросе настроек: {e}")
            messagebox.showerror("Ошибка", f"Произошла ошибка при сбросе настроек:\n{str(e)}")


def main():
    """Запуск приложения"""
    try:
        if TKDND_AVAILABLE:
            try:
                from tkinterdnd2 import TkinterDnD
                root = TkinterDnD.Tk()
            except:
                root = tk.Tk()
        else:
            root = tk.Tk()
        
        import warnings
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        
        def handle_exception(exc_type, exc_value, exc_traceback):
            logger.error("Необработанное исключение", 
                        exc_info=(exc_type, exc_value, exc_traceback))
            messagebox.showerror("Критическая ошибка", 
                               f"Произошла ошибка:\n{exc_type.__name__}: {exc_value}")
        
        sys.excepthook = handle_exception
        
        app = IPTVManager(root)
        root.mainloop()
        
    except Exception as e:
        logger.error(f"Ошибка запуска приложения: {e}")
        messagebox.showerror("Ошибка запуска", f"Не удалось запустить приложение:\n{str(e)}")


if __name__ == "__main__":
    main()
