"""
Система плагинов для IPTV Editor (совместимость с Python 3.14)
"""

import os
import sys
import importlib
import inspect
import importlib.machinery
import importlib.metadata
from enum import Enum
from typing import Dict, List, Optional, Any, Type
from dataclasses import dataclass
from datetime import datetime


class PluginType(Enum):
    """Типы плагинов"""
    MENU = "menu"
    TOOLBAR = "toolbar"
    EXPORT = "export"
    FILTER = "filter"
    TAB = "tab"
    GENERIC = "generic"


@dataclass
class PluginInfo:
    """Информация о плагине"""
    name: str
    version: str
    author: str
    description: str
    plugin_type: PluginType


class PluginBase:
    """Базовый класс для всех плагинов"""
    
    def __init__(self, app):
        self.app = app
        self.info = PluginInfo(
            name="Базовый плагин",
            version="1.0",
            author="Неизвестно",
            description="Базовый плагин",
            plugin_type=PluginType.GENERIC
        )
    
    def initialize(self):
        """Инициализация плагина"""
        pass
    
    def cleanup(self):
        """Очистка ресурсов плагина"""
        pass
    
    def is_compatible(self) -> bool:
        """Проверка совместимости с текущей версией приложения"""
        return True


class MenuPlugin(PluginBase):
    """Плагин для добавления пунктов меню"""
    
    def __init__(self, app):
        super().__init__(app)
        self.info.plugin_type = PluginType.MENU
    
    def add_menu_items(self, menu):
        """Добавление пунктов меню"""
        pass


class ToolbarPlugin(PluginBase):
    """Плагин для добавления кнопок на панель инструментов"""
    
    def __init__(self, app):
        super().__init__(app)
        self.info.plugin_type = PluginType.TOOLBAR
    
    def add_toolbar_buttons(self, toolbar):
        """Добавление кнопок на панель инструментов"""
        pass


class ExportPlugin(PluginBase):
    """Плагин для экспорта данных"""
    
    def __init__(self, app):
        super().__init__(app)
        self.info.plugin_type = PluginType.EXPORT
    
    def export_data(self, data, format_name: str) -> Optional[str]:
        """Экспорт данных в указанном формате"""
        return None


class FilterPlugin(PluginBase):
    """Плагин для фильтрации каналов"""
    
    def __init__(self, app):
        super().__init__(app)
        self.info.plugin_type = PluginType.FILTER
    
    def filter_channels(self, channels, criteria) -> List:
        """Фильтрация каналов по критериям"""
        return channels


class TabPlugin(PluginBase):
    """Плагин для добавления новых вкладок"""
    
    def __init__(self, app):
        super().__init__(app)
        self.info.plugin_type = PluginType.TAB
    
    def create_tab(self, parent):
        """Создание новой вкладки"""
        return None


