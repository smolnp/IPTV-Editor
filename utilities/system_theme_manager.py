import sys
import os
from typing import Dict


class SystemThemeManager:
    @staticmethod
    def get_hotkeys() -> Dict[str, str]:
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
        if sys.platform in ["linux", "linux2"]:
            config_home = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
            return os.path.join(config_home, "iptv_editor")
        elif sys.platform == "darwin":
            return os.path.expanduser("~/Library/Application Support/IPTVEditor")
        else:
            return os.path.expanduser("~/.iptv_editor")