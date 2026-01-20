from typing import Dict
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QGroupBox, QCheckBox,
    QRadioButton, QLabel, QDialogButtonBox
)


class RemoveMetadataDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Удаление метаданных из каналов")
        self.resize(400, 300)
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        info_label = QLabel("Выберите метаданные для удаления:")
        layout.addWidget(info_label)
        
        options_group = QGroupBox("Параметры удаления")
        options_layout = QVBoxLayout(options_group)
        
        self.tvg_id_check = QCheckBox("Удалить tvg-id")
        options_layout.addWidget(self.tvg_id_check)
        
        self.tvg_logo_check = QCheckBox("Удалить tvg-logo (логотипы)")
        options_layout.addWidget(self.tvg_logo_check)
        
        self.group_title_check = QCheckBox("Удалить group-title (группы)")
        options_layout.addWidget(self.group_title_check)
        
        self.user_agent_check = QCheckBox("Удалить User Agent")
        options_layout.addWidget(self.user_agent_check)
        
        self.catchup_check = QCheckBox("Удалить catchup атрибуты (catchup, catchup-days, catchup-source)")
        options_layout.addWidget(self.catchup_check)
        
        layout.addWidget(options_group)
        
        selection_group = QGroupBox("Область применения")
        selection_layout = QVBoxLayout(selection_group)
        
        self.current_channel_radio = QRadioButton("Только текущий канал")
        self.current_channel_radio.setChecked(True)
        selection_layout.addWidget(self.current_channel_radio)
        
        self.selected_channels_radio = QRadioButton("Выбранные каналы")
        selection_layout.addWidget(self.selected_channels_radio)
        
        self.all_channels_radio = QRadioButton("Все каналы в плейлисте")
        selection_layout.addWidget(self.all_channels_radio)
        
        layout.addWidget(selection_group)
        
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def get_metadata_options(self) -> Dict[str, bool]:
        return {
            'tvg_id': self.tvg_id_check.isChecked(),
            'tvg_logo': self.tvg_logo_check.isChecked(),
            'group_title': self.group_title_check.isChecked(),
            'user_agent': self.user_agent_check.isChecked(),
            'catchup': self.catchup_check.isChecked()
        }
    
    def get_selection_scope(self) -> str:
        if self.current_channel_radio.isChecked():
            return "current"
        elif self.selected_channels_radio.isChecked():
            return "selected"
        else:
            return "all"