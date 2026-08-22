import os
import sys
import sqlite3
import datetime

# Robust path resolution for compiled .exe vs source code
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB_PATH = os.path.join(APP_DIR, "zalo_bidder.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if license_key exists in old database before dropping
    license_key = ""
    try:
        cursor.execute("SELECT value FROM settings WHERE key = 'license_key'")
        row = cursor.fetchone()
        if row:
            license_key = row[0]
    except Exception:
        pass
        
    # Drop and recreate settings table to guarantee a completely fresh state on startup
    cursor.execute("DROP TABLE IF EXISTS settings")
    cursor.execute("""
    CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    
    # Drop and recreate logs table
    cursor.execute("DROP TABLE IF EXISTS logs")
    cursor.execute("""
    CREATE TABLE logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        ocr_text TEXT,
        valid_price INTEGER,
        bot_action TEXT,
        status TEXT,
        screenshot_path TEXT
    )
    """)
    
    # Initialize default settings
    defaults = {
        "start_price": "2000",
        "max_price": "5000",
        "step_price": "100",
        "end_time": "21:30:00",
        "random_delay_min": "0.0",
        "random_delay_max": "0.0",
        "auto_bid_last_seconds": "60",
        "username": "BOT",
        "chat_zone_x": "0",
        "chat_zone_y": "0",
        "chat_zone_w": "300",
        "chat_zone_h": "400",
        "input_zone_x": "0",
        "input_zone_y": "0",
        "input_zone_w": "300",
        "input_zone_h": "50",
        "input_ocr_zone_x": "0",
        "input_ocr_zone_y": "0",
        "input_ocr_zone_w": "300",
        "input_ocr_zone_h": "50",
        "send_btn_x": "0",
        "send_btn_y": "0",
        "manual_time_offset": "0",
        "network_time_offset": "0.0",
        "bid_mode": "last_seconds",
        "license_key": license_key
    }
    
    for k, v in defaults.items():
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, v))
        
    conn.commit()
    conn.close()

def get_setting(key, default=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return default

def save_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

import threading

def add_log(ocr_text, valid_price, bot_action, status, screenshot_path="", offset=0, net_offset=0.0):
    def _bg_write():
        try:
            conn = sqlite3.connect(DB_PATH, timeout=10.0)
            cursor = conn.cursor()
            
            adjusted_now = datetime.datetime.now() + datetime.timedelta(seconds=offset + net_offset)
            timestamp = adjusted_now.strftime("%Y-%m-%d %H:%M:%S")
            
            cursor.execute("""
            INSERT INTO logs (timestamp, ocr_text, valid_price, bot_action, status, screenshot_path)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (timestamp, str(ocr_text), valid_price, bot_action, status, screenshot_path))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Database Error] {e}")
            
    threading.Thread(target=_bg_write, daemon=True).start()

def get_logs(limit=100):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, ocr_text, valid_price, bot_action, status FROM logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_timeline():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, ocr_text, valid_price, bot_action, status FROM logs ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def clear_logs():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM logs")
    conn.commit()
    conn.close()
