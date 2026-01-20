import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from PyQt6.QtGui import QColor


@dataclass
class ChannelData:
    name: str = ""
    group: str = "Без группы"
    tvg_id: str = ""
    tvg_logo: str = ""
    url: str = ""
    extinf: str = ""
    user_agent: str = ""
    extvlcopt_lines: List[str] = field(default_factory=list)
    extra_headers: Dict[str, str] = field(default_factory=dict)
    has_url: bool = True
    url_status: Optional[bool] = None
    url_check_time: Optional[datetime] = None
    link_source: str = ""
    sort_change: int = 0
    
    def copy(self) -> 'ChannelData':
        channel = ChannelData()
        channel.name = self.name
        channel.group = self.group
        channel.tvg_id = self.tvg_id
        channel.tvg_logo = self.tvg_logo
        channel.url = self.url
        channel.extinf = self.extinf
        channel.user_agent = self.user_agent
        channel.extvlcopt_lines = self.extvlcopt_lines.copy()
        channel.extra_headers = self.extra_headers.copy()
        channel.has_url = self.has_url
        channel.url_status = self.url_status
        channel.url_check_time = self.url_check_time
        channel.link_source = self.link_source
        channel.sort_change = self.sort_change
        return channel
    
    def copy_metadata_only(self) -> 'ChannelData':
        channel = ChannelData()
        channel.name = self.name
        channel.group = self.group
        channel.tvg_id = self.tvg_id
        channel.tvg_logo = self.tvg_logo
        channel.user_agent = self.user_agent
        channel.extvlcopt_lines = self.extvlcopt_lines.copy()
        channel.extra_headers = self.extra_headers.copy()
        channel.update_extinf()
        return channel
    
    def update_metadata_from(self, source_channel: 'ChannelData'):
        self.group = source_channel.group
        self.tvg_id = source_channel.tvg_id
        self.tvg_logo = source_channel.tvg_logo
        self.user_agent = source_channel.user_agent
        self.extvlcopt_lines = source_channel.extvlcopt_lines.copy()
        self.extra_headers = source_channel.extra_headers.copy()
        self.update_extinf()
    
    def update_extinf(self):
        parts = ["#EXTINF:-1"]
        if self.tvg_id:
            parts.append(f'tvg-id="{self.tvg_id}"')
        if self.tvg_logo:
            parts.append(f'tvg-logo="{self.tvg_logo}"')
        if self.group:
            parts.append(f'group-title="{self.group}"')
        parts.append(f',{self.name}')
        self.extinf = ' '.join(parts)
    
    def parse_extvlcopt_headers(self):
        self.extra_headers = {}
        self.user_agent = ""
        
        for line in self.extvlcopt_lines:
            if line.startswith('#EXTVLCOPT:http-user-agent='):
                user_agent = line.replace('#EXTVLCOPT:http-user-agent=', '').strip('"')
                self.extra_headers['User-Agent'] = user_agent
                self.user_agent = user_agent
            elif line.startswith('#EXTVLCOPT:http-referrer='):
                referrer = line.replace('#EXTVLCOPT:http-referrer=', '').strip('"')
                self.extra_headers['Referer'] = referrer
            elif line.startswith('#EXTVLCOPT:http-header='):
                header_line = line.replace('#EXTVLCOPT:http-header=', '').strip('"')
                if ':' in header_line:
                    key, value = header_line.split(':', 1)
                    self.extra_headers[key.strip()] = value.strip()
    
    def update_extvlcopt_from_headers(self):
        self.extvlcopt_lines = []
        
        if self.user_agent:
            self.extvlcopt_lines.append(f'#EXTVLCOPT:http-user-agent="{self.user_agent}"')
        
        for key, value in self.extra_headers.items():
            if key.lower() == 'user-agent':
                continue
            elif key.lower() == 'referer':
                self.extvlcopt_lines.append(f'#EXTVLCOPT:http-referrer="{value}"')
            else:
                self.extvlcopt_lines.append(f'#EXTVLCOPT:http-header="{key}: {value}"')
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'group': self.group,
            'tvg_id': self.tvg_id,
            'tvg_logo': self.tvg_logo,
            'url': self.url,
            'extinf': self.extinf,
            'user_agent': self.user_agent,
            'extvlcopt_lines': self.extvlcopt_lines,
            'extra_headers': self.extra_headers,
            'has_url': self.has_url,
            'url_status': self.url_status,
            'url_check_time': self.url_check_time.isoformat() if self.url_check_time else None,
            'link_source': self.link_source,
            'sort_change': self.sort_change
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChannelData':
        channel = cls()
        channel.name = data.get('name', '')
        channel.group = data.get('group', 'Без группы')
        channel.tvg_id = data.get('tvg_id', '')
        channel.tvg_logo = data.get('tvg_logo', '')
        channel.url = data.get('url', '')
        channel.extinf = data.get('extinf', '')
        channel.user_agent = data.get('user_agent', '')
        channel.extvlcopt_lines = data.get('extvlcopt_lines', [])
        channel.extra_headers = data.get('extra_headers', {})
        channel.has_url = data.get('has_url', True)
        channel.url_status = data.get('url_status')
        channel.link_source = data.get('link_source', '')
        channel.sort_change = data.get('sort_change', 0)
        
        check_time = data.get('url_check_time')
        if check_time:
            try:
                channel.url_check_time = datetime.fromisoformat(check_time)
            except (ValueError, TypeError):
                channel.url_check_time = None
        
        return channel
    
    def get_status_icon(self) -> str:
        if not self.has_url or not self.url or not self.url.strip():
            return "∅"
        elif self.url_status is None:
            return "?"
        elif self.url_status is True:
            return "✓"
        elif self.url_status is False:
            return "✗"
        else:
            return "?"
    
    def get_status_color(self) -> QColor:
        if not self.has_url or not self.url or not self.url.strip():
            return QColor("gray")
        elif self.url_status is None:
            return QColor("orange")
        elif self.url_status is True:
            return QColor("green")
        elif self.url_status is False:
            return QColor("red")
        else:
            return QColor("orange")
    
    def get_status_tooltip(self) -> str:
        if not self.has_url or not self.url or not self.url.strip():
            return "Нет URL"
        elif self.url_status is None:
            return "Не проверялось"
        elif self.url_status:
            if self.url_check_time:
                return f"Работает (проверено: {self.url_check_time.strftime('%H:%M:%S')})"
            else:
                return "Работает"
        else:
            if self.url_check_time:
                return f"Не работает (проверено: {self.url_check_time.strftime('%H:%M:%S')})"
            else:
                return "Не работает"
    
    def get_change_color(self) -> QColor:
        if self.sort_change > 0:
            return QColor(255, 255, 200)  # Желтый - опустился
        elif self.sort_change < 0:
            return QColor(200, 255, 200)  # Зеленый - поднялся
        else:
            return QColor(240, 240, 240)  # Серый - без изменений
    
    def match_by_name(self, other_channel: 'ChannelData') -> bool:
        return self.name.lower() == other_channel.name.lower()
    
    def match_by_name_and_group(self, other_channel: 'ChannelData') -> bool:
        return (self.name.lower() == other_channel.name.lower() and 
                self.group.lower() == other_channel.group.lower())