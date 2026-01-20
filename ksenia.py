import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from main_window import IPTVEditor
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    
    if sys.platform in ["linux", "linux2", "darwin"]:
        app.setStyle("Fusion")
    else:
        app.setStyle("Fusion")
    
    window = IPTVEditor()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()