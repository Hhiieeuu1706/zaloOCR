import time
import random
import pyautogui
from PySide6.QtCore import QThread, Signal
from src.database import add_log

# Disable PyAutoGUI fail-safe to prevent user mouse moving slightly from throwing an error,
# but let's keep it enabled so the user can abort by moving mouse to corners, which is good practice.
pyautogui.FAILSAFE = True

class BidSenderThread(QThread):
    finished_bid = Signal(int, str) # price sent, status
    about_to_type = Signal() # signal emitted just before starting PyAutoGUI
    
    def __init__(self, target_price, config):
        super().__init__()
        self.target_price = target_price
        self.config = config
        
    def run(self):
        # 1. Random delay to simulate human behavior
        delay_min = self.config.random_delay_min
        delay_max = self.config.random_delay_max
        actual_delay = random.uniform(delay_min, delay_max)
        
        time.sleep(actual_delay)
        
        # 2. Safety check: Target price must be <= max price
        if self.target_price > self.config.max_price:
            self.finished_bid.emit(self.target_price, "Vượt quá giá tối đa!")
            return
            
        # Emit signal to stop suppression for typing
        self.about_to_type.emit()
        time.sleep(0.001) # let OS register the state change (reduced to 1ms)
        
        # 3. Perform clicks and keystrokes
        try:
            # Release any modifier keys that might be stuck due to pynput suppression
            for k in ['ctrl', 'shift', 'alt', 'win', 's', 'S']:
                try:
                    pyautogui.keyUp(k)
                except Exception:
                    pass
            time.sleep(0.001) # (reduced to 1ms)
            
            # Fetch coordinates for Input Zone
            input_x, input_y = self.config.input_zone
            
            # Click the input box
            pyautogui.click(input_x, input_y)
            time.sleep(0.001) # tiny delay after click (reduced to 1ms)
            
            # Type the target price instantly
            pyautogui.write(str(self.target_price), interval=0.0)
            time.sleep(0.001) # (reduced to 1ms)
            
            # Press Enter
            pyautogui.press('enter')
            
            # Log successful bid action
            add_log(
                ocr_text="None",
                valid_price=self.target_price,
                bot_action=f"Sent {self.target_price}",
                status="Sent"
            )
            
            self.finished_bid.emit(self.target_price, "Thành công")
            
        except Exception as e:
            self.finished_bid.emit(self.target_price, f"Lỗi gửi giá: {str(e)}")
