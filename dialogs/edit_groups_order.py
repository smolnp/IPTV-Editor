from typing import List
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
    QComboBox, QPushButton, QLabel
)
from PyQt6.QtCore import Qt


class EditGroupsOrderDialog(QDialog):
    def __init__(self, current_groups: List[str], all_groups: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Редактирование порядка групп")
        self.resize(400, 500)
        
        self.current_groups = current_groups.copy()
        self.all_groups = all_groups.copy()
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        self.list_widget = QListWidget()
        for group in self.current_groups:
            self.list_widget.addItem(group)
        self.list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        layout.addWidget(self.list_widget)
        
        add_group_layout = QHBoxLayout()
        self.group_combo = QComboBox()
        for group in self.all_groups:
            if group not in self.current_groups:
                self.group_combo.addItem(group)
        
        add_group_btn = QPushButton("Добавить группу")
        add_group_btn.clicked.connect(self._add_group)
        add_group_layout.addWidget(self.group_combo)
        add_group_layout.addWidget(add_group_btn)
        
        layout.addLayout(add_group_layout)
        
        button_layout = QHBoxLayout()
        
        btn_up = QPushButton("↑ Вверх")
        btn_up.clicked.connect(lambda: self.move_list_item(-1))
        button_layout.addWidget(btn_up)
        
        btn_down = QPushButton("↓ Вниз")
        btn_down.clicked.connect(lambda: self.move_list_item(1))
        button_layout.addWidget(btn_down)
        
        button_layout.addStretch()
        
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self.accept)
        button_layout.addWidget(btn_ok)
        
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(btn_cancel)
        
        layout.addLayout(button_layout)
    
    def _add_group(self):
        current_text = self.group_combo.currentText()
        if current_text and current_text not in [self.list_widget.item(i).text() for i in range(self.list_widget.count())]:
            self.list_widget.addItem(current_text)
            self.group_combo.removeItem(self.group_combo.currentIndex())
    
    def move_list_item(self, direction):
        current_row = self.list_widget.currentRow()
        if current_row < 0:
            return
            
        new_row = current_row + direction
        if 0 <= new_row < self.list_widget.count():
            current_item = self.list_widget.takeItem(current_row)
            self.list_widget.insertItem(new_row, current_item)
            self.list_widget.setCurrentRow(new_row)
    
    def get_groups_order(self) -> List[str]:
        new_order = []
        for i in range(self.list_widget.count()):
            new_order.append(self.list_widget.item(i).text())
        return new_order