class PluginManager:
    """Менеджер плагинов (исправлен для Python 3.14+)"""
    
    def __init__(self, app):
        self.app = app
        self.plugins: Dict[str, PluginBase] = {}
        # Используем абсолютный путь к plugins
        self.plugins_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")
        
        print(f"[DEBUG] Директория плагинов: {self.plugins_dir}")
        
        # Создаем директорию плагинов, если она не существует
        if not os.path.exists(self.plugins_dir):
            print(f"[DEBUG] Создаю директорию плагинов: {self.plugins_dir}")
            os.makedirs(self.plugins_dir)
    
    def scan_plugins(self) -> List[str]:
        """Сканирование директории плагинов"""
        available_plugins = []
        
        if not os.path.exists(self.plugins_dir):
            print(f"[DEBUG] Директория плагинов не существует: {self.plugins_dir}")
            return available_plugins
        
        print(f"[DEBUG] Сканирую директорию плагинов: {self.plugins_dir}")
        
        for item in os.listdir(self.plugins_dir):
            plugin_path = os.path.join(self.plugins_dir, item)
            
            if os.path.isdir(plugin_path):
                # Проверяем, есть ли файл __init__.py в папке плагина
                init_file = os.path.join(plugin_path, "__init__.py")
                if os.path.exists(init_file):
                    print(f"[DEBUG] Найден плагин: {item}")
                    available_plugins.append(item)
                else:
                    print(f"[DEBUG] Пропускаю папку {item}, нет __init__.py")
        
        print(f"[DEBUG] Всего найдено плагинов: {len(available_plugins)}")
        return available_plugins
    
    def find_plugin_module(self, plugin_name: str):
        """Находит модуль плагина (исправленная версия для Python 3.14)"""
        try:
            # Получаем полный путь к папке плагина
            plugin_dir = os.path.join(self.plugins_dir, plugin_name)
            
            # Проверяем существование папки
            if not os.path.exists(plugin_dir):
                print(f"[ERROR] Папка плагина не найдена: {plugin_dir}")
                return None
            
            # Проверяем наличие __init__.py
            init_file = os.path.join(plugin_dir, "__init__.py")
            if not os.path.exists(init_file):
                print(f"[ERROR] Файл __init__.py не найден в: {plugin_dir}")
                return None
            
            # ВАЖНО: Добавляем родительскую директорию (plugins) в sys.path
            # чтобы импортировать как module.submodule
            if self.plugins_dir not in sys.path:
                sys.path.insert(0, self.plugins_dir)
            
            # Импортируем модуль как plugins.plugin_name
            module_name = f"plugins.{plugin_name}"
            print(f"[DEBUG] Пытаюсь импортировать модуль: {module_name}")
            print(f"[DEBUG] sys.path содержит: {sys.path[:3]}...")
            
            module = importlib.import_module(module_name)
            print(f"[DEBUG] Модуль {module_name} успешно импортирован")
            
            return module
            
        except ImportError as e:
            print(f"[ERROR] Ошибка импорта плагина '{plugin_name}': {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def load_plugin(self, plugin_name: str) -> bool:
        """Загрузка плагина по имени"""
        try:
            # Проверяем, не загружен ли уже плагин
            if plugin_name in self.plugins:
                print(f"[WARNING] Плагин '{plugin_name}' уже загружен")
                return False
            
            print(f"[DEBUG] Начинаю загрузку плагина: {plugin_name}")
            
            # Импортируем модуль плагина
            module = self.find_plugin_module(plugin_name)
            if not module:
                print(f"[ERROR] Не удалось найти модуль для плагина: {plugin_name}")
                return False
            
            # Ищем классы плагинов в модуле
            plugin_classes = []
            for name, obj in inspect.getmembers(module):
                if (inspect.isclass(obj) and 
                    issubclass(obj, PluginBase) and 
                    obj != PluginBase):
                    print(f"[DEBUG] Найден класс плагина: {name}")
                    plugin_classes.append(obj)
            
            if not plugin_classes:
                print(f"[ERROR] В плагине '{plugin_name}' не найден класс плагина")
                return False
            
            # Создаем экземпляр первого найденного плагина
            plugin_class = plugin_classes[0]
            plugin_instance = plugin_class(self.app)
            
            # Инициализируем плагин
            plugin_instance.initialize()
            
            # Добавляем плагин в список загруженных
            self.plugins[plugin_name] = plugin_instance
            
            print(f"[SUCCESS] Плагин '{plugin_name}' успешно загружен")
            return True
            
        except Exception as e:
            print(f"[ERROR] Ошибка загрузки плагина '{plugin_name}': {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def load_all_plugins(self) -> int:
        """Загрузка всех доступных плагинов"""
        available_plugins = self.scan_plugins()
        loaded_count = 0
        
        print(f"[DEBUG] Доступные плагины для загрузки: {available_plugins}")
        
        for plugin_name in available_plugins:
            if self.load_plugin(plugin_name):
                loaded_count += 1
        
        print(f"[DEBUG] Загружено плагинов: {loaded_count} из {len(available_plugins)}")
        return loaded_count
    
    def unload_plugin(self, plugin_name: str) -> bool:
        """Выгрузка плагина"""
        if plugin_name not in self.plugins:
            print(f"[WARNING] Плагин '{plugin_name}' не загружен")
            return False
        
        try:
            plugin = self.plugins[plugin_name]
            plugin.cleanup()
            
            del self.plugins[plugin_name]
            print(f"[INFO] Плагин '{plugin_name}' выгружен")
            return True
            
        except Exception as e:
            print(f"[ERROR] Ошибка выгрузки плагина '{plugin_name}': {str(e)}")
            return False
    
    def unload_all_plugins(self):
        """Выгрузка всех плагинов"""
        for plugin_name in list(self.plugins.keys()):
            self.unload_plugin(plugin_name)
    
    def get_plugin_info(self, plugin_name: str) -> Optional[PluginInfo]:
        """Получение информации о плагине"""
        if plugin_name in self.plugins:
            return self.plugins[plugin_name].info
        return None
    
    def get_loaded_plugins(self) -> List[str]:
        """Получение списка загруженных плагинов"""
        return list(self.plugins.keys())
    
    def get_available_plugins(self) -> List[str]:
        """Получение списка доступных плагинов"""
        return self.scan_plugins()
    
    def is_plugin_loaded(self, plugin_name: str) -> bool:
        """Проверка, загружен ли плагин"""
        return plugin_name in self.plugins
    
    def execute_plugin_method(self, plugin_name: str, method_name: str, *args, **kwargs) -> Any:
        """Выполнение метода плагина"""
        if plugin_name not in self.plugins:
            return None
        
        plugin = self.plugins[plugin_name]
        if hasattr(plugin, method_name):
            method = getattr(plugin, method_name)
            return method(*args, **kwargs)
        
        return None


# Пример простого плагина для тестирования
class ExamplePlugin(MenuPlugin):
    """Пример плагина для тестирования системы плагинов"""
    
    def __init__(self, app):
        super().__init__(app)
        self.info.name = "Пример плагина"
        self.info.version = "1.0"
        self.info.author = "Система плагинов"
        self.info.description = "Пример плагина для демонстрации работы системы"
    
    def initialize(self):
        """Инициализация плагина"""
        print(f"[DEBUG] Плагин '{self.info.name}' инициализирован")
    
    def cleanup(self):
        """Очистка ресурсов плагина"""
        print(f"[DEBUG] Плагин '{self.info.name}' очищен")
    
    def add_menu_items(self, menu):
        """Добавление пунктов меню"""
        # Добавляем подменю
        example_menu = self.app.get_menu("Плагины/Пример")
        example_menu.add_command(label="Тестовая команда", command=self.test_command)
        example_menu.add_separator()
        example_menu.add_command(label="Информация о плагине", command=self.show_info)
    
    def test_command(self):
        """Тестовая команда плагина"""
        from tkinter import messagebox
        messagebox.showinfo("Тест плагина", "Это тестовая команда из плагина!")
    
    def show_info(self):
        """Показать информацию о плагине"""
        from tkinter import messagebox
        info_text = f"""
        Плагин: {self.info.name}
        Версия: {self.info.version}
        Автор: {self.info.author}
        
        {self.info.description}
        
        Тип: {self.info.plugin_type.value}
        """
        messagebox.showinfo("Информация о плагине", info_text)
