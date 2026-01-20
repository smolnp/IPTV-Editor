import re
from typing import List, Dict


class PlaylistHeaderManager:
    def __init__(self):
        self.header_lines: List[str] = []
        self.epg_sources: List[str] = []
        self.custom_attributes: Dict[str, str] = {}
        self.playlist_name: str = ""
        self.has_extm3u: bool = False
    
    def parse_header(self, content: str):
        self.header_lines = []
        self.epg_sources = []
        self.custom_attributes = {}
        self.playlist_name = ""
        self.has_extm3u = False
        
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('#EXTM3U'):
                self.has_extm3u = True
                self.header_lines.append(line)
                if ' ' in line:
                    attrs_line = line[8:]
                    attrs = re.findall(r'(\S+?)=["\']?([^"\'\s]+)["\']?', attrs_line)
                    for key, value in attrs:
                        if key.lower() == 'url-tvg':
                            self.epg_sources.append(value)
                        else:
                            self.custom_attributes[key] = value
                            
            elif line.startswith('#PLAYLIST:'):
                self.playlist_name = line[10:]
                self.header_lines.append(line)
            elif line.startswith('#'):
                self.header_lines.append(line)
            else:
                break
    
    def update_epg_sources(self, sources: List[str]):
        self.epg_sources = sources
        self._update_extm3u_line()
    
    def set_playlist_name(self, name: str):
        self.playlist_name = name
        self._update_playlist_name_line()
    
    def add_custom_attribute(self, key: str, value: str):
        self.custom_attributes[key] = value
        self._update_extm3u_line()
    
    def remove_custom_attribute(self, key: str):
        if key in self.custom_attributes:
            del self.custom_attributes[key]
            self._update_extm3u_line()
    
    def _update_extm3u_line(self):
        self.header_lines = [line for line in self.header_lines if not line.startswith('#EXTM3U')]
        
        parts = ["#EXTM3U"]
        
        for epg_source in self.epg_sources:
            parts.append(f'url-tvg="{epg_source}"')
        
        for key, value in self.custom_attributes.items():
            parts.append(f'{key}="{value}"')
        
        self.header_lines.insert(0, ' '.join(parts))
    
    def _update_playlist_name_line(self):
        self.header_lines = [line for line in self.header_lines if not line.startswith('#PLAYLIST:')]
        
        if self.playlist_name:
            extm3u_index = -1
            for i, line in enumerate(self.header_lines):
                if line.startswith('#EXTM3U'):
                    extm3u_index = i
                    break
            
            if extm3u_index >= 0:
                self.header_lines.insert(extm3u_index + 1, f'#PLAYLIST:{self.playlist_name}')
            else:
                self.header_lines.append(f'#PLAYLIST:{self.playlist_name}')
    
    def get_header_text(self) -> str:
        header_text = '\n'.join(self.header_lines)
        if header_text:
            header_text += '\n\n'
        return header_text