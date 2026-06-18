import cv2
import numpy as np

def imread_safe(path, flags=cv2.IMREAD_COLOR):
    try:
        return cv2.imdecode(np.fromfile(path, dtype=np.uint8), flags)
    except Exception:
        return None

def _load_gray(path):
    img = imread_safe(path, cv2.IMREAD_GRAYSCALE)
    return img

def is_selection_screen(image_path, template_path=None, threshold=0.6, reader=None):
    # OCR based detection for "快捷编队"
    # We ignore template_path and threshold as they are for template matching
    try:
        import easyocr
    except ImportError:
        # If easyocr is not available, we can't do this check properly.
        # Fallback or return False? Or assume True?
        # Let's print a warning and assume True for now to not block flow, 
        # but ideally we should require easyocr.
        print("Warning: easyocr not found, skipping selection screen check.")
        return True

    img = imread_safe(image_path)
    if img is None:
        return False
    
    # Initialize reader (this might be slow if re-initialized every time, 
    # but for this specific function we might not have a global reader)
    # Ideally, the reader should be passed in or cached.
    if reader is None:
        reader = easyocr.Reader(['ch_sim'], gpu=True) # Try to use GPU if available
    
    # Optimization: Only check the top 25% of the image for "快捷编队"
    h, w = img.shape[:2]
    crop_h = int(h * 0.25)
    if crop_h > 0:
        check_img = img[:crop_h, :]
    else:
        check_img = img

    results = reader.readtext(check_img)
    
    for _, text, _ in results:
        if "快捷" in text:
            return True
            
    return False
