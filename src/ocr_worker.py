import os
os.environ["OMP_THREAD_LIMIT"] = "1"
import sys
import re
import mss
import numpy as np
import cv2
import time
import queue
import threading
import pyautogui
from PySide6.QtCore import QThread, Signal
from PIL import Image, ImageDraw, ImageFont

# Robust path resolution for compiled .exe vs source code
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODELS_DIR = os.path.join(APP_DIR, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

# Set base directory for PaddleOCR downloads/lookup
os.environ["PADDLEOCR_BASE_DIR"] = MODELS_DIR
os.environ["PPOCR_DIR"] = MODELS_DIR


def _find_tesseract_path():
    """Auto-detect Tesseract binary on Windows"""
    common_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Tesseract-OCR", "tesseract.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Tesseract-OCR", "tesseract.exe"),
    ]
    for p in common_paths:
        if os.path.isfile(p):
            return p
    # Try PATH
    import shutil
    found = shutil.which("tesseract")
    if found:
        return found
    return None


class OCRWorker(QThread):
    text_detected = Signal(list, dict)  # list of strings, timings dict
    input_text_detected = Signal(str, float)  # observed draft, monotonic timestamp
    status_changed = Signal(str, bool) # status message, online/offline status
    screenshot_taken = Signal(object) # pass QImage or numpy image path for display
    debug_log = Signal(str)            # Debug log to UI
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.running = False
        self.is_capturing = False  # Controls whether to execute screen captures and OCR processing
        self.ocr = None
        self.ocr_engine_type = "mock"
        self.interval = 0.005 # 5ms capture interval for maximum responsiveness
        self.prev_img = None
        
        # Tesseract fast DLL OCR
        self.tesseract_available = False
        self.tesseract_api_handle = None
        self.tesseract_lib = None
        # Lock to prevent race condition: calibration (main thread) vs OCR loop (bg thread)
        self._tess_lock = threading.Lock()
        self.last_ocr_votes = {}
        
        # Get screen device pixel ratio on the GUI thread during initialization
        try:
            # Try to get the actual DPI scale from Windows API directly (more reliable than Qt on some setups)
            import ctypes
            user32 = ctypes.windll.user32
            user32.SetProcessDPIAware() # Ensure DPI awareness for this calculation
            hdc = user32.GetDC(0)
            logx = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88) # LOGPIXELSX = 88
            user32.ReleaseDC(0, hdc)
            self.device_pixel_ratio = logx / 96.0
        except Exception:
            try:
                from PySide6.QtGui import QGuiApplication
                self.device_pixel_ratio = QGuiApplication.primaryScreen().devicePixelRatio()
            except Exception:
                self.device_pixel_ratio = 1.0
            
        self.frame_queue = queue.Queue(maxsize=1)
        self.input_ocr_thread = None
        self.input_tesseract_handle = None
        self._input_tess_lock = threading.Lock()
        self.ocr_thread = None
        self.digits_templates = {}
        
    def init_ocr(self):
        # If already initialized, do not re-run (avoid extra DLL load overhead)
        if self.tesseract_available and self.tesseract_api_handle:
            self.status_changed.emit("GE DLL Online", True)
            return

        # Create handle
        try:
            self.status_changed.emit("Dang kiem tra GE DLL...", False)
            tess_path = _find_tesseract_path()
            if tess_path:
                tess_dir = os.path.dirname(tess_path)
                dll_path = os.path.join(tess_dir, "libtesseract-5.dll")
                
                if os.path.isfile(dll_path):
                    # Set DLL search directory
                    if hasattr(os, "add_dll_directory"):
                        try:
                            os.add_dll_directory(tess_dir)
                        except Exception:
                            pass
                    else:
                        os.environ["PATH"] = tess_dir + os.pathsep + os.environ["PATH"]
                    
                    import ctypes
                    self.tesseract_lib = ctypes.CDLL(dll_path)
                    
                    # Define C API signatures
                    self.tesseract_lib.TessBaseAPICreate.restype = ctypes.c_void_p
                    self.tesseract_lib.TessBaseAPICreate.argtypes = []
                    
                    self.tesseract_lib.TessBaseAPIInit3.restype = ctypes.c_int
                    self.tesseract_lib.TessBaseAPIInit3.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
                    
                    self.tesseract_lib.TessBaseAPISetImage.restype = None
                    self.tesseract_lib.TessBaseAPISetImage.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
                    
                    self.tesseract_lib.TessBaseAPIGetUTF8Text.restype = ctypes.POINTER(ctypes.c_char)
                    self.tesseract_lib.TessBaseAPIGetUTF8Text.argtypes = [ctypes.c_void_p]
                    
                    self.tesseract_lib.TessDeleteText.restype = None
                    self.tesseract_lib.TessDeleteText.argtypes = [ctypes.POINTER(ctypes.c_char)]
                    
                    self.tesseract_lib.TessBaseAPIDelete.restype = None
                    self.tesseract_lib.TessBaseAPIDelete.argtypes = [ctypes.c_void_p]
                    
                    self.tesseract_lib.TessBaseAPISetPageSegMode.restype = None
                    self.tesseract_lib.TessBaseAPISetPageSegMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
                    
                    self.tesseract_lib.TessBaseAPISetVariable.restype = ctypes.c_int
                    self.tesseract_lib.TessBaseAPISetVariable.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
                    
                    self.tesseract_api_handles = []
                    tessdata_path = os.path.join(tess_dir, "tessdata").encode('utf-8')
                    
                    for idx in range(5):
                        api = self.tesseract_lib.TessBaseAPICreate()
                        if api:
                            init_status = self.tesseract_lib.TessBaseAPIInit3(api, tessdata_path, b"eng")
                            if init_status == 0:
                                self.tesseract_lib.TessBaseAPISetPageSegMode(api, 3) # Default multiline
                                self.tesseract_lib.TessBaseAPISetVariable(api, b"tessedit_char_whitelist", b"0123456789:,\"\'kK ")
                                self.tesseract_api_handles.append(api)
                            else:
                                self.tesseract_lib.TessBaseAPIDelete(api)
                                print(f"[GE] GE API Init3 failed for worker {idx} with status {init_status}")
                                
                    if self.tesseract_api_handles:
                        self.tesseract_api_handle = self.tesseract_api_handles[0]
                        self.tesseract_available = True
                        if len(self.tesseract_api_handles) >= 5:
                            self.input_tesseract_handle = self.tesseract_api_handles[4]

                        print(f"[GE] GE DLL initialized successfully with {len(self.tesseract_api_handles)} workers from {dll_path}")
                        
                        # Warm up GE with a blank image to cache library initialization
                        try:
                            warm_up_img = np.zeros((40, 40), dtype=np.uint8)
                            self._tesseract_read_full(warm_up_img)
                            print("[GE] GE warmed up successfully")
                        except Exception as wu_err:
                            print(f"[GE] GE warm up error: {wu_err}")
                else:
                    print(f"[GE] GE DLL not found at {dll_path}")
            else:
                print("[GE] GE installation folder not found")
        except Exception as e:
            print(f"[GE] GE DLL initialization error: {e}")
        
        if self.tesseract_available:
            self.ocr_engine_type = "tesseract"
            self.ocr = True
            self.status_changed.emit("GE DLL Online", True)
        else:
            self.ocr_engine_type = "mock"
            self.ocr = False
            self.status_changed.emit("GE Offline (Gia lap)", False)
    
    def _extract_price(self, line):
        # Skip timestamps like 12:30 or 12:30:45
        if re.search(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', line):
            return None
            
        # Clean Tesseract OCR noise: remove common leading/trailing garbled symbols (like |, [, ], etc.)
        cleaned = line.strip()
        cleaned = re.sub(r'^[\s\|\[\(\{\-\+\#]+', '', cleaned)
        cleaned = re.sub(r'[\s\]\)\}\-\+\#]+$', '', cleaned).strip()
        
        # Strictly reject if it contains commas, dots, spaces, or letters (to enforce pure digit rule)
        # So the cleaned string must be pure digits
        if re.match(r"^\d+$", cleaned):
            # If the remaining string is a pure number of length 3 to 6, return it
            if 3 <= len(cleaned) <= 6:
                return cleaned
        return None

    def _ocr_single_worker(self, handle, padded_img):
        """Helper to run standard Tesseract OCR on a single handle and padded image (no locks)."""
        import ctypes
        try:
            ph, pw = padded_img.shape[:2]
            imagedata = padded_img.ctypes.data_as(ctypes.c_void_p)
            self.tesseract_lib.TessBaseAPISetPageSegMode(handle, 4)
            self.tesseract_lib.TessBaseAPISetImage(handle, imagedata, pw, ph, 1, pw)
            
            text_ptr = self.tesseract_lib.TessBaseAPIGetUTF8Text(handle)
            texts = []
            raw_lines = []
            if text_ptr:
                text_val = ctypes.string_at(text_ptr).decode('utf-8')
                self.tesseract_lib.TessDeleteText(text_ptr)
                for line in text_val.split('\n'):
                    cleaned = line.strip()
                    if cleaned:
                        raw_lines.append(cleaned)
                        cleaned_price = self._extract_price(cleaned)
                        if cleaned_price:
                            texts.append(cleaned_price)
                texts.reverse()
            return texts, raw_lines
        except Exception as e:
            print(f"[OCR Worker Handle Error] {e}")
            return [], []

    def _tesseract_read_full(self, img_gray):
        """Run standard Tesseract OCR on the full image using 4 parallel workers with Majority Vote."""
        if not self.tesseract_available or not hasattr(self, "tesseract_api_handles") or not self.tesseract_api_handles:
            return [], []
            
        with self._tess_lock:
            try:
                import cv2
                import numpy as np
                import concurrent.futures
                
                h, w = img_gray.shape[:2]
                
                # Pre-processing: Scale up image if small (DPI/character size enhancement)
                if h < 150:
                    scale = 2
                    img_gray_resized = cv2.resize(img_gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
                    h, w = img_gray_resized.shape[:2]
                else:
                    img_gray_resized = img_gray
                
                # Tạo 4 phiên bản ảnh khác nhau để 4 nhân viên nhận diện đa giả thuyết
                border = 15
                
                # 1. Ảnh xám gốc (Grayscale)
                pad1 = cv2.copyMakeBorder(img_gray_resized, border, border, border, border, cv2.BORDER_CONSTANT, value=255)
                
                # 2. Ảnh nhị phân thích ứng (Adaptive Thresholding)
                img_bin_adapt = cv2.adaptiveThreshold(
                    img_gray_resized, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                    cv2.THRESH_BINARY, 31, 15
                )
                pad2 = cv2.copyMakeBorder(img_bin_adapt, border, border, border, border, cv2.BORDER_CONSTANT, value=255)
                
                # 3. Ảnh nhị phân Otsu (Otsu Thresholding)
                _, img_bin_otsu = cv2.threshold(img_gray_resized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                pad3 = cv2.copyMakeBorder(img_bin_otsu, border, border, border, border, cv2.BORDER_CONSTANT, value=255)
                
                # 4. Ảnh xám không phóng to (Raw scale)
                pad4 = cv2.copyMakeBorder(img_gray, border, border, border, border, cv2.BORDER_CONSTANT, value=255)
                
                # Chạy 4 nhân viên quét song song dùng ThreadPoolExecutor (Giải phóng GIL của C++ ctypes)
                tasks = []
                num_workers = min(len(self.tesseract_api_handles), 4)
                
                images_to_use = [pad1, pad2, pad3, pad4]
                for idx in range(num_workers):
                    tasks.append((self.tesseract_api_handles[idx], images_to_use[idx]))
                
                results = [None] * num_workers
                with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
                    futures = {executor.submit(self._ocr_single_worker, h, img): idx for idx, (h, img) in enumerate(tasks)}
                    for future in concurrent.futures.as_completed(futures):
                        idx = futures[future]
                        try:
                            results[idx] = future.result()
                        except Exception as e:
                            print(f"[OCR Pool worker {idx} error] {e}")
                            results[idx] = ([], [])
                
                # Gộp kết quả bỏ phiếu
                primary_texts, primary_raw_lines = results[0] # Nhân viên 1 (Grayscale) là chủ lực về cấu trúc chữ (names/timings)
                
                # Gom toàn bộ giá trị đọc được từ tất cả nhân viên để đếm số phiếu bầu
                price_votes = {}
                for idx, res in enumerate(results):
                    if res and res[0]:
                        for price in res[0]:
                            price_votes[price] = price_votes.get(price, 0) + 1
                
                # Lọc ra các giá trị đạt từ 2 phiếu bầu trở lên
                consensus_prices = []
                for price, votes in price_votes.items():
                    if votes >= 2:
                        consensus_prices.append(price)
                
                # Sắp xếp các giá trị đạt đồng thuận theo thứ tự xuất hiện của chúng trong tin nhắn gốc
                final_texts = []
                
                if not consensus_prices:
                    final_texts = primary_texts
                else:
                    seen = set()
                    for p in primary_texts:
                        if p in consensus_prices and p not in seen:
                            final_texts.append(p)
                            seen.add(p)
                    for p in consensus_prices:
                        if p not in seen:
                            final_texts.append(p)
                            seen.add(p)
                
                self.last_ocr_votes = {price: f"{votes}/{num_workers}" for price, votes in price_votes.items()}
                return final_texts, primary_raw_lines
                
            except Exception as e:
                print(f"[Tesseract DLL Voting Pool] Error: {e}")
                return [], []

    def _tesseract_read_fast(self, img_gray):
        """Run optimized line-by-line Tesseract OCR using OpenCV segmentation."""
        if not self.tesseract_available or not self.tesseract_api_handle:
            return [], []
            
        try:
            import ctypes
            h_orig, w_orig = img_gray.shape[:2]
            
            # Pre-processing: Scale up image if small (DPI/character size enhancement)
            if h_orig < 300:
                scale = 2
                img_gray = cv2.resize(img_gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            
            # 1. Binarize to find text line regions using adaptiveThreshold
            binary = cv2.adaptiveThreshold(
                img_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY_INV, 19, 9
            )
            
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Find character-like contours
            char_candidates = []
            for ctr in contours:
                x, y, w, h = cv2.boundingRect(ctr)
                if 4 <= h <= 100 and 1 <= w <= 80:
                    char_candidates.append((x, y, w, h))
            
            if not char_candidates:
                return [], []
                
            # Group into horizontal text lines
            char_candidates.sort(key=lambda item: item[0])
            lines = []
            for item in char_candidates:
                x, y, w, h = item
                placed = False
                for line in lines:
                    line_y_min = min(c[1] for c in line)
                    line_y_max = max(c[1] + c[3] for c in line)
                    line_h = line_y_max - line_y_min
                    
                    overlap_y_min = max(y, line_y_min)
                    overlap_y_max = min(y + h, line_y_max)
                    if (overlap_y_max - overlap_y_min) > 0.4 * min(h, line_h):
                        line.append(item)
                        placed = True
                        break
                if not placed:
                    lines.append([item])
            
            # Sort lines from bottom to top (reversed)
            lines.sort(key=lambda l: min(c[1] for c in l), reverse=True)
            
            # Limit scanning to top 5 lines from bottom to guarantee zero lag
            lines = lines[:5]
            
            texts = []
            raw_lines = []
            # Treat image as a single text line (PSM 7) for ultra-fast Tesseract execution
            self.tesseract_lib.TessBaseAPISetPageSegMode(self.tesseract_api_handle, 7)
            
            for line in lines:
                # Find bounding box of the entire line
                x_min = min(c[0] for c in line)
                y_min = min(c[1] for c in line)
                x_max = max(c[0] + c[2] for c in line)
                y_max = max(c[1] + c[3] for c in line)
                
                # Add padding
                pad = 4
                h_img, w_img = img_gray.shape[:2]
                x1 = max(0, x_min - pad)
                y1 = max(0, y_min - pad)
                x2 = min(w_img, x_max + pad)
                y2 = min(h_img, y_max + pad)
                
                line_crop = img_gray[y1:y2, x1:x2]
                if line_crop.size == 0:
                    continue
                    
                # Threshold each line individually using adaptive thresh
                _, line_bin = cv2.threshold(line_crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                
                line_border = 5
                line_padded = cv2.copyMakeBorder(line_bin, line_border, line_border, line_border, line_border,
                                                 cv2.BORDER_CONSTANT, value=255)
                ph, pw = line_padded.shape[:2]
                
                imagedata = line_padded.ctypes.data_as(ctypes.c_void_p)
                self.tesseract_lib.TessBaseAPISetImage(self.tesseract_api_handle, imagedata, pw, ph, 1, pw)
                
                text_ptr = self.tesseract_lib.TessBaseAPIGetUTF8Text(self.tesseract_api_handle)
                if text_ptr:
                    text_val = ctypes.string_at(text_ptr).decode('utf-8').strip()
                    self.tesseract_lib.TessDeleteText(text_ptr)
                    
                    if text_val:
                        cleaned = text_val.strip()
                        raw_lines.append(cleaned)
                        cleaned_price = self._extract_price(cleaned)
                        if cleaned_price:
                            texts.append(cleaned_price)
            
            raw_lines.reverse()
            return texts, raw_lines
            
        except Exception as e:
            self.debug_log.emit(f"[Tesseract Fast Debug] Lỗi quét dòng: {str(e)}")
            return [], []

    def _tesseract_read(self, img_gray):
        """Run standard Tesseract OCR using PSM 3 for initial baseline calibration (multiline)."""
        return self._tesseract_read_full(img_gray)

    def start_capturing(self):
        self.prev_img = None
        self.is_capturing = True
        try:
            x, y, w, h = self.config.chat_zone
            dpr = self.device_pixel_ratio
            px = int(x * dpr)
            py = int(y * dpr)
            pw = int(w * dpr)
            ph = int(h * dpr)
            self.debug_log.emit(f"[Hệ thống] Bắt đầu quét màn hình. Vùng chụp hình (Logical): ({x}, {y}, {w}, {h}) -> (Physical): ({px}, {py}, {pw}, {ph}) ở DPR {dpr}")
        except Exception as e:
            print(f"[OCRWorker start_capturing log error] {e}")
        
    def stop_capturing(self):
        self.is_capturing = False
        
    def stop(self):
        self.running = False
        self.is_capturing = False
        if self.input_ocr_thread and self.input_ocr_thread.is_alive():
            self.input_ocr_thread.join(timeout=0.5)
        self.input_tesseract_handle = None

        # Release Tesseract BaseAPI handles if exist to prevent memory leaks
        if self.tesseract_available and hasattr(self, "tesseract_api_handles") and self.tesseract_api_handles and self.tesseract_lib:
            try:
                for handle in self.tesseract_api_handles:
                    self.tesseract_lib.TessBaseAPIDelete(handle)
                self.tesseract_api_handles = []
                self.tesseract_api_handle = None
                print("[OCR] All Tesseract BaseAPI handles deleted successfully.")
            except Exception as e:
                print(f"[OCR] Error deleting Tesseract handles: {e}")
        
    def run(self):
        self.running = True
        self.init_ocr()
        
        # Clear queue
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break
                
        # Start background OCR thread
        self.ocr_thread = threading.Thread(target=self._ocr_processing_loop, daemon=True)
        self.ocr_thread.start()
        
        # Start the dedicated draft OCR sensor. It owns the fifth Tesseract
        # handle, so chat OCR and input OCR never call the same API concurrently.
        self.input_ocr_thread = threading.Thread(target=self._input_ocr_loop, daemon=True)
        self.input_ocr_thread.start()

        # Initialize mss once outside the loop to save CPU and connect/disconnect overhead
        with mss.mss() as sct:
            while self.running:
                # If capturing is not enabled yet, sleep and check again
                if not self.is_capturing:
                    time.sleep(0.05)
                    continue
                    
                start_time = time.time()
                
                # Fetch settings chat zone (logical coords)
                x, y, w, h = self.config.chat_zone
                if w <= 0 or h <= 0:
                    time.sleep(0.05)
                    continue
                    
                try:
                    # Scale logical -> physical coordinates for PyAutoGUI screenshot, which expects physical coordinates on scaled Windows displays
                    dpr = self.device_pixel_ratio
                    px = int(round(x * dpr))
                    py = int(round(y * dpr))
                    pw = int(round(w * dpr))
                    ph = int(round(h * dpr))
                    
                    monitor = {"left": px, "top": py, "width": pw, "height": ph}
                    sct_img = sct.grab(monitor)
                    arr = np.array(sct_img)  # BGRA
                    if arr.size > 0:
                        img_gray = cv2.cvtColor(arr, cv2.COLOR_BGRA2GRAY)
                        
                        # Cắt lấy 60% chiều cao dưới cùng để giảm thời gian xử lý OCR và tăng độ chính xác
                        h_img, w_img = img_gray.shape[:2]
                        if h_img >= 100:
                            crop_h = int(h_img * 0.6)
                            ocr_img = img_gray[h_img - crop_h:h_img, :]
                        else:
                            ocr_img = img_gray
                        
                        # ===== Bộ lọc biến động Pixel-diff thông minh bằng OpenCV =====
                        has_change = True
                        if self.prev_img is not None and self.prev_img.shape == ocr_img.shape:
                            diff = cv2.absdiff(self.prev_img, ocr_img)
                            _, diff_thresh = cv2.threshold(diff, 15, 255, cv2.THRESH_BINARY)
                            changed_pixels = np.sum(diff_thresh > 0)
                            total_pixels = ocr_img.size
                            change_ratio = changed_pixels / total_pixels
                            
                            # Nhận diện nếu tỉ lệ thay đổi lớn hơn 0.1% (loại bỏ nháy con trỏ chuột)
                            if change_ratio < 0.001:
                                has_change = False
                                
                            # Cơ chế quét cưỡng bức Force Scan mỗi 50 khung hình (~250ms) chống sót tin
                            if not hasattr(self, "_force_scan_counter"):
                                self._force_scan_counter = 0
                            self._force_scan_counter += 1
                            if self._force_scan_counter >= 50:
                                self._force_scan_counter = 0
                                has_change = True
                        else:
                            has_change = True
                            
                        self.prev_img = ocr_img.copy()
                        
                        # ===== OCR queueing (Continuous) =====
                        if has_change:
                            t_capture_end = time.time()
                            if self.frame_queue.full():
                                try:
                                    self.frame_queue.get_nowait()
                                except queue.Empty:
                                    pass
                            self.frame_queue.put_nowait((ocr_img, start_time, t_capture_end))
                    
                except Exception as e:
                    self.debug_log.emit(f"[Lỗi Capture] {str(e)}")
                    print(f"[OCRWorker Capture Error] {e}")
                    
                # Control cycle speed
                elapsed = time.time() - start_time
                sleep_time = max(0.001, self.interval - elapsed)
                time.sleep(sleep_time)

    def _read_input_draft(self, img_gray):
        """Read one numeric draft from the dedicated Zalo input rectangle."""
        handle = self.input_tesseract_handle
        if not self.tesseract_available or not handle or img_gray is None or img_gray.size == 0:
            return ""

        import ctypes
        try:
            # Zalo commonly renders light text on a dark editor. Upscale, binarize
            # and normalize to dark digits on a white background for Tesseract.
            scaled = cv2.resize(img_gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            blurred = cv2.GaussianBlur(scaled, (3, 3), 0)
            _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            if float(np.mean(binary)) < 127.0:
                binary = cv2.bitwise_not(binary)
            padded = cv2.copyMakeBorder(binary, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)
            padded = np.ascontiguousarray(padded)
            ph, pw = padded.shape[:2]

            with self._input_tess_lock:
                self.tesseract_lib.TessBaseAPISetPageSegMode(handle, 7)
                self.tesseract_lib.TessBaseAPISetVariable(handle, b"tessedit_char_whitelist", b"0123456789")
                self.tesseract_lib.TessBaseAPISetImage(
                    handle, padded.ctypes.data_as(ctypes.c_void_p), pw, ph, 1, pw
                )
                text_ptr = self.tesseract_lib.TessBaseAPIGetUTF8Text(handle)
                if not text_ptr:
                    return ""
                raw = ctypes.string_at(text_ptr).decode("utf-8", errors="ignore")
                self.tesseract_lib.TessDeleteText(text_ptr)

            # Keep the full digit sequence so duplicated drafts such as
            # 12001200 remain visible to the state controller as a mismatch.
            return "".join(ch for ch in raw if ch.isdigit())
        except Exception as e:
            print(f"[Input OCR Error] {e}")
            return ""

    def _input_ocr_loop(self):
        """Continuously observe the draft box without entering the send critical path."""
        with mss.mss() as sct:
            while self.running:
                cycle_start = time.monotonic()
                if not self.is_capturing or not self.input_tesseract_handle:
                    time.sleep(0.05)
                    continue

                x, y, w, h = self.config.input_ocr_zone
                if x <= 0 or y <= 0 or w <= 1 or h <= 1:
                    time.sleep(0.05)
                    continue

                try:
                    dpr = self.device_pixel_ratio
                    monitor = {
                        "left": int(round(x * dpr)),
                        "top": int(round(y * dpr)),
                        "width": int(round(w * dpr)),
                        "height": int(round(h * dpr)),
                    }
                    shot = np.array(sct.grab(monitor))
                    gray = cv2.cvtColor(shot, cv2.COLOR_BGRA2GRAY)
                    observed = self._read_input_draft(gray)
                    self.input_text_detected.emit(observed, time.monotonic())
                except Exception as e:
                    print(f"[Input OCR Capture Error] {e}")

                # The input crop is small. About 30 Hz is enough to establish
                # two stable observations without consuming chat OCR capacity.
                elapsed = time.monotonic() - cycle_start
                time.sleep(max(0.005, 0.033 - elapsed))

    def _ocr_processing_loop(self):
        """Background thread loop for running OCR on captured frames."""
        while self.running:
            try:
                # Block wait for a frame (up to 100ms)
                item = self.frame_queue.get(timeout=0.1)
                if item is None:
                    continue
                ocr_img, start_time, t_capture_end = item
                t_ocr_start = time.time()
                
                texts = []
                raw_lines = []
                
                # PRIMARY: Standard full image Tesseract OCR
                if self.tesseract_available:
                    texts, raw_lines = self._tesseract_read_full(ocr_img)
                
                # FALLBACK: PaddleOCR - ONLY if Tesseract is not available
                if not texts and not self.tesseract_available and self.ocr and self.ocr_engine_type == "paddle":
                    ocr_bgr = cv2.merge([ocr_img, ocr_img, ocr_img])
                    result = self.ocr.ocr(ocr_bgr, cls=False)
                    if result and result[0]:
                        sorted_lines = sorted(result[0], key=lambda line: line[0][0][1])
                        for line in sorted_lines:
                            text = line[1][0]
                            confidence = line[1][1]
                            if confidence > 0.5:
                                raw_lines.append(text)
                                cleaned_price = self._extract_price(text)
                                if cleaned_price:
                                    texts.append(cleaned_price)
                        texts.reverse()
                
                t_ocr_end = time.time()
                
                # Print debug to UI console about processed GE results
                if texts:
                    timings = {
                        "capture_start": start_time,
                        "capture_duration_ms": int((t_capture_end - start_time) * 1000),
                        "queue_duration_ms": int((t_ocr_start - t_capture_end) * 1000),
                        "ocr_duration_ms": int((t_ocr_end - t_ocr_start) * 1000),
                        "raw_lines": raw_lines,
                    }
                    self.text_detected.emit(texts, timings)
                else:
                    # Even if no valid prices, emit raw lines for history/context update if raw_lines exist
                    if raw_lines:
                        timings = {
                            "capture_start": start_time,
                            "capture_duration_ms": int((t_capture_end - start_time) * 1000),
                            "queue_duration_ms": int((t_ocr_start - t_capture_end) * 1000),
                            "ocr_duration_ms": int((t_ocr_end - t_ocr_start) * 1000),
                            "raw_lines": raw_lines,
                        }
                        self.text_detected.emit([], timings)
                    
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[OCR Processing Thread Error] {e}")

    def generate_mock_texts(self):
        return []

    def _generate_templates(self):
        """Generates binary character templates. Prioritizes local disk templates from 'templates/' folder, falls back to Windows Segoe UI."""
        self.digits_templates = {}
        templates_dir = os.path.join(APP_DIR, "templates")
        
        char_map = {
            "0": "0", "1": "1", "2": "2", "3": "3", "4": "4",
            "5": "5", "6": "6", "7": "7", "8": "8", "9": "9",
            ".": "dot", ",": "comma", ";": "semicolon",
            ":": "colon", "/": "slash", "-": "dash"
        }
        
        # Check if templates directory exists and contains all 16 template files
        has_disk_templates = True
        if os.path.isdir(templates_dir):
            for char, file_key in char_map.items():
                p = os.path.join(templates_dir, f"{file_key}.png")
                if not os.path.isfile(p):
                    has_disk_templates = False
                    break
        else:
            has_disk_templates = False
            
        if has_disk_templates:
            print("[OCR] Loading templates from disk...")
            for char, file_key in char_map.items():
                p = os.path.join(templates_dir, f"{file_key}.png")
                img_gray = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
                if img_gray is not None:
                    resized = cv2.resize(img_gray, (16, 24), interpolation=cv2.INTER_CUBIC)
                    _, self.digits_templates[char] = cv2.threshold(resized, 127, 255, cv2.THRESH_BINARY)
            return
            
        font_paths = [
            r"C:\Windows\Fonts\segoeuib.ttf",
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\arial.ttf"
        ]
        
        font_path = None
        for p in font_paths:
            if os.path.exists(p):
                font_path = p
                break
                
        for char in "0123456789.,;:/-":
            # Render character onto a 40x60 canvas
            img = Image.new("L", (40, 60), 0)
            draw = ImageDraw.Draw(img)
            try:
                if font_path:
                    font = ImageFont.truetype(font_path, 40)
                else:
                    font = ImageFont.load_default()
            except Exception:
                font = ImageFont.load_default()
                
            if hasattr(font, "getbbox"):
                bbox = font.getbbox(char)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                tx = (40 - tw) // 2 - bbox[0]
                ty = (60 - th) // 2 - bbox[1]
            else:
                tw, th = draw.textsize(char, font=font)
                tx = (40 - tw) // 2
                ty = (60 - th) // 2
                
            draw.text((tx, ty), char, fill=255, font=font)
            
            arr = np.array(img)
            pts = np.argwhere(arr > 0)
            if len(pts) > 0:
                y_min, x_min = pts.min(axis=0)
                y_max, x_max = pts.max(axis=0)
                cropped = arr[y_min:y_max+1, x_min:x_max+1]
            else:
                cropped = arr
                
            resized = cv2.resize(cropped, (16, 24), interpolation=cv2.INTER_CUBIC)
            _, self.digits_templates[char] = cv2.threshold(resized, 127, 255, cv2.THRESH_BINARY)

    def _opencv_read(self, img_gray):
        """Extremely fast custom OpenCV template-matching OCR for digits 0-9 and punctuation.
        Runs in < 1ms."""
        if not self.digits_templates:
            self._generate_templates()
            
        try:
            # Adaptive thresholding to handle mixed background colors (blue bubble, white bubble, gray window)
            # Outputs white text on black background automatically
            binary = cv2.adaptiveThreshold(
                img_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY_INV, 19, 9
            )
            
            # Find contours
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Filter character candidates (support smaller heights for punctuation symbols)
            char_candidates = []
            for ctr in contours:
                x, y, w, h = cv2.boundingRect(ctr)
                if 8 <= h <= 50 and 2 <= w <= 40:
                    ratio = w / h
                    if 0.1 <= ratio <= 1.5:
                        char_candidates.append((x, y, w, h))
                        
            if not char_candidates:
                return []
                
            # Merge vertically aligned components (like for colon ':' and semicolon ';')
            char_candidates.sort(key=lambda item: item[0])
            merged_candidates = []
            for box in char_candidates:
                bx, by, bw, bh = box
                merged = False
                for i, m_box in enumerate(merged_candidates):
                    mx, my, mw, mh = m_box
                    # Check X overlap
                    overlap_x = min(bx + bw, mx + mw) - max(bx, mx)
                    min_w = min(bw, mw)
                    if overlap_x > 0.5 * min_w:
                        new_x = min(bx, mx)
                        new_y = min(by, my)
                        new_w = max(bx + bw, mx + mw) - new_x
                        new_h = max(by + bh, my + mh) - new_y
                        merged_candidates[i] = (new_x, new_y, new_w, new_h)
                        merged = True
                        break
                if not merged:
                    merged_candidates.append((bx, by, bw, bh))
            
            if merged_candidates:
                self.debug_log.emit(f"[OpenCV Debug] Tìm thấy {len(merged_candidates)} nét ký tự.")
                
            # Group into horizontal text lines
            merged_candidates.sort(key=lambda item: item[0])
            lines = []
            for item in merged_candidates:
                x, y, w, h = item
                placed = False
                for line in lines:
                    line_y_min = min(c[1] for c in line)
                    line_y_max = max(c[1] + c[3] for c in line)
                    line_h = line_y_max - line_y_min
                    
                    overlap_y_min = max(y, line_y_min)
                    overlap_y_max = min(y + h, line_y_max)
                    if (overlap_y_max - overlap_y_min) > 0.4 * min(h, line_h):
                        line.append(item)
                        placed = True
                        break
                if not placed:
                    lines.append([item])
                    
            detected_texts = []
            for line in lines:
                line.sort(key=lambda item: item[0])
                line_str = ""
                scores = []
                for x, y, w, h in line:
                    char_crop = binary[y:y+h, x:x+w]
                    char_crop_res = cv2.resize(char_crop, (16, 24), interpolation=cv2.INTER_CUBIC)
                    _, char_crop_bin = cv2.threshold(char_crop_res, 127, 255, cv2.THRESH_BINARY)
                    
                    best_score = -1.0
                    best_char = ""
                    for char, template in self.digits_templates.items():
                        if char in [".", ","]:
                            continue  # Skip dot and comma to avoid matching tiny noise
                        res = cv2.matchTemplate(char_crop_bin, template, cv2.TM_CCOEFF_NORMED)
                        score = res[0][0]
                        if score > best_score:
                            best_score = score
                            best_char = char
                            
                    if best_score > 0.45:
                        line_str += best_char
                        scores.append(best_score)
                    else:
                        # Log unmatched components
                        scores.append(0.0)
                        
                if line_str:
                    avg_score = int((sum(scores) / len(scores)) * 100) if scores else 0
                    contains_punctuation = any(c in line_str for c in ".,;:/-")
                    if contains_punctuation:
                        self.debug_log.emit(f"[OpenCV Debug] Dòng '{line_str}' bị bỏ qua vì chứa ký tự đặc biệt (Độ khớp: {avg_score}%).")
                    elif not line_str.isdigit():
                        self.debug_log.emit(f"[OpenCV Debug] Dòng '{line_str}' không phải số nguyên chất (Độ khớp: {avg_score}%).")
                    else:
                        self.debug_log.emit(f"[OpenCV Debug] Đọc được giá: {line_str} (Độ khớp: {avg_score}%).")
                        detected_texts.append(line_str)
                        
            detected_texts.reverse()
            return detected_texts
        except Exception as e:
            self.debug_log.emit(f"[OpenCV Debug] Lỗi trong _opencv_read: {str(e)}")
            return []
