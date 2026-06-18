import os
import sys
import shutil
import tempfile
import threading
from pathlib import Path
import stage_excel

# Setup paths for submodules
if getattr(sys, 'frozen', False):
    # PyInstaller 6+ puts data in _internal
    _internal = os.path.join(os.path.dirname(sys.executable), '_internal')
    if os.path.exists(_internal):
        BASE_DIR = _internal
    else:
        BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MIXED_TOOL_DIR = os.path.join(BASE_DIR, "mixed_tool1.1")
PICTURES_GET_DIR = os.path.join(MIXED_TOOL_DIR, "pictures_get")
PICTURE_RECOGNIZE_DIR = os.path.join(MIXED_TOOL_DIR, "picture_recognize")

# Try to add local .venv site-packages if available (for portability)
VENV_SITE_PACKAGES = os.path.join(PICTURES_GET_DIR, ".venv", "Lib", "site-packages")
if os.path.exists(VENV_SITE_PACKAGES):
    sys.path.append(VENV_SITE_PACKAGES)

sys.path.append(PICTURES_GET_DIR)
sys.path.append(PICTURE_RECOGNIZE_DIR)

# Global cache for heavy resources
_OCR_READER = None
_WHITELIST = None
_OCR_LOCK = threading.Lock()

def get_ocr_reader():
    global _OCR_READER
    if _OCR_READER is None:
        try:
            import easyocr
            # Initialize reader once
            model_dir = os.path.join(BASE_DIR, "models")
            if not os.path.exists(model_dir):
                model_dir = None
            _OCR_READER = easyocr.Reader(['ch_sim'], gpu=True, model_storage_directory=model_dir)
        except ImportError:
            print("Error: easyocr not installed.")
            return None
        except Exception as e:
            print(f"Error: failed to initialize easyocr: {e}")
            return None
    return _OCR_READER

def get_whitelist():
    global _WHITELIST
    if _WHITELIST is None:
        try:
            from gui_recognize_ops import load_whitelist_from_xlsx
            xlsx_path = os.path.join(BASE_DIR, "Arknights_Operators.xlsx")
            _WHITELIST = load_whitelist_from_xlsx(xlsx_path)
        except ImportError:
            print("Error: Failed to import whitelist loader.")
            return set()
    return _WHITELIST


def _short_error(e):
    msg = str(e).strip()
    if not msg:
        return e.__class__.__name__
    return msg.splitlines()[0][:120]


def fetch_video_details(url, status_callback=None):
    """
    Downloads video, extracts frames, and recognizes operators.
    Returns: (count, names_str) or (None, None) if failed.
    """
    count, names, _ = fetch_video_details_with_status(url, status_callback=status_callback)
    return count, names


def fetch_video_details_with_status(url, status_callback=None):
    """
    Downloads video, extracts frames, and recognizes operators.
    Returns: (count, names_str, status_message).
    """
    if not url:
        return None, None, "链接为空"

    # Lazy import to avoid startup cost if not used
    try:
        from bili_capture import process_input
        import detect
        from gui_recognize_ops import ocr_names, match_whitelist
    except ImportError as e:
        print(f"Import Error: {e}")
        return None, None, f"依赖导入失败: {_short_error(e)}"

    if status_callback:
        status_callback("正在初始化 OCR 模型...")
    
    reader = get_ocr_reader()
    if not reader:
        return None, None, "OCR初始化失败"
        
    whitelist = get_whitelist()
    if not whitelist:
        return None, None, "干员白名单为空或加载失败"
    
    temp_dir = tempfile.mkdtemp()
    try:
        if status_callback:
            status_callback("正在下载视频并抽帧...")
            
        # Download and extract frames (using fps=4, duration=6)
        cookie = stage_excel.get_bili_cookie()
        frames_dir = process_input(url, Path(temp_dir), fps=4, duration_sec=6, cookie=cookie)
        
        if not frames_dir or not frames_dir.exists():
            return None, None, "视频抽帧失败"
            
        if status_callback:
            status_callback("正在识别画面...")
            
        files = sorted([f for f in os.listdir(frames_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))])
        if not files:
            return None, None, "未生成有效帧"
            
        # Detection logic from integrated_gui.py
        # Iterate to find selection screen, then recognize next frame
        for i in range(len(files) - 1):
            fname = files[i]
            fpath = os.path.join(frames_dir, fname)
            
            is_selection = False
            with _OCR_LOCK:
                is_selection = detect.is_selection_screen(fpath, reader=reader)
            
            if is_selection:
                # Target is the NEXT frame
                target_fname = files[i+1]
                target_path = os.path.join(frames_dir, target_fname)
                
                with _OCR_LOCK:
                    names = ocr_names(target_path, reader=reader)
                valid_names = match_whitelist(names, whitelist)
                
                if valid_names:
                    # Found it
                    return len(valid_names), " ".join(valid_names), "阵容识别成功"
        
        # If no selection screen found, maybe try the last frame or specific frames? 
        # For now, stick to strict logic to avoid garbage data.
        return None, None, "未识别到编队画面"

    except Exception as e:
        print(f"Processing Error: {e}")
        return None, None, f"视频处理失败: {_short_error(e)}"
    finally:
        # Cleanup
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass
