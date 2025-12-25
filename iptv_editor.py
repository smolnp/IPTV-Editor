import tkinter as tk
from tkinter import ttk, filedialog, messagebox, Menu
import os
import re
from datetime import datetime
import winreg
import ctypes
import platform
import sys
from typing import Optional, List, Dict

# Получаем абсолютный путь к директории, где находится основной файл программы
if getattr(sys, 'frozen', False):
    # Если программа запущена как исполняемый файл (exe)
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Если программа запущена из исходного кода
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PLUGINS_DIR = os.path.join(BASE_DIR, "plugins")

# Добавляем путь к текущей директории для импорта плагинов
sys.path.insert(0, BASE_DIR)

try:
    from plugin_system import PluginManager, PluginBase, MenuPlugin, ToolbarPlugin, ExportPlugin, FilterPlugin, TabPlugin
    PLUGIN_SYSTEM_AVAILABLE = True
except ImportError:
    PLUGIN_SYSTEM_AVAILABLE = False
    print("Плагинная система недоступна. Функционал плагинов будет отключен.")
    print(f"BASE_DIR: {BASE_DIR}")
    print(f"PLUGINS_DIR: {PLUGINS_DIR}")


class WindowsThemeManager:
    """Менеджер тем Windows для чтения настроек из реестра"""
    
    @staticmethod
    def get_system_dpi_scale():
        """Получение масштаба DPI из реестра Windows"""
        try:
            if platform.system() != "Windows":
                return 1.0
                
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop")
            value, _ = winreg.QueryValueEx(key, "LogPixels")
            winreg.CloseKey(key)
            return value / 96.0
        except:
            return 1.0
    
    @staticmethod
    def get_menu_font():
        """Получение шрифта меню из реестра Windows"""
        try:
            if platform.system() != "Windows":
                return "Segoe UI", 11
                
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop\WindowMetrics")
            data, _ = winreg.QueryValueEx(key, "MenuFont")
            winreg.CloseKey(key)
            
            font_size_pt = int.from_bytes(data[:4], byteorder='little')
            if font_size_pt < 0:
                font_size_pt = -font_size_pt
            
            font_size_pt = max(font_size_pt, 11)
            
            font_name = data[4:].decode('utf-16le').split('\x00')[0]
            return font_name, font_size_pt
        except:
            return "Segoe UI", 11
    
    @staticmethod
    def get_system_colors():
        """Получение системных цветов"""
        colors = {}
        try:
            if platform.system() != "Windows":
                return colors
                
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM")
            try:
                accent_color, _ = winreg.QueryValueEx(key, "AccentColor")
                colors['accent'] = accent_color
            except:
                pass
            winreg.CloseKey(key)
        except:
            pass
        return colors
    
    @staticmethod
    def get_dialog_font():
        """Получение шрифта диалогов"""
        try:
            if platform.system() != "Windows":
                return "Segoe UI", 11
                
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop\WindowMetrics")
            data, _ = winreg.QueryValueEx(key, "MessageFont")
            winreg.CloseKey(key)
            
            font_size_pt = int.from_bytes(data[:4], byteorder='little')
            if font_size_pt < 0:
                font_size_pt = -font_size_pt
            
            font_size_pt = max(font_size_pt, 11)
            
            font_name = data[4:].decode('utf-16le').split('\x00')[0]
            return font_name, font_size_pt
        except:
            return "Segoe UI", 11
    
    @staticmethod
    def get_hotkeys():
        """Получение системных горячих клавиш"""
        hotkeys = {
            'open': '<Control-o>',
            'save': '<Control-s>',
            'save_as': '<Control-Shift-S>',
            'new': '<Control-n>',
            'find': '<Control-f>',
            'add': '<Control-a>',
            'delete': '<Delete>',
            'exit': '<Alt-F4>'
        }
        return hotkeys


class ChannelData:
    """Класс для хранения данных о канале"""
    
    def __init__(self):
        self.name = ""
        self.group = ""
        self.tvg_id = ""
        self.tvg_logo = ""
        self.url = ""
        self.extinf = ""
        self.has_url = True
    
    def __repr__(self):
        return f"ChannelData(name='{self.name}', group='{self.group}')"


class TextContextMenu:
    """Класс для контекстного меню текстовых полей"""
    
    @staticmethod
    def create_context_menu(widget):
        """Создает контекстное меню для виджета"""
        menu = Menu(widget, tearoff=0)
        
        menu.add_command(label="Отменить", 
                        command=lambda: widget.event_generate("<<Undo>>"))
        menu.add_command(label="Повторить", 
                        command=lambda: widget.event_generate("<<Redo>>"))
        menu.add_separator()
        menu.add_command(label="Вырезать", 
                        command=lambda: widget.event_generate("<<Cut>>"))
        menu.add_command(label="Копировать", 
                        command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Вставить", 
                        command=lambda: widget.event_generate("<<Paste>>"))
        menu.add_command(label="Удалить", 
                        command=lambda: widget.select_range(0, tk.END) or widget.delete(0, tk.END))
        menu.add_separator()
        menu.add_command(label="Выделить всё", 
                        command=lambda: widget.select_range(0, tk.END))
        
        widget.bind("<Button-3>", lambda e: TextContextMenu.show_context_menu(e, menu))
        return menu
    
    @staticmethod
    def show_context_menu(event, menu):
        """Показывает контекстное меню"""
        try:
            widget = event.widget
            widget.focus_set()
            
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()


