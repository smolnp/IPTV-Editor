import re
from PyQt6.QtWidgets import (
    QPlainTextEdit, QMenu, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import (
    QAction, QFont, QColor, QTextCharFormat, 
    QSyntaxHighlighter, QTextCursor, QPainter, QFontMetrics
)
from widgets.line_number_area import LineNumberArea


class M3USyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []
        
        extinf_format = QTextCharFormat()
        extinf_format.setForeground(QColor("#FF6B6B"))
        extinf_format.setFontWeight(QFont.Weight.Bold)
        self.highlighting_rules.append((r'^#EXTINF.*', extinf_format))
        
        extvlcopt_format = QTextCharFormat()
        extvlcopt_format.setForeground(QColor("#4ECDC4"))
        extvlcopt_format.setFontItalic(True)
        self.highlighting_rules.append((r'^#EXTVLCOPT.*', extvlcopt_format))
        
        extx_format = QTextCharFormat()
        extx_format.setForeground(QColor("#9B59B6"))
        self.highlighting_rules.append((r'^#EXT.*', extx_format))
        
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#95A5A6"))
        comment_format.setFontItalic(True)
        self.highlighting_rules.append((r'^#.*', comment_format))
        
        attribute_format = QTextCharFormat()
        attribute_format.setForeground(QColor("#3498DB"))
        self.highlighting_rules.append((r'\b(tvg-id|tvg-logo|group-title)=\"[^"]*\"', attribute_format))
        
        url_format = QTextCharFormat()
        url_format.setForeground(QColor("#2ECC71"))
        url_format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
        self.highlighting_rules.append((r'^(?!\s*#).*://.*', url_format))
        
        http_format = QTextCharFormat()
        http_format.setForeground(QColor("#E67E22"))
        self.highlighting_rules.append((r'^https?://[^\s]+', http_format))
        
        rtmp_format = QTextCharFormat()
        rtmp_format.setForeground(QColor("#E74C3C"))
        self.highlighting_rules.append((r'^rtmp://[^\s]+', rtmp_format))
        
        udp_format = QTextCharFormat()
        udp_format.setForeground(QColor("#F39C12"))
        self.highlighting_rules.append((r'^udp://[^\s]+', udp_format))
    
    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            expression = re.compile(pattern)
            for match in expression.finditer(text):
                start = match.start()
                length = match.end() - start
                self.setFormat(start, length, format)


class EnhancedTextEdit(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(QFont("Courier New", 10))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.highlighter = M3USyntaxHighlighter(self.document())
        
        self.setViewportMargins(40, 0, 0, 0)
        
        self.line_number_area = LineNumberArea(self)
        self.update_line_number_area_width()
        
        self.textChanged.connect(self.update_line_numbers)
        self.verticalScrollBar().valueChanged.connect(self.update_line_numbers)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
    
    def update_line_number_area_width(self):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)
    
    def line_number_area_width(self):
        digits = 1
        count = max(1, self.blockCount())
        while count >= 10:
            count //= 10
            digits += 1
        space = 3 + self.fontMetrics().horizontalAdvance('9') * digits
        return space
    
    def update_line_numbers(self):
        self.update_line_number_area_width()
        self.line_number_area.update()
    
    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width()
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            cr.left(), cr.top(),
            self.line_number_area_width(), cr.height()
        )
    
    def _show_context_menu(self, position: QPoint):
        menu = QMenu(self)
        
        undo_action = QAction("Отменить", menu)
        undo_action.triggered.connect(self.undo)
        menu.addAction(undo_action)
        
        redo_action = QAction("Повторить", menu)
        redo_action.triggered.connect(self.redo)
        menu.addAction(redo_action)
        
        menu.addSeparator()
        
        cut_action = QAction("Вырезать", menu)
        cut_action.triggered.connect(self.cut)
        menu.addAction(cut_action)
        
        copy_action = QAction("Копировать", menu)
        copy_action.triggered.connect(self.copy)
        menu.addAction(copy_action)
        
        paste_action = QAction("Вставить", menu)
        paste_action.triggered.connect(self.paste)
        menu.addAction(paste_action)
        
        menu.addSeparator()
        
        select_all_action = QAction("Выделить всё", menu)
        select_all_action.triggered.connect(self.selectAll)
        menu.addAction(select_all_action)
        
        menu.addSeparator()
        
        format_action = QAction("Форматировать M3U", menu)
        format_action.triggered.connect(self.format_m3u)
        menu.addAction(format_action)
        
        menu.addSeparator()
        
        clear_action = QAction("Очистить", menu)
        clear_action.triggered.connect(self.clear)
        menu.addAction(clear_action)
        
        menu.exec(self.mapToGlobal(position))
    
    def format_m3u(self):
        text = self.toPlainText()
        lines = text.split('\n')
        
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if line:
                if line.startswith('#EXTINF'):
                    if ',' in line:
                        parts = line.split(',', 1)
                        attrs = parts[0]
                        name = parts[1].strip()
                        attrs = re.sub(r'\s+', ' ', attrs)
                        formatted_lines.append(f'{attrs},{name}')
                    else:
                        formatted_lines.append(line)
                elif line.startswith('#EXTVLCOPT'):
                    line = re.sub(r'\s+', ' ', line)
                    formatted_lines.append(line)
                elif not line.startswith('#'):
                    formatted_lines.append(line.strip())
                else:
                    formatted_lines.append(line)
        
        self.setPlainText('\n'.join(formatted_lines))