"""
Плагин для сравнения двух плейлистов в IPTV Editor
"""

from __future__ import annotations
from plugin_system import PluginBase, PluginType
from tkinter import Toplevel, Frame, Label, Listbox, Scrollbar, Button, StringVar, TclError, Menu, BooleanVar
from tkinter import ttk, messagebox, filedialog
import os
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Set, Optional, Any
import difflib
import shutil
import re
from datetime import datetime
import json
import threading
import tkinter as tk


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
    
    @classmethod
    def from_extinf(cls, extinf_line: str, url_line: str = "", file_path: str = "") -> Channel:
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
            'file_path': self.file_path
        }


@dataclass
class ComparisonResult:
    """Результат сравнения двух плейлистов"""
    unique_in_first: List[Channel] = field(default_factory=list)
    unique_in_second: List[Channel] = field(default_factory=list)
    common_channels: List[Channel] = field(default_factory=list)
    similar_channels: List[Dict[str, Any]] = field(default_factory=list)
    different_url_channels: List[Dict[str, Any]] = field(default_factory=list)


class PlaylistComparatorPlugin(PluginBase):
    """Плагин для сравнения двух плейлистов"""
    
    def __init__(self, app):
        super().__init__(app)
        self.info.name = "Сравнение плейлистов"
        self.info.version = "1.0"
        self.info.author = "SmolNP"
        self.info.description = "Сравнение двух плейлистов для поиска уникальных, общих и похожих каналов"
        self.info.plugin_type = PluginType.MENU
        
        self.comparison_window = None
        self.first_playlist = None
        self.second_playlist = None
        self.comparison_result = None
        
        self._playlist_cache = {}
        
        self.unique_first_tree = None
        self.unique_second_tree = None
        self.common_tree = None
        self.similar_tree = None
        self.different_url_tree = None
        self.unique_first_search_var = None
        self.unique_second_search_var = None
        self.common_search_var = None
        self.similar_search_var = None
        self.different_url_search_var = None
        self.unique_first_count_label = None
        self.unique_second_count_label = None
        self.common_count_label = None
        self.similar_count_label = None
        self.different_url_count_label = None
        self.stats_label = None
        self.first_playlist_var = None
        self.second_playlist_var = None
        self.results_notebook = None
        
        self.progress_window = None
        self.progress_var = None
        self.progress_label = None
        
        self.similarity_threshold = 0.7
    
    def initialize(self):
        """Инициализация плагина"""
        print(f"[INFO] Плагин '{self.info.name}' v{self.info.version} инициализирован")
    
    def cleanup(self):
        """Очистка ресурсов плагина"""
        if self.comparison_window and self.comparison_window.winfo_exists():
            try:
                self.comparison_window.destroy()
            except TclError:
                pass
    
    def add_menu_items(self, menu):
        """Добавление пунктов меню"""
        menu.add_command(label="Сравнить плейлисты", command=self.open_comparison_tool)
    
    def open_comparison_tool(self):
        """Открыть инструмент сравнения плейлистов"""
        try:
            if self.comparison_window and self.comparison_window.winfo_exists():
                self.comparison_window.lift()
                self.comparison_window.focus()
                return
            
            self.comparison_window = Toplevel(self.app.root)
            self.comparison_window.title("Сравнение плейлистов v2.0")
            self.comparison_window.geometry("1320x800")  # Увеличенная ширина
            self.comparison_window.minsize(1000, 700)
            
            self.comparison_window.update_idletasks()
            screen_width = self.comparison_window.winfo_screenwidth()
            screen_height = self.comparison_window.winfo_screenheight()
            window_width = self.comparison_window.winfo_width()
            window_height = self.comparison_window.winfo_height()
            x = (screen_width // 2) - (window_width // 2)
            y = (screen_height // 2) - (window_height // 2)
            self.comparison_window.geometry(f'+{x}+{y}')
            
            self.comparison_window.transient(self.app.root)
            self.comparison_window.grab_set()
            
            self._create_interface()
            
            self.comparison_window.protocol("WM_DELETE_WINDOW", self.close_comparison_tool)
            
            self.comparison_window.focus_set()
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть инструмент сравнения:\n{str(e)}")
    
    def close_comparison_tool(self):
        """Закрыть инструмент сравнения"""
        if self.comparison_window:
            try:
                self.comparison_window.destroy()
            except:
                pass
            self.comparison_window = None
    
    def _save_comparison_results(self):
        """Сохранить результаты сравнения в файл"""
        if not self.comparison_result:
            messagebox.showwarning("Предупреждение", "Нет результатов для сохранения")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="Сохранить результаты сравнения",
            defaultextension=".json",
            filetypes=[("JSON файлы", "*.json"), ("Все файлы", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            data = {
                'timestamp': datetime.now().isoformat(),
                'first_playlist': {
                    'name': self.first_playlist_var.get() if self.first_playlist_var else '',
                    'channels_count': len(self.first_playlist['channels']) if self.first_playlist else 0
                },
                'second_playlist': {
                    'name': self.second_playlist_var.get() if self.second_playlist_var else '',
                    'channels_count': len(self.second_playlist['channels']) if self.second_playlist else 0
                },
                'results': {
                    'unique_in_first': [ch.to_dict() for ch in self.comparison_result.unique_in_first],
                    'unique_in_second': [ch.to_dict() for ch in self.comparison_result.unique_in_second],
                    'common_channels': [ch.to_dict() for ch in self.comparison_result.common_channels],
                    'similar_channels': [
                        {
                            'first': item['first'].to_dict(),
                            'second': item['second'].to_dict(),
                            'similarity': item.get('total_similarity', 0)
                        }
                        for item in self.comparison_result.similar_channels
                    ],
                    'different_url_channels': [
                        {
                            'first': item['first'].to_dict(),
                            'second': item['second'].to_dict()
                        }
                        for item in self.comparison_result.different_url_channels
                    ]
                }
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            messagebox.showinfo("Успех", f"Результаты сохранены в:\n{file_path}")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить результаты:\n{str(e)}")
    
    def validate_playlist(self, file_path: str) -> Tuple[bool, str]:
        """Проверить валидность плейлиста"""
        try:
            if not os.path.exists(file_path):
                return False, "Файл не существует"
            
            if os.path.getsize(file_path) == 0:
                return False, "Файл пуст"
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read(1024)
            
            if not content.startswith('#EXTM3U'):
                try:
                    with open(file_path, 'r', encoding='cp1251') as f:
                        content = f.read(1024)
                    if not content.startswith('#EXTM3U'):
                        return False, "Файл не является валидным M3U плейлистом"
                except:
                    return False, "Файл не является валидным M3U плейлистом"
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                try:
                    with open(file_path, 'r', encoding='cp1251') as f:
                        lines = f.readlines()
                except:
                    return False, "Неподдерживаемая кодировка файла"
            
            extinf_count = sum(1 for line in lines if line.startswith('#EXTINF:'))
            if extinf_count == 0:
                return False, "В плейлисте не найдены каналы"
            
            return True, f"Валидный плейлист ({extinf_count} каналов)"
            
        except IOError as e:
            return False, f"Ошибка чтения файла: {str(e)}"
        except Exception as e:
            return False, f"Неизвестная ошибка: {str(e)}"
    
    def _load_playlist(self, file_path: str, use_cache: bool = True) -> Optional[Dict]:
        """Загрузить плейлист с кэшированием"""
        try:
            if use_cache and file_path in self._playlist_cache:
                cached_data = self._playlist_cache[file_path]
                mtime = os.path.getmtime(file_path)
                if cached_data.get('mtime') == mtime:
                    return cached_data['data']
            
            is_valid, message = self.validate_playlist(file_path)
            if not is_valid:
                messagebox.showwarning("Предупреждение", 
                                     f"Файл может быть поврежден:\n{message}\n\nПопробовать загрузить все равно?")
                
                if not messagebox.askyesno("Подтверждение", "Загрузить несмотря на предупреждение?"):
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
                messagebox.showerror("Ошибка", "Не удалось определить кодировку файла")
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
            
            playlist_data = {
                'file_path': file_path,
                'channels': channels,
                'count': len(channels),
                'name': os.path.basename(file_path),
                'size': os.path.getsize(file_path),
                'mtime': os.path.getmtime(file_path),
                'encoding': encoding if 'encoding' in locals() else 'utf-8'
            }
            
            self._playlist_cache[file_path] = {
                'data': playlist_data,
                'mtime': playlist_data['mtime']
            }
            
            return playlist_data
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить плейлист:\n{str(e)}")
            return None
    
    def _create_interface(self):
        """Создание интерфейса инструмента сравнения"""
        main_frame = ttk.Frame(self.comparison_window, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        # Создание главного меню
        menubar = Menu(self.comparison_window)
        self.comparison_window.config(menu=menubar)
        
        export_menu = Menu(menubar, tearoff=0)
        export_menu.add_command(label="В файл", command=self.export_results)
        export_menu.add_separator()
        export_menu.add_command(label="Уникальные каналы из первого во второй", command=self.export_unique_first_to_second)
        export_menu.add_command(label="Уникальные каналы из второго в первый", command=self.export_unique_second_to_first)
        menubar.add_cascade(label="Экспорт", menu=export_menu)
        
        delete_menu = Menu(menubar, tearoff=0)
        delete_menu.add_command(label="Общих каналов из первого плейлиста", command=self.delete_common_from_first)
        delete_menu.add_command(label="Общих каналов из второго плейлиста", command=self.delete_common_from_second)
        menubar.add_cascade(label="Удаление", menu=delete_menu)
        
        merge_menu = Menu(menubar, tearoff=0)
        merge_menu.add_command(label="Объединить", command=self.create_combined_playlist)
        merge_menu.add_command(label="Объединить (без дубликатов)", command=self.merge_playlists_no_duplicates)
        menubar.add_cascade(label="Слияние", menu=merge_menu)
        
        quick_menu = Menu(menubar, tearoff=0)
        quick_menu.add_command(label="Инвертировать выбор", command=self.invert_selection)
        quick_menu.add_command(label="Копировать в буфер", command=self.copy_to_clipboard)
        menubar.add_cascade(label="Быстрые операции", menu=quick_menu)
        
        # edit_frame теперь расположен сразу под главным меню
        edit_frame = ttk.Frame(main_frame)
        edit_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Button(edit_frame, text="Сравнить", 
                  command=self.compare_playlists, width=15).pack(side="left", padx=(0, 10))
        ttk.Button(edit_frame, text="Обновить", 
                  command=self.refresh_playlists, width=12).pack(side="left", padx=(0, 10))
        ttk.Button(edit_frame, text="Очистить", 
                  command=self.clear_selection, width=12).pack(side="left", padx=(0, 10))
        ttk.Button(edit_frame, text="Настройки", 
                  command=self.open_settings, width=12).pack(side="left")
        
        top_frame = ttk.LabelFrame(main_frame, text="Выбор плейлистов", padding=10)
        top_frame.pack(fill="x", pady=(0, 10))
        
        row1 = ttk.Frame(top_frame)
        row1.pack(fill="x", pady=(0, 5))
        
        ttk.Label(row1, text="Первый плейлист:").pack(side="left", padx=(0, 5))
        self.first_playlist_var = StringVar(value="Не выбран")
        ttk.Label(row1, textvariable=self.first_playlist_var, width=40, 
                  relief="sunken", padding=2).pack(side="left", padx=(0, 10), fill="x", expand=True)
        
        btn_frame = ttk.Frame(row1)
        btn_frame.pack(side="left")
        
        ttk.Button(btn_frame, text="Выбрать...", 
                  command=self.select_first_playlist, width=12).pack(side="left", padx=(0, 5))
        ttk.Button(btn_frame, text="Очистить", 
                  command=lambda: self._clear_playlist('first'), width=8).pack(side="left")
        
        row2 = ttk.Frame(top_frame)
        row2.pack(fill="x", pady=(5, 0))
        
        ttk.Label(row2, text="Второй плейлист:").pack(side="left", padx=(0, 5))
        self.second_playlist_var = StringVar(value="Не выбран")
        ttk.Label(row2, textvariable=self.second_playlist_var, width=40, 
                  relief="sunken", padding=2).pack(side="left", padx=(0, 10), fill="x", expand=True)
        
        btn_frame2 = ttk.Frame(row2)
        btn_frame2.pack(side="left")
        
        ttk.Button(btn_frame2, text="Выбрать...", 
                  command=self.select_second_playlist, width=12).pack(side="left", padx=(0, 5))
        ttk.Button(btn_frame2, text="Очистить", 
                  command=lambda: self._clear_playlist('second'), width=8).pack(side="left")
        
        results_frame = ttk.Frame(main_frame)
        results_frame.pack(fill="both", expand=True)
        
        self.results_notebook = ttk.Notebook(results_frame)
        self.results_notebook.pack(fill="both", expand=True)
        
        self._create_results_tabs()
        
        stats_frame = ttk.Frame(main_frame)
        stats_frame.pack(fill="x", pady=(10, 0))
        
        self.stats_label = ttk.Label(stats_frame, text="Выберите два плейлиста для сравнения")
        self.stats_label.pack(side="left", fill="x", expand=True)
    
    def _clear_playlist(self, playlist_type: str):
        """Очистить выбранный плейлист"""
        if playlist_type == 'first':
            self.first_playlist = None
            if self.first_playlist_var:
                self.first_playlist_var.set("Не выбран")
        elif playlist_type == 'second':
            self.second_playlist = None
            if self.second_playlist_var:
                self.second_playlist_var.set("Не выбран")
        
        self.app.update_status(f"Плейлист {playlist_type} очищен")
    
    def refresh_playlists(self):
        """Обновить загруженные плейлисты"""
        if self.first_playlist:
            file_path = self.first_playlist['file_path']
            self.first_playlist = self._load_playlist(file_path, use_cache=False)
            if self.first_playlist:
                self.first_playlist_var.set(os.path.basename(file_path))
        
        if self.second_playlist:
            file_path = self.second_playlist['file_path']
            self.second_playlist = self._load_playlist(file_path, use_cache=False)
            if self.second_playlist:
                self.second_playlist_var.set(os.path.basename(file_path))
        
        self.app.update_status("Плейлисты обновлены")
    
    def open_settings(self):
        """Открыть настройки плагина"""
        settings_window = Toplevel(self.comparison_window)
        settings_window.title("Настройки сравнения")
        settings_window.geometry("400x300")
        settings_window.transient(self.comparison_window)
        
        main_frame = ttk.Frame(settings_window, padding=20)
        main_frame.pack(fill="both", expand=True)
        
        ttk.Label(main_frame, text="Порог схожести каналов (%):").pack(anchor='w', pady=(0, 5))
        similarity_var = tk.IntVar(value=int(self.similarity_threshold * 100))
        similarity_scale = ttk.Scale(
            main_frame, 
            from_=50, 
            to=95, 
            variable=similarity_var,
            orient='horizontal'
        )
        similarity_scale.pack(fill='x', pady=(0, 10))
        
        similarity_value_label = ttk.Label(main_frame, text=f"{similarity_var.get()}%")
        similarity_value_label.pack()
        
        def update_similarity_label(*args):
            similarity_value_label.config(text=f"{similarity_var.get()}%")
        
        similarity_var.trace('w', update_similarity_label)
        
        compare_url_var = BooleanVar(value=True)
        ttk.Checkbutton(
            main_frame, 
            text="Сравнивать URL при проверке общих каналов",
            variable=compare_url_var
        ).pack(anchor='w', pady=5)
        
        ignore_case_var = BooleanVar(value=True)
        ttk.Checkbutton(
            main_frame, 
            text="Игнорировать регистр при сравнении",
            variable=ignore_case_var
        ).pack(anchor='w', pady=5)
        
        auto_refresh_var = BooleanVar(value=True)
        ttk.Checkbutton(
            main_frame, 
                text="Автоматически обновлять при изменении файлов",
                variable=auto_refresh_var
        ).pack(anchor='w', pady=5)
        
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill='x', pady=(20, 0))
        
        def save_settings():
            self.similarity_threshold = similarity_var.get() / 100
            self.compare_urls = compare_url_var.get()
            self.ignore_case = ignore_case_var.get()
            self.auto_refresh = auto_refresh_var.get()
            settings_window.destroy()
            messagebox.showinfo("Сохранено", "Настройки сохранены")
        
        ttk.Button(btn_frame, text="Сохранить", command=save_settings).pack(side='right', padx=(5, 0))
        ttk.Button(btn_frame, text="Отмена", command=settings_window.destroy).pack(side='right')
    
    def _create_results_tabs(self):
        """Создание вкладок для отображения результатов"""
        tab1 = ttk.Frame(self.results_notebook)
        self.results_notebook.add(tab1, text="Уникальные в первом")
        self._create_list_with_controls(tab1, "unique_first")
        
        tab2 = ttk.Frame(self.results_notebook)
        self.results_notebook.add(tab2, text="Уникальные во втором")
        self._create_list_with_controls(tab2, "unique_second")
        
        tab3 = ttk.Frame(self.results_notebook)
        self.results_notebook.add(tab3, text="Общие каналы")
        self._create_list_with_controls(tab3, "common")
        
        tab4 = ttk.Frame(self.results_notebook)
        self.results_notebook.add(tab4, text="Похожие")
        self._create_list_with_controls(tab4, "similar")
        
        tab5 = ttk.Frame(self.results_notebook)
        self.results_notebook.add(tab5, text="Разные URL")
        self._create_list_with_controls(tab5, "different_url")
    
    def _create_list_with_controls(self, parent, list_type):
        """Создание списка с элементами управления"""
        control_frame = ttk.Frame(parent)
        control_frame.pack(fill="x", pady=(0, 5))
        
        ttk.Label(control_frame, text="Поиск:").pack(side="left", padx=(0, 5))
        search_var = StringVar()
        search_entry = ttk.Entry(control_frame, textvariable=search_var, width=30)
        search_entry.pack(side="left", padx=(0, 10))
        
        def on_search_changed(*args):
            self._filter_tree(list_type, search_var.get())
        
        search_var.trace('w', on_search_changed)
        
        action_frame = ttk.Frame(control_frame)
        action_frame.pack(side="left", fill="x", expand=True)
        
        if list_type == "unique_first":
            ttk.Button(action_frame, text="Выделить все", 
                      command=lambda: self.select_all_in_tree(self.unique_first_tree)).pack(side="left", padx=2)
            ttk.Button(action_frame, text="Экспорт в файл", 
                      command=lambda: self.export_selected_to_file(self.unique_first_tree, "unique_first")).pack(side="left", padx=2)
            self.unique_first_search_var = search_var
        elif list_type == "unique_second":
            ttk.Button(action_frame, text="Выделить все", 
                      command=lambda: self.select_all_in_tree(self.unique_second_tree)).pack(side="left", padx=2)
            ttk.Button(action_frame, text="Экспорт в файл", 
                      command=lambda: self.export_selected_to_file(self.unique_second_tree, "unique_second")).pack(side="left", padx=2)
            self.unique_second_search_var = search_var
        elif list_type == "common":
            ttk.Button(action_frame, text="Выделить все", 
                      command=lambda: self.select_all_in_tree(self.common_tree)).pack(side="left", padx=2)
            ttk.Button(action_frame, text="Экспорт в файл", 
                      command=lambda: self.export_selected_to_file(self.common_tree, "common")).pack(side="left", padx=2)
            self.common_search_var = search_var
        elif list_type == "similar":
            ttk.Button(action_frame, text="Выделить все", 
                      command=lambda: self.select_all_in_tree(self.similar_tree)).pack(side="left", padx=2)
            ttk.Button(action_frame, text="Экспорт в файл", 
                      command=lambda: self.export_selected_to_file(self.similar_tree, "similar")).pack(side="left", padx=2)
            self.similar_search_var = search_var
        elif list_type == "different_url":
            ttk.Button(action_frame, text="Выделить все", 
                      command=lambda: self.select_all_in_tree(self.different_url_tree)).pack(side="left", padx=2)
            ttk.Button(action_frame, text="Экспорт в файл", 
                      command=lambda: self.export_selected_to_file(self.different_url_tree, "different_url")).pack(side="left", padx=2)
            self.different_url_search_var = search_var
        
        count_label = ttk.Label(control_frame, text="Всего: 0")
        count_label.pack(side="right", padx=(10, 0))
        
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill="both", expand=True)
        
        columns = ("name", "group", "url", "info") if list_type in ["similar", "different_url"] else ("name", "group", "url")
        
        tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            selectmode="extended"
        )
        
        if list_type in ["similar", "different_url"]:
            tree.heading("name", text="Канал 1")
            tree.heading("group", text="Группа 1")
            tree.heading("url", text="URL 1")
            tree.heading("info", text="Канал 2 / Сходство")
            
            tree.column("name", width=200, stretch=True)
            tree.column("group", width=150, stretch=True)
            tree.column("url", width=200, stretch=True)
            tree.column("info", width=250, stretch=True)
        else:
            tree.heading("name", text="Название")
            tree.heading("group", text="Группа")
            tree.heading("url", text="URL")
            
            tree.column("name", width=250, stretch=True)
            tree.column("group", width=150, stretch=True)
            tree.column("url", width=300, stretch=True)
        
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        
        context_menu = Menu(tree, tearoff=0)
        context_menu.add_command(label="Копировать название", 
                               command=lambda: self.copy_selected_item(tree, "name"))
        context_menu.add_command(label="Копировать URL", 
                               command=lambda: self.copy_selected_item(tree, "url"))
        
        tree.bind("<Button-3>", lambda e: self.show_context_menu(e, context_menu, tree))
        
        if list_type == "unique_first":
            self.unique_first_tree = tree
            self.unique_first_count_label = count_label
        elif list_type == "unique_second":
            self.unique_second_tree = tree
            self.unique_second_count_label = count_label
        elif list_type == "common":
            self.common_tree = tree
            self.common_count_label = count_label
        elif list_type == "similar":
            self.similar_tree = tree
            self.similar_count_label = count_label
        elif list_type == "different_url":
            self.different_url_tree = tree
            self.different_url_count_label = count_label
    
    def _filter_tree(self, list_type: str, search_text: str):
        """Фильтрация дерева по поисковому запросу"""
        try:
            tree = None
            items = []
            
            if list_type == "unique_first" and self.unique_first_tree and self.comparison_result:
                tree = self.unique_first_tree
                items = self.comparison_result.unique_in_first
            elif list_type == "unique_second" and self.unique_second_tree and self.comparison_result:
                tree = self.unique_second_tree
                items = self.comparison_result.unique_in_second
            elif list_type == "common" and self.common_tree and self.comparison_result:
                tree = self.common_tree
                items = self.comparison_result.common_channels
            elif list_type == "similar" and self.similar_tree and self.comparison_result:
                tree = self.similar_tree
                items = self.comparison_result.similar_channels
            elif list_type == "different_url" and self.different_url_tree and self.comparison_result:
                tree = self.different_url_tree
                items = self.comparison_result.different_url_channels
            
            if not tree or not items:
                return
            
            for item in tree.get_children():
                tree.delete(item)
            
            search_lower = search_text.lower()
            
            if list_type in ["similar", "different_url"]:
                for idx, item in enumerate(items):
                    if search_lower in item['first'].name.lower() or \
                       search_lower in item['second'].name.lower() or \
                       search_lower in item['first'].group.lower() or \
                       search_lower in item['second'].group.lower() or \
                       (search_lower and not search_lower.strip()):
                        
                        if list_type == "similar":
                            info = f"{item['second'].name} ({item.get('total_similarity', 0):.1%})"
                        else:
                            info = item['second'].name
                        
                        tree.insert("", "end", values=(
                            item['first'].name,
                            item['first'].group,
                            item['first'].url[:50] + "..." if len(item['first'].url) > 50 else item['first'].url,
                            info
                        ))
            else:
                for idx, channel in enumerate(items):
                    if search_lower in channel.name.lower() or \
                       search_lower in channel.group.lower() or \
                       search_lower in channel.url.lower() or \
                       (search_lower and not search_lower.strip()):
                        
                        url_display = channel.url
                        if url_display and len(url_display) > 50:
                            url_display = url_display[:50] + "..."
                        
                        tree.insert("", "end", values=(
                            channel.name,
                            channel.group,
                            url_display or ""
                        ))
            
            count = len(tree.get_children())
            if list_type == "unique_first":
                self.unique_first_count_label.config(text=f"Всего: {count}")
            elif list_type == "unique_second":
                self.unique_second_count_label.config(text=f"Всего: {count}")
            elif list_type == "common":
                self.common_count_label.config(text=f"Всего: {count}")
            elif list_type == "similar":
                self.similar_count_label.config(text=f"Всего: {count}")
            elif list_type == "different_url":
                self.different_url_count_label.config(text=f"Всего: {count}")
                
        except Exception as e:
            print(f"Ошибка фильтрации: {e}")
    
    def select_first_playlist(self):
        """Выбрать первый плейлист"""
        try:
            file_path = filedialog.askopenfilename(
                title="Выберите первый плейлист",
                filetypes=[("M3U файлы", "*.m3u *.m3u8"), ("Все файлы", "*.*")]
            )
            
            if file_path:
                self.first_playlist = self._load_playlist(file_path)
                if self.first_playlist:
                    self.first_playlist_var.set(os.path.basename(file_path))
                    self.app.update_status(f"Выбран первый плейлист: {os.path.basename(file_path)} ({self.first_playlist['count']} каналов)")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось выбрать плейлист:\n{str(e)}")
    
    def select_second_playlist(self):
        """Выбрать второй плейлист"""
        try:
            file_path = filedialog.askopenfilename(
                title="Выберите второй плейлист",
                filetypes=[("M3U файлы", "*.m3u *.m3u8"), ("Все файлы", "*.*")]
            )
            
            if file_path:
                self.second_playlist = self._load_playlist(file_path)
                if self.second_playlist:
                    self.second_playlist_var.set(os.path.basename(file_path))
                    self.app.update_status(f"Выбран второй плейлист: {os.path.basename(file_path)} ({self.second_playlist['count']} каналов)")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось выбрать плейлист:\n{str(e)}")
    
    def compare_playlists(self):
        """Сравнить два плейлиста с прогресс-индикацией"""
        try:
            if not self.first_playlist or not self.second_playlist:
                messagebox.showwarning("Предупреждение", "Выберите оба плейлиста для сравнения")
                return
            
            self._show_progress_window("Идет сравнение плейлистов...")
            
            def compare_thread():
                try:
                    first_channels = self.first_playlist['channels']
                    second_channels = self.second_playlist['channels']
                    
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
                    
                    self._update_progress(30, "Поиск общих каналов...")
                    
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
                            self._update_progress(
                                30 + int(40 * idx / len(common_keys)),
                                f"Проверка URL... {idx}/{len(common_keys)}"
                            )
                    
                    unique_in_first = [first_dict[key] for key in unique_first_keys]
                    unique_in_second = [second_dict[key] for key in unique_second_keys]
                    
                    self._update_progress(70, "Поиск похожих каналов...")
                    
                    similar_channels = self._find_similar_channels(
                        first_channels, 
                        second_channels,
                        min_similarity=self.similarity_threshold
                    )
                    
                    self._update_progress(90, "Формирование результатов...")
                    
                    self.comparison_result = ComparisonResult(
                        unique_in_first=unique_in_first,
                        unique_in_second=unique_in_second,
                        common_channels=true_common,
                        similar_channels=similar_channels,
                        different_url_channels=different_url_common
                    )
                    
                    self.comparison_window.after(0, self._display_results)
                    self.comparison_window.after(0, self._update_stats)
                    self.comparison_window.after(0, self._hide_progress_window)
                    self.comparison_window.after(0, lambda: self.app.update_status("Сравнение плейлистов завершено"))
                    
                except Exception as e:
                    self.comparison_window.after(0, self._hide_progress_window)
                    self.comparison_window.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка при сравнении плейлистов:\n{str(e)}"))
            
            thread = threading.Thread(target=compare_thread, daemon=True)
            thread.start()
            
        except Exception as e:
            self._hide_progress_window()
            messagebox.showerror("Ошибка", f"Ошибка при запуске сравнения:\n{str(e)}")
    
    def _find_similar_channels(self, first_channels: List[Channel], 
                              second_channels: List[Channel], 
                              min_similarity: float = 0.7) -> List[Dict]:
        """Найти похожие каналы с улучшенным алгоритмом"""
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
                    
                    if total_similarity >= min_similarity:
                        similar.append({
                            'first': ch1,
                            'second': ch2,
                            'name_similarity': name_similarity,
                            'group_similarity': group_similarity,
                            'total_similarity': total_similarity
                        })
                        processed_pairs.add(pair_key)
                    
                    if processed % 1000 == 0:
                        self._update_progress(
                            70 + int(20 * processed / total_pairs),
                            f"Сравнение каналов... {processed}/{total_pairs}"
                        )
                        
                except Exception as e:
                    print(f"Ошибка при сравнении каналов: {e}")
        
        similar.sort(key=lambda x: x['total_similarity'], reverse=True)
        
        return similar
    
    def _show_progress_window(self, message: str):
        """Показать окно с прогресс-баром"""
        if self.progress_window and self.progress_window.winfo_exists():
            self.progress_window.destroy()
        
        self.progress_window = Toplevel(self.comparison_window)
        self.progress_window.title("Сравнение...")
        self.progress_window.geometry("400x120")
        self.progress_window.transient(self.comparison_window)
        self.progress_window.grab_set()
        
        self.progress_window.update_idletasks()
        x = self.comparison_window.winfo_x() + (self.comparison_window.winfo_width() // 2) - 200
        y = self.comparison_window.winfo_y() + (self.comparison_window.winfo_height() // 2) - 60
        self.progress_window.geometry(f'+{x}+{y}')
        
        main_frame = ttk.Frame(self.progress_window, padding=20)
        main_frame.pack(fill="both", expand=True)
        
        self.progress_label = ttk.Label(main_frame, text=message)
        self.progress_label.pack(pady=(0, 10))
        
        self.progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(
            main_frame, 
            variable=self.progress_var,
            maximum=100,
            mode='determinate'
        )
        progress_bar.pack(fill='x')
        
        self.progress_window.update()
    
    def _update_progress(self, value: int, message: str = None):
        """Обновить прогресс-бар"""
        if not self.progress_window or not self.progress_window.winfo_exists():
            return
        
        self.comparison_window.after(0, lambda: self.progress_var.set(value))
        if message and self.progress_label:
            self.comparison_window.after(0, lambda: self.progress_label.config(text=message))
        self.progress_window.update()
    
    def _hide_progress_window(self):
        """Скрыть окно с прогресс-баром"""
        if self.progress_window and self.progress_window.winfo_exists():
            try:
                self.progress_window.destroy()
            except:
                pass
            self.progress_window = None
    
    def _display_results(self):
        """Отобразить результаты сравнения"""
        try:
            if not self.comparison_result:
                return
            
            if self.unique_first_tree and self.unique_first_count_label:
                self._populate_tree(self.unique_first_tree, 
                                  self.comparison_result.unique_in_first, 
                                  self.unique_first_count_label,
                                  "unique_first")
            
            if self.unique_second_tree and self.unique_second_count_label:
                self._populate_tree(self.unique_second_tree, 
                                  self.comparison_result.unique_in_second, 
                                  self.unique_second_count_label,
                                  "unique_second")
            
            if self.common_tree and self.common_count_label:
                self._populate_tree(self.common_tree, 
                                  self.comparison_result.common_channels, 
                                  self.common_count_label,
                                  "common")
            
            if self.similar_tree and self.similar_count_label:
                self._populate_similar_tree()
            
            if self.different_url_tree and self.different_url_count_label:
                self._populate_different_url_tree()
                
        except Exception as e:
            print(f"Ошибка отображения результатов: {e}")
    
    def _populate_tree(self, tree, channels, count_label, list_type):
        """Заполнить дерево каналами"""
        try:
            for item in tree.get_children():
                tree.delete(item)
            
            for channel in channels:
                url_display = channel.url
                if url_display and len(url_display) > 50:
                    url_display = url_display[:50] + "..."
                
                tree.insert("", "end", values=(
                    channel.name,
                    channel.group,
                    url_display or ""
                ))
            
            count_label.config(text=f"Всего: {len(channels)}")
            
        except Exception as e:
            print(f"Ошибка заполнения дерева: {e}")
    
    def _populate_similar_tree(self):
        """Заполнить дерево похожими каналами"""
        try:
            if not self.similar_tree or not self.comparison_result:
                return
            
            tree = self.similar_tree
            count_label = self.similar_count_label
            
            for item in tree.get_children():
                tree.delete(item)
            
            for item in self.comparison_result.similar_channels:
                ch1 = item['first']
                ch2 = item['second']
                similarity = item['total_similarity']
                
                url1_display = ch1.url[:30] + "..." if len(ch1.url) > 30 else ch1.url
                url2_display = ch2.url[:30] + "..." if len(ch2.url) > 30 else ch2.url
                
                tree.insert("", "end", values=(
                    ch1.name,
                    ch1.group,
                    url1_display,
                    f"{ch2.name} ({similarity:.1%})"
                ))
            
            if count_label:
                count_label.config(text=f"Всего: {len(self.comparison_result.similar_channels)}")
                
        except Exception as e:
            print(f"Ошибка заполнения дерева похожих каналов: {e}")
    
    def _populate_different_url_tree(self):
        """Заполнить дерево каналами с разными URL"""
        try:
            if not self.different_url_tree or not self.comparison_result:
                return
            
            tree = self.different_url_tree
            count_label = self.different_url_count_label
            
            for item in tree.get_children():
                tree.delete(item)
            
            for item in self.comparison_result.different_url_channels:
                ch1 = item['first']
                ch2 = item['second']
                
                url1_display = ch1.url[:30] + "..." if len(ch1.url) > 30 else ch1.url
                url2_display = ch2.url[:30] + "..." if len(ch2.url) > 30 else ch2.url
                
                tree.insert("", "end", values=(
                    ch1.name,
                    ch1.group,
                    url1_display,
                    f"{ch2.name} (разные URL)"
                ))
            
            if count_label:
                count_label.config(text=f"Всего: {len(self.comparison_result.different_url_channels)}")
                
        except Exception as e:
            print(f"Ошибка заполнения дерева разных URL: {e}")
    
    def _update_stats(self):
        """Обновить статистику сравнения"""
        if not self.comparison_result or not self.stats_label:
            return
        
        try:
            first_count = len(self.first_playlist['channels']) if self.first_playlist else 0
            second_count = len(self.second_playlist['channels']) if self.second_playlist else 0
            
            stats_text = (
                f"📊 Статистика: "
                f"Первый: {first_count} | "
                f"Второй: {second_count} | "
                f"Уникальных в первом: {len(self.comparison_result.unique_in_first)} | "
                f"Уникальных во втором: {len(self.comparison_result.unique_in_second)} | "
                f"Общих: {len(self.comparison_result.common_channels)} | "
                f"Похожих: {len(self.comparison_result.similar_channels)} | "
                f"Разные URL: {len(self.comparison_result.different_url_channels)}"
            )
            
            self.stats_label.config(text=stats_text)
            
        except Exception as e:
            print(f"Ошибка обновления статистики: {e}")
    
    def clear_selection(self):
        """Очистить выбранные плейлисты и результаты"""
        try:
            self.first_playlist = None
            self.second_playlist = None
            self.comparison_result = None
            
            if self.first_playlist_var:
                self.first_playlist_var.set("Не выбран")
            if self.second_playlist_var:
                self.second_playlist_var.set("Не выбран")
            if self.stats_label:
                self.stats_label.config(text="Выберите два плейлиста для сравнения")
            
            trees = [
                self.unique_first_tree, self.unique_second_tree, 
                self.common_tree, self.similar_tree, self.different_url_tree
            ]
            count_labels = [
                self.unique_first_count_label, self.unique_second_count_label, 
                self.common_count_label, self.similar_count_label, self.different_url_count_label
            ]
            
            for tree in trees:
                if tree:
                    for item in tree.get_children():
                        tree.delete(item)
            
            for label in count_labels:
                if label:
                    label.config(text="Всего: 0")
            
            search_vars = [
                self.unique_first_search_var, self.unique_second_search_var,
                self.common_search_var, self.similar_search_var, self.different_url_search_var
            ]
            
            for var in search_vars:
                if var:
                    var.set("")
            
            self.app.update_status("Выбор плейлистов очищен")
            
        except Exception as e:
            print(f"Ошибка очистки выбора: {e}")
    
    def export_unique_first_to_second(self):
        """Экспорт уникальных каналов из первого плейлиста во второй"""
        if not self.comparison_result or not self.second_playlist:
            messagebox.showwarning("Предупреждение", "Сначала сравните плейлисты и выберите второй плейлист")
            return
        
        if not self.comparison_result.unique_in_first:
            messagebox.showinfo("Информация", "Нет уникальных каналов в первом плейлисте")
            return
        
        if not messagebox.askyesno("Подтверждение", 
                                  f"Экспортировать {len(self.comparison_result.unique_in_first)} уникальных каналов из первого плейлиста во второй?"):
            return
        
        try:
            original_file = self.second_playlist['file_path']
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
            
            self.second_playlist = self._load_playlist(original_file, use_cache=False)
            
            messagebox.showinfo("Успех", 
                              f"Экспортировано {len(self.comparison_result.unique_in_first)} уникальных каналов из первого плейлиста во второй.\n"
                              f"Создана резервная копия: {os.path.basename(backup_file)}")
            
            self.compare_playlists()
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось экспортировать каналы:\n{str(e)}")
    
    def export_unique_second_to_first(self):
        """Экспорт уникальных каналов из второго плейлиста в первый"""
        if not self.comparison_result or not self.first_playlist:
            messagebox.showwarning("Предупреждение", "Сначала сравните плейлисты и выберите первый плейлист")
            return
        
        if not self.comparison_result.unique_in_second:
            messagebox.showinfo("Информация", "Нет уникальных каналов во втором плейлисте")
            return
        
        if not messagebox.askyesno("Подтверждение", 
                                  f"Экспортировать {len(self.comparison_result.unique_in_second)} уникальных каналов из второго плейлиста в первый?"):
            return
        
        try:
            original_file = self.first_playlist['file_path']
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
            for channel in self.comparison_result.unique_in_second:
                new_lines.append(channel.extinf)
                new_lines.append(channel.url if channel.url else '')
            new_lines.extend(lines[insert_position:])
            
            with open(original_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(new_lines))
            
            self.first_playlist = self._load_playlist(original_file, use_cache=False)
            
            messagebox.showinfo("Успех", 
                              f"Экспортировано {len(self.comparison_result.unique_in_second)} уникальных каналов из второго плейлиста в первый.\n"
                              f"Создана резервная копия: {os.path.basename(backup_file)}")
            
            self.compare_playlists()
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось экспортировать каналы:\n{str(e)}")
    
    def delete_common_from_first(self):
        """Удалить общие каналы из первого плейлиста"""
        if not self.comparison_result or not self.first_playlist:
            messagebox.showwarning("Предупреждение", "Сначала сравните плейлисты и выберите первый плейлист")
            return
        
        if not self.comparison_result.common_channels:
            messagebox.showinfo("Информация", "Нет общих каналов в первом плейлисте")
            return
        
        if not messagebox.askyesno("Подтверждение", 
                                  f"Удалить {len(self.comparison_result.common_channels)} общих каналов из первого плейлиста?"):
            return
        
        try:
            original_file = self.first_playlist['file_path']
            backup_file = original_file + '.backup_' + datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(original_file, backup_file)
            
            with open(original_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.splitlines()
            i = 0
            new_lines = []
            
            common_set = set()
            for channel in self.comparison_result.common_channels:
                key = channel.key
                common_set.add(key)
            
            while i < len(lines):
                line = lines[i].strip()
                
                if line.startswith('#EXTINF:'):
                    channel_data = self._parse_extinf_line(line)
                    
                    key = f"{channel_data['name']}|{channel_data['group']}".lower()
                    
                    if key in common_set:
                        i += 1
                        while i < len(lines) and (not lines[i].strip() or lines[i].startswith('#')):
                            i += 1
                        if i < len(lines) and not lines[i].startswith('#'):
                            i += 1
                        continue
                    else:
                        new_lines.append(line)
                        i += 1
                        if i < len(lines) and not lines[i].startswith('#'):
                            new_lines.append(lines[i])
                            i += 1
                else:
                    new_lines.append(line)
                    i += 1
            
            with open(original_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(new_lines))
            
            self.first_playlist = self._load_playlist(original_file, use_cache=False)
            
            messagebox.showinfo("Успех", 
                              f"Удалено {len(self.comparison_result.common_channels)} общих каналов из первого плейлиста.\n"
                              f"Создана резервная копия: {os.path.basename(backup_file)}")
            
            self.compare_playlists()
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось удалить каналы:\n{str(e)}")
    
    def delete_common_from_second(self):
        """Удалить общие каналы из второго плейлиста"""
        if not self.comparison_result or not self.second_playlist:
            messagebox.showwarning("Предупреждение", "Сначала сравните плейлисты и выберите второй плейлист")
            return
        
        if not self.comparison_result.common_channels:
            messagebox.showinfo("Информация", "Нет общих каналов во втором плейлисте")
            return
        
        if not messagebox.askyesno("Подтверждение", 
                                  f"Удалить {len(self.comparison_result.common_channels)} общих каналов из второго плейлиста?"):
            return
        
        try:
            original_file = self.second_playlist['file_path']
            backup_file = original_file + '.backup_' + datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(original_file, backup_file)
            
            with open(original_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.splitlines()
            i = 0
            new_lines = []
            
            common_set = set()
            for channel in self.comparison_result.common_channels:
                key = channel.key
                common_set.add(key)
            
            while i < len(lines):
                line = lines[i].strip()
                
                if line.startswith('#EXTINF:'):
                    channel_data = self._parse_extinf_line(line)
                    
                    key = f"{channel_data['name']}|{channel_data['group']}".lower()
                    
                    if key in common_set:
                        i += 1
                        while i < len(lines) and (not lines[i].strip() or lines[i].startswith('#')):
                            i += 1
                        if i < len(lines) and not lines[i].startswith('#'):
                            i += 1
                        continue
                    else:
                        new_lines.append(line)
                        i += 1
                        if i < len(lines) and not lines[i].startswith('#'):
                            new_lines.append(lines[i])
                            i += 1
                else:
                    new_lines.append(line)
                    i += 1
            
            with open(original_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(new_lines))
            
            self.second_playlist = self._load_playlist(original_file, use_cache=False)
            
            messagebox.showinfo("Успех", 
                              f"Удалено {len(self.comparison_result.common_channels)} общих каналов из второго плейлиста.\n"
                              f"Создана резервная копия: {os.path.basename(backup_file)}")
            
            self.compare_playlists()
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось удалить каналы:\n{str(e)}")
    
    def merge_playlists_no_duplicates(self):
        """Объединить плейлисты, исключив общие каналы"""
        if not self.comparison_result or not self.first_playlist or not self.second_playlist:
            messagebox.showwarning("Предупреждение", "Сначала сравните оба плейлиста")
            return
        
        default_name = f"merged_{os.path.basename(self.first_playlist['file_path'])}"
        file_path = filedialog.asksaveasfilename(
            title="Сохранить объединенный плейлист",
            defaultextension=".m3u",
            initialfile=default_name,
            filetypes=[("M3U файлы", "*.m3u"), ("M3U8 файлы", "*.m3u8"), ("Все файлы", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            all_unique_channels = []
            
            all_unique_channels.extend(self.comparison_result.unique_in_first)
            all_unique_channels.extend(self.comparison_result.unique_in_second)
            all_unique_channels.extend(self.comparison_result.common_channels)
            
            if not all_unique_channels:
                messagebox.showwarning("Предупреждение", "Нет каналов для объединения")
                return
            
            if not messagebox.askyesno("Подтверждение", 
                                      f"Создать объединенный плейлист из {len(all_unique_channels)} уникальных каналов?"):
                return
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('#EXTM3U\n')
                for channel in all_unique_channels:
                    f.write(channel.extinf + '\n')
                    f.write(channel.url + '\n' if channel.url else '\n')
            
            messagebox.showinfo("Успех", 
                              f"Создан объединенный плейлист из {len(all_unique_channels)} каналов.\n"
                              f"Файл: {os.path.basename(file_path)}")
            
            self._open_playlist_in_editor(file_path)
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось объединить плейлисты:\n{str(e)}")
    
    def create_combined_playlist(self):
        """Создать новый плейлист с каналами из обоих плейлистов"""
        if not self.first_playlist or not self.second_playlist:
            messagebox.showwarning("Предупреждение", "Сначала выберите оба плейлиста")
            return
        
        default_name = f"combined_{os.path.basename(self.first_playlist['file_path'])}"
        file_path = filedialog.asksaveasfilename(
            title="Сохранить комбинированный плейлист",
            defaultextension=".m3u",
            initialfile=default_name,
            filetypes=[("M3U файлы", "*.m3u"), ("M3U8 файлы", "*.m3u8"), ("Все файлы", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            first_channels = self._load_all_channels(self.first_playlist['file_path'])
            second_channels = self._load_all_channels(self.second_playlist['file_path'])
            
            all_channels = first_channels + second_channels
            
            if not all_channels:
                messagebox.showwarning("Предупреждение", "Нет каналов для объединения")
                return
            
            if not messagebox.askyesno("Подтверждение", 
                                      f"Создать комбинированный плейлист из {len(all_channels)} каналов?"):
                return
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('#EXTM3U\n')
                for channel in all_channels:
                    f.write(channel.extinf + '\n')
                    f.write(channel.url + '\n' if channel.url else '\n')
            
            messagebox.showinfo("Успех", 
                              f"Создан комбинированный плейлист из {len(all_channels)} каналов.\n"
                              f"Файл: {os.path.basename(file_path)}")
            
            self._open_playlist_in_editor(file_path)
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось создать комбинированный плейлист:\n{str(e)}")
    
    def invert_selection(self):
        """Инвертировать выделение в активной вкладке"""
        if not self.results_notebook:
            return
        
        current_tab = self.results_notebook.index(self.results_notebook.select())
        
        trees = [
            self.unique_first_tree,
            self.unique_second_tree,
            self.common_tree,
            self.similar_tree,
            self.different_url_tree
        ]
        
        if 0 <= current_tab < len(trees) and trees[current_tab]:
            tree = trees[current_tab]
            all_items = tree.get_children()
            selected_items = tree.selection()
            
            to_select = [item for item in all_items if item not in selected_items]
            tree.selection_set(to_select)
    
    def copy_to_clipboard(self):
        """Скопировать выделенные каналы в буфер обмена"""
        if not self.results_notebook:
            return
        
        current_tab = self.results_notebook.index(self.results_notebook.select())
        
        trees = [
            self.unique_first_tree,
            self.unique_second_tree,
            self.common_tree,
            self.similar_tree,
            self.different_url_tree
        ]
        
        if 0 <= current_tab < len(trees) and trees[current_tab]:
            tree = trees[current_tab]
            selected_items = tree.selection()
            
            if not selected_items:
                messagebox.showwarning("Предупреждение", "Выберите каналы для копирования")
                return
            
            clipboard_text = ""
            for item in selected_items:
                values = tree.item(item, 'values')
                if values:
                    if current_tab in [3, 4]:
                        clipboard_text += f"{values[0]} ({values[1]}) -> {values[3]}\n"
                    else:
                        clipboard_text += f"{values[0]} ({values[1]})\n"
            
            if clipboard_text:
                self.comparison_window.clipboard_clear()
                self.comparison_window.clipboard_append(clipboard_text)
                self.app.update_status(f"Скопировано {len(selected_items)} каналов в буфер обмена")
    
    def _parse_extinf_line(self, line):
        """Парсит строку EXTINF и возвращает данные канала"""
        channel_data = {
            'name': '',
            'group': 'Без группы',
            'tvg_id': '',
            'tvg_logo': ''
        }
        
        if ',' in line:
            parts = line.split(',', 1)
            channel_data['name'] = parts[1].strip()
        
        attrs_part = line.split(',')[0] if ',' in line else line
        
        tvg_id_match = re.search(r'tvg-id="([^"]*)"', attrs_part)
        if tvg_id_match:
            channel_data['tvg_id'] = tvg_id_match.group(1)
        
        logo_match = re.search(r'tvg-logo="([^"]*)"', attrs_part)
        if logo_match:
            channel_data['tvg_logo'] = logo_match.group(1)
        
        group_match = re.search(r'group-title="([^"]*)"', attrs_part)
        if group_match:
            channel_data['group'] = group_match.group(1)
        
        return channel_data
    
    def _load_all_channels(self, file_path):
        """Загружает все каналы из файла плейлиста"""
        playlist = self._load_playlist(file_path)
        return playlist['channels'] if playlist else []
    
    def _open_playlist_in_editor(self, file_path):
        """Открывает плейлист в основном редакторе"""
        try:
            if hasattr(self.app, 'create_new_tab'):
                self.app.create_new_tab(file_path)
                self.app.update_status(f"Открыт плейлист: {os.path.basename(file_path)}")
        except Exception as e:
            print(f"Ошибка открытия плейлиста в редакторе: {e}")
    
    def select_all_in_tree(self, tree):
        """Выделить все элементы в дереве"""
        if tree:
            tree.selection_set(tree.get_children())
    
    def export_selected_to_file(self, tree, list_type):
        """Экспортировать выбранные каналы в файл"""
        if not tree:
            return
        
        selection = tree.selection()
        if not selection:
            messagebox.showwarning("Предупреждение", "Выберите каналы для экспорта")
            return
        
        source_list = None
        if list_type == "unique_first" and self.comparison_result:
            source_list = self.comparison_result.unique_in_first
        elif list_type == "unique_second" and self.comparison_result:
            source_list = self.comparison_result.unique_in_second
        elif list_type == "common" and self.comparison_result:
            source_list = self.comparison_result.common_channels
        elif list_type == "similar" and self.comparison_result:
            source_list = self.comparison_result.similar_channels
        elif list_type == "different_url" and self.comparison_result:
            source_list = self.comparison_result.different_url_channels
        
        if not source_list:
            return
        
        file_path = filedialog.asksaveasfilename(
            title="Экспорт выбранных каналов",
            defaultextension=".m3u",
            filetypes=[("M3U файлы", "*.m3u"), ("Текстовые файлы", "*.txt"), ("Все файлы", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            selected_channels = []
            
            if list_type in ["similar", "different_url"]:
                for item_id in selection:
                    idx = tree.index(item_id)
                    if 0 <= idx < len(source_list):
                        item = source_list[idx]
                        selected_channels.append(item['first'])
                        selected_channels.append(item['second'])
            else:
                for item_id in selection:
                    idx = tree.index(item_id)
                    if 0 <= idx < len(source_list):
                        selected_channels.append(source_list[idx])
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('#EXTM3U\n')
                for channel in selected_channels:
                    if hasattr(channel, 'extinf'):
                        f.write(channel.extinf + '\n')
                        f.write(channel.url + '\n' if channel.url else '\n')
            
            messagebox.showinfo("Успех", f"Экспортировано {len(selected_channels)} каналов")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось экспортировать каналы:\n{str(e)}")
    
    def show_context_menu(self, event, menu, tree):
        """Показать контекстное меню"""
        try:
            item = tree.identify_row(event.y)
            if item:
                tree.selection_set(item)
                menu.tk_popup(event.x_root, event.y_root)
        except:
            pass
    
    def copy_selected_item(self, tree, column):
        """Копировать выбранный элемент"""
        try:
            selection = tree.selection()
            if selection:
                item = tree.item(selection[0])
                if column == "name":
                    value = item["values"][0]
                elif column == "url":
                    value = item["values"][2] if len(item["values"]) > 2 else ""
                else:
                    return
                
                self.comparison_window.clipboard_clear()
                self.comparison_window.clipboard_append(value)
                self.app.update_status(f"Скопировано: {value[:50]}...")
        except:
            pass
    
    def export_results(self):
        """Экспортировать результаты сравнения"""
        try:
            if not self.comparison_result:
                messagebox.showwarning("Предупреждение", "Нет результатов для экспорта")
                return
            
            format_dialog = Toplevel(self.comparison_window)
            format_dialog.title("Формат экспорта")
            format_dialog.geometry("400x300")
            format_dialog.transient(self.comparison_window)
            
            format_dialog.update_idletasks()
            x = self.comparison_window.winfo_x() + (self.comparison_window.winfo_width() // 2) - 200
            y = self.comparison_window.winfo_y() + (self.comparison_window.winfo_height() // 2) - 150
            format_dialog.geometry(f'+{x}+{y}')
            
            main_frame = ttk.Frame(format_dialog, padding=20)
            main_frame.pack(fill="both", expand=True)
            
            format_var = StringVar(value="txt")
            
            formats = [
                ("Текстовый файл (.txt)", "txt"),
                ("CSV файл (.csv)", "csv"),
                ("HTML отчет (.html)", "html"),
                ("JSON файл (.json)", "json"),
                ("M3U плейлист (.m3u)", "m3u")
            ]
            
            ttk.Label(main_frame, text="Выберите формат экспорта:").pack(anchor='w', pady=(0, 10))
            
            for i, (text, value) in enumerate(formats):
                ttk.Radiobutton(
                    main_frame, 
                    text=text, 
                    variable=format_var, 
                    value=value
                ).pack(anchor='w', padx=5, pady=2)
            
            ttk.Label(main_frame, text="Что экспортировать:").pack(anchor='w', pady=(10, 5))
            
            include_unique_var = BooleanVar(value=True)
            include_common_var = BooleanVar(value=False)
            include_similar_var = BooleanVar(value=False)
            include_different_url_var = BooleanVar(value=False)
            
            ttk.Checkbutton(
                main_frame, 
                text="Уникальные каналы", 
                variable=include_unique_var
            ).pack(anchor='w', padx=20)
            
            ttk.Checkbutton(
                main_frame, 
                text="Общие каналы", 
                variable=include_common_var
            ).pack(anchor='w', padx=20)
            
            ttk.Checkbutton(
                main_frame, 
                text="Похожие каналы", 
                variable=include_similar_var
            ).pack(anchor='w', padx=20)
            
            ttk.Checkbutton(
                main_frame, 
                text="Каналы с разными URL", 
                variable=include_different_url_var
            ).pack(anchor='w', padx=20)
            
            def do_export():
                format_type = format_var.get()
                format_dialog.destroy()
                
                filetypes = {
                    "txt": [("Текстовые файлы", "*.txt")],
                    "csv": [("CSV файлы", "*.csv")],
                    "html": [("HTML файлы", "*.html")],
                    "json": [("JSON файлы", "*.json")],
                    "m3u": [("M3У плейлисты", "*.m3u *.m3u8")]
                }
                
                default_ext = {
                    "txt": ".txt",
                    "csv": ".csv",
                    "html": ".html",
                    "json": ".json",
                    "m3u": ".m3u"
                }
                
                file_path = filedialog.asksaveasfilename(
                    defaultextension=default_ext[format_type],
                    filetypes=filetypes[format_type] + [("Все файлы", "*.*")]
                )
                
                if file_path:
                    self._perform_export(
                        file_path, 
                        format_type,
                        include_unique_var.get(),
                        include_common_var.get(),
                        include_similar_var.get(),
                        include_different_url_var.get()
                    )
            
            btn_frame = ttk.Frame(main_frame)
            btn_frame.pack(fill='x', pady=(20, 0))
            
            ttk.Button(btn_frame, text="Экспортировать", command=do_export).pack(side='right', padx=(5, 0))
            ttk.Button(btn_frame, text="Отмена", command=format_dialog.destroy).pack(side='right')
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось экспортировать результаты:\n{str(e)}")
    
    def _perform_export(self, file_path: str, format_type: str, include_unique: bool, 
                       include_common: bool, include_similar: bool, include_different_url: bool):
        """Выполнить экспорт в выбранный формат"""
        try:
            if format_type == 'csv':
                self._export_to_csv(file_path, include_unique, include_common, include_similar, include_different_url)
            elif format_type == 'html':
                self._export_to_html(file_path, include_unique, include_common, include_similar, include_different_url)
            elif format_type == 'json':
                self._export_to_json(file_path, include_unique, include_common, include_similar, include_different_url)
            elif format_type == 'm3u':
                self._export_to_m3u(file_path, include_unique, include_common, include_similar, include_different_url)
            else:
                self._export_to_txt(file_path, include_unique, include_common, include_similar, include_different_url)
            
            messagebox.showinfo("Успех", f"Результаты экспортированы в:\n{file_path}")
            self.app.update_status(f"Экспорт завершен: {os.path.basename(file_path)}")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось экспортировать результаты:\n{str(e)}")
    
    def _export_to_txt(self, file_path: str, include_unique: bool, include_common: bool, 
                      include_similar: bool, include_different_url: bool):
        """Экспорт в текстовый файл"""
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("СРАВНЕНИЕ ПЛЕЙЛИСТОВ\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"Дата сравнения: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Первый плейлист: {self.first_playlist_var.get() if self.first_playlist_var else 'Не выбран'}\n")
            f.write(f"Второй плейлиста: {self.second_playlist_var.get() if self.second_playlist_var else 'Не выбран'}\n\n")
            
            f.write("СТАТИСТИКА:\n")
            f.write("-" * 40 + "\n")
            f.write(f"Всего в первом плейлисте: {len(self.first_playlist['channels']) if self.first_playlist else 0}\n")
            f.write(f"Всего во втором плейлисте: {len(self.second_playlist['channels']) if self.second_playlist else 0}\n")
            f.write(f"Уникальных в первом: {len(self.comparison_result.unique_in_first)}\n")
            f.write(f"Уникальных во втором: {len(self.comparison_result.unique_in_second)}\n")
            f.write(f"Общих каналов: {len(self.comparison_result.common_channels)}\n")
            f.write(f"Похожих каналов: {len(self.comparison_result.similar_channels)}\n")
            f.write(f"Каналов с разными URL: {len(self.comparison_result.different_url_channels)}\n\n")
            
            if include_unique and self.comparison_result.unique_in_first:
                f.write("УНИКАЛЬНЫЕ КАНАЛЫ В ПЕРВОМ ПЛЕЙЛИСТЕ:\n")
                f.write("-" * 40 + "\n")
                for i, channel in enumerate(self.comparison_result.unique_in_first, 1):
                    f.write(f"{i:3}. {channel.name} | {channel.group} | {channel.url[:80]}...\n" 
                           if len(channel.url) > 80 else 
                           f"{i:3}. {channel.name} | {channel.group} | {channel.url}\n")
                f.write("\n")
            
            if include_unique and self.comparison_result.unique_in_second:
                f.write("УНИКАЛЬНЫЕ КАНАЛЫ ВО ВТОРОМ ПЛЕЙЛИСТЕ:\n")
                f.write("-" * 40 + "\n")
                for i, channel in enumerate(self.comparison_result.unique_in_second, 1):
                    f.write(f"{i:3}. {channel.name} | {channel.group} | {channel.url[:80]}...\n" 
                           if len(channel.url) > 80 else 
                           f"{i:3}. {channel.name} | {channel.group} | {channel.url}\n")
                f.write("\n")
            
            if include_common and self.comparison_result.common_channels:
                f.write("ОБЩИЕ КАНАЛЫ:\n")
                f.write("-" * 40 + "\n")
                for i, channel in enumerate(self.comparison_result.common_channels, 1):
                    f.write(f"{i:3}. {channel.name} | {channel.group} | {channel.url[:80]}...\n" 
                           if len(channel.url) > 80 else 
                           f"{i:3}. {channel.name} | {channel.group} | {channel.url}\n")
                f.write("\n")
            
            if include_similar and self.comparison_result.similar_channels:
                f.write("ПОХОЖИЕ КАНАЛЫ:\n")
                f.write("-" * 40 + "\n")
                for i, item in enumerate(self.comparison_result.similar_channels, 1):
                    ch1 = item['first']
                    ch2 = item['second']
                    similarity = item.get('total_similarity', 0)
                    f.write(f"{i:3}. {ch1.name} ({ch1.group}) - {ch2.name} ({ch2.group}) - Сходство: {similarity:.1%}\n")
                f.write("\n")
            
            if include_different_url and self.comparison_result.different_url_channels:
                f.write("КАНАЛЫ С РАЗНЫМИ URL:\n")
                f.write("-" * 40 + "\n")
                for i, item in enumerate(self.comparison_result.different_url_channels, 1):
                    ch1 = item['first']
                    ch2 = item['second']
                    f.write(f"{i:3}. {ch1.name} ({ch1.group})\n")
                    f.write(f"     URL1: {ch1.url}\n")
                    f.write(f"     URL2: {ch2.url}\n")
                f.write("\n")
    
    def _export_to_csv(self, file_path: str, include_unique: bool, include_common: bool, 
                      include_similar: bool, include_different_url: bool):
        """Экспорт в CSV файл"""
        import csv
        
        with open(file_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            
            writer.writerow(["Сравнение плейлистов"])
            writer.writerow([f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
            writer.writerow([f"Первый плейлист: {self.first_playlist_var.get() if self.first_playlist_var else ''}"])
            writer.writerow([f"Второй плейлист: {self.second_playlist_var.get() if self.second_playlist_var else ''}"])
            writer.writerow([])
            
            writer.writerow(["Статистика"])
            writer.writerow(["Параметр", "Значение"])
            writer.writerow(["Всего в первом", len(self.first_playlist['channels']) if self.first_playlist else 0])
            writer.writerow(["Всего во втором", len(self.second_playlist['channels']) if self.second_playlist else 0])
            writer.writerow(["Уникальных в первом", len(self.comparison_result.unique_in_first)])
            writer.writerow(["Уникальных во втором", len(self.comparison_result.unique_in_second)])
            writer.writerow(["Общих", len(self.comparison_result.common_channels)])
            writer.writerow(["Похожих", len(self.comparison_result.similar_channels)])
            writer.writerow(["Разные URL", len(self.comparison_result.different_url_channels)])
            writer.writerow([])
            
            if include_unique and self.comparison_result.unique_in_first:
                writer.writerow(["Уникальные в первом плейлисте"])
                writer.writerow(["Название", "Группа", "URL"])
                for channel in self.comparison_result.unique_in_first:
                    writer.writerow([channel.name, channel.group, channel.url])
                writer.writerow([])
            
            if include_unique and self.comparison_result.unique_in_second:
                writer.writerow(["Уникальные во втором плейлисте"])
                writer.writerow(["Название", "Группа", "URL"])
                for channel in self.comparison_result.unique_in_second:
                    writer.writerow([channel.name, channel.group, channel.url])
                writer.writerow([])
    
    def _export_to_html(self, file_path: str, include_unique: bool, include_common: bool, 
                       include_similar: bool, include_different_url: bool):
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
                <tr><td>Первый плейлист:</td><td><b>{self.first_playlist_var.get() if self.first_playlist_var else ''}</b></td></tr>
                <tr><td>Второй плейлист:</td><td><b>{self.second_playlist_var.get() if self.second_playlist_var else ''}</b></td></tr>
                <tr><td>Всего каналов в первом:</td><td>{len(self.first_playlist['channels']) if self.first_playlist else 0}</td></tr>
                <tr><td>Всего каналов во втором:</td><td>{len(self.second_playlist['channels']) if self.second_playlist else 0}</td></tr>
                <tr><td>Уникальных в первом:</td><td>{len(self.comparison_result.unique_in_first)}</td></tr>
                <tr><td>Уникальных во втором:</td><td>{len(self.comparison_result.unique_in_second)}</td></tr>
                <tr><td>Общих каналов:</td><td>{len(self.comparison_result.common_channels)}</td></tr>
                <tr><td>Похожих каналов:</td><td>{len(self.comparison_result.similar_channels)}</td></tr>
                <tr><td>Каналов с разными URL:</td><td>{len(self.comparison_result.different_url_channels)}</td></tr>
            </table>
        </div>
"""
        
        if include_unique and self.comparison_result.unique_in_first:
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
        
        if include_unique and self.comparison_result.unique_in_second:
            html += """
        <div class="section">
            <h2>🎯 Уникальные каналы во втором плейлисте</h2>
            <table>
                <tr><th>#</th><th>Название</th><th>Группа</th><th>URL</th></tr>
"""
            for i, channel in enumerate(self.comparison_result.unique_in_second, 1):
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
        
        if include_common and self.comparison_result.common_channels:
            html += """
        <div class="section">
            <h2>🤝 Общие каналы</h2>
            <table>
                <tr><th>#</th><th>Название</th><th>Группа</th><th>URL</th></tr>
"""
            for i, channel in enumerate(self.comparison_result.common_channels, 1):
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
    
    def _export_to_json(self, file_path: str, include_unique: bool, include_common: bool, 
                       include_similar: bool, include_different_url: bool):
        """Экспорт в JSON файл"""
        data = {
            'timestamp': datetime.now().isoformat(),
            'first_playlist': {
                'name': self.first_playlist_var.get() if self.first_playlist_var else '',
                'file_path': self.first_playlist['file_path'] if self.first_playlist else '',
                'channels_count': len(self.first_playlist['channels']) if self.first_playlist else 0
            },
            'second_playlist': {
                'name': self.second_playlist_var.get() if self.second_playlist_var else '',
                'file_path': self.second_playlist['file_path'] if self.second_playlist else '',
                'channels_count': len(self.second_playlist['channels']) if self.second_playlist else 0
            },
            'statistics': {
                'unique_in_first': len(self.comparison_result.unique_in_first),
                'unique_in_second': len(self.comparison_result.unique_in_second),
                'common_channels': len(self.comparison_result.common_channels),
                'similar_channels': len(self.comparison_result.similar_channels),
                'different_url_channels': len(self.comparison_result.different_url_channels)
            }
        }
        
        if include_unique:
            data['unique_in_first_channels'] = [ch.to_dict() for ch in self.comparison_result.unique_in_first]
            data['unique_in_second_channels'] = [ch.to_dict() for ch in self.comparison_result.unique_in_second]
        
        if include_common:
            data['common_channels_list'] = [ch.to_dict() for ch in self.comparison_result.common_channels]
        
        if include_similar:
            data['similar_channels_list'] = [
                {
                    'first': item['first'].to_dict(),
                    'second': item['second'].to_dict(),
                    'similarity': item.get('total_similarity', 0)
                }
                for item in self.comparison_result.similar_channels
            ]
        
        if include_different_url:
            data['different_url_channels_list'] = [
                {
                    'first': item['first'].to_dict(),
                    'second': item['second'].to_dict()
                }
                for item in self.comparison_result.different_url_channels
            ]
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _export_to_m3u(self, file_path: str, include_unique: bool, include_common: bool, 
                      include_similar: bool, include_different_url: bool):
        """Экспорт в M3U плейлист"""
        channels = []
        
        if include_unique:
            channels.extend(self.comparison_result.unique_in_first)
            channels.extend(self.comparison_result.unique_in_second)
        
        if include_common:
            channels.extend(self.comparison_result.common_channels)
        
        if include_similar:
            for item in self.comparison_result.similar_channels:
                channels.append(item['first'])
                channels.append(item['second'])
        
        if include_different_url:
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
