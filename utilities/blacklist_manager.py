import os
import json
from datetime import datetime
from typing import List, Dict, Tuple
import logging

from models.channel_data import ChannelData
from utilities.system_theme_manager import SystemThemeManager

logger = logging.getLogger(__name__)


class BlacklistManager:
    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = SystemThemeManager.get_config_dir()
        
        self.config_dir = config_dir
        self.blacklist_file = os.path.join(config_dir, "blacklist.json")
        self.blacklist: List[Dict[str, str]] = []
        
        self._ensure_config_dir()
        self._load_blacklist()
    
    def _ensure_config_dir(self):
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir, exist_ok=True)
    
    def _load_blacklist(self):
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
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.error(f"Ошибка загрузки чёрного списка: {e}")
            self.blacklist = []
    
    def _save_blacklist(self):
        try:
            with open(self.blacklist_file, 'w', encoding='utf-8') as f:
                json.dump(self.blacklist, f, ensure_ascii=False, indent=2)
            return True
        except (IOError, OSError) as e:
            logger.error(f"Ошибка сохранения чёрного списка: {e}")
            return False
    
    def add_channel(self, name: str, tvg_id: str = ""):
        for item in self.blacklist:
            if (item.get('name', '').lower() == name.lower() and
                item.get('tvg_id', '').lower() == tvg_id.lower()):
                return False
        
        self.blacklist.append({
            'name': name,
            'tvg_id': tvg_id,
            'added_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        return self._save_blacklist()
    
    def remove_channel(self, name: str, tvg_id: str = ""):
        for i, item in enumerate(self.blacklist):
            if (item.get('name', '').lower() == name.lower() and
                item.get('tvg_id', '').lower() == tvg_id.lower()):
                del self.blacklist[i]
                self._save_blacklist()
                return True
        return False
    
    def get_all(self) -> List[Dict[str, str]]:
        return self.blacklist.copy()
    
    def clear(self):
        self.blacklist.clear()
        self._save_blacklist()
    
    def filter_channels(self, channels: List[ChannelData]) -> Tuple[List[ChannelData], int]:
        filtered_channels = []
        removed_count = 0
        
        for channel in channels:
            should_remove = False
            
            for black_item in self.blacklist:
                name_match = black_item.get('name', '').lower() in channel.name.lower()
                tvg_id_match = (black_item.get('tvg_id', '') and 
                               black_item.get('tvg_id', '').lower() == channel.tvg_id.lower())
                
                if name_match or tvg_id_match:
                    should_remove = True
                    break
            
            if not should_remove:
                filtered_channels.append(channel)
            else:
                removed_count += 1
        
        return filtered_channels, removed_count