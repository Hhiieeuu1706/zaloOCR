from src.database import get_setting, save_setting, init_db

class Config:
    def __init__(self):
        init_db()
        self._cache = {}
        self.reload()
        
    def reload(self):
        """Load all settings from database into memory cache."""
        try:
            self._cache["start_price"] = int(get_setting("start_price", 2000))
            self._cache["max_price"] = int(get_setting("max_price", 5000))
            self._cache["step_price"] = int(get_setting("step_price", 100))
            self._cache["end_time"] = get_setting("end_time", "21:30:00")
            self._cache["random_delay_min"] = float(get_setting("random_delay_min", 0.0))
            self._cache["random_delay_max"] = float(get_setting("random_delay_max", 0.0))
            self._cache["auto_bid_last_seconds"] = int(get_setting("auto_bid_last_seconds", 60))
            self._cache["username"] = get_setting("username", "BOT")
            self._cache["use_opencv_ocr"] = get_setting("use_opencv_ocr", "0") == "1"
            self._cache["license_key"] = get_setting("license_key", "")
            
            # Chat Zone
            x = int(get_setting("chat_zone_x", 0))
            y = int(get_setting("chat_zone_y", 0))
            w = int(get_setting("chat_zone_w", 300))
            h = int(get_setting("chat_zone_h", 400))
            self._cache["chat_zone"] = (x, y, w, h)
            
            # Input Zone
            ix = int(get_setting("input_zone_x", 0))
            iy = int(get_setting("input_zone_y", 0))
            iw = int(get_setting("input_zone_w", 300))
            ih = int(get_setting("input_zone_h", 50))
            self._cache["input_zone"] = (ix, iy, iw, ih)
            
            # Send Button
            sbx = int(get_setting("send_btn_x", 0))
            sby = int(get_setting("send_btn_y", 0))
            self._cache["send_btn"] = (sbx, sby)
            
            # Manual Time Offset
            self._cache["manual_time_offset"] = int(get_setting("manual_time_offset", 0))
            
            # Network Time Offset
            self._cache["network_time_offset"] = float(get_setting("network_time_offset", 0.0))
            
            # Bidding Mode
            self._cache["bid_mode"] = get_setting("bid_mode", "last_seconds")
        except Exception as e:
            print(f"[Config Cache Load Error] {e}")
            
    @property
    def start_price(self) -> int:
        return self._cache.get("start_price", 2000)
        
    @start_price.setter
    def start_price(self, val: int):
        self._cache["start_price"] = int(val)
        save_setting("start_price", val)
        
    @property
    def max_price(self) -> int:
        return self._cache.get("max_price", 5000)
        
    @max_price.setter
    def max_price(self, val: int):
        self._cache["max_price"] = int(val)
        save_setting("max_price", val)
        
    @property
    def step_price(self) -> int:
        return self._cache.get("step_price", 100)
        
    @step_price.setter
    def step_price(self, val: int):
        self._cache["step_price"] = int(val)
        save_setting("step_price", val)
        
    @property
    def end_time(self) -> str:
        return self._cache.get("end_time", "21:30:00")
        
    @end_time.setter
    def end_time(self, val: str):
        self._cache["end_time"] = val
        save_setting("end_time", val)
        
    @property
    def random_delay_min(self) -> float:
        return self._cache.get("random_delay_min", 0.0)
        
    @random_delay_min.setter
    def random_delay_min(self, val: float):
        self._cache["random_delay_min"] = float(val)
        save_setting("random_delay_min", val)
        
    @property
    def random_delay_max(self) -> float:
        return self._cache.get("random_delay_max", 0.0)
        
    @random_delay_max.setter
    def random_delay_max(self, val: float):
        self._cache["random_delay_max"] = float(val)
        save_setting("random_delay_max", val)
        
    @property
    def auto_bid_last_seconds(self) -> int:
        return self._cache.get("auto_bid_last_seconds", 60)
        
    @auto_bid_last_seconds.setter
    def auto_bid_last_seconds(self, val: int):
        self._cache["auto_bid_last_seconds"] = int(val)
        save_setting("auto_bid_last_seconds", val)
        
    @property
    def username(self) -> str:
        return self._cache.get("username", "BOT")
        
    @username.setter
    def username(self, val: str):
        self._cache["username"] = val
        save_setting("username", val)
        
    # Chat Zone coordinates
    @property
    def chat_zone(self) -> tuple:
        return self._cache.get("chat_zone", (0, 0, 300, 400))
        
    @chat_zone.setter
    def chat_zone(self, val: tuple):
        self._cache["chat_zone"] = val
        x, y, w, h = val
        save_setting("chat_zone_x", x)
        save_setting("chat_zone_y", y)
        save_setting("chat_zone_w", w)
        save_setting("chat_zone_h", h)
        
    # Input Zone coordinates
    @property
    def input_zone(self) -> tuple:
        return self._cache.get("input_zone", (0, 0, 300, 50))
        
    @input_zone.setter
    def input_zone(self, val: tuple):
        self._cache["input_zone"] = val
        x, y, w, h = val
        save_setting("input_zone_x", x)
        save_setting("input_zone_y", y)
        save_setting("input_zone_w", w)
        save_setting("input_zone_h", h)
        
    # Send Button coordinates
    @property
    def send_btn(self) -> tuple:
        return self._cache.get("send_btn", (0, 0))
        
    @send_btn.setter
    def send_btn(self, val: tuple):
        self._cache["send_btn"] = val
        x, y = val
        save_setting("send_btn_x", x)
        save_setting("send_btn_y", y)
        
    @property
    def use_opencv_ocr(self) -> bool:
        return self._cache.get("use_opencv_ocr", False)
        
    @use_opencv_ocr.setter
    def use_opencv_ocr(self, val: bool):
        self._cache["use_opencv_ocr"] = val
        save_setting("use_opencv_ocr", "1" if val else "0")
  
    @property
    def license_key(self) -> str:
        return self._cache.get("license_key", "")
        
    @license_key.setter
    def license_key(self, val: str):
        self._cache["license_key"] = val
        save_setting("license_key", val)
        
    @property
    def manual_time_offset(self) -> int:
        return self._cache.get("manual_time_offset", 0)
        
    @manual_time_offset.setter
    def manual_time_offset(self, val: int):
        self._cache["manual_time_offset"] = int(val)
        save_setting("manual_time_offset", int(val))
        
    @property
    def network_time_offset(self) -> float:
        return self._cache.get("network_time_offset", 0.0)
        
    @network_time_offset.setter
    def network_time_offset(self, val: float):
        self._cache["network_time_offset"] = float(val)
        save_setting("network_time_offset", float(val))
    @property
    def bid_mode(self) -> str:
        return self._cache.get("bid_mode", "last_seconds")
        
    @bid_mode.setter
    def bid_mode(self, val: str):
        self._cache["bid_mode"] = val
        save_setting("bid_mode", val)
  
    def reset_to_defaults(self):
        """Reset settings to default values (except license key)"""
        self.start_price = 2000
        self.max_price = 5000
        self.step_price = 100
        self.end_time = "21:30:00"
        self.random_delay_min = 0.0
        self.random_delay_max = 0.0
        self.auto_bid_last_seconds = 60
        self.username = "BOT"
        self.chat_zone = (0, 0, 300, 400)
        self.input_zone = (0, 0, 300, 50)
        self.send_btn = (0, 0)
        self.use_opencv_ocr = False
        self.bid_mode = "last_seconds"
