import sys
import time
import ctypes
import ctypes.wintypes
import threading
import pyautogui
pyautogui.PAUSE = 0.001
pyautogui.FAILSAFE = False
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal, Slot, QMetaObject, Qt

from src.config import Config
from src.ocr_worker import OCRWorker
from src.auction_engine import AuctionEngine
from src.ui.main_window import MainWindow

# ── Win32 API setup ────────────────────────────────────────────────────────
_user32   = ctypes.WinDLL('user32',   use_last_error=True)
_kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

WH_KEYBOARD_LL = 13
WH_MOUSE_LL    = 14
WM_KEYDOWN     = 0x0100
WM_SYSKEYDOWN  = 0x0104
PM_REMOVE      = 0x0001

HOOKPROC = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int,
                             ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)

class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ('vkCode',      ctypes.wintypes.DWORD),
        ('scanCode',    ctypes.wintypes.DWORD),
        ('flags',       ctypes.wintypes.DWORD),
        ('time',        ctypes.wintypes.DWORD),
        ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong)),
    ]

VK_S = 0x53  # Virtual key code for 'S'


class InputSuppressor(QObject):
    """
    Zero-lag keyboard+mouse suppressor using Win32 low-level hooks via ctypes.
    Hooks install/uninstall in ~0ms.
    The Win32 message pump runs on a background daemon thread — UI thread is never blocked.
    Pressing physical 'S' fires stop_bot_signal safely back to the Qt main thread.
    """
    stop_bot_signal = Signal()

    def __init__(self):
        super().__init__()
        self.is_active   = False
        self._hook_kb    = None
        self._hook_mouse = None
        self._pump_thread = None
        self._pump_tid    = None          # thread ID of the pump thread (needed for PostThreadMessage)
        self._tid_ready   = threading.Event()

        # Keep strong references to callbacks so they are not GC'd
        self._cb_kb    = HOOKPROC(self._kb_proc)
        self._cb_mouse = HOOKPROC(self._mouse_proc)

    # ── Low-level hook callbacks (run on pump thread) ──────────────────────
    def _kb_proc(self, nCode, wParam, lParam):
        if nCode >= 0 and self.is_active:
            if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                kb = ctypes.cast(lParam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                if kb.vkCode == VK_S:
                    # Signal back to Qt main thread safely
                    QMetaObject.invokeMethod(self, "_emit_stop", Qt.QueuedConnection)
                    return 1  # suppress the 'S' key press
            return 1  # suppress ALL other keys while active
        return _user32.CallNextHookEx(None, nCode, wParam, lParam)

    def _mouse_proc(self, nCode, wParam, lParam):
        if nCode >= 0 and self.is_active:
            return 1  # suppress all mouse events while active
        return _user32.CallNextHookEx(None, nCode, wParam, lParam)

    @Slot()
    def _emit_stop(self):
        self.stop_bot_signal.emit()

    # ── Message pump (runs on background thread) ───────────────────────────
    def _pump(self):
        """Runs GetMessage loop so low-level hooks receive events."""
        self._pump_tid = _kernel32.GetCurrentThreadId()
        self._tid_ready.set()

        msg = ctypes.wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

    # ── Public API ─────────────────────────────────────────────────────────
    def start_suppression(self):
        if self.is_active:
            return
        self.is_active = True

        # Start pump thread once (reuse if already alive)
        if self._pump_thread is None or not self._pump_thread.is_alive():
            self._tid_ready.clear()
            self._pump_thread = threading.Thread(target=self._pump, daemon=True)
            self._pump_thread.start()
            self._tid_ready.wait(timeout=1.0)  # wait until thread ID is ready

        # Install hooks on the pump thread (required by Win32)
        h_inst = _kernel32.GetModuleHandleW(None)
        self._hook_kb    = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._cb_kb,    h_inst, 0)
        self._hook_mouse = _user32.SetWindowsHookExW(WH_MOUSE_LL,    self._cb_mouse, h_inst, 0)

    def stop_suppression(self):
        if not self.is_active:
            return
        self.is_active = False

        if self._hook_kb:
            _user32.UnhookWindowsHookEx(self._hook_kb)
            self._hook_kb = None
        if self._hook_mouse:
            _user32.UnhookWindowsHookEx(self._hook_mouse)
            self._hook_mouse = None

        # Stop the message pump thread
        if self._pump_tid:
            _user32.PostThreadMessageW(self._pump_tid, 0x0012, 0, 0)  # WM_QUIT
            self._pump_tid = None


# Global input suppressor instance
suppressor = InputSuppressor()

def main():
    # Set DPI awareness for exact multi-monitor / varying laptop screen coordinate mapping
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE = 2
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    app = QApplication(sys.argv)
    
    config = Config()
    ocr_worker = OCRWorker(config)
    auction_engine = AuctionEngine(config)
    
    window = MainWindow(config, ocr_worker, auction_engine)
    window.show()
    
    # Connect window start/stop events to suppression (Disabled to prevent Windows message queue lag/deadlock)
    # We run the application directly using PyQt event loop.
    exit_code = app.exec()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
