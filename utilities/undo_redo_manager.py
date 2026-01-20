from typing import List, Dict, Any, Optional
from datetime import datetime
from models.channel_data import ChannelData


class UndoRedoManager:
    def __init__(self, max_steps: int = 50):
        self.max_steps = max_steps
        self.undo_stack: List[Dict[str, Any]] = []
        self.redo_stack: List[Dict[str, Any]] = []
    
    def save_state(self, channels: List[ChannelData], description: str = ""):
        if self.redo_stack:
            self.redo_stack.clear()
        
        state = {
            'channels': [ch.to_dict() for ch in channels],
            'description': description,
            'timestamp': datetime.now().strftime("%H:%M:%S")
        }
        
        self.undo_stack.append(state)
        
        if len(self.undo_stack) > self.max_steps:
            self.undo_stack.pop(0)
    
    def can_undo(self) -> bool:
        return len(self.undo_stack) > 0
    
    def can_redo(self) -> bool:
        return len(self.redo_stack) > 0
    
    def undo(self) -> Optional[Dict[str, Any]]:
        if not self.can_undo():
            return None
        
        current_state = self.undo_stack.pop()
        self.redo_stack.append(current_state)
        
        if self.undo_stack:
            return self.undo_stack[-1]
        else:
            return {
                'channels': [],
                'description': 'Начальное состояние',
                'timestamp': datetime.now().strftime("%H:%M:%S")
            }
    
    def redo(self) -> Optional[Dict[str, Any]]:
        if not self.can_redo():
            return None
        
        state = self.redo_stack.pop()
        self.undo_stack.append(state)
        
        return state