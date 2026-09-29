import sys
import os
import time
import threading
import datetime
import pyautogui
pyautogui.PAUSE = 0.001
pyautogui.FAILSAFE = False
import mss as _mss_lib
import numpy as np
import cv2
import ctypes

# Win32 Keyboard Inputs Structures & Constants
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_CONTROL = 0x11
VK_A = 0x41
VK_RETURN = 0x0D
VK_BACK = 0x08
VK_V = 0x56

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_ulonglong)  # Use 64-bit pointer size
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT)
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("u", INPUT_UNION)
    ]

def press_win32_key(vk, is_up=False):
    flags = KEYEVENTF_KEYUP if is_up else 0
    # dwExtraInfo set to 0 (ULONG_PTR) for 64-bit compatibility
    ii = INPUT_UNION()
    ii.ki = KEYBDINPUT(vk, 0, flags, 0, 0)
    inp = INPUT(1, ii)  # INPUT_KEYBOARD = 1
    ctypes.windll.user32.SendInput(1, ctypes.pointer(inp), ctypes.sizeof(inp))

def press_win32_hotkey(vk_mod, vk_key):
    press_win32_key(vk_mod, False)
    press_win32_key(vk_key, False)
    press_win32_key(vk_key, True)
    press_win32_key(vk_mod, True)

def win32_click(x, y):
    ctypes.windll.user32.SetCursorPos(int(x), int(y))
    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0) # LEFTDOWN
    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0) # LEFTUP

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QTextEdit, QGroupBox, QFileDialog, QMessageBox, QDialog, QListWidget, QListWidgetItem, QCheckBox,
    QTimeEdit
)
from PySide6.QtCore import Signal, Slot, Qt, QTimer
from PySide6.QtGui import QFont, QColor

from src.ui.overlay import SelectionOverlay, IndicatorOverlay
from src.database import get_logs, get_timeline, clear_logs
from src.license import get_hardware_id, verify_license_key
class TrackedMessage:
    def __init__(self, raw_text, timestamp, status="TIN NHẮN THƯỜNG", cleaned_price=None):
        self.raw_text = raw_text
        self.timestamp = timestamp
        self.status = status  # "HỢP LỆ", "KHÔNG HỢP LỆ (Giá cũ)", "KHÔNG HỢP LỆ (Giá nhảy)", "TIN NHẮN THƯỜNG", "BẠN (BOT)"
        self.cleaned_price = cleaned_price

class LicenseDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Kích Hoạt Bản Quyền")
        self.setFixedSize(400, 220)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e24;
            }
            QLabel {
                color: #e0e0e0;
                font-family: 'Segoe UI', Inter, sans-serif;
                font-size: 13px;
                font-weight: bold;
            }
            QLineEdit {
                background-color: #2b2b36;
                border: 1px solid #4a4a56;
                border-radius: 4px;
                padding: 6px;
                color: #ffffff;
            }
            QPushButton {
                background-color: #3a86c8;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                color: #ffffff;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a96d8;
            }
        """)
        
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        layout.addWidget(QLabel("Mã thiết bị (HWID):"))
        self.txt_hwid = QLineEdit(get_hardware_id())
        self.txt_hwid.setReadOnly(True)
        layout.addWidget(self.txt_hwid)
        
        layout.addWidget(QLabel("Trạng thái:"))
        self.lbl_info = QLabel("Đang kiểm tra...")
        layout.addWidget(self.lbl_info)
        
        layout.addWidget(QLabel("Key bản quyền:"))
        self.txt_key = QLineEdit(self.config.license_key)
        layout.addWidget(self.txt_key)
        
        btn_layout = QHBoxLayout()
        self.btn_activate = QPushButton("Kích Hoạt")
        self.btn_activate.clicked.connect(self.activate)
        btn_layout.addWidget(self.btn_activate)
        
        self.btn_close = QPushButton("Đóng")
        self.btn_close.clicked.connect(self.close)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)
        
        self.update_status()
        
    def update_status(self):
        key = self.txt_key.text().strip()
        valid, msg, days_left, expiry_str = verify_license_key(key)
        if valid:
            self.lbl_info.setText("Đã kích hoạt. Hạn sử dụng: Vĩnh viễn")
            self.lbl_info.setStyleSheet("color: #00ff66; font-weight: bold;")
        else:
            self.lbl_info.setText("Chưa kích hoạt hoặc đã hết hạn!")
            self.lbl_info.setStyleSheet("color: #ff3333; font-weight: bold;")
            
    def activate(self):
        key = self.txt_key.text().strip()
        self.config.license_key = key
        self.update_status()
        if self.parent():
            self.parent().check_license()

def get_edit_distance(s1, s2):
    if len(s1) < len(s2):
        return get_edit_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
        
    return previous_row[-1]

def find_zalo_hwnd():
    import ctypes
    EnumWindows = ctypes.windll.user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)
    GetWindowText = ctypes.windll.user32.GetWindowTextW
    GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
    IsWindowVisible = ctypes.windll.user32.IsWindowVisible
    
    zalo_hwnds = []
    
    def foreach_window(hwnd, lParam):
        if IsWindowVisible(hwnd):
            length = GetWindowTextLength(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                GetWindowText(hwnd, buff, length + 1)
                title = buff.value
                if title == "Zalo":
                    zalo_hwnds.append(hwnd)
        return True
        
    EnumWindows(EnumWindowsProc(foreach_window), 0)
    return zalo_hwnds[0] if zalo_hwnds else None

class MainWindow(QMainWindow):
    global_space_pressed = Signal()
    bid_finished_signal = Signal(int, str)
    update_reaction_time_signal = Signal(str)

    def __init__(self, config, ocr_worker, auction_engine):
        super().__init__()
        self.config = config
        self.ocr_worker = ocr_worker
        self.auction_engine = auction_engine
        
        self.bid_sender_thread = None
        self.auto_bid_enabled = False
        self.user_last_bid = 0
        self.license_valid = False
        self.indicator_overlay = IndicatorOverlay(self.config)
        self.pre_typed_price = None
        # Only one bid may own the Zalo input/send path at a time. This also
        # prevents update_prices() from preparing a stale draft while the
        # previous bid is still being submitted.
        self.bid_send_in_progress = False
        self.draft_state = "EMPTY"
        self.draft_expected_price = None
        self.draft_observed_text = ""
        self.draft_candidate_text = None
        self.draft_candidate_since = 0.0
        self.draft_stable_frames = 0
        self.draft_observed_at = 0.0
        self.draft_ignore_until = 0.0
        self.draft_last_repair_at = 0.0
        self.draft_mismatch_key = None
        self.draft_mismatch_locked_logged = False
        self.draft_generation = 0
        self.draft_repair_attempts = 0
        self.pending_bid_request = None
        self.wait_confirm_generation = 0
        # pynput may emit repeated on_press events while Space is held. Keep a
        # key-down latch plus a short debounce so one physical press toggles
        # Semi-Auto at most once.
        self._space_key_down = False
        self._last_space_trigger_at = 0.0
        self._space_debounce_seconds = 0.25
        self.logged_chat_lines = set()
        self.last_frame_lines = []
        self.session_chat_history = []
        
        # UI configuration
        self.setWindowTitle("Zalo Auction Auto Bidder")
        self.setMinimumSize(540, 680)
        self.resize(540, 680)
        self.setup_stylesheet()
        
        self.init_ui()
        self.load_settings_to_ui()
        self.check_license()
        
        # Connect signals
        self.ocr_worker.status_changed.connect(self.update_ocr_status)
        self.ocr_worker.text_detected.connect(self.handle_ocr_texts)
        self.ocr_worker.debug_log.connect(self.log)
        self.ocr_worker.input_text_detected.connect(self.handle_input_text_detected)
        
        self.global_space_pressed.connect(self.action_manual_bid)
        self.bid_finished_signal.connect(self.on_bid_finished)
        self.update_reaction_time_signal.connect(self.lbl_reaction_time.setText)
        
        # Start pynput keyboard listener
        try:
            from pynput import keyboard
            self.pynput_listener = keyboard.Listener(
                on_press=self.on_global_key_press,
                on_release=self.on_global_key_release,
            )
            self.pynput_listener.start()
        except Exception as pynput_err:
            print(f"[Pynput Listener Error] {pynput_err}")
        self.auction_engine.price_updated.connect(self.update_prices)
        self.auction_engine.countdown_updated.connect(self.update_countdown)
        self.auction_engine.status_changed.connect(self.update_engine_status)
        self.auction_engine.auto_bid_triggered.connect(self.trigger_auto_bid)
        self.auction_engine.session_ended.connect(self.handle_session_end)
        
        # Local timer for countdown refresh (runs at 30ms for smooth millisecond clock update)
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_time)
        self.timer.start(30)
        
        # Timer to refresh open log windows in real-time (every 500ms)
        self.log_refresh_timer = QTimer(self)
        self.log_refresh_timer.setInterval(500)
        self.log_refresh_timer.timeout.connect(self.refresh_open_logs)
        
        # Start time sync background thread
        threading.Thread(target=self.sync_time_worker, daemon=True).start()
        
        # Auto-start OCR worker thread to load libraries and models immediately in the background
        from src.database import clear_logs
        try:
            clear_logs()
        except Exception:
            pass
        self.ocr_worker.start()
        
        # Auto-save signal connections on edit/input
        self.txt_start_price.textChanged.connect(self.auto_save_settings_from_ui)
        self.txt_max_price.textChanged.connect(self.auto_save_settings_from_ui)
        self.txt_step_price.textChanged.connect(self.auto_save_settings_from_ui)
        self.txt_end_time.timeChanged.connect(self.auto_save_settings_from_ui)
        self.txt_auto_bid_last.textChanged.connect(self.auto_save_settings_from_ui)
        self.txt_manual_time_offset.textChanged.connect(self.auto_save_settings_from_ui)
        self.cb_bid_mode.currentIndexChanged.connect(self.auto_save_settings_from_ui)
        
    def setup_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e24;
            }
            QWidget {
                color: #e0e0e0;
                font-family: 'Segoe UI', Inter, sans-serif;
                font-size: 13px;
            }
            QGroupBox {
                border: 2px solid #3a3a42;
                border-radius: 8px;
                margin-top: 2px;
                padding-top: 4px;
                margin-bottom: 2px;
                font-weight: bold;
                color: #ffb703;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QLabel {
                font-weight: normal;
            }
            QLineEdit, QComboBox, QTimeEdit {
                background-color: #2b2b36;
                border: 1px solid #4a4a56;
                border-radius: 4px;
                padding: 5px;
                color: #ffffff;
            }
            QLineEdit:focus, QComboBox:focus, QTimeEdit:focus {
                border: 1px solid #ffb703;
            }
            QTimeEdit QAbstractItemView, QTimeEdit QSpinBox, QComboBox QAbstractItemView {
                color: #000000;
                background-color: #ffffff;
            }
            /* Style specific text color of QTimeEdit and QComboBox inside settings panel */
            QTimeEdit, QComboBox {
                color: #000000;
                background-color: #ffffff;
            }
            /* Set QMessageBox texts to black to look neat and clean */
            QMessageBox QLabel {
                color: #000000;
            }
            QMessageBox QPushButton {
                color: #000000;
                background-color: #f0f0f0;
                border: 1px solid #ababab;
            }
            QMessageBox {
                background-color: #f0f0f0;
                color: #000000;
            }
            QPushButton {
                background-color: #2b2b36;
                border: 1px solid #4a4a56;
                border-radius: 4px;
                padding: 4px 8px;
                color: #ffffff;
                font-weight: bold;
                min-height: 24px;
            }
            QPushButton:hover {
                background-color: #3e3e4f;
                border-color: #ffb703;
            }
            QPushButton:pressed {
                background-color: #1e1e24;
            }
            QTextEdit {
                background-color: #15151b;
                border: 1px solid #3a3a42;
                border-radius: 6px;
                font-family: 'Consolas', monospace;
                color: #00ff66;
            }
            /* Styling for active state indicators */
            .status-green { color: #00ff66; font-weight: bold; }
            .status-red { color: #ff3333; font-weight: bold; }
            .price-highlight { font-size: 24px; font-weight: bold; color: #ffb703; }
            .countdown-highlight { font-size: 24px; font-weight: bold; color: #ff3333; }
        """)
        
    def init_ui(self):
        # Master horizontal layout to split Left (settings/logs) and Right (Price List)
        master_layout = QHBoxLayout()
        central_widget = QWidget()
        central_widget.setLayout(master_layout)
        self.setCentralWidget(central_widget)
        
        # Left container
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        left_widget.setLayout(left_layout)
        master_layout.addWidget(left_widget, 3) # Left side gets stretch factor 3
        
        # Left controls panel (Column 1 of Left side)
        left_controls_widget = QWidget()
        left_controls_layout = QVBoxLayout()
        left_controls_layout.setContentsMargins(2, 2, 2, 2)
        left_controls_layout.setSpacing(4)
        left_controls_widget.setLayout(left_controls_layout)
        left_layout.addWidget(left_controls_widget, 1) # stretch factor 1
        
        # Right container (Price Timeline List)
        right_group = QGroupBox()
        right_layout = QVBoxLayout()
        right_group.setLayout(right_layout)
        
        self.price_list_widget = QListWidget()
        self.price_list_widget.setStyleSheet("""
            QListWidget {
                background-color: #15151b;
                border: 2px solid #3a3a42;
                border-radius: 6px;
                color: #888899;
                font-family: 'Consolas', monospace;
                font-size: 14px;
                font-weight: bold;
            }
            QListWidget::item {
                padding: 5px;
                border-bottom: 1px solid #25252f;
            }
            QListWidget::item:selected {
                background-color: #ffb703;
                color: #1e1e24;
            }
        """)
        right_layout.addWidget(self.price_list_widget)
        master_layout.addWidget(right_group, 1) # Right side gets stretch factor 1
        
        # Assign main_layout as left_controls_layout so existing widgets code works on left controls panel
        main_layout = left_controls_layout
        
        # 1. THÔNG TIN PHIÊN ĐẤU GIÁ (Hai cột)
        info_group = QGroupBox()
        info_layout = QGridLayout()
        info_layout.setSpacing(6)
        info_layout.setContentsMargins(8, 8, 8, 8)
        info_group.setLayout(info_layout)
        
        # Đồng hồ realtime đặt ở đầu groupbox
        header_layout = QHBoxLayout()
        header_layout.addStretch()
        
        self.lbl_realtime_clock = QLabel("---")
        self.lbl_realtime_clock.setStyleSheet("font-size: 14px; font-weight: bold; color: #00ff66; font-family: 'Consolas', monospace;")
        header_layout.addWidget(self.lbl_realtime_clock)
        info_layout.addLayout(header_layout, 0, 0, 1, 4)
        
        # Cột 1
        info_layout.addWidget(QLabel("Giá hiện tại:"), 1, 0)
        self.lbl_curr_price = QLabel("---")
        self.lbl_curr_price.setStyleSheet("font-size: 18px; font-weight: bold; color: #00ff66;")
        info_layout.addWidget(self.lbl_curr_price, 1, 1)
        
        info_layout.addWidget(QLabel("Bước giá kế tiếp:"), 2, 0)
        self.lbl_next_price = QLabel("---")
        self.lbl_next_price.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffb703;")
        info_layout.addWidget(self.lbl_next_price, 2, 1)
        
        info_layout.addWidget(QLabel("Giá đã bid:"), 3, 0)
        self.lbl_user_bid = QLabel("Chưa bid")
        self.lbl_user_bid.setStyleSheet("font-size: 14px; color: #00d2ff; font-weight: bold;")
        info_layout.addWidget(self.lbl_user_bid, 3, 1)
        
        # Cột 2
        info_layout.addWidget(QLabel("Giờ kết thúc:"), 1, 2)
        self.lbl_end_time = QLabel("---")
        self.lbl_end_time.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffffff;")
        info_layout.addWidget(self.lbl_end_time, 1, 3)
        
        info_layout.addWidget(QLabel("Đếm ngược:"), 2, 2)
        self.lbl_countdown = QLabel("---")
        self.lbl_countdown.setStyleSheet("font-size: 20px; font-weight: bold; color: #ff3333;")
        info_layout.addWidget(self.lbl_countdown, 2, 3)
        
        info_layout.addWidget(QLabel("Phản xạ trễ:"), 3, 2)
        self.lbl_reaction_time = QLabel("Trễ: -- ms")
        self.lbl_reaction_time.setStyleSheet("font-size: 13px; font-weight: bold; color: #00d2ff;")
        info_layout.addWidget(self.lbl_reaction_time, 3, 3)
        
        # Adjust column stretch to balance the columns
        info_layout.setColumnStretch(1, 1)
        info_layout.setColumnStretch(3, 1)
        
        main_layout.addWidget(info_group, 0)
        
        # 2. CẤU HÌNH ĐẤU GIÁ (Bỏ tiêu đề)
        settings_group = QGroupBox()
        settings_layout = QGridLayout()
        settings_layout.setSpacing(6)
        settings_layout.setContentsMargins(8, 8, 8, 8)
        settings_group.setLayout(settings_layout)
        
        settings_layout.addWidget(QLabel("Chế độ đấu:"), 0, 0)
        self.cb_bid_mode = QComboBox()
        self.cb_bid_mode.addItem("Đấu tự do (Gửi ngay)", "last_seconds")
        self.cb_bid_mode.addItem("Giá mục tiêu (Max Price)", "target_price")
        self.cb_bid_mode.addItem("Kích hoạt thủ công (Semi-Auto)", "semi_auto")
        self.cb_bid_mode.addItem("Thả giá hẹn giờ (Fixed Price)", "fixed_schedule")
        self.cb_bid_mode.currentIndexChanged.connect(self.on_bid_mode_changed)
        settings_layout.addWidget(self.cb_bid_mode, 0, 1, 1, 3)

        self.lbl_start_price_title = QLabel("Giá bắt đầu:")
        settings_layout.addWidget(self.lbl_start_price_title, 1, 0)
        self.txt_start_price = QLineEdit()
        settings_layout.addWidget(self.txt_start_price, 1, 1)

        self.lbl_max_price_title = QLabel("Giá tối đa:")
        settings_layout.addWidget(self.lbl_max_price_title, 1, 2)
        self.txt_max_price = QLineEdit()
        settings_layout.addWidget(self.txt_max_price, 1, 3)
        
        self.lbl_step_price_title = QLabel("Bước giá:")
        settings_layout.addWidget(self.lbl_step_price_title, 2, 0)
        self.txt_step_price = QLineEdit()
        settings_layout.addWidget(self.txt_step_price, 2, 1)
        
        self.lbl_end_time_title = QLabel("Giờ kết thúc:")
        settings_layout.addWidget(self.lbl_end_time_title, 2, 2)
        self.txt_end_time = QTimeEdit()
        self.txt_end_time.setDisplayFormat("HH:mm:ss")
        settings_layout.addWidget(self.txt_end_time, 2, 3)
        
        self.lbl_auto_bid_last_title = QLabel("Kích hoạt cuối:")
        settings_layout.addWidget(self.lbl_auto_bid_last_title, 3, 0)
        self.container_auto_bid_last = QWidget()
        last_layout = QHBoxLayout(self.container_auto_bid_last)
        last_layout.setContentsMargins(0, 0, 0, 0)
        self.txt_auto_bid_last = QLineEdit("60")
        self.txt_auto_bid_last.setFixedWidth(50)
        last_layout.addWidget(self.txt_auto_bid_last)
        last_layout.addWidget(QLabel("giây"))
        settings_layout.addWidget(self.container_auto_bid_last, 3, 1)
        
        self.lbl_manual_time_offset_title = QLabel("Lệch giờ (s):")
        settings_layout.addWidget(self.lbl_manual_time_offset_title, 3, 2)
        self.txt_manual_time_offset = QLineEdit("0")
        settings_layout.addWidget(self.txt_manual_time_offset, 3, 3)
        
        # Selection buttons
        self.btn_select_chat = QPushButton("Chọn Vùng Chat (Né AVT)")
        self.btn_select_chat.clicked.connect(self.select_chat_zone)
        settings_layout.addWidget(self.btn_select_chat, 4, 0, 1, 2)
        
        self.btn_select_input = QPushButton("Chọn Điểm Nhập Tin")
        self.btn_select_input.clicked.connect(self.select_input_zone)
        settings_layout.addWidget(self.btn_select_input, 4, 2, 1, 2)

        self.btn_select_input_ocr = QPushButton("Chọn Vùng Chữ Ô Nhập (OCR)")
        self.btn_select_input_ocr.clicked.connect(self.select_input_ocr_zone)
        settings_layout.addWidget(self.btn_select_input_ocr, 5, 0, 1, 4)
        
        self.btn_select_send = QPushButton("Chọn Nút Gửi (Xanh)")
        self.btn_select_send.setStyleSheet("color: #00d2ff; font-weight: bold;")
        self.btn_select_send.clicked.connect(self.select_send_btn)
        settings_layout.addWidget(self.btn_select_send, 6, 0, 1, 4) # Spans full width
        
        self.btn_save_config = QPushButton("Lưu Cấu Hình")
        self.btn_save_config.setStyleSheet("background-color: #3a86c8;")
        self.btn_save_config.clicked.connect(self.save_settings_from_ui)
        settings_layout.addWidget(self.btn_save_config, 7, 0, 1, 2)
        
        self.btn_reset_config = QPushButton("Reset Mặc Định")
        self.btn_reset_config.setStyleSheet("background-color: #555555;")
        self.btn_reset_config.clicked.connect(self.reset_settings_action)
        settings_layout.addWidget(self.btn_reset_config, 7, 2, 1, 2)
        
        main_layout.addWidget(settings_group, 0)
        
        # 3. TRẠNG THÁI & ĐIỀU KHIỂN (Thu gọn 1 hàng, bỏ tiêu đề)
        control_group = QGroupBox()
        control_layout = QHBoxLayout()
        control_group.setLayout(control_layout)
        
        # Cột trạng thái xếp chồng dọc ở bên trái
        status_widget = QWidget()
        status_v_layout = QVBoxLayout(status_widget)
        status_v_layout.setContentsMargins(0, 0, 0, 0)
        status_v_layout.setSpacing(2)
        
        row_ge = QHBoxLayout()
        row_ge.addWidget(QLabel("GE:"))
        self.lbl_status_ocr = QLabel("Offline")
        self.lbl_status_ocr.setStyleSheet("color: #ff3333; font-weight: bold;")
        row_ge.addWidget(self.lbl_status_ocr)
        row_ge.addStretch()
        status_v_layout.addLayout(row_ge)
        
        row_ab = QHBoxLayout()
        row_ab.addWidget(QLabel("Auto Bid:"))
        self.lbl_status_autobid = QLabel("OFF")
        self.lbl_status_autobid.setStyleSheet("color: #ff3333; font-weight: bold;")
        row_ab.addWidget(self.lbl_status_autobid)
        row_ab.addStretch()
        status_v_layout.addLayout(row_ab)
        
        row_score = QHBoxLayout()
        row_score.addWidget(QLabel("Vùng quét:"))
        self.lbl_ocr_score = QLabel("Chưa đánh giá")
        self.lbl_ocr_score.setStyleSheet("color: #888888; font-weight: bold;")
        row_score.addWidget(self.lbl_ocr_score)
        row_score.addStretch()
        status_v_layout.addLayout(row_score)

        row_draft = QHBoxLayout()
        row_draft.addWidget(QLabel("Draft OCR:"))
        self.lbl_draft_status = QLabel("EMPTY | OCR: <TRỐNG>")
        self.lbl_draft_status.setStyleSheet("color: #aaaaaa; font-weight: bold;")
        row_draft.addWidget(self.lbl_draft_status)
        row_draft.addStretch()
        status_v_layout.addLayout(row_draft)
        
        control_layout.addWidget(status_widget)
        control_layout.addStretch()
        
        self.btn_manual_bid = QPushButton("KÍCH HOẠT ĐẤU [SPACE]")
        self.btn_manual_bid.setStyleSheet("background-color: #0077b6; font-size: 13px; height: 30px; min-width: 160px; font-weight: bold; color: #ffffff;")
        self.btn_manual_bid.clicked.connect(self.action_manual_bid)
        self.btn_manual_bid.hide() # Hidden by default
        control_layout.addWidget(self.btn_manual_bid)
        
        self.btn_start = QPushButton("START")
        self.btn_start.setStyleSheet("background-color: #004b23; font-size: 13px; height: 30px; min-width: 80px;")
        self.btn_start.clicked.connect(self.action_start)
        control_layout.addWidget(self.btn_start)
        
        self.btn_stop = QPushButton("STOP")
        self.btn_stop.setStyleSheet("background-color: #800f2f; font-size: 13px; height: 30px; min-width: 80px;")
        self.btn_stop.clicked.connect(self.action_stop)
        control_layout.addWidget(self.btn_stop)
        
        main_layout.addWidget(control_group, 0)
        
        # Log text box (visible directly on UI as a small screen)
        self.txt_logs = QTextEdit()
        self.txt_logs.setReadOnly(True)
        self.txt_logs.setFixedHeight(90)  # Cố định chiều cao 90px làm màn hình log
        main_layout.addWidget(self.txt_logs)
        
        self.btn_clear_log = QPushButton("Xóa Log")
        self.btn_clear_log.clicked.connect(self.clear_logs_action)
        self.btn_clear_log.hide()  # Ẩn nút Xóa Log khỏi giao diện
        
        self.btn_replay = QPushButton("Xem Replay")
        self.btn_replay.clicked.connect(self.replay_timeline)
        self.btn_show_log = QPushButton("Xem Log")
        self.btn_show_log.clicked.connect(self.show_log_popup)
        
        self.btn_license_popup = QPushButton("Bản Quyền")
        self.btn_license_popup.clicked.connect(self.open_license_dialog)
        self.btn_license_popup.hide()  # Ẩn nút Bản Quyền khỏi giao diện
        
        # Add signature at the bottom
        lbl_signature = QLabel("Software developed by Hieu Duong")
        lbl_signature.setAlignment(Qt.AlignCenter)
        lbl_signature.setStyleSheet("color: #555566; font-size: 11px; font-style: italic; margin-top: 5px;")
        main_layout.addWidget(lbl_signature)
        
        # Bottom button bar (chỉ còn Xem Replay và Xem Log)
        bottom_btn_layout = QHBoxLayout()
        bottom_btn_layout.addWidget(self.btn_replay)
        bottom_btn_layout.addWidget(self.btn_show_log)
        main_layout.addLayout(bottom_btn_layout)
        
        # Hide unneeded labels/status in engine status
        self.lbl_status_engine = QLabel()
        
    def load_settings_to_ui(self):
        # Select bid mode in dropdown
        mode_idx = self.cb_bid_mode.findData(self.config.bid_mode)
        if mode_idx >= 0:
            self.cb_bid_mode.setCurrentIndex(mode_idx)
        else:
            self.cb_bid_mode.setCurrentIndex(0)

        self.txt_start_price.setText(str(self.config.start_price))
        self.txt_max_price.setText(str(self.config.max_price))
        self.txt_step_price.setText(str(self.config.step_price))
        
        # Load end time to QTimeEdit supporting milliseconds (.zzz)
        from PySide6.QtCore import QTime
        t_str = self.config.end_time
        ms = 0
        if "." in t_str:
            t_parts = t_str.split('.')
            time_part = t_parts[0]
            try:
                ms_str = t_parts[1].ljust(3, '0')[:3]
                ms = int(ms_str)
            except ValueError:
                pass
        else:
            time_part = t_str
            
        parts = time_part.split(':')
        if len(parts) == 3:
            q_time = QTime(int(parts[0]), int(parts[1]), int(parts[2]), ms)
        elif len(parts) == 2:
            q_time = QTime(int(parts[0]), int(parts[1]), 0, ms)
        else:
            q_time = QTime(21, 30, 0, 0)
        self.txt_end_time.setTime(q_time)
        
        self.txt_auto_bid_last.setText(str(self.config.auto_bid_last_seconds))
        self.txt_manual_time_offset.setText(str(self.config.manual_time_offset))
        
        self.lbl_curr_price.setText("---")
        self.lbl_curr_price.setStyleSheet("font-size: 20px; font-weight: bold; color: #00ff66;")
        self.lbl_next_price.setText("---")
        self.lbl_next_price.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffb703;")
        self.lbl_user_bid.setText("Chưa bid")
        self.lbl_user_bid.setStyleSheet("font-size: 16px; color: #00d2ff;")
        self.lbl_end_time.setText(self.config.end_time)
        self.lbl_countdown.setText("---")
        self.lbl_reaction_time.setText("Trễ: -- ms")
        self.price_list_widget.clear()
        
        # Apply UI visibility based on loaded mode
        self.on_bid_mode_changed()
        self.update_selection_ticks()
        
    def update_selection_ticks(self):
        # Update Chat Zone button text and style
        if self.config.chat_zone != (0, 0, 300, 400):
            self.btn_select_chat.setText("Chọn Vùng Chat (Né AVT)  [Đã chọn ✓]")
            self.btn_select_chat.setStyleSheet("background-color: #004b23; color: #ffffff; font-weight: bold;")
        else:
            self.btn_select_chat.setText("Chọn Vùng Chat (Né AVT)")
            self.btn_select_chat.setStyleSheet("")

        # Update Input Zone button text and style
        if self.config.input_zone != (0, 0, 300, 50):
            self.btn_select_input.setText("Chọn Ô Nhập Tin  [Đã chọn ✓]")
            self.btn_select_input.setStyleSheet("background-color: #004b23; color: #ffffff; font-weight: bold;")
        else:
            self.btn_select_input.setText("Chọn Ô Nhập Tin")
            self.btn_select_input.setStyleSheet("")

        # Update Input OCR rectangle button text and style
        if self.config.input_ocr_zone != (0, 0, 300, 50):
            self.btn_select_input_ocr.setText("Chọn Vùng Chữ Ô Nhập (OCR)  [Đã chọn ✓]")
            self.btn_select_input_ocr.setStyleSheet("background-color: #004b23; color: #ffffff; font-weight: bold;")
        else:
            self.btn_select_input_ocr.setText("Chọn Vùng Chữ Ô Nhập (OCR)")
            self.btn_select_input_ocr.setStyleSheet("color: #ffb703; font-weight: bold;")

        # Update Send Button button text and style
        if self.config.send_btn != (0, 0):
            self.btn_select_send.setText("Chọn Nút Gửi (Xanh)  [Đã chọn ✓]")
            self.btn_select_send.setStyleSheet("background-color: #004b23; color: #ffffff; font-weight: bold;")
        else:
            self.btn_select_send.setText("Chọn Nút Gửi (Xanh)")
            self.btn_select_send.setStyleSheet("color: #00d2ff; font-weight: bold;")

    def auto_save_settings_from_ui(self):
        try:
            self.config.bid_mode = self.cb_bid_mode.currentData()
            
            start_price_text = self.txt_start_price.text().strip()
            if start_price_text.isdigit():
                self.config.start_price = int(start_price_text)
                
            max_price_text = self.txt_max_price.text().strip()
            if max_price_text.isdigit():
                self.config.max_price = int(max_price_text)
                
            step_price_text = self.txt_step_price.text().strip()
            if step_price_text.isdigit():
                self.config.step_price = int(step_price_text)
                
            if self.config.bid_mode == "fixed_schedule":
                self.config.end_time = self.txt_end_time.time().toString("HH:mm:ss.zzz")
            else:
                self.config.end_time = self.txt_end_time.time().toString("HH:mm:ss")
                
            auto_bid_last_text = self.txt_auto_bid_last.text().strip()
            if auto_bid_last_text.isdigit():
                self.config.auto_bid_last_seconds = int(auto_bid_last_text)
                
            manual_time_offset_text = self.txt_manual_time_offset.text().strip()
            if manual_time_offset_text.lstrip('-').isdigit():
                self.config.manual_time_offset = int(manual_time_offset_text)
                
            # Update UI label immediately
            if self.config.bid_mode == "last_seconds":
                self.lbl_end_time.setText(self.config.end_time)
            elif self.config.bid_mode == "target_price":
                self.lbl_end_time.setText("--- (Mục tiêu)")
            elif self.config.bid_mode == "fixed_schedule":
                self.lbl_end_time.setText(self.config.end_time)
            else:
                self.lbl_end_time.setText("--- (Thủ công)")
            
            # Reset engine price timeline
            self.auction_engine.reset()
        except Exception:
            pass
        
    def save_settings_from_ui(self):
        try:
            self.config.bid_mode = self.cb_bid_mode.currentData()
            self.config.start_price = int(self.txt_start_price.text())
            self.config.max_price = int(self.txt_max_price.text())
            self.config.step_price = int(self.txt_step_price.text())
            if self.config.bid_mode == "fixed_schedule":
                self.config.end_time = self.txt_end_time.time().toString("HH:mm:ss.zzz")
            else:
                self.config.end_time = self.txt_end_time.time().toString("HH:mm:ss")
            self.config.auto_bid_last_seconds = int(self.txt_auto_bid_last.text())
            self.config.manual_time_offset = int(self.txt_manual_time_offset.text())
            self.config.random_delay_min = 0.0
            self.config.random_delay_max = 0.0
            
            # Update UI label immediately
            if self.config.bid_mode == "last_seconds":
                self.lbl_end_time.setText(self.config.end_time)
            elif self.config.bid_mode == "target_price":
                self.lbl_end_time.setText("--- (Mục tiêu)")
            elif self.config.bid_mode == "fixed_schedule":
                self.lbl_end_time.setText(self.config.end_time)
            else:
                self.lbl_end_time.setText("--- (Thủ công)")
            
            self.log("Đã lưu cấu hình thành công!")
            self.auction_engine.reset()
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể lưu cấu hình: {str(e)}")

    def on_bid_mode_changed(self, index=None):
        mode = self.cb_bid_mode.currentData()
        if mode == "target_price":
            self.txt_end_time.setDisplayFormat("HH:mm:ss")
            self.lbl_start_price_title.hide()
            self.txt_start_price.hide()
            self.lbl_end_time_title.hide()
            self.txt_end_time.hide()
            self.lbl_auto_bid_last_title.hide()
            self.container_auto_bid_last.hide()
            self.lbl_step_price_title.show()
            self.txt_step_price.show()
            
            self.lbl_max_price_title.setText("Giá mục tiêu:")
            self.lbl_max_price_title.show()
            self.txt_max_price.show()
            
            self.lbl_end_time.setText("--- (Mục tiêu)")
            self.lbl_countdown.setText("---")
            self.btn_manual_bid.hide()
            
        elif mode == "semi_auto":
            self.txt_end_time.setDisplayFormat("HH:mm:ss")
            self.lbl_start_price_title.show()
            self.txt_start_price.show()
            self.lbl_max_price_title.setText("Giá tối đa:")
            self.lbl_max_price_title.show()
            self.txt_max_price.show()
            self.lbl_step_price_title.show()
            self.txt_step_price.show()
            
            self.lbl_end_time_title.hide()
            self.txt_end_time.hide()
            self.lbl_auto_bid_last_title.hide()
            self.container_auto_bid_last.hide()
            
            self.lbl_end_time.setText("--- (Thủ công)")
            self.lbl_countdown.setText("---")
            self.btn_manual_bid.setText("KÍCH HOẠT ĐẤU [SPACE]")
            self.btn_manual_bid.setStyleSheet("background-color: #0077b6; font-size: 13px; height: 30px; min-width: 160px; font-weight: bold; color: #ffffff;")
            self.btn_manual_bid.setEnabled(self.auction_engine.is_active)
            self.btn_manual_bid.show()
            
        elif mode == "fixed_schedule":
            self.txt_end_time.setDisplayFormat("HH:mm:ss.zzz")
            self.lbl_start_price_title.hide()
            self.txt_start_price.hide()
            self.lbl_step_price_title.hide()
            self.txt_step_price.hide()
            self.lbl_auto_bid_last_title.hide()
            self.container_auto_bid_last.hide()
            
            self.lbl_max_price_title.setText("Giá thả:")
            self.lbl_max_price_title.show()
            self.txt_max_price.show()
            
            self.lbl_end_time_title.setText("Giờ thả:")
            self.lbl_end_time_title.show()
            self.txt_end_time.show()
            
            self.lbl_end_time.setText(self.config.end_time)
            self.lbl_countdown.setText("---")
            self.btn_manual_bid.hide()
            
        else: # last_seconds
            self.txt_end_time.setDisplayFormat("HH:mm:ss")
            self.lbl_start_price_title.show()
            self.txt_start_price.show()
            self.lbl_max_price_title.setText("Giá tối đa:")
            self.lbl_max_price_title.show()
            self.txt_max_price.show()
            self.lbl_step_price_title.show()
            self.txt_step_price.show()
            
            self.lbl_end_time_title.setText("Giờ kết thúc:")
            self.lbl_end_time_title.show()
            self.txt_end_time.show()
            # Free Auto now reacts to every valid next price; the end time
            # still controls when the auction session stops.
            self.lbl_auto_bid_last_title.hide()
            self.container_auto_bid_last.hide()
            
            self.lbl_end_time.setText(self.config.end_time)
            self.btn_manual_bid.hide()



    def reset_settings_action(self):
        reply = QMessageBox.question(
            self, 
            "Xác nhận Reset", 
            "Bạn có chắc chắn muốn đặt lại toàn bộ cấu hình về giá trị mặc định và khởi động lại ứng dụng không?",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                # 1. Reset config variables
                self.config.reset_to_defaults()
                
                # 2. Spawn new process of the application
                import sys
                import subprocess
                subprocess.Popen([sys.executable] + sys.argv)
                
                # 3. Exit current application
                sys.exit(0)
            except Exception as e:
                QMessageBox.critical(self, "Lỗi", f"Không thể reset và khởi động lại: {str(e)}")
            
    def check_license(self):
        key = self.config.license_key
        valid, msg, days_left, expiry_str = verify_license_key(key)
        self.license_valid = valid
        if valid:
            self.btn_start.setEnabled(True)
            self.btn_license_popup.setText("Bản Quyền: Vĩnh Viễn")
            self.btn_license_popup.setStyleSheet("background-color: #004b23;")
        else:
            self.btn_start.setEnabled(False)
            self.btn_license_popup.setText("Bản Quyền: Chưa kích hoạt")
            self.btn_license_popup.setStyleSheet("background-color: #800f2f;")
            
    def open_license_dialog(self):
        dialog = LicenseDialog(self.config, self)
        dialog.exec()
        
    def log(self, message):
        offset_seconds = getattr(self.config, "manual_time_offset", 0)
        net_offset = getattr(self.config, "network_time_offset", 0.0)
        now = datetime.datetime.now() + datetime.timedelta(seconds=offset_seconds + net_offset)
        now_str = now.strftime("%H:%M:%S.%f")[:-3]
        self.txt_logs.append(f"[{now_str}] {message}")
        # Automatically scroll to the bottom to display the latest log entries
        self.txt_logs.ensureCursorVisible()
        
    @Slot(str, bool)
    def update_ocr_status(self, text, is_online):
        self.lbl_status_ocr.setText(text)
        color = "#00ff66" if is_online else "#ff3333"
        self.lbl_status_ocr.setStyleSheet(f"color: {color}; font-weight: bold;")
        
    @Slot(str, bool)
    def update_engine_status(self, text, is_online):
        self.lbl_status_engine.setText(text)
        color = "#00ff66" if is_online else "#ff3333"
        self.lbl_status_engine.setStyleSheet(f"color: {color}; font-weight: bold;")
        
    def _set_draft_state(self, state):
        self.draft_state = state
        expected = self.draft_expected_price
        observed = self.draft_observed_text or ""
        colors = {
            "READY": "#00ff66", "PREPARING": "#ffb703",
            "WAIT_CLEAR": "#00d2ff", "ERROR": "#ff3333", "EMPTY": "#aaaaaa",
        }
        color = colors.get(state, "#aaaaaa")
        if hasattr(self, "lbl_draft_status"):
            shown = observed if observed else "<EMPTY>"
            target = expected if expected is not None else "-"
            self.lbl_draft_status.setText(f"{state} | OCR: {shown} | Expected: {target} | Stable: {self.draft_stable_frames}")
            self.lbl_draft_status.setStyleSheet(f"color: {color}; font-weight: bold;")
        if self.indicator_overlay:
            self.indicator_overlay.set_draft_status(state, expected, observed, self.draft_stable_frames)

    def _reset_draft_controller(self):
        self.draft_expected_price = None
        self.draft_observed_text = ""
        self.draft_candidate_text = None
        self.draft_candidate_since = 0.0
        self.draft_stable_frames = 0
        self.draft_observed_at = 0.0
        self.draft_ignore_until = 0.0
        self.draft_last_repair_at = 0.0
        self.draft_mismatch_key = None
        self.draft_mismatch_locked_logged = False
        self.draft_repair_attempts = 0
        self.pending_bid_request = None
        self.pre_typed_price = None
        self.bid_send_in_progress = False
        self.wait_confirm_generation += 1
        self._set_draft_state("EMPTY")

    def _draft_is_ready(self, price):
        return (
            self.draft_state == "READY"
            and self.draft_expected_price == price
            and self.draft_observed_text == str(price)
            and self.draft_stable_frames >= 2
            and (time.monotonic() - self.draft_observed_at) <= 0.25
        )

    def _write_input_text(self, text):
        """The only OCR-mode path allowed to mutate the Zalo input editor."""
        try:
            ix, iy, iw, ih = self.config.input_zone
            if ix <= 0 or iy <= 0:
                self.log("[Draft Controller] Zalo input point is not configured.")
                return False
            dpr = self.ocr_worker.device_pixel_ratio
            win32_click(int(round((ix + iw // 2) * dpr)), int(round((iy + ih // 2) * dpr)))
            time.sleep(0.005)
            press_win32_hotkey(VK_CONTROL, VK_A)
            press_win32_key(VK_BACK, False)
            press_win32_key(VK_BACK, True)
            if text:
                pyautogui.write(str(text), interval=0.0)
            return True
        except Exception as exc:
            self.log(f"[Draft Controller] Could not replace editor text: {exc}")
            return False

    def _request_draft(self, price, force=False, is_repair=False):
        """Set desired draft; all editor writes are serialized through here."""
        if price is None:
            # After Send, let Zalo clear the editor and only cancel the queued
            # next draft. In every other state, remove a bot-owned stale draft
            # once (for example when an opponent reaches max_price).
            self.draft_expected_price = None
            if self.draft_state == "WAIT_CLEAR":
                self._set_draft_state("WAIT_CLEAR")
                return
            if self.draft_state != "EMPTY":
                self.draft_ignore_until = time.monotonic() + 0.12
                if not self._write_input_text(""):
                    self._set_draft_state("ERROR")
                    return
            self.pre_typed_price = None
            self.draft_candidate_text = None
            self.draft_candidate_since = 0.0
            self.draft_stable_frames = 0
            self._set_draft_state("EMPTY")
            return
        if (not self.auto_bid_enabled or not self.auction_engine.is_active
                or self.bid_send_in_progress or price <= 0 or price > self.config.max_price):
            return

        # While Zalo is clearing a sent message, remember the next desired value
        # without touching the editor. EMPTY confirmation will resume preparation.
        if self.draft_state == "WAIT_CLEAR":
            self.draft_expected_price = price
            self._set_draft_state("WAIT_CLEAR")
            return
        if (not force and self.draft_expected_price == price
                and self.draft_state in ("PREPARING", "READY")):
            return

        desired_changed = self.draft_expected_price != price
        self.draft_expected_price = price
        self.pre_typed_price = None
        self.draft_candidate_text = None
        self.draft_candidate_since = 0.0
        self.draft_stable_frames = 0
        self.draft_mismatch_key = None
        self.draft_mismatch_locked_logged = False
        if desired_changed and not is_repair:
            self.draft_repair_attempts = 0
        self.draft_generation += 1
        generation = self.draft_generation
        self.draft_ignore_until = time.monotonic() + 0.12
        self._set_draft_state("PREPARING")
        if not self._write_input_text(str(price)):
            self._set_draft_state("ERROR")
            return
        action = "Repair" if is_repair else "Prepared"
        self.log(f"[Draft Controller] {action} {price}; observing Input OCR.")
        QTimer.singleShot(1000, lambda g=generation: self._check_prepare_timeout(g))

    def _chat_barrier_is_clear(self):
        checker = getattr(self.ocr_worker, "has_unprocessed_chat_change", None)
        return not callable(checker) or not checker()

    def _try_dispatch_pending_bid(self):
        if self.pending_bid_request is None or self.bid_send_in_progress:
            return
        price, timings = self.pending_bid_request
        if self.draft_expected_price != price:
            self._request_draft(price)
            return
        if not self._draft_is_ready(price) or not self._chat_barrier_is_clear():
            return
        self.pending_bid_request = None
        QTimer.singleShot(0, lambda p=price, t=timings: self.trigger_bid_simulated(p, t))

    @Slot(str, float)
    def handle_input_text_detected(self, observed, observed_at):
        observed = "".join(ch for ch in (observed or "") if ch.isdigit())
        self.draft_observed_text = observed
        self.draft_observed_at = observed_at

        # Ignore samples captured while our own Ctrl+A/write operation is still
        # rendering. They are observations for display, not control decisions.
        if observed_at < self.draft_ignore_until:
            self._set_draft_state(self.draft_state)
            return

        if observed == self.draft_candidate_text:
            self.draft_stable_frames += 1
        else:
            self.draft_candidate_text = observed
            self.draft_candidate_since = observed_at
            self.draft_stable_frames = 1

        if self.draft_state == "WAIT_CLEAR":
            if observed == "" and self.draft_stable_frames >= 2:
                next_desired = self.draft_expected_price
                self.draft_expected_price = None
                self._set_draft_state("EMPTY")
                if next_desired is not None and self.auto_bid_enabled and self.auction_engine.is_active:
                    QTimer.singleShot(0, lambda p=next_desired: self._request_draft(p, force=True))
            else:
                self._set_draft_state("WAIT_CLEAR")
            return

        expected = self.draft_expected_price
        if expected is None:
            self._set_draft_state("EMPTY")
            return
        if observed == str(expected):
            if self.draft_stable_frames >= 2:
                self.draft_repair_attempts = 0
                self.draft_mismatch_key = None
                self.draft_mismatch_locked_logged = False
                self.pre_typed_price = expected
                self._set_draft_state("READY")
                self._try_dispatch_pending_bid()
            else:
                self._set_draft_state("PREPARING")
            return

        # A mismatch is an observation, never a terminal controller state.
        self._set_draft_state("PREPARING")
        mismatch_age = observed_at - self.draft_candidate_since
        persistent = self.draft_stable_frames >= 4 and mismatch_age >= 0.10
        if not persistent:
            return

        mismatch_key = (expected, observed)
        if mismatch_key != self.draft_mismatch_key:
            self.draft_mismatch_key = mismatch_key
            self.log(
                f"[Draft Controller] Persistent mismatch OCR='{observed or '<EMPTY>'}', "
                f"expected='{expected}'. Send remains locked."
            )

        # Use the capture timestamp for all mismatch timing decisions. This
        # keeps persistence and repair cooldown on the same clock even when an
        # OCR sample waited briefly in the signal queue.
        now = observed_at
        if self.draft_repair_attempts < 2 and now - self.draft_last_repair_at >= 0.20:
            self.draft_repair_attempts += 1
            self.draft_last_repair_at = now
            QTimer.singleShot(
                0,
                lambda p=expected: self._request_draft(p, force=True, is_repair=True),
            )
        elif self.draft_repair_attempts >= 2 and not self.draft_mismatch_locked_logged:
            self.draft_mismatch_locked_logged = True
            self.log("[Draft Controller] Repair limit reached; Send locked, monitoring continues.")

    def _check_prepare_timeout(self, generation):
        if generation != self.draft_generation or self.draft_state == "READY":
            return
        if self.draft_expected_price is not None and self.auction_engine.is_active:
            self._set_draft_state("PREPARING")
            self.log("[Draft Controller] Draft not READY after 1 second; Send locked, engine continues.")

    def _check_wait_confirm_timeout(self, generation):
        if generation != self.wait_confirm_generation or self.draft_state != "WAIT_CLEAR":
            return
        self.log("[Draft Controller] Input did not clear after Send; clearing once and continuing.")
        self.draft_ignore_until = time.monotonic() + 0.12
        if not self._write_input_text(""):
            self._set_draft_state("ERROR")

    def _calculate_prepared_price(self, current_valid):
        """Price to keep in the editor while waiting for the next opponent bid."""
        if self.config.bid_mode == "target_price":
            # Once the target has already been reached, leave the editor empty.
            # Re-preparing the same target after a successful send creates a
            # stale draft even though no further bid is legal.
            if current_valid >= self.config.max_price:
                return None
            return self.config.max_price
        if current_valid <= 0:
            return self.config.start_price
        if current_valid == self.user_last_bid:
            # Example: our 2200 is highest; wait for opponent 2300, then send 2400.
            return current_valid + 2 * self.config.step_price
        # Opponent is highest; our immediate response is one step above.
        return current_valid + self.config.step_price

    @Slot(int, int)
    def update_prices(self, current_valid, next_valid):
        self.lbl_curr_price.setText(str(current_valid))
        self.lbl_next_price.setText(str(next_valid))
        if self.indicator_overlay:
            self.indicator_overlay.set_current_price(current_valid)
            
        # Publish one desired draft. Only the Draft Controller may mutate
        # the editor; price updates never type directly.
        if self.auto_bid_enabled and not self.bid_send_in_progress and self.pending_bid_request is None:
            price_to_type = self._calculate_prepared_price(current_valid)
            if price_to_type is None:
                self._request_draft(None)
            else:
                price_to_type = max(price_to_type, self.config.start_price)
                if price_to_type <= self.config.max_price:
                    self._request_draft(price_to_type)
            
        # Draw and update the price timeline list on the right (Optimized: only redraw on value changes)
        timeline = getattr(self.auction_engine, "price_timeline", [])
        if timeline:
            # Check if we already have items and the active one hasn't changed to avoid expensive redraws
            has_items = self.price_list_widget.count() > 0
            is_same_selection = False
            selected_idx = -1
            
            for idx, price in enumerate(timeline):
                if price == current_valid:
                    selected_idx = idx
                    break
            
            if has_items:
                current_selected_row = self.price_list_widget.currentRow()
                if current_selected_row == selected_idx:
                    is_same_selection = True
            
            if not is_same_selection:
                self.price_list_widget.clear()
                for idx, price in enumerate(timeline):
                    # Format text: highlight start_price, max_price and normal steps
                    price_text = f"  {price}"
                    if price == self.config.start_price:
                        price_text += " [BAT DAU]"
                    elif price == self.config.max_price:
                        price_text += " [TOI DA]"
                    
                    # If this is the current active price, add pointer
                    if price == current_valid:
                        price_text = f"▶ {price_text.strip()}"
                    else:
                        price_text = f"  {price_text.strip()}"
                        
                    item = QListWidgetItem(price_text)
                    self.price_list_widget.addItem(item)
                    
                    # Paint backgrounds depending on price zone
                    if price == current_valid:
                        item.setForeground(QColor("#00ff66"))
                    elif price == next_valid:
                        item.setForeground(QColor("#ffb703"))
                    elif price > self.config.max_price:
                        item.setForeground(QColor("#ff3333"))
                    elif price >= self.config.start_price:
                        item.setForeground(QColor("#00d2ff")) # Bid zone color
                    
                if selected_idx >= 0:
                    self.price_list_widget.setCurrentRow(selected_idx)
        else:
            self.price_list_widget.clear()
            
    def calibrate_baseline_sync(self):
        """Synchronous calibration - kept for compatibility.
        Prefer _run_calibration_async() which does not block the UI thread.
        """
        x, y, w, h = self.config.chat_zone
        if w <= 0 or h <= 0:
            return
            
        try:
            dpr = self.ocr_worker.device_pixel_ratio
            monitor = {
                "top":    int(round(y * dpr)),
                "left":   int(round(x * dpr)),
                "width":  int(round(w * dpr)),
                "height": int(round(h * dpr)),
            }
            with _mss_lib.MSS() as sct:
                screenshot = sct.grab(monitor)
            arr      = np.array(screenshot)
            img_bgr  = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
            img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

            texts = []
            if self.ocr_worker.tesseract_available:
                texts = self.ocr_worker._tesseract_read(img_gray)
            elif self.ocr_worker.ocr and self.ocr_worker.ocr_engine_type == "paddle":
                result = self.ocr_worker.ocr.ocr(img_bgr, cls=False)
                if result and result[0]:
                    for line in result[0]:
                        if line[1][1] > 0.5:
                            texts.append(line[1][0])

            if texts:
                self.log(f"Đọc được từ màn hình: {texts}")
                self.auction_engine.process_ocr_texts(texts, time.time())
            else:
                self.log("Không đọc được ký tự nào trong Chat Zone. Vui lòng kiểm tra lại khung khoanh đỏ.")
        except Exception as e:
            self.log(f"Lỗi đồng bộ giá ban đầu: {str(e)}")
        
    @Slot(str, int)
    def update_countdown(self, countdown_str, seconds_remaining):
        if self.config.bid_mode in ("last_seconds", "fixed_schedule"):
            self.lbl_countdown.setText(countdown_str)
            self.seconds_remaining = seconds_remaining
        else:
            self.lbl_countdown.setText("---")
            self.seconds_remaining = 0
        
    def clean_and_normalize(self, line):
        import re
        s = line.lower()
        s = re.sub(r'[^a-z0-9]', '', s)
        return s

    def get_lcs_matched_indices(self, L, C):
        m, n = len(L), len(C)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if L[i-1] == C[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                else:
                    dp[i][j] = max(dp[i-1][j], dp[i][j-1])
                    
        matched_in_c = set()
        i, j = m, n
        while i > 0 and j > 0:
            if L[i-1] == C[j-1]:
                matched_in_c.add(j-1)
                i -= 1
                j -= 1
            elif dp[i-1][j] >= dp[i][j-1]:
                i -= 1
            else:
                j -= 1
        return matched_in_c

    def get_new_chat_lines(self, current_lines):
        clean_curr = [l.strip() for l in current_lines if self.clean_and_normalize(l)]
        norm_curr = [self.clean_and_normalize(l) for l in clean_curr]
        
        if not hasattr(self, "last_frame_lines") or not self.last_frame_lines:
            self.last_frame_lines = clean_curr
            return clean_curr
            
        clean_last = self.last_frame_lines
        norm_last = [self.clean_and_normalize(l) for l in clean_last]
        
        matched_in_c = self.get_lcs_matched_indices(norm_last, norm_curr)
        
        new_lines = []
        for idx, line in enumerate(clean_curr):
            if idx not in matched_in_c:
                new_lines.append(line)
                
        self.last_frame_lines = clean_curr
        return new_lines

    @Slot(list, object)
    def handle_ocr_texts(self, texts, timings):
        processed = False
        try:
            if isinstance(timings, dict) and timings.get("ocr_error"):
                self.pending_bid_request = None
                self.log(
                    f"[Chat Controller] Skipped failed OCR frame: "
                    f"{timings['ocr_error']}"
                )
            else:
                self._process_ocr_texts(texts, timings)
                processed = True
        except Exception as exc:
            # A malformed/failed frame is skipped. Never release a pending Send
            # created by a partially processed frame, but keep the engine alive
            # so the next captured change can be handled normally.
            self.pending_bid_request = None
            self.log(f"[Chat Controller] Skipped failed OCR frame: {exc}")
        finally:
            if isinstance(timings, dict):
                generation = timings.get("chat_frame_generation")
                marker = getattr(self.ocr_worker, "mark_chat_frame_consumed", None)
                if callable(marker):
                    marker(generation)
        if processed:
            self._try_dispatch_pending_bid()

    def _process_ocr_texts(self, texts, timings):
        # 1. Get new raw lines using the robust LCS-based previous frame comparison
        new_raw_lines = []
        if isinstance(timings, dict) and "raw_lines" in timings:
            curr_lines = [l.strip() for l in timings["raw_lines"] if l.strip()]
            new_raw_lines = self.get_new_chat_lines(curr_lines)
            
        # 2. Add to session history and classify
        new_messages = []
        now_str = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        is_calibration = (self.auction_engine.current_price <= 0)
        
        for line in new_raw_lines:
            # Ghi nhận tất cả các tin nhắn chat mới nhận diện được vào Log để người dùng quan sát trực quan
            self.log(f"[OCR - Tin mới] {line.strip()}")
            
            cleaned_price = self.ocr_worker._extract_price(line)
            price_val = int(cleaned_price) if cleaned_price else None
            
            msg = TrackedMessage(line, now_str, cleaned_price=price_val)
            
            # Lấy thông số đồng thuận bỏ phiếu cho giá trị đọc được
            votes_str = ""
            if cleaned_price:
                votes_val = getattr(self.ocr_worker, "last_ocr_votes", {}).get(str(cleaned_price), "")
                if votes_val:
                    votes_str = f" ({votes_val})"
            
            if is_calibration:
                if msg.cleaned_price is not None:
                    msg.status = "ĐỒNG BỘ BAN ĐẦU"
            else:
                if msg.cleaned_price is not None:
                    # Classify status
                    expected_next = self.auction_engine.get_next_valid_price()
                    current_price = self.auction_engine.current_price
                    
                    if price_val == self.user_last_bid:
                        msg.status = "BẠN (BOT)"
                        self.log(f"[OCR] Bạn (BOT) gửi giá: {price_val}{votes_str}")
                    elif price_val == expected_next:
                        msg.status = "HỢP LỆ"
                        self.log(f"[OCR] Khách gửi giá hợp lệ: {price_val}{votes_str}")
                    elif price_val > expected_next:
                        msg.status = f"KHÔNG HỢP LỆ (Giá nhảy: {price_val} > {expected_next})"
                        self.log(f"[Cảnh báo] Phát hiện giá nhảy vọt {price_val}{votes_str} (Mong đợi {expected_next}). Bỏ qua tin nhắn này.")
                    elif price_val < current_price:
                        msg.status = f"KHÔNG HỢP LỆ (Giá cũ: {price_val} < {current_price})"
                        self.log(f"[Cảnh báo] Phát hiện giá cũ {price_val}{votes_str} (Giá hiện tại đang là {current_price}). Bỏ qua.")
                    else:
                        msg.status = "KHÔNG HỢP LỆ (Trùng/Sai thứ tự)"
            
            self.session_chat_history.append(msg)
            new_messages.append(msg)
            
        # 3. Decide what prices to pass to the engine
        if self.auction_engine.is_active:
            if is_calibration:
                # Engine needs calibration, pass all texts
                self.auction_engine.process_ocr_texts(texts, timings)
            else:
                # Already calibrated, only process prices from newly arrived messages
                new_prices = []
                for msg in new_messages:
                    if msg.cleaned_price is not None:
                        new_prices.append(str(msg.cleaned_price))
                        
                if new_prices:
                    new_prices.reverse() # Reverse because process_ocr_texts reverses it back
                    self.auction_engine.process_ocr_texts(new_prices, timings)

    def refresh_time(self):
        # Update system realtime clock to align with logs timestamp (with milliseconds)
        offset_seconds = getattr(self.config, "manual_time_offset", 0)
        net_offset = getattr(self.config, "network_time_offset", 0.0)
        now = datetime.datetime.now() + datetime.timedelta(seconds=offset_seconds + net_offset)
        now_str = now.strftime("%H:%M:%S.%f")[:-3]
        self.lbl_realtime_clock.setText(now_str)
        
        if self.auction_engine.is_active:
            # Check high-precision trigger in fixed_schedule mode
            if self.config.bid_mode == "fixed_schedule":
                try:
                    time_str = self.config.end_time
                    ms = 0
                    if "." in time_str:
                        parts = time_str.split(".")
                        time_str = parts[0]
                        try:
                            ms_str = parts[1].ljust(3, '0')[:3]
                            ms = int(ms_str)
                        except ValueError:
                            pass
                    
                    parts = time_str.split(':')
                    if len(parts) == 3:
                        target_time = now.replace(hour=int(parts[0]), minute=int(parts[1]), second=int(parts[2]), microsecond=ms * 1000)
                    elif len(parts) == 2:
                        target_time = now.replace(hour=int(parts[0]), minute=int(parts[1]), second=0, microsecond=ms * 1000)
                    else:
                        target_time = None
                    
                    if target_time:
                        # If target time is in the past by more than 5 seconds, assume it's next day
                        if target_time < now and (now - target_time).total_seconds() > 5.0:
                            target_time += datetime.timedelta(days=1)
                        
                        if target_time <= now:
                            diff_sec = (now - target_time).total_seconds()
                            # Check if trigger condition is met
                            if diff_sec <= 2.0 and target_time >= (getattr(self, "engine_start_time", now) - datetime.timedelta(seconds=2)):
                                self.trigger_scheduled_bid(target_time)
                except Exception as e:
                    self.log(f"[Lỗi hẹn giờ] {e}")

            # Throttle countdown calculation to once per second (approx every 33 ticks of 30ms = 990ms)
            if not hasattr(self, "_countdown_tick_count"):
                self._countdown_tick_count = 0
            self._countdown_tick_count += 1
            if self._countdown_tick_count >= 33:
                self._countdown_tick_count = 0
                self.auction_engine.update_countdown()

    def sync_time_worker(self):
        self.log("[Time Sync] Đang đồng bộ giờ trực tuyến từ Google/Microsoft...")
        import urllib.request
        import email.utils
        
        urls = ["https://www.google.com", "https://www.microsoft.com"]
        for url in urls:
            try:
                req = urllib.request.Request(url, method="HEAD")
                t_start = time.time()
                with urllib.request.urlopen(req, timeout=3.0) as response:
                    t_end = time.time()
                    date_str = response.info().get("Date")
                    if date_str:
                        gmt_tuple = email.utils.parsedate_to_datetime(date_str)
                        local_dt = gmt_tuple.astimezone().replace(tzinfo=None)
                        rtt = t_end - t_start
                        sys_now = datetime.datetime.now()
                        network_dt = local_dt + datetime.timedelta(seconds=rtt/2)
                        offset = (network_dt - sys_now).total_seconds()
                        
                        self.config.network_time_offset = offset
                        self.log(f"[Time Sync] Đồng bộ giờ mạng thành công từ {url}. Độ lệch giờ hệ thống: {offset:.3f} giây.")
                        return
            except Exception as e:
                self.log(f"[Time Sync] Không thể lấy giờ từ {url}: {str(e)}")
                continue
                
        # If all failed, set network_time_offset to 0
        self.config.network_time_offset = 0.0
        self.log("[Time Sync] Không thể lấy giờ mạng (Dùng giờ hệ thống).")
            

        
    def action_start(self):
        if not self.license_valid:
            QMessageBox.warning(self, "Bản quyền", "Vui lòng nhập License Key hợp lệ để sử dụng.")
            return
            
        self.save_settings_from_ui()
        if self.config.bid_mode != "fixed_schedule" and self.config.input_ocr_zone == (0, 0, 300, 50):
            QMessageBox.warning(self, "Missing Input OCR Zone", "Select the Input OCR text rectangle before START.")
            return
        self.logged_chat_lines.clear()
        self._reset_draft_controller()
        self.last_frame_lines = []
        self.session_chat_history.clear()
        if hasattr(self, "seen_invalid_prices"):
            self.seen_invalid_prices.clear()
        self.auction_engine.reset()
        
        # Record start time
        offset_seconds = getattr(self.config, "manual_time_offset", 0)
        net_offset = getattr(self.config, "network_time_offset", 0.0)
        self.engine_start_time = datetime.datetime.now() + datetime.timedelta(seconds=offset_seconds + net_offset)
        
        # Start engine and enable auto-bid
        # Start engine
        self.auction_engine.start()
        
        # Populate countdown
        self.auction_engine.update_countdown()
        
        if self.config.bid_mode != "fixed_schedule":
            # Make sure the OCR worker background thread is running
            if not self.ocr_worker.isRunning():
                self.ocr_worker.start()
                self.log("[Hệ thống] Đang khởi động lại luồng quét GE...")
            
            # Start capturing immediately - the main OCR worker thread will handle initial syncing
            self.ocr_worker.start_capturing()
                
            self.log("BẮT ĐẦU theo dõi đấu giá.")
            
            # Show overlay immediately
            if self.indicator_overlay:
                self.indicator_overlay.set_current_price(self.auction_engine.current_price)
                self.indicator_overlay.show()
        else:
            self.log("BẮT ĐẦU theo dõi đấu giá.")
            self.log("[Hệ thống] Chế độ thả giá hẹn giờ hoạt động không cần quét màn hình (OCR).")
            
        # Toggle manual bid button if mode is semi-auto
        if self.config.bid_mode == "semi_auto":
            self.semi_auto_armed = False
            self.toggle_auto_bid(False)
            self.btn_manual_bid.setText("KÍCH HOẠT ĐẤU [SPACE]")
            self.btn_manual_bid.setStyleSheet("background-color: #0077b6; font-size: 13px; height: 30px; min-width: 160px; font-weight: bold; color: #ffffff;")
            self.btn_manual_bid.setEnabled(True)
            self.btn_manual_bid.show()
        else:
            self.toggle_auto_bid(True)
            self.btn_manual_bid.hide()
            
        # Start from a known empty editor through the single controller path.
        if not self._write_input_text(""):
            self.log("[Lỗi Focus Click] Không thể làm trống ô nhập khi START.")
        
    def restore_main_window(self):
        if self.indicator_overlay:
            self.indicator_overlay.hide()
        
    def action_pause(self):
        self.ocr_worker.stop_capturing()
        self.auction_engine.stop()
        self.toggle_auto_bid(False)
        self.semi_auto_armed = False
        if self.config.bid_mode == "semi_auto":
            self.btn_manual_bid.setText("KÍCH HOẠT ĐẤU [SPACE]")
            self.btn_manual_bid.setStyleSheet("background-color: #0077b6; font-size: 13px; height: 30px; min-width: 160px; font-weight: bold; color: #ffffff;")
            self.btn_manual_bid.setEnabled(False)
            self.btn_manual_bid.show()
        else:
            self.btn_manual_bid.hide()
        self.pre_typed_price = None
        self.clear_input_zone()
        self.log("TẠM DỪNG theo dõi.")
        self.restore_main_window()
        
    def action_stop(self):
        self.ocr_worker.stop_capturing()
        self.auction_engine.stop()
        self.toggle_auto_bid(False)
        self.semi_auto_armed = False
        if self.config.bid_mode == "semi_auto":
            self.btn_manual_bid.setText("KÍCH HOẠT ĐẤU [SPACE]")
            self.btn_manual_bid.setStyleSheet("background-color: #0077b6; font-size: 13px; height: 30px; min-width: 160px; font-weight: bold; color: #ffffff;")
            self.btn_manual_bid.setEnabled(False)
            self.btn_manual_bid.show()
        else:
            self.btn_manual_bid.hide()
        self.user_last_bid = 0
        self.pre_typed_price = None
        self.clear_input_zone()
        self.log("DỪNG hẳn theo dõi. Đã reset lượt bid cuối của bạn.")
        self.restore_main_window()

    def action_manual_bid(self):
        if not self.auction_engine.is_active:
            return
            
        if not hasattr(self, "semi_auto_armed"):
            self.semi_auto_armed = False
            
        if not self.semi_auto_armed:
            # ARM the auto-bidder (Toggle ON)
            self.semi_auto_armed = True
            self.toggle_auto_bid(True)
            
            # Change style to bright green
            self.btn_manual_bid.setStyleSheet("background-color: #00ff66; font-size: 13px; height: 30px; min-width: 160px; font-weight: bold; color: #000000;")
            self.btn_manual_bid.setText("ĐANG ĐẤU TỰ ĐỘNG...")
            
            # Focus chat input box since the user might have clicked the button on our GUI, shifting focus to our window
            try:
                input_x, input_y, input_w, input_h = self.config.input_zone
                if input_w <= 1 and input_h <= 1:
                    click_x = input_x
                    click_y = input_y
                else:
                    click_x = input_x + input_w / 2
                    click_y = input_y + input_h / 2
                    
                dpr = self.ocr_worker.device_pixel_ratio
                cx = int(click_x * dpr)
                cy = int(click_y * dpr)
                win32_click(cx, cy)
                time.sleep(0.05) # Give Windows 50ms to switch focus
            except Exception as focus_err:
                self.log(f"[Lỗi Focus Click] {focus_err}")
            
            # Immediately trigger the first bid
            next_price = self.auction_engine.get_next_valid_price()
            if next_price <= 0:
                self.log("[Cảnh báo] Chưa xác định được giá để gửi!")
                return
            if next_price > self.config.max_price:
                self.log(f"[Cảnh báo] Giá tiếp theo {next_price} vượt quá giá tối đa {self.config.max_price}!")
                return
                
            self.log(f"[Thủ công] Kích hoạt và gửi giá đầu tiên: {next_price}")
            self.trigger_bid_simulated(next_price)
        else:
            # DISARM the auto-bidder (Toggle OFF)
            self.semi_auto_armed = False
            self.toggle_auto_bid(False)
            
            # Change style back to blue
            self.btn_manual_bid.setStyleSheet("background-color: #0077b6; font-size: 13px; height: 30px; min-width: 160px; font-weight: bold; color: #ffffff;")
            self.btn_manual_bid.setText("KÍCH HOẠT ĐẤU [SPACE]")
            self.clear_input_zone()
            self.log("[Thủ công] Đã tạm dừng quyền đấu giá tự động.")
        
    def action_test_ocr(self):
        self.log("Bắt đầu TEST OCR vùng chọn...")
        # Run ocr_worker logic once without thread loop to test screenshot
        pass
        
    def action_test_send(self):
        self.log("Bắt đầu TEST SEND 1 bước giá vào ô chat...")
        next_price = self.auction_engine.get_next_valid_price()
        self.trigger_bid_simulated(next_price)
        
    def action_emergency(self):
        self.action_stop()
        self.toggle_auto_bid(False)
        self.log("!!! EMERGENCY STOP KÍCH HOẠT !!! Dừng toàn bộ hoạt động.")
        self.restore_main_window()
            
    def toggle_auto_bid(self, state):
        self.auto_bid_enabled = state
        status_text = "AUTO" if state else "OFF"
        color = "#00ff66" if state else "#ff3333"
        self.lbl_status_autobid.setText(status_text)
        self.lbl_status_autobid.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.log(f"Chế độ Auto Bid: {status_text}")
        
    def trigger_auto_bid(self, target_price, timings):
        if not self.auto_bid_enabled or not self.auction_engine.is_active:
            return
            
        # SAFETY CHECK: Do not bid if price is invalid or zero
        if target_price <= 0:
            return
            
        # Handle modes:
        if self.config.bid_mode == "target_price":
            # In Target Price Mode, only trigger when next_price matches the target price (config.max_price)
            if target_price != self.config.max_price:
                return
        elif self.config.bid_mode == "semi_auto":
            # In Semi-Auto, only allow auto-bidding if armed
            if not getattr(self, "semi_auto_armed", False):
                return
        else: # last_seconds (free auto): send immediately on a valid next step
            if target_price < self.config.start_price:
                return
            
        # SAFETY: Do not exceed max price (target price in Target Price mode is also config.max_price)
        if target_price > self.config.max_price:
            return
            
        # CHẶN TỰ BID ĐÈ: Nếu giá cao nhất hiện tại đã bằng đúng giá của bot vừa bid, không bid tiếp
        if self.auction_engine.current_price == self.user_last_bid:
            return
            
        # Check if we already bid this price
        if self.user_last_bid >= target_price:
            return
            
        self.log(f"[Auto Bid] Kích hoạt gửi giá: {target_price}")
        self.trigger_bid_simulated(target_price, timings)

    def _is_bid_price_still_valid(self, price):
        """Validate an OCR-mode bid against the latest engine price."""
        if self.config.bid_mode == "fixed_schedule":
            return True
        current_price = self.auction_engine.current_price
        if current_price <= 0 or current_price == self.user_last_bid:
            return False
        return price == current_price + self.config.step_price
        
    @Slot()
    def handle_session_end(self):
        # Stop components
        self.action_stop()
        
        # Define directories
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
        screenshot_dir = os.path.join(app_dir, "screenshots")
        logs_dir = os.path.join(app_dir, "logs")
        os.makedirs(screenshot_dir, exist_ok=True)
        os.makedirs(logs_dir, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Paths
        img_filename = f"phien_ket_thuc_{timestamp}.png"
        img_filepath = os.path.join(screenshot_dir, img_filename)
        
        log_filename = f"lich_su_dau_gia_{timestamp}.txt"
        log_filepath = os.path.join(logs_dir, log_filename)
        
        # 1. Take screenshot of the entire desktop
        try:
            time.sleep(0.5)
            screenshot = pyautogui.screenshot()
            screenshot.save(img_filepath)
            self.log(f"Đã tự động chụp màn hình kết quả tại: screenshots/{img_filename}")
        except Exception as e:
            self.log(f"Lỗi chụp ảnh màn hình: {str(e)}")
            img_filepath = None
            
        # 2. Write human-readable text log file for non-technical users
        try:
            # Gather timeline logs from database
            from src.database import get_timeline
            rows = get_timeline()
            
            with open(log_filepath, "w", encoding="utf-8") as f:
                f.write("============================================================\n")
                f.write("              LỊCH SỬ CHI TIẾT PHIÊN ĐẤU GIÁ\n")
                f.write("============================================================\n")
                f.write(f"Thời gian kết thúc: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
                f.write(f"Cấu hình: Giá khởi điểm={self.config.start_price} | Bước giá={self.config.step_price} | Giá tối đa={self.config.max_price}\n")
                if img_filepath:
                    f.write(f"Đường dẫn ảnh chụp kết quả: {img_filepath}\n")
                f.write("------------------------------------------------------------\n\n")
                
                f.write(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Khởi động giám sát đấu giá...\n")
                
                for row in rows:
                    ts, ocr, price, bot_act, status = row
                    time_only = ts.split(" ")[1] if " " in ts else ts
                    
                    if bot_act and bot_act != "None":
                        f.write(f"[{time_only}] [BẠN (BOT)] tự động gửi giá: {price} [{status}]\n")
                    else:
                        # Friendly text formatting depending on validity
                        if status == "Valid Bid Detected":
                            f.write(f"[{time_only}] [ĐỐI THỦ] trả giá hợp lệ: {price}\n")
                        else:
                            f.write(f"[{time_only}] [ĐỐI THỦ] trả giá lỗi: {ocr} -> (Hệ thống bỏ qua vì không đúng thứ tự hoặc sai bước giá)\n")
                
                f.write(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] HẾT GIỜ ĐẤU GIÁ - Phiên đấu giá kết thúc.\n\n")
                f.write("============================================================\n")
                f.write("              NHẬT KÝ TIN NHẮN CHAT CHI TIẾT (OCR)\n")
                f.write("============================================================\n")
                if not hasattr(self, "session_chat_history") or not self.session_chat_history:
                    f.write("Không có nhật ký tin nhắn.\n")
                else:
                    for msg in self.session_chat_history:
                        f.write(f"[{msg.timestamp}] {msg.raw_text} [{msg.status}]\n")
                f.write("============================================================\n")
                f.write("Cảm ơn bạn đã sử dụng phần mềm Zalo Auction Auto Bidder!\n")
                
            self.log(f"Đã lưu lịch sử đấu giá dạng văn bản tại: logs/{log_filename}")
        except Exception as e:
            self.log(f"Lỗi ghi file lịch sử: {str(e)}")
            log_filepath = None
            
        self.log("==============================================")
        self.log("--- PHIÊN ĐẤU GIÁ KẾT THÚC (HẾT GIỜ) ---")
        self.log("==============================================")
        
        # 3. Show a friendly MessageBox with interactive options
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Phiên Đấu Giá Kết Thúc!")
        msg_box.setText("Đồng hồ đếm ngược đã hết giờ đấu giá.\nPhần mềm đã chụp ảnh màn hình và xuất file lịch sử phiên.")
        msg_box.setIcon(QMessageBox.Information)
        
        btn_open_img = msg_box.addButton("Xem Ảnh Chụp", QMessageBox.ActionRole)
        btn_open_log = msg_box.addButton("Xem Lịch Sử", QMessageBox.ActionRole)
        btn_close = msg_box.addButton("Đóng", QMessageBox.AcceptRole)
        
        # Suppressor is stopped, so mouse/keyboard are free for clicking the popup
        msg_box.exec()
        
        # Actions based on button click
        clicked_btn = msg_box.clickedButton()
        if clicked_btn == btn_open_img and img_filepath:
            os.startfile(img_filepath)
        elif clicked_btn == btn_open_log and log_filepath:
            os.startfile(log_filepath)
            
    def trigger_scheduled_bid(self, target_time):
        # 1. Immediately disarm/stop to prevent double triggers
        self.action_stop()
        
        # 2. Get target price
        price = self.config.max_price
        
        # 3. Log
        target_time_str = target_time.strftime("%H:%M:%S.%f")[:-3]
        self.log(f"[Hệ thống] Hẹn giờ kích hoạt lúc {target_time_str}. Thả giá: {price}")
        
        # 4. Trigger simulated bid
        self.trigger_bid_simulated(price, timings=target_time.timestamp())
            
    def trigger_bid_simulated(self, price, timings=None):
        self.log(f"Preparing bid {price}...")
        if price <= 0 or price > self.config.max_price:
            self.bid_finished_signal.emit(price, "Invalid price or above maximum")
            return

        is_fixed_schedule = self.config.bid_mode == "fixed_schedule"
        if self.bid_send_in_progress:
            self.log(f"[Duplicate Guard] A bid is being sent; ignored {price}.")
            return

        if not is_fixed_schedule:
            # Latest request wins. If the desired draft is already being prepared,
            # attach pending Send without retyping the same value.
            if not self._draft_is_ready(price):
                previous = self.pending_bid_request[0] if self.pending_bid_request else None
                self.pending_bid_request = (price, timings)
                if previous is not None and previous != price:
                    self.log(f"[Draft Controller] Pending updated {previous} -> {price}.")
                self._request_draft(price)
                return

            # A newer chat image exists but AuctionEngine has not consumed it yet.
            # Preserve the request and let handle_ocr_texts retry after consumption.
            if not self._chat_barrier_is_clear():
                self.pending_bid_request = (price, timings)
                captured, consumed = (None, None)
                getter = getattr(self.ocr_worker, "get_chat_generations", None)
                if callable(getter):
                    captured, consumed = getter()
                self.log(
                    f"[Chat Barrier] Send {price} deferred; "
                    f"captured={captured}, consumed={consumed}."
                )
                return

            # Validate against the latest consumed engine price immediately before
            # the synchronous Send action.
            if not self._is_bid_price_still_valid(price):
                current_price = self.auction_engine.current_price
                expected_now = current_price + self.config.step_price if current_price > 0 else None
                self.pending_bid_request = None
                self.log(
                    f"[Final Guard] Blocked stale bid {price}; "
                    f"current={current_price}, expected={expected_now}."
                )

                replacement = self._calculate_prepared_price(current_price)
                if replacement is not None:
                    replacement = max(replacement, self.config.start_price)
                    if replacement <= self.config.max_price:
                        if current_price != self.user_last_bid:
                            self.pending_bid_request = (replacement, timings)
                        self._request_draft(
                            replacement,
                            force=self.draft_expected_price != replacement,
                        )
                        return
                self.clear_input_zone()
                return

            # Re-check the barrier at the last possible point before clicking.
            if not self._chat_barrier_is_clear():
                self.pending_bid_request = (price, timings)
                return

        self.bid_send_in_progress = True
        self.pending_bid_request = None
        try:
            t_send_start = time.time()
            if is_fixed_schedule:
                ix, iy, iw, ih = self.config.input_zone
                if ix > 0 and iy > 0:
                    dpr = self.ocr_worker.device_pixel_ratio
                    win32_click(int(round((ix + iw // 2) * dpr)), int(round((iy + ih // 2) * dpr)))
                    time.sleep(0.005)
                press_win32_hotkey(VK_CONTROL, VK_A)
                press_win32_key(VK_BACK, False)
                press_win32_key(VK_BACK, True)
                pyautogui.write(str(price), interval=0.0)

            # OCR modes arrive here only when READY and the chat barrier is clear.
            sbx, sby = self.config.send_btn
            if sbx > 0 and sby > 0:
                dpr = self.ocr_worker.device_pixel_ratio
                win32_click(int(round(sbx * dpr)), int(round(sby * dpr)))
            else:
                pyautogui.press("enter")
            t_send_end = time.time()

            self.pre_typed_price = None
            self.draft_expected_price = None
            self.draft_candidate_text = None
            self.draft_candidate_since = 0.0
            self.draft_stable_frames = 0
            self.wait_confirm_generation += 1
            wait_generation = self.wait_confirm_generation
            if is_fixed_schedule:
                self._set_draft_state("EMPTY")
            else:
                self._set_draft_state("WAIT_CLEAR")
                QTimer.singleShot(1200, lambda g=wait_generation: self._check_wait_confirm_timeout(g))

            send_ms = int((t_send_end - t_send_start) * 1000)
            status_str = f"Sent (Send action: {send_ms}ms)"
            if isinstance(timings, dict) and "capture_start" in timings:
                total_ms = int((t_send_end - timings["capture_start"]) * 1000)
                status_str = f"Sent ({total_ms}ms | Capture:{timings.get('capture_duration_ms', 0)}ms | Queue:{timings.get('queue_duration_ms', 0)}ms | OCR:{timings.get('ocr_duration_ms', 0)}ms | Send:{send_ms}ms)"
                self.update_reaction_time_signal.emit(f"Latency: {total_ms} ms")
                self.log(f"Total bid reaction latency: {total_ms} ms")
            elif isinstance(timings, (int, float)):
                offset = self.config.manual_time_offset + self.config.network_time_offset
                latency_ms = max(0, int((t_send_end + offset - timings) * 1000))
                status_str = f"Sent ({latency_ms}ms | Send:{send_ms}ms)"
                self.update_reaction_time_signal.emit(f"Latency: {latency_ms} ms")

            from src.database import add_log
            add_log(ocr_text="None", valid_price=price, bot_action=f"Sent {price}", status=status_str,
                    offset=self.config.manual_time_offset, net_offset=self.config.network_time_offset)
            self.bid_finished_signal.emit(price, "Success")
        except Exception as e:
            self.bid_send_in_progress = False
            self.pending_bid_request = None
            self.pre_typed_price = None
            self._set_draft_state("ERROR")
            self.bid_finished_signal.emit(price, f"Send error: {str(e)}")

    def pre_type_bid(self, price, force=False):
        """Compatibility wrapper; Draft Controller is the sole editor owner."""
        self._request_draft(price, force=force)

    @Slot(int, str)
    def on_bid_finished(self, price, status):
        self.bid_send_in_progress = False
        if status == "Success":
            self.user_last_bid = price
            self.lbl_user_bid.setText(str(price))
            self.lbl_user_bid.setStyleSheet("font-size: 18px; color: #00ff66; font-weight: bold;")
            self.log(f"Send command completed for price: {price}")
            self.auction_engine.update_price_on_bid_success(price)
            if self.config.bid_mode == "fixed_schedule":
                self._set_draft_state("EMPTY")
        else:
            self._set_draft_state("ERROR")
            self.log(f"Bid {price} failed: {status}")

    def clear_input_zone(self):
        """Clear the bot-owned editor through the single controller path."""
        try:
            owned = (
                self.draft_state != "EMPTY"
                or self.draft_expected_price is not None
                or bool(self.draft_observed_text)
            )
            if owned:
                self._write_input_text("")
            for key in ("ctrl", "shift", "alt", "win"):
                pyautogui.keyUp(key)
            self._reset_draft_controller()
            self.log("[Draft Controller] Bot draft cleared and state reset.")
        except Exception as e:
            self._set_draft_state("ERROR")
            self.log(f"Input cleanup error: {str(e)}")

    # Selection helpers
    def select_chat_zone(self):
        self.hide() # hide main window temporarily
        self.overlay = SelectionOverlay(mode="chat")
        self.overlay.selection_completed.connect(self.on_selection_completed)
        self.overlay.selection_cancelled.connect(self.on_selection_cancelled)
        self.overlay.show()
        
    def select_input_zone(self):
        self.hide()
        self.overlay = SelectionOverlay(mode="input")
        self.overlay.selection_completed.connect(self.on_selection_completed)
        self.overlay.selection_cancelled.connect(self.on_selection_cancelled)
        self.overlay.show()

    def select_input_ocr_zone(self):
        self.hide()
        self.overlay = SelectionOverlay(mode="input_ocr")
        self.overlay.selection_completed.connect(self.on_selection_completed)
        self.overlay.selection_cancelled.connect(self.on_selection_cancelled)
        self.overlay.show()

    def select_send_btn(self):
        self.hide()
        self.overlay = SelectionOverlay(mode="send_btn")
        self.overlay.selection_completed.connect(self.on_selection_completed)
        self.overlay.selection_cancelled.connect(self.on_selection_cancelled)
        self.overlay.show()
        
    @Slot(str, tuple)
    def on_selection_completed(self, mode, coords):
        self.show() # restore main window
        if mode == "chat":
            x, y, w, h = coords
            self.config.chat_zone = coords
            self.log(f"Đã cập nhật Chat Zone: X={x}, Y={y}, W={w}, H={h}")
            self.evaluate_chat_zone_quality(x, y, w, h)
        elif mode == "input_ocr":
            x, y, w, h = coords
            self.config.input_ocr_zone = coords
            self.log(f"Updated Input OCR Zone: X={x}, Y={y}, W={w}, H={h}")
        elif mode == "send_btn":
            x, y, w, h = coords
            self.config.send_btn = (x, y)
            self.log(f"Đã cập nhật Nút Gửi: X={x}, Y={y}")
        else:
            x, y, w, h = coords
            self.config.input_zone = coords
            self.log(f"Đã cập nhật Input Zone: X={x}, Y={y}, W={w}, H={h}")
        self.update_selection_ticks()
            
    def evaluate_chat_zone_quality(self, x, y, w, h):
        self.lbl_ocr_score.setText("Đang đánh giá...")
        self.lbl_ocr_score.setStyleSheet("color: #ffb703; font-weight: bold;")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents() # Cập nhật giao diện lập tức
        
        try:
            import mss
            import numpy as np
            import cv2
            
            dpr = self.ocr_worker.device_pixel_ratio
            px = int(round(x * dpr))
            py = int(round(y * dpr))
            pw = int(round(w * dpr))
            ph = int(round(h * dpr))
            
            # 1. Chụp màn hình vùng vừa chọn
            with mss.mss() as sct:
                monitor = {"left": px, "top": py, "width": pw, "height": ph}
                sct_img = sct.grab(monitor)
                arr = np.array(sct_img)
                
            if arr.size == 0:
                self.lbl_ocr_score.setText("Lỗi (0/10) - Không thể chụp ảnh")
                self.lbl_ocr_score.setStyleSheet("color: #ff3333; font-weight: bold;")
                return
                
            img_gray = cv2.cvtColor(arr, cv2.COLOR_BGRA2GRAY)
            
            # Đảm bảo Tesseract DLL đã sẵn sàng
            if not self.ocr_worker.tesseract_available:
                self.ocr_worker.init_ocr()
                
            if not self.ocr_worker.tesseract_available:
                self.lbl_ocr_score.setText("Lỗi (0/10) - Thư viện GE lỗi")
                self.lbl_ocr_score.setStyleSheet("color: #ff3333; font-weight: bold;")
                return
                
            # Reset toàn bộ các biến phiên cũ và giao diện danh sách bảng giá bên phải để sẵn sàng nạp mới
            self.user_last_bid = 0
            self.lbl_user_bid.setText("Chưa bid")
            self.lbl_user_bid.setStyleSheet("font-size: 14px; color: #00d2ff; font-weight: bold;")
            self.last_frame_lines = []
            self.logged_chat_lines.clear()
            self.session_chat_history.clear()
            self.price_list_widget.clear()
            self.auction_engine.reset()
            
            # 2. Chạy thử OCR xem có đọc tốt không
            texts, raw_lines = self.ocr_worker._tesseract_read_full(img_gray)
            
            # Nếu nhận diện được số giá đấu, nạp thử vào Engine để sinh và hiển thị bảng giá ngay lập tức
            if texts:
                self.auction_engine.is_active = True
                self.auction_engine.process_ocr_texts(texts, timings=None)
                self.auction_engine.is_active = False # Tạm dừng chờ bấm nút START thực tế
            
            # In kết quả đọc thử trực tiếp lên khung log của UI
            self.log("==============================================")
            self.log("[Xác minh OCR] KẾT QUẢ ĐỌC THỬ VÙNG CHAT VỪA CHỌN:")
            if raw_lines:
                for idx, line in enumerate(raw_lines):
                    self.log(f"  - Dòng {idx+1}: \"{line.strip()}\"")
            else:
                self.log("  (Không có văn bản nào được đọc ra)")
            if texts:
                prices_str = []
                for p in texts:
                    votes_str = getattr(self.ocr_worker, "last_ocr_votes", {}).get(p, "N/A")
                    prices_str.append(f"{p} (đồng thuận {votes_str})")
                self.log(f"  -> Nhận diện được các số giá đấu: {', '.join(prices_str)}")
            else:
                self.log("  -> Không nhận diện được số giá đấu nào hợp lệ!")
            self.log("==============================================")
            
            score = 10
            reasons = []
            
            # Đánh giá dựa trên việc phát hiện số (giá tiền)
            if not texts:
                score -= 6
                reasons.append("Không nhận dạng được giá số")
            else:
                reasons.append(f"Đọc được {len(texts)} giá số ({', '.join(texts[:3])})")
                
            # Đánh giá số dòng đọc được
            valid_lines = [l for l in raw_lines if len(l.strip()) > 1]
            if len(valid_lines) < 3:
                score -= 2
                reasons.append(f"Số dòng tin ít ({len(valid_lines)} dòng)")
            elif len(valid_lines) > 6:
                score -= 1
                reasons.append("Vùng quét chứa quá nhiều dòng tin")
            else:
                reasons.append(f"Nhìn thấy {len(valid_lines)} dòng chat")
                
            # Giới hạn điểm từ 0-10
            score = max(0, min(10, score))
            
            # Hiển thị điểm số kèm màu sắc
            if score >= 8:
                self.lbl_ocr_score.setText(f"Tốt ({score}/10) - {'; '.join(reasons)}")
                self.lbl_ocr_score.setStyleSheet("color: #00ff66; font-weight: bold;")
            elif score >= 4:
                self.lbl_ocr_score.setText(f"Cảnh báo ({score}/10) - {'; '.join(reasons)}")
                self.lbl_ocr_score.setStyleSheet("color: #ffb703; font-weight: bold;")
            else:
                self.lbl_ocr_score.setText(f"Lỗi ({score}/10) - {'; '.join(reasons)}")
                self.lbl_ocr_score.setStyleSheet("color: #ff3333; font-weight: bold;")
                
        except Exception as e:
            self.lbl_ocr_score.setText(f"Lỗi chẩn đoán: {str(e)}")
            self.lbl_ocr_score.setStyleSheet("color: #ff3333; font-weight: bold;")
            
    @Slot()
    def on_selection_cancelled(self):
        self.show() # restore main window
        self.log("[Hủy chọn] Vùng quét quá nhỏ hoặc bạn đã nhấn ESC. Vui lòng bấm chọn lại.")
        QMessageBox.warning(self, "Hủy chọn", "Vùng quét quá nhỏ hoặc thao tác bị hủy. Vui lòng thực hiện chọn lại.")
            
    def clear_logs_action(self):
        clear_logs()
        self.txt_logs.clear()
        self.logged_chat_lines.clear()
        self.last_frame_lines = []
        self.session_chat_history.clear()
        self.log("Đã xóa toàn bộ lịch sử đấu giá.")

    def show_log_popup(self):
        # Close existing references to prevent multiple instances
        if hasattr(self, "chat_dialog") and self.chat_dialog:
            try:
                self.chat_dialog.close()
            except Exception:
                pass
        if hasattr(self, "process_dialog") and self.process_dialog:
            try:
                self.process_dialog.close()
            except Exception:
                pass
                
        # Get screen geometry to place side-by-side
        screen = self.screen().geometry()
        center_x = screen.x() + screen.width() // 2
        center_y = screen.y() + screen.height() // 2
        
        dlg_w = 480
        dlg_h = 600
        
        dialog_style = """
            QDialog {
                background-color: #1e1e24;
            }
            QLabel {
                font-family: 'Segoe UI', Inter, sans-serif;
                font-size: 13px;
                font-weight: bold;
            }
            QTextEdit {
                background-color: #121212;
                border: 1px solid #2b2b36;
                border-radius: 4px;
                padding: 6px;
            }
        """
        
        # 1. Left Window: Lịch sử Chat (OCR)
        self.chat_dialog = QDialog(self)
        self.chat_dialog.setWindowTitle("Lịch sử Chat (OCR) - Zalo OCR Bid")
        self.chat_dialog.setMinimumSize(dlg_w, dlg_h)
        self.chat_dialog.resize(dlg_w, dlg_h)
        self.chat_dialog.setStyleSheet(dialog_style)
        self.chat_dialog.move(center_x - dlg_w - 10, center_y - dlg_h // 2)
        
        chat_layout = QVBoxLayout()
        lbl_left = QLabel("NHẬT KÝ KHUNG CHAT ZALO (OCR ĐỌC ĐƯỢC)")
        lbl_left.setStyleSheet("color: #00d2ff;")
        chat_layout.addWidget(lbl_left)
        
        txt_chat = QTextEdit()
        txt_chat.setReadOnly(True)
        txt_chat.setStyleSheet("color: #00ff66; font-family: 'Consolas', monospace; font-size: 12px;")
        
        chat_text = ""
        if hasattr(self, "session_chat_history") and self.session_chat_history:
            for msg in self.session_chat_history:
                chat_text += f"[{msg.timestamp}] {msg.raw_text} [{msg.status}]\n"
        else:
            chat_text = "Chưa có nhật ký tin nhắn chat Zalo nào."
        txt_chat.setPlainText(chat_text)
        chat_layout.addWidget(txt_chat)
        self.chat_dialog.setLayout(chat_layout)
        
        # 2. Right Window: Lịch sử Tiến Trình (Process)
        self.process_dialog = QDialog(self)
        self.process_dialog.setWindowTitle("Lịch sử Tiến Trình (Process) - Zalo OCR Bid")
        self.process_dialog.setMinimumSize(dlg_w, dlg_h)
        self.process_dialog.resize(dlg_w, dlg_h)
        self.process_dialog.setStyleSheet(dialog_style)
        self.process_dialog.move(center_x + 10, center_y - dlg_h // 2)
        
        process_layout = QVBoxLayout()
        lbl_right = QLabel("TIẾN TRÌNH XỬ LÝ ĐẤU GIÁ (BOT PROCESS)")
        lbl_right.setStyleSheet("color: #ffb703;")
        process_layout.addWidget(lbl_right)
        
        txt_process = QTextEdit()
        txt_process.setReadOnly(True)
        txt_process.setStyleSheet("color: #ffb703; font-family: 'Consolas', monospace; font-size: 12px;")
        
        from src.database import get_timeline
        rows = get_timeline()
        process_text = ""
        if rows:
            for row in rows:
                ts, ocr, price, bot_act, status = row
                time_only = ts.split(" ")[1] if " " in ts else ts
                if bot_act and bot_act != "None":
                    process_text += f"[{time_only}] [BẠN (BOT)] Tự động gửi giá: {price} -> {status}\n"
                else:
                    if status == "Valid Bid Detected":
                        process_text += f"[{time_only}] [ĐỐI THỦ] Trả giá hợp lệ: {price}\n"
                    else:
                        process_text += f"[{time_only}] [ĐỐI THỦ] Bỏ qua: {ocr} (Sai lệch/Cũ)\n"
        else:
            process_text = "Chưa có lịch sử tiến trình xử lý đấu giá nào."
        txt_process.setPlainText(process_text)
        process_layout.addWidget(txt_process)
        self.process_dialog.setLayout(process_layout)
        
        # Show both windows
        self.chat_dialog.show()
        self.process_dialog.show()
        
        # Lưu tham chiếu để cập nhật log thời gian thực
        self.chat_log_textedit = txt_chat
        self.process_log_textedit = txt_process
        
        # Bắt đầu timer tự động cập nhật log
        self.log_refresh_timer.start()

    def refresh_open_logs(self):
        chat_visible = hasattr(self, "chat_dialog") and self.chat_dialog.isVisible()
        process_visible = hasattr(self, "process_dialog") and self.process_dialog.isVisible()
        
        # Nếu cả 2 cửa sổ đều đã đóng, tắt timer đi để tiết kiệm tài nguyên
        if not chat_visible and not process_visible:
            self.log_refresh_timer.stop()
            return
            
        # 1. Cập nhật cửa sổ Lịch sử Chat (OCR)
        if chat_visible and hasattr(self, "chat_log_textedit"):
            chat_text = ""
            if hasattr(self, "session_chat_history") and self.session_chat_history:
                for msg in self.session_chat_history:
                    chat_text += f"[{msg.timestamp}] {msg.raw_text} [{msg.status}]\n"
            else:
                chat_text = "Chưa có nhật ký tin nhắn chat Zalo nào."
                
            # Chỉ cập nhật nếu có sự thay đổi nội dung để tránh nháy màn hình
            if self.chat_log_textedit.toPlainText() + "\n" != chat_text and self.chat_log_textedit.toPlainText() != chat_text:
                scrollbar = self.chat_log_textedit.verticalScrollBar()
                scroll_pos = scrollbar.value()
                max_pos = scrollbar.maximum()
                is_at_bottom = (scroll_pos >= max_pos - 10)  # Threshold for being at bottom
                
                self.chat_log_textedit.setPlainText(chat_text)
                
                # Cập nhật GUI để scrollbar tính toán lại maximum()
                from PySide6.QtWidgets import QApplication
                QApplication.processEvents()
                
                if is_at_bottom:
                    scrollbar.setValue(scrollbar.maximum())
                else:
                    scrollbar.setValue(scroll_pos)
                    
        # 2. Cập nhật cửa sổ Lịch sử Tiến Trình (Process)
        if process_visible and hasattr(self, "process_log_textedit"):
            from src.database import get_timeline
            rows = get_timeline()
            process_text = ""
            if rows:
                for row in rows:
                    ts, ocr, price, bot_act, status = row
                    time_only = ts.split(" ")[1] if " " in ts else ts
                    if bot_act and bot_act != "None":
                        process_text += f"[{time_only}] [BẠN (BOT)] Tự động gửi giá: {price} -> {status}\n"
                    else:
                        if status == "Valid Bid Detected":
                            process_text += f"[{time_only}] [ĐỐI THỦ] Trả giá hợp lệ: {price}\n"
                        else:
                            process_text += f"[{time_only}] [ĐỐI THỦ] Bỏ qua: {ocr} (Sai lệch/Cũ)\n"
            else:
                process_text = "Chưa có lịch sử tiến trình xử lý đấu giá nào."
                
            if self.process_log_textedit.toPlainText() + "\n" != process_text and self.process_log_textedit.toPlainText() != process_text:
                scrollbar = self.process_log_textedit.verticalScrollBar()
                scroll_pos = scrollbar.value()
                max_pos = scrollbar.maximum()
                is_at_bottom = (scroll_pos >= max_pos - 10)
                
                self.process_log_textedit.setPlainText(process_text)
                
                from PySide6.QtWidgets import QApplication
                QApplication.processEvents()
                
                if is_at_bottom:
                    scrollbar.setValue(scrollbar.maximum())
                else:
                    scrollbar.setValue(scroll_pos)

    def replay_timeline(self):
        rows = get_timeline()
        replay_lines = []
        replay_lines.append("=============================================")
        replay_lines.append("           REPLAY TIMELINE TIẾN TRÌNH ĐẤU GIÁ")
        replay_lines.append("=============================================")
        if not rows:
            replay_lines.append("Không có lịch sử nào.")
        for row in rows:
            ts, ocr, price, bot_act, status = row
            time_only = ts.split(" ")[1] if " " in ts else ts
            if bot_act and bot_act != "None":
                replay_lines.append(f"[{time_only}]  [BẠN (BOT)] -> Gửi giá: {price} ({status})")
            else:
                replay_lines.append(f"[{time_only}]  [ĐỐI THỦ]   -> Giá: {price} (GE: {ocr})")
        replay_lines.append("=============================================\n")
        
        # 2. Print Full Chat Log (raw OCR lines captured)
        replay_lines.append("=== LỊCH SỬ TIN NHẮN CHAT (OCR ĐỌC ĐƯỢC) ===")
        if not hasattr(self, "session_chat_history") or not self.session_chat_history:
            replay_lines.append("Không có lịch sử tin nhắn.")
        else:
            for msg in self.session_chat_history:
                replay_lines.append(f"[{msg.timestamp}]  {msg.raw_text} [{msg.status}]")
        replay_lines.append("=============================================\n")
        
        full_text = "\n".join(replay_lines)
        self.txt_logs.append(full_text)
        
        # Pop up dialog for Replay
        dialog = QDialog(self)
        dialog.setWindowTitle("Replay Timeline & Lịch Sử Chat")
        dialog.setMinimumSize(600, 500)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #1e1e24;
            }
            QTextEdit {
                background-color: #121212;
                border: 1px solid #2b2b36;
                border-radius: 4px;
                padding: 6px;
                color: #ffffff;
                font-family: 'Consolas', monospace;
                font-size: 12px;
            }
        """)
        layout = QVBoxLayout()
        txt_replay = QTextEdit()
        txt_replay.setReadOnly(True)
        txt_replay.setPlainText(full_text)
        layout.addWidget(txt_replay)
        dialog.setLayout(layout)
        dialog.exec()
        
    def closeEvent(self, event):
        if hasattr(self, "pynput_listener") and self.pynput_listener:
            try:
                self.pynput_listener.stop()
            except Exception:
                pass
        if self.indicator_overlay:
            self.indicator_overlay.close()
        event.accept()

    def keyPressEvent(self, event):
        # Delegate space to global pynput hook to prevent double triggering when focused
        super().keyPressEvent(event)

    def on_global_key_press(self, key):
        try:
            from pynput import keyboard
            if key == keyboard.Key.space:
                if self._space_key_down:
                    return
                self._space_key_down = True

                now = time.monotonic()
                if now - self._last_space_trigger_at < self._space_debounce_seconds:
                    return
                if self.config.bid_mode == "semi_auto" and self.auction_engine.is_active:
                    self._last_space_trigger_at = now
                    self.global_space_pressed.emit()
        except Exception:
            pass

    def on_global_key_release(self, key):
        try:
            from pynput import keyboard
            if key == keyboard.Key.space:
                self._space_key_down = False
        except Exception:
            pass