class PlaylistTab:
    """Вкладка с плейлистом"""
    
    def __init__(self, parent, manager, file_path=None):
        self.manager = manager
        self.parent = parent  # Это Notebook
        self.file_path = file_path
        self.playlist_data = []
        self.filtered_data = []
        self.current_channel = None
        self.selected_channels = []  # Список выделенных каналов
        self.sort_column = None
        self.sort_reverse = False
        self.modified = False
        self.tab_frame = None
        
        # Сначала создаем вкладку в Notebook
        tab_name = self._get_tab_name(file_path)
        self.tab_frame = ttk.Frame(parent)
        self.tab_id = parent.add(self.tab_frame, text=tab_name)
        
        # Затем создаем интерфейс
        self._create_interface()
        
        # И только потом загружаем файл
        if file_path and os.path.exists(file_path):
            self.load_from_file(file_path)
        
        parent.select(self.tab_frame)
    
    def _get_tab_name(self, file_path):
        """Генерирует имя для вкладки"""
        if file_path:
            name = os.path.basename(file_path)
        else:
            name = "Новый плейлист"
        
        if len(name) > 15:
            return name[:13] + ".."
        return name
    
    def _create_interface(self):
        """Создание интерфейса вкладки"""
        # Применяем системные стили
        self._apply_system_styles()
        
        control_frame = ttk.Frame(self.tab_frame)
        control_frame.pack(fill=tk.X, padx=5, pady=5)
        
        search_frame = ttk.Frame(control_frame)
        search_frame.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(search_frame, text="Поиск:").pack(side=tk.LEFT, padx=(0, 5))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=40)
        search_entry.pack(side=tk.LEFT)
        search_entry.bind('<KeyRelease>', lambda e: self.filter_channels())
        TextContextMenu.create_context_menu(search_entry)
        
        group_frame = ttk.Frame(control_frame)
        group_frame.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(group_frame, text="Группа:").pack(side=tk.LEFT, padx=(0, 5))
        self.group_var = tk.StringVar()
        self.group_combo = ttk.Combobox(group_frame, textvariable=self.group_var, 
                                       width=20, state='readonly')
        self.group_combo.pack(side=tk.LEFT)
        self.group_combo.set("Все группы")
        self.group_combo.bind('<<ComboboxSelected>>', lambda e: self.filter_channels())
        TextContextMenu.create_context_menu(self.group_combo)
        
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(side=tk.RIGHT)
        
        ttk.Button(button_frame, text="Сортировать", command=self.sort_channels_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Экспорт", command=self.export_channels).pack(side=tk.LEFT, padx=2)
        
        main_frame = ttk.Frame(self.tab_frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self._create_table(main_frame)
        self._create_editor_panel(main_frame)
    
    def _apply_system_styles(self):
        """Применение системных стилей к виджетам"""
        style = ttk.Style()
        
        available_themes = style.theme_names()
        if 'vista' in available_themes:
            style.theme_use('vista')
        elif 'winnative' in available_themes:
            style.theme_use('winnative')
        elif 'clam' in available_themes:
            style.theme_use('clam')
    
    def _create_table(self, parent):
        """Создание таблицы с каналами"""
        table_frame = ttk.Frame(parent)
        table_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.table_menu = Menu(table_frame, tearoff=0)
        self.table_menu.add_command(label="Копировать название", command=self.copy_channel_name)
        self.table_menu.add_command(label="Копировать URL", command=self.copy_channel_url)
        self.table_menu.add_separator()
        self.table_menu.add_command(label="Переместить вверх", command=self.move_channel_up)
        self.table_menu.add_command(label="Переместить вниз", command=self.move_channel_down)
        self.table_menu.add_separator()
        self.table_menu.add_command(label="Удалить канал", command=self.delete_channel)
        self.table_menu.add_command(label="Дублировать канал", command=self.duplicate_channel)
        
        # ВОССТАНАВЛИВАЕМ МНОЖЕСТВЕННОЕ ВЫДЕЛЕНИЕ - меняем selectmode='browse' на 'extended'
        self.tree = ttk.Treeview(
            table_frame,
            columns=('number', 'name', 'group', 'url', 'has_url'),
            show='headings',
            height=25,
            selectmode='extended'  # ИЗМЕНЕНО: было 'browse', стало 'extended'
        )
        
        self.tree.heading('number', text='№', command=lambda: self.sort_by_column('number'))
        self.tree.column('number', width=50, anchor='center', stretch=False)
        
        self.tree.heading('name', text='Название', command=lambda: self.sort_by_column('name'))
        self.tree.column('name', width=250, stretch=True)
        
        self.tree.heading('group', text='Группа', command=lambda: self.sort_by_column('group'))
        self.tree.column('group', width=150, stretch=True)
        
        self.tree.heading('url', text='URL')
        self.tree.column('url', width=350, stretch=True)
        
        self.tree.heading('has_url', text='Статус')
        self.tree.column('has_url', width=80, anchor='center', stretch=False)
        
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        
        self.tree.bind('<<TreeviewSelect>>', self.on_channel_select)
        self.tree.bind('<Double-Button-1>', self.on_double_click)
        self.tree.bind('<Button-3>', self.show_table_menu)
        self.tree.bind('<Delete>', lambda e: self.delete_channel())
        
        # ДОБАВЛЯЕМ ПОДДЕРЖКУ КЛАВИШ CTRL и SHIFT для множественного выделения
        self.tree.bind('<Control-Button-1>', self.on_ctrl_click)
        self.tree.bind('<Shift-Button-1>', self.on_shift_click)
    
    def on_ctrl_click(self, event):
        """Обработчик Ctrl+клик для множественного выделения"""
        # Treeview автоматически обрабатывает Ctrl+клик при selectmode='extended'
        pass
    
    def on_shift_click(self, event):
        """Обработчик Shift+клик для выделения диапазона"""
        # Treeview автоматически обрабатывает Shift+клик при selectmode='extended'
        pass
    
    def _create_editor_panel(self, parent):
        """Создание панели редактирования"""
        editor_frame = ttk.LabelFrame(parent, text="Редактирование канала", padding=10)
        editor_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        
        fields_frame = ttk.Frame(editor_frame)
        fields_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(fields_frame, text="Название:").grid(row=0, column=0, sticky='w', pady=2)
        self.name_var = tk.StringVar()
        name_entry = ttk.Entry(fields_frame, textvariable=self.name_var, width=30)
        name_entry.grid(row=0, column=1, sticky='ew', pady=2, padx=(5, 0))
        TextContextMenu.create_context_menu(name_entry)
        
        ttk.Label(fields_frame, text="Группа:").grid(row=1, column=0, sticky='w', pady=2)
        self.group_edit_var = tk.StringVar()
        self.group_edit_combo = ttk.Combobox(fields_frame, textvariable=self.group_edit_var, width=28)
        self.group_edit_combo.grid(row=1, column=1, sticky='ew', pady=2, padx=(5, 0))
        TextContextMenu.create_context_menu(self.group_edit_combo)
        
        ttk.Label(fields_frame, text="TVG-ID:").grid(row=2, column=0, sticky='w', pady=2)
        self.tvg_id_var = tk.StringVar()
        tvg_id_entry = ttk.Entry(fields_frame, textvariable=self.tvg_id_var, width=30)
        tvg_id_entry.grid(row=2, column=1, sticky='ew', pady=2, padx=(5, 0))
        TextContextMenu.create_context_menu(tvg_id_entry)
        
        ttk.Label(fields_frame, text="Логотип:").grid(row=3, column=0, sticky='w', pady=2)
        logo_frame = ttk.Frame(fields_frame)
        logo_frame.grid(row=3, column=1, sticky='ew', pady=2, padx=(5, 0))
        self.logo_var = tk.StringVar()
        logo_entry = ttk.Entry(logo_frame, textvariable=self.logo_var, width=22)
        logo_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        TextContextMenu.create_context_menu(logo_entry)
        ttk.Button(logo_frame, text="...", width=3, command=self.browse_logo).pack(side=tk.RIGHT, padx=(2, 0))
        
        ttk.Label(fields_frame, text="URL:").grid(row=4, column=0, sticky='w', pady=2)
        url_frame = ttk.Frame(fields_frame)
        url_frame.grid(row=4, column=1, sticky='ew', pady=2, padx=(5, 0))
        self.url_var = tk.StringVar()
        url_entry = ttk.Entry(url_frame, textvariable=self.url_var, width=22)
        url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        TextContextMenu.create_context_menu(url_entry)
        ttk.Button(url_frame, text="📋", width=3, command=self.paste_url).pack(side=tk.RIGHT, padx=(2, 0))
        
        button_frame = ttk.Frame(editor_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(button_frame, text="Новый", command=self.new_channel).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(button_frame, text="Сохранить", command=self.save_channel).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(button_frame, text="Отмена", command=self.cancel_edit).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        
        action_frame = ttk.Frame(editor_frame)
        action_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(action_frame, text="Удалить", command=self.delete_channel).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(action_frame, text="Дублировать", command=self.duplicate_channel).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        
        move_frame = ttk.Frame(editor_frame)
        move_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(move_frame, text="↑ Вверх", command=self.move_channel_up).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(move_frame, text="↓ Вниз", command=self.move_channel_down).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        
        info_frame = ttk.LabelFrame(editor_frame, text="Информация", padding=10)
        info_frame.pack(fill=tk.X, pady=10)
        
        self.info_label = ttk.Label(info_frame, text="Каналов: 0")
        self.info_label.pack(anchor='w')
        
        self.modified_label = ttk.Label(info_frame, text="Изменений: нет")
        self.modified_label.pack(anchor='w')
        
        self.update_group_completions()
    
    def browse_logo(self):
        """Открыть диалог выбора логотипа"""
        file_path = filedialog.askopenfilename(
            title="Выберите логотип",
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.gif *.bmp"), ("Все файлы", "*.*")]
        )
        if file_path:
            self.logo_var.set(file_path)
    
    def paste_url(self):
        """Вставить URL из буфера обмена"""
        try:
            clipboard = self.tab_frame.clipboard_get()
            if clipboard:
                self.url_var.set(clipboard.strip())
        except tk.TclError:
            pass
    
    def load_from_file(self, file_path):
        """Загрузка плейлиста из файла"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            self._parse_m3u(content)
            self.filtered_data = self.playlist_data.copy()
            self.update_table()
            self.update_group_filter()
            self.update_info()
            
            # Обновляем имя вкладки
            self.update_tab_name()
            
            self.manager.update_status(f"Загружено: {len(self.playlist_data)} каналов")
            self.modified = False
            self.update_modified_label()
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить файл:\n{str(e)}")
    
    def update_tab_name(self):
        """Безопасное обновление имени вкладки"""
        try:
            tab_name = self._get_tab_name(self.file_path)
            index = self.parent.index(self.tab_frame)
            self.parent.tab(index, text=tab_name)
        except Exception as e:
            print(f"Не удалось обновить имя вкладки: {e}")
    
    def _parse_m3u(self, content):
        """Парсинг M3U формата"""
        self.playlist_data = []
        lines = content.splitlines()
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
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
                while j < len(lines) and (not lines[j].strip() or lines[j].startswith('#')):
                    j += 1
                
                if j < len(lines):
                    channel.url = lines[j].strip()
                    channel.has_url = bool(channel.url.strip())
                    i = j
                else:
                    channel.has_url = False
                
                self.playlist_data.append(channel)
            
            i += 1
    
    def update_table(self):
        """Обновление таблицы каналов"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        for idx, channel in enumerate(self.filtered_data):
            display_idx = idx + 1
            
            url_display = channel.url
            if url_display and len(url_display) > 50:
                url_display = url_display[:50] + "..."
            
            status = "✓" if channel.has_url else "✗"
            
            item_id = self.tree.insert('', 'end', values=(
                display_idx,
                channel.name,
                channel.group,
                url_display or "",
                status
            ))
            
            if not channel.has_url:
                self.tree.item(item_id, tags=('no_url',))
        
        self.tree.tag_configure('no_url', foreground='red')
    
    def update_group_filter(self):
        """Обновление фильтра по группам"""
        groups = sorted({ch.group for ch in self.playlist_data if ch.group})
        groups.insert(0, "Все группы")
        self.group_combo['values'] = groups
        self.update_group_completions()
    
    def update_group_completions(self):
        """Обновление автодополнения групп"""
        groups = sorted({ch.group for ch in self.playlist_data if ch.group})
        if hasattr(self, 'group_edit_combo'):
            self.group_edit_combo['values'] = groups
    
    def update_info(self):
        """Обновление информации о плейлисте"""
        total = len(self.playlist_data)
        filtered = len(self.filtered_data)
        with_url = sum(1 for ch in self.playlist_data if ch.has_url)
        without_url = total - with_url
        
        self.info_label.config(
            text=f"Всего: {total}\n"
                 f"Отфильтровано: {filtered}\n"
                 f"С URL: {with_url}\n"
                 f"Без URL: {without_url}"
        )
    
    def update_modified_label(self):
        """Обновление метки изменений"""
        if self.modified:
            self.modified_label.config(text="Изменения: есть", foreground='red')
        else:
            self.modified_label.config(text="Изменений: нет", foreground='black')
    
    def filter_channels(self):
        """Фильтрация каналов по поиску и группе"""
        search_text = self.search_var.get().lower()
        group_filter = self.group_var.get()
        
        if group_filter == "Все группы":
            if search_text:
                self.filtered_data = [
                    ch for ch in self.playlist_data
                    if search_text in ch.name.lower() or 
                       search_text in ch.group.lower() or
                       search_text in (ch.tvg_id or "").lower()
                ]
            else:
                self.filtered_data = self.playlist_data.copy()
        else:
            if search_text:
                self.filtered_data = [
                    ch for ch in self.playlist_data
                    if ch.group == group_filter and 
                    (search_text in ch.name.lower() or 
                     search_text in ch.group.lower() or
                     search_text in (ch.tvg_id or "").lower())
                ]
            else:
                self.filtered_data = [
                    ch for ch in self.playlist_data
                    if ch.group == group_filter
                ]
        
        self.update_table()
        self.update_info()
    
    def sort_by_column(self, column):
        """Сортировка по колонке"""
        if column == self.sort_column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False
        
        if column == 'number':
            key = lambda x: self.filtered_data.index(x)
        elif column == 'name':
            key = lambda x: x.name.lower()
        elif column == 'group':
            key = lambda x: x.group.lower()
        else:
            return
        
        self.filtered_data.sort(key=key, reverse=self.sort_reverse)
        self.update_table()
    
    def sort_channels_dialog(self):
        """Диалог сортировки каналов"""
        dialog = tk.Toplevel(self.tab_frame)
        dialog.title("Сортировка каналов")
        dialog.geometry("300x200")
        dialog.transient(self.tab_frame)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Выберите поле для сортировки:").pack(pady=10)
        
        sort_var = tk.StringVar(value="name")
        
        ttk.Radiobutton(dialog, text="По названию", variable=sort_var, value="name").pack(anchor='w', padx=20)
        ttk.Radiobutton(dialog, text="По группе", variable=sort_var, value="group").pack(anchor='w', padx=20)
        ttk.Radiobutton(dialog, text="По TVG-ID", variable=sort_var, value="tvg_id").pack(anchor='w', padx=20)
        
        order_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(dialog, text="Обратный порядок", variable=order_var).pack(anchor='w', padx=20, pady=10)
        
        def apply_sort():
            if sort_var.get() == "name":
                key = lambda x: x.name.lower()
            elif sort_var.get() == "group":
                key = lambda x: x.group.lower()
            else:
                key = lambda x: (x.tvg_id or "").lower()
            
            self.playlist_data.sort(key=key, reverse=order_var.get())
            self.filter_channels()
            self.update_group_filter()
            dialog.destroy()
            self.manager.update_status("Каналы отсортированы")
            self.modified = True
            self.update_modified_label()
        
        ttk.Button(dialog, text="Применить", command=apply_sort).pack(pady=20)
    
    def on_channel_select(self, event=None):
        """Обработчик выбора канала"""
        selection = self.tree.selection()
        if not selection:
            self.selected_channels = []
            return
        
        # Получаем список всех выбранных каналов
        self.selected_channels = []
        for item in selection:
            idx = self.tree.index(item)
            if 0 <= idx < len(self.filtered_data):
                self.selected_channels.append(self.filtered_data[idx])
        
        # Отображаем в редакторе последний выбранный канал (для совместимости)
        if self.selected_channels:
            self.current_channel = self.selected_channels[-1]
            self.load_channel_to_editor(self.current_channel)
    
    def on_double_click(self, event):
        """Обработчик двойного клика"""
        self.on_channel_select()
    
    def show_table_menu(self, event):
        """Показать контекстное меню таблицы"""
        item = self.tree.identify_row(event.y)
        if item:
            # Если кликнули не на выделенной строке, то выделяем только ее
            if item not in self.tree.selection():
                self.tree.selection_set(item)
                self.on_channel_select()
            
            self.table_menu.tk_popup(event.x_root, event.y_root)
    
    def load_channel_to_editor(self, channel):
        """Загрузка данных канала в редактор"""
        self.current_channel = channel
        
        self.name_var.set(channel.name)
        self.group_edit_var.set(channel.group)
        self.tvg_id_var.set(channel.tvg_id)
        self.logo_var.set(channel.tvg_logo)
        self.url_var.set(channel.url)
    
    def new_channel(self):
        """Создание нового канала"""
        self.current_channel = None
        self.selected_channels = []
        self.name_var.set("")
        self.group_edit_var.set("Без группы")
        self.tvg_id_var.set("")
        self.logo_var.set("")
        self.url_var.set("")
        self.tree.selection_remove(self.tree.selection())
    
    def cancel_edit(self):
        """Отмена редактирования"""
        if self.current_channel:
            self.load_channel_to_editor(self.current_channel)
        else:
            self.new_channel()
    
    def save_channel(self):
        """Сохранение канала"""
        if not self.name_var.get().strip():
            messagebox.showwarning("Предупреждение", "Введите название канала")
            return
        
        name = self.name_var.get().strip()
        group = self.group_edit_var.get().strip() or "Без группы"
        tvg_id = self.tvg_id_var.get().strip()
        logo = self.logo_var.get().strip()
        url = self.url_var.get().strip()
        
        if self.current_channel:
            self.current_channel.name = name
            self.current_channel.group = group
            self.current_channel.tvg_id = tvg_id
            self.current_channel.tvg_logo = logo
            self.current_channel.url = url
            self.current_channel.has_url = bool(url.strip())
            
            self._update_extinf(self.current_channel)
        else:
            channel = ChannelData()
            channel.name = name
            channel.group = group
            channel.tvg_id = tvg_id
            channel.tvg_logo = logo
            channel.url = url
            channel.has_url = bool(url.strip())
            
            self._update_extinf(channel)
            self.playlist_data.append(channel)
            self.current_channel = channel
        
        self.filter_channels()
        self.update_group_filter()
        self.manager.update_status("Канал сохранен")
        self.modified = True
        self.update_modified_label()
    
    def _update_extinf(self, channel):
        """Обновление строки EXTINF"""
        parts = ["#EXTINF:-1"]
        
        if channel.tvg_id:
            parts.append(f'tvg-id="{channel.tvg_id}"')
        if channel.tvg_logo:
            parts.append(f'tvg-logo="{channel.tvg_logo}"')
        if channel.group:
            parts.append(f'group-title="{channel.group}"')
        
        parts.append(f',{channel.name}')
        channel.extinf = ' '.join(parts)
    
    def duplicate_channel(self):
        """Дублирование канала"""
        if not self.current_channel:
            messagebox.showwarning("Предупреждение", "Выберите канал для дублирования")
            return
        
        channel = ChannelData()
        channel.name = f"{self.current_channel.name} (копия)"
        channel.group = self.current_channel.group
        channel.tvg_id = self.current_channel.tvg_id
        channel.tvg_logo = self.current_channel.tvg_logo
        channel.url = self.current_channel.url
        channel.has_url = self.current_channel.has_url
        
        self._update_extinf(channel)
        
        idx = self.playlist_data.index(self.current_channel) + 1
        self.playlist_data.insert(idx, channel)
        
        self.filter_channels()
        self.update_group_filter()
        self.manager.update_status("Канал дублирован")
        self.modified = True
        self.update_modified_label()
    
    def delete_channel(self):
        """Удаление канала"""
        # Если есть выделенные каналы, удаляем все выделенные
        if self.selected_channels:
            if len(self.selected_channels) == 1:
                message_text = f"Удалить канал '{self.selected_channels[0].name}'?"
            else:
                message_text = f"Удалить выбранные {len(self.selected_channels)} каналов?"
        elif self.current_channel:
            message_text = f"Удалить канал '{self.current_channel.name}'?"
        else:
            messagebox.showwarning("Предупреждение", "Выберите канал для удаления")
            return
        
        if messagebox.askyesno("Подтверждение", message_text):
            # Удаляем выделенные каналы, если они есть
            channels_to_delete = self.selected_channels if self.selected_channels else [self.current_channel]
            
            for channel in channels_to_delete:
                if channel in self.playlist_data:
                    self.playlist_data.remove(channel)
            
            self.new_channel()
            self.filter_channels()
            self.update_group_filter()
            self.manager.update_status(f"Удалено {len(channels_to_delete)} каналов")
            self.modified = True
            self.update_modified_label()
    
    def move_channel_up(self):
        """Перемещение канала вверх"""
        if not self.current_channel:
            messagebox.showwarning("Предупреждение", "Выберите канал для перемещения")
            return
        
        idx = self.playlist_data.index(self.current_channel)
        if idx > 0:
            self.playlist_data[idx], self.playlist_data[idx-1] = self.playlist_data[idx-1], self.playlist_data[idx]
            self.filter_channels()
            
            if self.current_channel in self.filtered_data:
                new_idx = self.filtered_data.index(self.current_channel)
                self.tree.selection_set(self.tree.get_children()[new_idx])
            
            self.manager.update_status("Канал перемещен вверх")
            self.modified = True
            self.update_modified_label()
    
    def move_channel_down(self):
        """Перемещение канала вниз"""
        if not self.current_channel:
            messagebox.showwarning("Предупреждение", "Выберите канал для перемещения")
            return
        
        idx = self.playlist_data.index(self.current_channel)
        if idx < len(self.playlist_data) - 1:
            self.playlist_data[idx], self.playlist_data[idx+1] = self.playlist_data[idx+1], self.playlist_data[idx]
            self.filter_channels()
            
            if self.current_channel in self.filtered_data:
                new_idx = self.filtered_data.index(self.current_channel)
                self.tree.selection_set(self.tree.get_children()[new_idx])
            
            self.manager.update_status("Канал перемещен вниз")
            self.modified = True
            self.update_modified_label()
    
    def copy_channel_name(self):
        """Копирование названия канала"""
        if self.current_channel:
            self.tab_frame.clipboard_clear()
            self.tab_frame.clipboard_append(self.current_channel.name)
            self.manager.update_status("Название скопировано в буфер")
    
    def copy_channel_url(self):
        """Копирование URL канала"""
        if self.current_channel and self.current_channel.url:
            self.tab_frame.clipboard_clear()
            self.tab_frame.clipboard_append(self.current_channel.url)
            self.manager.update_status("URL скопирован в буфер")
    
    def save_to_file(self, file_path=None):
        """Сохранение плейлиста в файл"""
        if file_path:
            self.file_path = file_path
        
        if not self.file_path:
            return False
        
        try:
            backup_path = None
            if os.path.exists(self.file_path):
                backup_path = self.file_path + '.bak'
                try:
                    os.rename(self.file_path, backup_path)
                except Exception as e:
                    messagebox.showwarning("Внимание", f"Не удалось создать резервную копию: {str(e)}")
            
            with open(self.file_path, 'w', encoding='utf-8') as f:
                f.write('#EXTM3U\n')
                for channel in self.playlist_data:
                    f.write(channel.extinf + '\n')
                    f.write(channel.url + '\n' if channel.url else '\n')
            
            self.update_tab_name()
            
            self.manager.update_status(f"Сохранено в: {os.path.basename(self.file_path)}")
            self.modified = False
            self.update_modified_label()
            return True
            
        except Exception as e:
            if backup_path and os.path.exists(backup_path):
                try:
                    os.rename(backup_path, self.file_path)
                except Exception:
                    pass
            messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{str(e)}")
            return False
    
    def export_channels(self):
        """Экспорт списка каналов"""
        if not self.playlist_data:
            messagebox.showwarning("Предупреждение", "Нет каналов для экспорта")
            return
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Текстовые файлы", "*.txt"), ("CSV файлы", "*.csv"), ("Все файлы", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            ext = os.path.splitext(file_path)[1].lower()
            
            if ext == '.csv':
                with open(file_path, 'w', encoding='utf-8-sig') as f:
                    f.write("Название;Группа;TVG-ID;Логотип;URL\n")
                    for channel in self.playlist_data:
                        f.write(f'{channel.name};{channel.group};{channel.tvg_id};{channel.tvg_logo};{channel.url}\n')
            else:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"Экспорт каналов из плейлиста\n")
                    f.write(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Всего каналов: {len(self.playlist_data)}\n")
                    f.write("="*80 + "\n\n")
                    
                    groups = {}
                    for channel in self.playlist_data:
                        if channel.group not in groups:
                            groups[channel.group] = []
                        groups[channel.group].append(channel)
                    
                    for group in sorted(groups.keys()):
                        f.write(f"\nГруппа: {group}\n")
                        f.write("-"*40 + "\n")
                        for idx, channel in enumerate(groups[group], 1):
                            status = "✓" if channel.has_url else "✗"
                            f.write(f"{idx:3}. {status} {channel.name}\n")
                            if channel.url:
                                display_url = channel.url[:50] + "..." if len(channel.url) > 50 else channel.url
                                f.write(f"     URL: {display_url}\n")
            
            self.manager.update_status(f"Экспорт завершен: {os.path.basename(file_path)}")
            messagebox.showinfo("Успех", "Экспорт каналов завершен успешно!")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось экспортировать:\n{str(e)}")
    
    def merge_duplicates(self):
        """Объединение дубликатов каналов"""
        if not self.playlist_data:
            messagebox.showinfo("Информация", "Нет каналов для проверки")
            return
        
        duplicates = {}
        for channel in self.playlist_data:
            key = (channel.name, channel.url)
            if key not in duplicates:
                duplicates[key] = []
            duplicates[key].append(channel)
        
        dup_count = sum(len(channels) - 1 for channels in duplicates.values() if len(channels) > 1)
        
        if dup_count == 0:
            messagebox.showinfo("Информация", "Дубликаты не найдены")
            return
        
        if messagebox.askyesno("Подтверждение", 
                              f"Найдено {dup_count} дубликатов. Удалить их?\n"
                              f"Будет оставлен только первый канал из каждой группы дубликатов."):
            new_list = []
            seen = set()
            
            for channel in self.playlist_data:
                key = (channel.name, channel.url)
                if key not in seen:
                    new_list.append(channel)
                    seen.add(key)
            
            removed = len(self.playlist_data) - len(new_list)
            self.playlist_data = new_list
            self.filter_channels()
            self.update_group_filter()
            
            self.manager.update_status(f"Удалено {removed} дубликатов")
            messagebox.showinfo("Успех", f"Удалено {removed} дубликатов")
            self.modified = True
            self.update_modified_label()
    
    def refresh_view(self):
        """Обновление вида"""
        self.filter_channels()
        self.update_info()
        self.manager.update_status("Вид обновлен")


class IPTVEditor:
    """Главное окно редактора с системными темами Windows и поддержкой плагинов"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Редактор IPTV листов")
        
        # Инициализация менеджера тем Windows
        self.theme_manager = WindowsThemeManager()
        
        # Применение системных настроек
        self._apply_system_settings()
        
        # Настройка размеров окна с учетом DPI
        self._configure_window_size()
        
        self.tabs = {}
        self.current_tab = None
        
        self._create_menu()
        self._create_toolbar()
        self._create_notebook()
        self._create_status_bar()
        
        # Инициализация плагинной системы
        self._init_plugin_system()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.create_new_tab()
    
    def _init_plugin_system(self):
        """Инициализация плагинной системы"""
        if not PLUGIN_SYSTEM_AVAILABLE:
            print("Плагинная система не доступна. Плагины не будут загружены.")
            self.plugin_manager = None
            return
        
        try:
            # Создаем менеджер плагинов с правильным путем
            self.plugin_manager = PluginManager(self)
            
            # Переопределяем путь к плагинам в менеджере
            if hasattr(self.plugin_manager, 'plugins_dir'):
                self.plugin_manager.plugins_dir = PLUGINS_DIR
                print(f"Установлен путь к плагинов: {PLUGINS_DIR}")
            
            # Загружаем все плагины
            loaded = self.plugin_manager.load_all_plugins()
            
            # После загрузки плагинов, добавляем их в меню
            self._add_plugins_to_menu()
            
            self.update_status(f"Загружено {loaded} плагинов")
            
        except Exception as e:
            print(f"Ошибка инициализации плагинной системы: {e}")
            self.plugin_manager = None
    
    def _add_plugins_to_menu(self):
        """Добавляет пункты плагинов в меню"""
        if not self.plugin_manager:
            return
        
        # Добавляем плагины в меню "Инструменты"
        if hasattr(self, 'tools_menu') and self.tools_menu:
            # Очищаем старое меню (кроме первых двух пунктов)
            try:
                # Удаляем все пункты кроме "Загрузка инструментов..." и разделителя
                menu_items = self.tools_menu.index('end')
                if menu_items > 1:  # Если есть больше 2 пунктов
                    for i in range(menu_items, 1, -1):
                        self.tools_menu.delete(i)
            except:
                pass
            
            # Добавляем плагины
            loaded_plugins = self.plugin_manager.get_loaded_plugins()
            if loaded_plugins:
                # Добавляем разделитель
                self.tools_menu.add_separator()
                
                for plugin_name in loaded_plugins:
                    plugin_info = self.plugin_manager.get_plugin_info(plugin_name)
                    if plugin_info:
                        # Создаем подменю для плагина
                        plugin_submenu = Menu(self.tools_menu, tearoff=0)
                        self.tools_menu.add_cascade(label=plugin_info.name, menu=plugin_submenu)
                        
                        # Добавляем пункты плагина
                        plugin = self.plugin_manager.plugins[plugin_name]
                        if hasattr(plugin, 'add_menu_items'):
                            plugin.add_menu_items(plugin_submenu)
                        
                        # Добавляем разделитель
                        plugin_submenu.add_separator()
                        
                        # Добавляем информацию о плагине
                        plugin_submenu.add_command(
                            label="Информация о плагине",
                            command=lambda pn=plugin_name: self.show_plugin_info(pn)
                        )
    
    def show_plugin_path_info(self):
        """Показывает информацию о путях плагинов"""
        info_text = f"""
        Информация о путях:
        
        Основная директория программы:
        {BASE_DIR}
        
        Директория плагинов:
        {PLUGINS_DIR}
        
        Существует ли директория плагинов: {os.path.exists(PLUGINS_DIR)}
        
        Содержимое директории плагинов:
        """
        
        if os.path.exists(PLUGINS_DIR):
            try:
                items = os.listdir(PLUGINS_DIR)
                if items:
                    for item in items:
                        item_path = os.path.join(PLUGINS_DIR, item)
                        info_text += f"\n  - {item}"
                        if os.path.isdir(item_path):
                            info_text += " (папка)"
                            # Проверяем наличие __init__.py
                            init_file = os.path.join(item_path, "__init__.py")
                            if os.path.exists(init_file):
                                info_text += " [есть __init__.py]"
                            else:
                                info_text += " [нет __init__.py]"
                else:
                    info_text += "\n  (пусто)"
            except Exception as e:
                info_text += f"\n  Ошибка чтения: {str(e)}"
        else:
            info_text += "\n  (директория не существует)"
        
        messagebox.showinfo("Информация о путях плагинов", info_text)
    
    def show_plugins_list(self):
        """Показывает список всех плагинов"""
        if not self.plugin_manager:
            messagebox.showinfo("Плагины", "Плагинная система не инициализирована")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Список плагинов")
        dialog.geometry("500x400")
        dialog.transient(self.root)
        
        # Создаем Treeview для отображения плагинов
        frame = ttk.Frame(dialog)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        tree = ttk.Treeview(frame, columns=('status', 'version', 'author'), show='headings')
        tree.heading('#0', text='Название')
        tree.column('#0', width=200)
        tree.heading('status', text='Статус')
        tree.column('status', width=80, anchor='center')
        tree.heading('version', text='Версия')
        tree.column('version', width=80, anchor='center')
        tree.heading('author', text='Автор')
        tree.column('author', width=150)
        
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        # Заполняем список плагинов
        available_plugins = self.plugin_manager.get_available_plugins()
        loaded_plugins = self.plugin_manager.get_loaded_plugins()
        
        for plugin_name in available_plugins:
            plugin_info = self.plugin_manager.get_plugin_info(plugin_name)
            if plugin_info:
                status = "✓" if plugin_name in loaded_plugins else "✗"
                tree.insert('', 'end', text=plugin_info.name, 
                           values=(status, plugin_info.version, plugin_info.author))
        
        # Кнопки управления
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        def load_selected():
            selection = tree.selection()
            if selection:
                item = tree.item(selection[0])
                plugin_name = self._find_plugin_by_name(item['text'])
                if plugin_name and not self.plugin_manager.is_plugin_loaded(plugin_name):
                    if self.plugin_manager.load_plugin(plugin_name):
                        self._add_plugins_to_menu()
                        messagebox.showinfo("Успех", f"Плагин '{item['text']}' загружен")
                        dialog.destroy()
        
        def unload_selected():
            selection = tree.selection()
            if selection:
                item = tree.item(selection[0])
                plugin_name = self._find_plugin_by_name(item['text'])
                if plugin_name and self.plugin_manager.is_plugin_loaded(plugin_name):
                    if self.plugin_manager.unload_plugin(plugin_name):
                        self._add_plugins_to_menu()
                        messagebox.showinfo("Успех", f"Плагин '{item['text']}' выгружен")
                        dialog.destroy()
        
        ttk.Button(button_frame, text="Загрузить", command=load_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Выгрузить", command=unload_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Закрыть", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    def _find_plugin_by_name(self, display_name):
        """Находит имя плагина по отображаемому имени"""
        if not self.plugin_manager:
            return None
        
        for plugin_name in self.plugin_manager.get_available_plugins():
            plugin_info = self.plugin_manager.get_plugin_info(plugin_name)
            if plugin_info and plugin_info.name == display_name:
                return plugin_name
        return None
    
    def show_plugin_info(self, plugin_name):
        """Показывает информацию о плагине"""
        if not self.plugin_manager:
            return
        
        plugin_info = self.plugin_manager.get_plugin_info(plugin_name)
        if plugin_info:
            info_text = f"""
            Плагин: {plugin_info.name}
            Версия: {plugin_info.version}
            Автор: {plugin_info.author}
            Тип: {plugin_info.plugin_type.value}
            
            Описание:
            {plugin_info.description}
            
            Статус: {'Загружен' if self.plugin_manager.is_plugin_loaded(plugin_name) else 'Не загружен'}
            """
            messagebox.showinfo(f"Информация о плагине", info_text)
    
    def refresh_plugins(self):
        """Обновляет список плагинов"""
        if self.plugin_manager:
            self.plugin_manager.scan_plugins()
            self._add_plugins_to_menu()
            messagebox.showinfo("Плагины", "Список плагинов обновлен")
    
    def open_plugins_directory(self):
        """Открывает директорию с плагинами"""
        import subprocess
        
        # Создаем директорию, если она не существует
        if not os.path.exists(PLUGINS_DIR):
            os.makedirs(PLUGINS_DIR)
            # Создаем README файл
            readme_path = os.path.join(PLUGINS_DIR, "README.txt")
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write("Директория для плагинов IPTV редактора\n")
                f.write("="*50 + "\n\n")
                f.write("Поместите сюда папки с плагинами.\n")
                f.write("Каждый плагин должен быть в отдельной папке.\n")
                f.write("В папке плагина должен быть файл __init__.py\n")
                f.write(f"\nТекущий путь: {PLUGINS_DIR}\n")
        
        # Открываем директорию в зависимости от ОС
        system = platform.system()
        try:
            if system == "Windows":
                os.startfile(PLUGINS_DIR)
            elif system == "Darwin":  # macOS
                subprocess.Popen(["open", PLUGINS_DIR])
            else:  # Linux
                subprocess.Popen(["xdg-open", PLUGINS_DIR])
        except Exception as e:
            messagebox.showwarning("Ошибка", f"Не удалось открыть директорию:\n{str(e)}")
    
    # API методы для плагинов
    def get_menu(self, menu_path):
        """Возвращает меню по пути (создает, если не существует) - для плагинов"""
        menubar = self.root.nametowidget(self.root['menu'])
        
        parts = menu_path.split('/')
        current_menu = menubar
        
        for part in parts:
            found = False
            # Ищем существующее меню
            try:
                for i in range(current_menu.index('end') + 1):
                    if current_menu.type(i) == 'cascade' and current_menu.entrycget(i, 'label') == part:
                        current_menu = current_menu.nametowidget(current_menu.entrycget(i, 'menu'))
                        found = True
                        break
            except:
                pass
            
            # Если меню не найдено, создаем новое
            if not found:
                new_menu = Menu(current_menu, tearoff=0)
                current_menu.add_cascade(label=part, menu=new_menu)
                current_menu = new_menu
        
        return current_menu
    
    def update_status(self, text):
        """Обновляет строку состояния (для использования плагинами)"""
        if hasattr(self, 'status_label'):
            self.status_label.config(text=text)
            self.root.after(5000, lambda: self.status_label.config(text="Готов"))
    
    def get_current_playlist(self):
        """Возвращает текущий плейлист (для использования плагинами)"""
        return self.current_tab
    
    def _apply_system_settings(self):
        """Применение системных настроек Windows"""
        dpi_scale = self.theme_manager.get_system_dpi_scale()
        font_name, font_size_pt = self.theme_manager.get_menu_font()
        dialog_font_name, dialog_font_size_pt = self.theme_manager.get_dialog_font()
        system_colors = self.theme_manager.get_system_colors()
        hotkeys = self.theme_manager.get_hotkeys()
        
        self.root.tk.call('tk', 'scaling', dpi_scale)
        
        default_font = (font_name, font_size_pt)
        dialog_font = (dialog_font_name, dialog_font_size_pt)
        
        self.root.option_add("*Font", default_font)
        self.root.option_add("*Dialog*Font", dialog_font)
        
        self.hotkeys = hotkeys
        
        self.style = ttk.Style()
        
        available_themes = self.style.theme_names()
        if 'vista' in available_themes:
            self.style.theme_use('vista')
        elif 'winnative' in available_themes:
            self.style.theme_use('winnative')
        elif 'clam' in available_themes:
            self.style.theme_use('clam')
        
        self.style.configure("TLabel", font=default_font)
        self.style.configure("TButton", font=default_font)
        self.style.configure("TEntry", font=default_font)
        self.style.configure("TCombobox", font=default_font)
        self.style.configure("Treeview", font=default_font)
        self.style.configure("Treeview.Heading", font=default_font)
        self.style.configure("TNotebook.Tab", font=default_font)
        self.style.configure("TLabelframe.Label", font=default_font)
        
        if 'accent' in system_colors:
            try:
                accent_color = system_colors['accent']
                if accent_color > 0xFFFFFF:
                    accent_color = accent_color & 0xFFFFFF
                
                self.style.configure("Accent.TButton", 
                                   background=f'#{accent_color:06x}')
            except:
                pass
    
    def _configure_window_size(self):
        """Настройка размеров окна с учетом DPI"""
        base_width = 1200
        base_height = 700
        
        dpi_scale = self.theme_manager.get_system_dpi_scale()
        scaled_width = int(base_width * dpi_scale)
        scaled_height = int(base_height * dpi_scale)
        
        self.root.geometry(f"{scaled_width}x{scaled_height}")
        self._center_window()
    
    def _center_window(self):
        """Центрирование окна на экране"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def _create_menu(self):
        """Создание меню с системными шрифтами"""
        menubar = Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Файл", menu=file_menu)
        file_menu.add_command(label="Создать", 
                             accelerator="Ctrl+N", 
                             command=self.create_new_playlist)
        file_menu.add_command(label="Открыть", 
                             accelerator="Ctrl+O", 
                             command=self.open_playlist)
        file_menu.add_separator()
        file_menu.add_command(label="Сохранить", 
                             accelerator="Ctrl+S", 
                             command=self.save_current)
        file_menu.add_command(label="Сохранить как...", 
                             accelerator="Ctrl+Shift+S", 
                             command=self.save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Импорт из файла...", 
                             command=self.import_channels)
        file_menu.add_command(label="Экспорт списка...", 
                             command=self.export_list)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", 
                             accelerator="Alt+F4", 
                             command=self.on_closing)
        
        edit_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Правка", menu=edit_menu)
        edit_menu.add_command(label="Добавить канал", 
                             accelerator="Ctrl+A", 
                             command=self.add_channel)
        edit_menu.add_command(label="Найти...", 
                             accelerator="Ctrl+F", 
                             command=self.show_search)
        edit_menu.add_separator()
        edit_menu.add_command(label="Сортировать...", 
                             command=self.sort_channels)
        edit_menu.add_command(label="Объединить дубликаты", 
                             command=self.merge_duplicates)
        
        # ДОБАВЛЕНО: Меню "Инструменты" для плагинов
        self.tools_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Инструменты", menu=self.tools_menu)
        
        # ДОБАВЛЯЕМ ВРЕМЕННЫЙ ПУНКТ, ЧТОБЫ МЕНЮ БЫЛО ВИДИМО
        self.tools_menu.add_command(label="Загрузка инструментов...", 
                                  command=self.show_tools_info)
        self.tools_menu.add_separator()
        
        view_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Вид", menu=view_menu)
        view_menu.add_command(label="Обновить", 
                             command=self.refresh_view)
        
        # Меню "Плагины" (если плагинная система доступна)
        if hasattr(self, 'plugin_manager') and self.plugin_manager:
            plugin_menu = Menu(menubar, tearoff=0)
            menubar.add_cascade(label="Плагины", menu=plugin_menu)
            
            manage_menu = Menu(plugin_menu, tearoff=0)
            plugin_menu.add_cascade(label="Управление", menu=manage_menu)
            
            manage_menu.add_command(label="Список плагинов", 
                                   command=self.show_plugins_list)
            manage_menu.add_command(label="Обновить список", 
                                   command=self.refresh_plugins)
            manage_menu.add_separator()
            manage_menu.add_command(label="Директория плагинов", 
                                   command=self.open_plugins_directory)
            manage_menu.add_command(label="Информация о пути", 
                                   command=self.show_plugin_path_info)
            
            plugin_menu.add_separator()
            
            # Добавляем плагины из менеджера
            loaded_plugins = self.plugin_manager.get_loaded_plugins()
            if loaded_plugins:
                plugin_menu.add_separator()
                for plugin_name in loaded_plugins:
                    plugin_info = self.plugin_manager.get_plugin_info(plugin_name)
                    if plugin_info:
                        plugin_menu.add_command(
                            label=f"{plugin_info.name} ({plugin_info.version})",
                            command=lambda pn=plugin_name: self.show_plugin_info(pn)
                        )
    
        help_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Справка", menu=help_menu)
        help_menu.add_command(label="О программе", 
                             command=self.show_about)
        
        self._bind_system_hotkeys()
    
    def show_tools_info(self):
        """Показывает информацию о доступных инструментах"""
        if hasattr(self, 'plugin_manager') and self.plugin_manager:
            loaded_plugins = self.plugin_manager.get_loaded_plugins()
            info_text = "Доступные инструменты:\n\n"
            
            for plugin_name in loaded_plugins:
                plugin_info = self.plugin_manager.get_plugin_info(plugin_name)
                if plugin_info:
                    info_text += f"• {plugin_info.name} ({plugin_info.version})\n"
                    info_text += f"  {plugin_info.description}\n\n"
            
            if len(info_text) > len("Доступные инструменты:\n\n"):
                messagebox.showinfo("Инструменты", info_text)
            else:
                messagebox.showinfo("Инструменты", "Нет загруженных инструментов. Плагины могут добавлять инструменты в это меню.")
        else:
            messagebox.showinfo("Инструменты", "Система плагинов не загружена.")
    
    def _bind_system_hotkeys(self):
        """Привязка системных горячих клавиш"""
        hotkeys = self.hotkeys
        
        self.root.bind('<Control-n>', lambda e: self.create_new_playlist())
        self.root.bind('<Control-o>', lambda e: self.open_playlist())
        self.root.bind('<Control-s>', lambda e: self.save_current())
        self.root.bind('<Control-Shift-S>', lambda e: self.save_as())
        self.root.bind('<Control-f>', lambda e: self.show_search())
        self.root.bind('<Control-a>', lambda e: self.add_channel())
        self.root.bind('<Delete>', lambda e: self.delete_selected_channel())
        self.root.bind('<F5>', lambda e: self.refresh_view())
    
    def delete_selected_channel(self):
        """Удаление выбранного канала по горячей клавише"""
        if self.current_tab:
            self.current_tab.delete_channel()
    
    def _create_toolbar(self):
        """Создание панели инструментов - УПРОЩЕННАЯ ВЕРСИЯ"""
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(toolbar, text="📄 Создать", command=self.create_new_playlist).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="📂 Открыть", command=self.open_playlist).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="💾 Сохранить", command=self.save_current).pack(side=tk.LEFT, padx=2)
    
    def _create_notebook(self):
        """Создание блока вкладок"""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.notebook.bind('<<NotebookTabChanged>>', self.on_tab_changed)
        
        self.notebook_menu = Menu(self.notebook, tearoff=0)
        self.notebook_menu.add_command(label="Закрыть вкладку", command=self.close_current_tab)
        self.notebook_menu.add_command(label="Закрыть все вкладки", command=self.close_all_tabs)
        self.notebook_menu.add_command(label="Закрыть другие вкладки", command=self.close_other_tabs)
        self.notebook.bind('<Button-3>', self.show_notebook_menu)
    
    def _create_status_bar(self):
        """Создание строки состояния"""
        self.status_frame = ttk.Frame(self.root, height=30)
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_frame.pack_propagate(False)
        
        self.status_label = ttk.Label(self.status_frame, text="Готов к работе")
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        self.tab_count_label = ttk.Label(self.status_frame, text="")
        self.tab_count_label.pack(side=tk.RIGHT, padx=10)
        self.update_tab_count()
    
    def update_tab_count(self):
        """Обновление счетчика вкладок"""
        self.tab_count_label.config(text=f"Вкладок: {len(self.tabs)}")
    
    def on_tab_changed(self, event=None):
        """Обработчик переключения вкладок"""
        self.update_tab_count()
        self.current_tab = self.get_current_tab()
    
    def show_notebook_menu(self, event):
        """Показать контекстное меню вкладок"""
        try:
            tab_index = self.notebook.index(f"@{event.x},{event.y}")
            if tab_index >= 0:
                self.notebook.select(tab_index)
                self.current_tab = self.get_current_tab()
                self.notebook_menu.tk_popup(event.x_root, event.y_root)
        except tk.TclError:
            pass
    
    def get_current_tab(self):
        """Получение текущей активной вкладки"""
        try:
            current_index = self.notebook.index(self.notebook.select())
            if current_index >= 0:
                tab_frame = self.notebook.winfo_children()[current_index]
                return self.tabs.get(tab_frame)
        except tk.TclError:
            pass
        return None
    
    def create_new_tab(self, file_path=None):
        """Создание новой вкладки"""
        try:
            tab = PlaylistTab(self.notebook, self, file_path)
            self.tabs[tab.tab_frame] = tab
            self.update_tab_count()
            self.current_tab = tab
            return tab
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось создать вкладку: {str(e)}")
            return None
    
    def create_new_playlist(self):
        """Создание нового плейлиста"""
        self.create_new_tab()
        self.update_status("Создан новый плейлист")
    
    def open_playlist(self):
        """Открытие плейлиста из файла"""
        file_paths = filedialog.askopenfilenames(
            title="Выберите файлы плейлистов",
            filetypes=[("M3U файлы", "*.m3u *.m3u8"), ("Все файлы", "*.*")]
        )
        
        if not file_paths:
            return
        
        for file_path in file_paths:
            self.create_new_tab(file_path)
            self.update_status(f"Открыт файл: {os.path.basename(file_path)}")
    
    def save_current(self):
        """Сохранение текущего плейлиста"""
        if not self.current_tab:
            messagebox.showwarning("Предупреждение", "Нет активной вкладки")
            return
        
        if self.current_tab.file_path:
            if self.current_tab.save_to_file():
                self.update_status("Плейлист сохранен")
        else:
            self.save_as()
    
    def save_as(self):
        """Сохранение плейлиста как..."""
        if not self.current_tab:
            messagebox.showwarning("Предупреждение", "Нет активной вкладки")
            return
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".m3u",
            filetypes=[("M3U файлы", "*.m3u"), ("M3U8 файлы", "*.m3u8"), ("Все файлы", "*.*")]
        )
        
        if file_path:
            if self.current_tab.save_to_file(file_path):
                self.update_status(f"Сохранено как: {os.path.basename(file_path)}")
    
    def add_channel(self):
        """Добавление нового канала"""
        if self.current_tab:
            self.current_tab.new_channel()
            self.update_status("Готов к добавлению нового канала")
    
    def show_search(self):
        """Показать поиск"""
        if self.current_tab:
            for widget in self.current_tab.tab_frame.winfo_children():
                if isinstance(widget, ttk.Frame):
                    for child in widget.winfo_children():
                        if isinstance(child, ttk.Entry) and child.winfo_width() > 30:
                            child.focus_set()
                            return
    
    def sort_channels(self):
        """Сортировка каналов"""
        if self.current_tab:
            self.current_tab.sort_channels_dialog()
    
    def import_channels(self):
        """Импорт каналов из файла"""
        if not self.current_tab:
            messagebox.showwarning("Предупреждение", "Нет активной вкладки")
            return
        
        file_path = filedialog.askopenfilename(
            title="Импорт каналов из файла",
            filetypes=[("Текстовые файлы", "*.txt"), ("CSV файлы", "*.csv"), ("Все файлы", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            imported = 0
            for line in lines:
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
                        
                        self.current_tab.playlist_data.append(channel)
                        imported += 1
            
            self.current_tab.filter_channels()
            self.current_tab.update_group_filter()
            self.update_status(f"Импортировано {imported} каналов")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось импортировать файл:\n{str(e)}")
    
    def export_list(self):
        """Экспорт списка каналов"""
        if self.current_tab:
            self.current_tab.export_channels()
    
    def merge_duplicates(self):
        """Объединение дубликатов"""
        if self.current_tab:
            self.current_tab.merge_duplicates()
    
    def refresh_view(self):
        """Обновление вида"""
        if self.current_tab:
            self.current_tab.refresh_view()
    
    def close_current_tab(self):
        """Закрыть текущую вкладку"""
        if not self.current_tab:
            return
        
        if self.current_tab.modified:
            if not messagebox.askyesno("Подтверждение", 
                                      "Вкладка содержит несохраненные изменения. Закрыть без сохранения?"):
                return
        
        tab_frame = self.current_tab.tab_frame
        self.notebook.forget(tab_frame)
        if tab_frame in self.tabs:
            del self.tabs[tab_frame]
        self.update_tab_count()
        self.current_tab = self.get_current_tab()
    
    def close_all_tabs(self):
        """Закрыть все вкладки"""
        modified_tabs = [tab for tab in self.tabs.values() if tab.modified]
        
        if modified_tabs:
            if not messagebox.askyesno("Подтверждение", 
                                      f"Некоторые вкладки содержат несохраненные изменения. Закрыть все без сохранения?"):
                return
        
        for tab_frame in list(self.tabs.keys()):
            self.notebook.forget(tab_frame)
        
        self.tabs.clear()
        self.update_tab_count()
        self.current_tab = None
        
        self.create_new_tab()
    
    def close_other_tabs(self):
        """Закрыть другие вкладки"""
        if not self.current_tab:
            return
        
        modified_other_tabs = [tab for tab in self.tabs.values() 
                              if tab != self.current_tab and tab.modified]
        
        if modified_other_tabs:
            if not messagebox.askyesno("Подтверждение", 
                                      f"Некоторые вкладки содержат несохраненные изменения. Закрыть их без сохранения?"):
                return
        
        current_tab_frame = self.current_tab.tab_frame
        
        for tab_frame in list(self.tabs.keys()):
            if tab_frame != current_tab_frame:
                self.notebook.forget(tab_frame)
                del self.tabs[tab_frame]
        
        self.update_tab_count()
    
    def show_about(self):
        """Показать информацию о программе"""
        about_text = (
            "Редактор IPTV листов\n\n"
            "Версия: в разработке\n\n"
            "Буду рад если оставите на чай\n"
            "Озон: 2204 3201 7065 3176\n"
            "Сбер: 2202 2010 9153 6009"
        )
        
        messagebox.showinfo("О программе", about_text)
    
    def on_closing(self):
        """Обработчик закрытия окна"""
        # Выгружаем все плагины
        if self.plugin_manager:
            self.plugin_manager.unload_all_plugins()
        
        modified_tabs = [tab for tab in self.tabs.values() if tab.modified]
        
        if modified_tabs:
            response = messagebox.askyesnocancel(
                "Подтверждение", 
                f"Найдено {len(modified_tabs)} вкладок с несохраненными изменениями.\n"
                "Сохранить изменения перед выходом?"
            )
            
            if response is None:
                return
            elif response:
                for tab in modified_tabs:
                    if tab.file_path:
                        tab.save_to_file()
                    else:
                        file_path = filedialog.asksaveasfilename(
                            defaultextension=".m3u",
                            filetypes=[("M3U файлы", "*.m3u"), ("M3U8 файлы", "*.m3u8")]
                        )
                        if file_path:
                            tab.save_to_file(file_path)
                        else:
                            return
        
        self.root.destroy()


def main():
    """Главная функция"""
    try:
        if platform.system() == "Windows":
            if hasattr(ctypes, 'windll'):
                try:
                    ctypes.windll.shcore.SetProcessDpiAwareness(1)
                except:
                    pass
        
        root = tk.Tk()
        
        app = IPTVEditor(root)
        
        root.mainloop()
        
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось запустить приложение:\n{str(e)}")


if __name__ == "__main__":
    main()
