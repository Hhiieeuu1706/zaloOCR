import re
import datetime
import time
from PySide6.QtCore import QObject, Signal
from src.database import add_log

class AuctionEngine(QObject):
    # Signals
    price_updated = Signal(int, int) # current_valid_price, next_valid_price
    countdown_updated = Signal(str, int) # countdown_str, seconds_remaining
    status_changed = Signal(str, bool) # status, is_online
    bid_suggested = Signal(int) # suggest_price
    auto_bid_triggered = Signal(int, object) # auto bid target price, timings dict or detect_time
    session_ended = Signal() # signal fired when session ends
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.current_price = 0
        self.is_active = False
        self.seen_prices = set()
        
    def reset(self):
        # Initialize current price to 0 and let calibration set it to the screen's actual price
        self.current_price = 0
        self.is_active = False
        self.price_timeline = []
        self.current_index = 0
        self.seen_prices = set()
        self.price_updated.emit(0, 0)
        
    def start(self):
        self.is_active = True
        self.status_changed.emit("Engine Online", True)
        
    def stop(self):
        self.is_active = False
        self.status_changed.emit("Engine Stopped", False)
        
    def get_display_current_price(self):
        return self.current_price

    def get_next_valid_price(self):
        if self.current_price <= 0:
            return self.config.start_price
        return self.current_price + self.config.step_price

    def process_ocr_texts(self, texts, timings=None):
        if not self.is_active:
            return
            
        start_time = None
        if isinstance(timings, dict):
            start_time = timings.get("capture_start")
        elif isinstance(timings, (int, float)):
            start_time = timings
            timings = {"capture_start": start_time}
            
        t_engine_start = time.time()
        updated = False
        t_calib_start = time.time()
        if self.current_price <= 0:
            calibrated_price = None
            # Scan from bottom to top (texts is already newest first / bottom-to-top)
            for text in texts:
                cleaned = text.strip()
                if ":" in cleaned:
                    continue
                if cleaned.isdigit():
                    try:
                        price_val = int(cleaned)
                        # Strictly validate against the start_price and step_price sequence
                        if price_val >= self.config.start_price and price_val <= self.config.max_price:
                            if (price_val - self.config.start_price) % self.config.step_price == 0:
                                calibrated_price = price_val
                                break # Found the most recent valid bid at the bottom, stop scanning!
                    except ValueError:
                        continue
            
            # Fallback if no price matched the strict step sequence
            if calibrated_price is None:
                prices_seen = []
                for text in texts:
                    cleaned = text.strip()
                    if ":" in cleaned:
                        continue
                    if cleaned.isdigit():
                        try:
                            price_val = int(cleaned)
                            if price_val >= self.config.start_price and price_val <= self.config.max_price:
                                prices_seen.append(price_val)
                        except ValueError:
                            continue
                if prices_seen:
                    calibrated_price = max(prices_seen)
            
            if calibrated_price is not None:
                self.current_price = calibrated_price
                self.seen_prices = {self.current_price}
                updated = True
                
                # Generate timeline based on this baseline price up to max_price
                self.price_timeline = []
                p = self.current_price
                while p <= self.config.max_price:
                    self.price_timeline.append(p)
                    p += self.config.step_price
                self.current_index = 0
                
                add_log(
                    ocr_text="Baseline Calibration",
                    valid_price=self.current_price,
                    bot_action="None",
                    status=f"Calibrated to screen price: {self.current_price}",
                    offset=self.config.manual_time_offset,
                    net_offset=self.config.network_time_offset
                )
        t_calib_end = time.time()
                
        # If already calibrated, perform sequential checking for new bids
        t_detect_start = time.time()
        db_log_time = 0.0
        if not updated:
            # texts is reversed (bottom-to-top). Let's reverse it back to chronological (top-to-bottom) order
            chrono_texts = list(reversed(texts))
            
            # Process at most ONE expected next price per frame to prevent concurrent double bidding
            if hasattr(self, "price_timeline") and self.price_timeline and self.current_index + 1 < len(self.price_timeline):
                expected_next = self.price_timeline[self.current_index + 1]
                for text in chrono_texts:
                    cleaned = text.strip()
                    if cleaned.isdigit():
                        try:
                            price_val = int(cleaned)
                            if price_val == expected_next:
                                self.seen_prices.add(price_val)
                                self.current_price = price_val
                                self.current_index += 1
                                updated = True
                                
                                t_db_start = time.time()
                                add_log(
                                    ocr_text=text,
                                    valid_price=self.current_price,
                                    bot_action="None",
                                    status="Valid Bid Detected",
                                    offset=self.config.manual_time_offset,
                                    net_offset=self.config.network_time_offset
                                )
                                db_log_time += (time.time() - t_db_start)
                                break  # Stop scanning once the expected next price is matched
                        except ValueError:
                            continue
        t_detect_end = time.time()
                
        if updated:
            next_price = self.get_next_valid_price()
            
            # 1. Trigger Auto Bid immediately first to bypass UI rendering lag
            if next_price <= self.config.max_price:
                if isinstance(timings, dict):
                    t_now = time.time()
                    total_engine = int((t_now - t_engine_start) * 1000)
                    calib_ms = int((t_calib_end - t_calib_start) * 1000)
                    detect_ms = int((t_detect_end - t_detect_start) * 1000)
                    db_ms = int(db_log_time * 1000)
                    
                    timings["engine_duration_ms"] = total_engine
                    timings["engine_details"] = f"calib:{calib_ms}ms, detect:{detect_ms}ms (db_trigger:{db_ms}ms)"
                self.auto_bid_triggered.emit(next_price, timings)
            
            # 2. Update UI signals afterwards
            self.price_updated.emit(self.current_price, next_price)
            self.bid_suggested.emit(next_price)
                
    def update_price_on_bid_success(self, price):
        """Immediately advances current price index when our own bid succeeds."""
        if not self.is_active:
            return
            
        if hasattr(self, "price_timeline") and self.price_timeline:
            if price in self.price_timeline:
                idx = self.price_timeline.index(price)
                if idx > self.current_index:
                    self.current_index = idx
            
        if not hasattr(self, "seen_prices"):
            self.seen_prices = set()
        self.seen_prices.add(price)
        self.current_price = price
        
        next_price = self.get_next_valid_price()
        self.price_updated.emit(self.current_price, next_price)
        self.bid_suggested.emit(next_price)
        
        add_log(
            ocr_text="None (Instant Sync)",
            valid_price=self.current_price,
            bot_action="None",
            status="Valid Bid Detected (Instant Sync)",
            offset=self.config.manual_time_offset,
            net_offset=self.config.network_time_offset
        )
                
    def update_countdown(self):
        """Should be called every second to update countdown display and trigger time-based actions"""
        if not self.is_active:
            return 0
            
        try:
            now = datetime.datetime.now()
            time_str = self.config.end_time
            # Adjust local time calculation using manual offset + network offset
            offset_seconds = getattr(self.config, "manual_time_offset", 0)
            net_offset = getattr(self.config, "network_time_offset", 0.0)
            adjusted_now = now + datetime.timedelta(seconds=offset_seconds + net_offset)
            
            # Parse milliseconds
            ms = 0
            if "." in time_str:
                parts = time_str.split(".")
                time_str = parts[0]
                try:
                    ms_str = parts[1].ljust(3, '0')[:3]
                    ms = int(ms_str)
                except ValueError:
                    pass
            
            # support both HH:MM and HH:MM:SS
            parts = time_str.split(':')
            if len(parts) == 2:
                end_time_obj = adjusted_now.replace(hour=int(parts[0]), minute=int(parts[1]), second=0, microsecond=ms * 1000)
            elif len(parts) == 3:
                end_time_obj = adjusted_now.replace(hour=int(parts[0]), minute=int(parts[1]), second=int(parts[2]), microsecond=ms * 1000)
            else:
                end_time_obj = adjusted_now.replace(hour=23, minute=59, second=59, microsecond=0)
                
            # If end time has already passed today, assume it's for the next day or show 00:00:00
            if end_time_obj < adjusted_now:
                # If within 5 seconds, let's keep it (so it can trigger). Otherwise assume next day.
                if (adjusted_now - end_time_obj).total_seconds() > 5.0:
                    end_time_obj += datetime.timedelta(days=1)
                
            diff = end_time_obj - adjusted_now
            total_seconds = int(diff.total_seconds())
            
            if total_seconds <= 0:
                self.countdown_updated.emit("00:00:00", 0)
                # In fixed_schedule mode, refresh_time will trigger the bid, so we don't call session_ended here to avoid race condition
                if getattr(self.config, "bid_mode", "last_seconds") != "fixed_schedule":
                    if self.is_active:
                        self.is_active = False
                        self.session_ended.emit()
                return 0
                
            # format countdown_str
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            countdown_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            
            self.countdown_updated.emit(countdown_str, total_seconds)
            return total_seconds
        except Exception as e:
            self.countdown_updated.emit("00:00:00", 0)
            return 0
