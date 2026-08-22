from PySide6.QtCore import Qt, QPoint, QRect, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget, QApplication

class SelectionOverlay(QWidget):
    selection_completed = Signal(str, tuple)
    selection_cancelled = Signal()
    
    def __init__(self, mode="chat"):
        super().__init__()
        self.mode = mode # "chat" or "input" or "send_btn"
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SubWindow)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        
        # Kích thước khung quét cố định cho Chat Zone
        self.box_width = 250
        self.box_height = 200
        
        self.begin = QPoint()
        self.end = QPoint()
        self.is_dragging = False
        
        screen = QApplication.primaryScreen()
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CrossCursor)
        
        # Khởi tạo tâm của hộp quét nằm chính giữa màn hình
        geom = screen.geometry()
        self.box_center = QPoint(geom.width() // 2, geom.height() // 2)
        self.end = self.box_center
        self.is_dragging_box = False
        self.drag_offset = QPoint()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        
        if self.mode in ("input", "send_btn"):
            # Lớp phủ mờ
            painter.fillRect(self.rect(), QColor(0, 0, 0, 80))
            # Vẽ hồng tâm tại vị trí con trỏ chuột
            cx, cy = self.end.x(), self.end.y()
            color = QColor(0, 180, 255) if self.mode == "send_btn" else QColor(255, 165, 0)
            pen = QPen(color, 2, Qt.SolidLine)
            painter.setPen(pen)
            painter.drawEllipse(cx - 8, cy - 8, 16, 16)
            painter.drawLine(cx - 14, cy, cx + 14, cy)
            painter.drawLine(cx, cy - 14, cx, cy + 14)
        else: # chat
            # Lấy kích thước màn hình
            sw = self.width()
            sh = self.height()
            
            # Tính toán tọa độ hộp hướng dẫn
            cx, cy = self.box_center.x(), self.box_center.y()
            rx = cx - self.box_width // 2
            ry = cy - self.box_height // 2
            
            # Vẽ 4 hình chữ nhật mờ xung quanh vùng chọn để tạo hiệu ứng lớp phủ (không dùng CompositionMode_Clear để tránh lag)
            overlay_color = QColor(0, 0, 0, 100)
            
            # Top
            painter.fillRect(QRect(0, 0, sw, max(0, ry)), overlay_color)
            # Bottom
            painter.fillRect(QRect(0, ry + self.box_height, sw, max(0, sh - (ry + self.box_height))), overlay_color)
            # Left
            painter.fillRect(QRect(0, max(0, ry), max(0, rx), self.box_height), overlay_color)
            # Right
            painter.fillRect(QRect(rx + self.box_width, max(0, ry), max(0, sw - (rx + self.box_width)), self.box_height), overlay_color)
            
            # Vẽ viền đỏ nổi bật cho hộp hướng dẫn
            rect = QRect(rx, ry, self.box_width, self.box_height)
            pen = QPen(QColor(255, 0, 0), 2, Qt.SolidLine)
            painter.setPen(pen)
            painter.drawRect(rect)
            
            # Vẽ tâm điều hướng đặc màu xanh lá để dễ click vào
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 255, 120))
            painter.drawEllipse(cx - 15, cy - 15, 30, 30)
            painter.setBrush(Qt.NoBrush) # Reset brush để tránh ảnh hưởng đến các đối tượng vẽ sau
            
            # Vẽ chữ thập màu đen nhỏ bên trong để làm hồng tâm chính xác
            pen_cross = QPen(QColor(0, 0, 0), 2, Qt.SolidLine)
            painter.setPen(pen_cross)
            painter.drawLine(cx - 8, cy, cx + 8, cy)
            painter.drawLine(cx, cy - 8, cx, cy + 8)
            
            # Vẽ văn bản hướng dẫn phía trên khung
            painter.setPen(QColor(255, 0, 0))
            font = painter.font()
            font.setBold(True)
            font.setPointSize(10)
            painter.setFont(font)
            painter.drawText(rect.left(), rect.top() - 8, "KÉO TÂM XANH ĐỂ DI CHUYỂN, THẢ CHUỘT ĐỂ CHỌN")
            
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            try:
                pos = event.globalPosition().toPoint()
            except AttributeError:
                pos = event.globalPos()
                
            if self.mode in ("input", "send_btn"):
                self.is_dragging = True
            else: # chat
                # Kiểm tra xem có click trúng tâm xanh (bán kính 25px) hay không
                dx = pos.x() - self.box_center.x()
                dy = pos.y() - self.box_center.y()
                if dx * dx + dy * dy <= 625: # 25px radius
                    self.is_dragging_box = True
                    self.drag_offset = pos - self.box_center
                    self.setCursor(Qt.ClosedHandCursor)
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            try:
                pos = event.globalPosition().toPoint()
            except AttributeError:
                pos = event.globalPos()
                
            if self.mode in ("input", "send_btn") and getattr(self, "is_dragging", False):
                self.is_dragging = False
                x = pos.x()
                y = pos.y()
                self.selection_completed.emit(self.mode, (x, y, 1, 1))
                self.close()
            elif self.mode == "chat" and self.is_dragging_box:
                self.is_dragging_box = False
                self.setCursor(Qt.CrossCursor)
                x = self.box_center.x() - self.box_width // 2
                y = self.box_center.y() - self.box_height // 2
                self.selection_completed.emit(self.mode, (x, y, self.box_width, self.box_height))
                self.close()
            
    def mouseMoveEvent(self, event):
        try:
            pos = event.globalPosition().toPoint()
        except AttributeError:
            pos = event.globalPos()
            
        if self.mode in ("input", "send_btn"):
            self.end = pos
            self.update()
        else: # chat
            if self.is_dragging_box:
                self.box_center = pos - self.drag_offset
                self.update()
            else:
                # Thay đổi con trỏ chuột khi hover qua tâm điều hướng để báo hiệu có thể kéo thả
                dx = pos.x() - self.box_center.x()
                dy = pos.y() - self.box_center.y()
                if dx * dx + dy * dy <= 625:
                    self.setCursor(Qt.OpenHandCursor)
                else:
                    self.setCursor(Qt.CrossCursor)
            
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.selection_cancelled.emit()
            self.close()

class IndicatorOverlay(QWidget):
    """
    Always-on-top, click-through overlay that displays a red border around the Chat Zone
    and a green indicator box around the Input Zone point during active bidding.
    """
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.current_price = 0
        
        # Frameless, Always on Top, Click-through (Transparent for Input), Tool Window (no taskbar icon)
        self.setWindowFlags(
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnTopHint | 
            Qt.WindowTransparentForInput | 
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Fill the entire screen
        screen = QApplication.primaryScreen()
        self.setGeometry(screen.geometry())
        
    def set_current_price(self, price):
        self.current_price = price
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        
        # 1. Draw Chat Zone (Red Box)
        cx, cy, cw, ch = self.config.chat_zone
        if cw > 0 and ch > 0:
            pen_chat = QPen(QColor(255, 0, 0), 2, Qt.SolidLine)
            painter.setPen(pen_chat)
            painter.drawRect(cx, cy, cw, ch)
            
            # Label the box (draw outside the box to prevent OCR capturing it)
            painter.setPen(QColor(255, 0, 0))
            label_y = cy - 5 if cy > 20 else cy + ch + 15
            painter.drawText(cx + 5, label_y, "VUNG GE THEO DOI [ZALO]")
            
            # Draw Current Valid Price Text (Outside Chat Zone)
            if self.current_price > 0:
                # Semi-transparent dark background banner above the chat zone
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(0, 0, 0, 180))
                text_str = f"GIA HIEN TAI: {self.current_price}"
                
                # Determine Y position to stay outside of the captured area
                text_y = cy - 10 if cy > 40 else cy + ch + 25
                painter.drawRect(cx, text_y - 20, 220, 25)
                
                # Draw green bold text
                painter.setPen(QColor(0, 255, 100))
                font = painter.font()
                font.setBold(True)
                font.setPointSize(12)
                painter.setFont(font)
                painter.drawText(cx + 10, text_y - 2, text_str)
            
        # 2. Draw Input Zone (Green Box or Point Indicator)
        ix, iy, iw, ih = self.config.input_zone
        if iw > 0 and ih > 0:
            pen_input = QPen(QColor(0, 255, 100), 2, Qt.SolidLine)
            painter.setPen(pen_input)
            
            if iw == 1 and ih == 1:
                # Draw a small crosshair for single point
                size = 8
                painter.drawLine(ix - size, iy, ix + size, iy)
                painter.drawLine(ix, iy - size, ix, iy + size)
                painter.drawText(ix + 12, iy + 5, "DIEM NHAP TIN NHAN [ZALO]")
            else:
                painter.drawRect(ix, iy, iw, ih)
                painter.drawText(ix + 5, iy + 15, "O NHAP TIN NHAN [ZALO]")
                
        # 3. Draw Send Button Point (Blue crosshair)
        bx, by = self.config.send_btn
        if bx > 0 and by > 0:
            pen_btn = QPen(QColor(0, 180, 255), 2, Qt.SolidLine)
            painter.setPen(pen_btn)
            size = 8
            painter.drawLine(bx - size, by, bx + size, by)
            painter.drawLine(bx, by - size, bx, by + size)
            painter.drawText(bx + 12, by + 5, "DIEM CLICK GUI (SEND BUTTON)")
