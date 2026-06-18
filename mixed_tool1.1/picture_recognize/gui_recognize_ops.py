import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import re
import os
import zipfile
from xml.etree import ElementTree as ET
from PIL import Image, ImageTk
import detect
import cv2
import numpy as np
import difflib

def filter_text(s):
    if not s:
        return False
    if len(s) < 1 or len(s) > 6:
        return False
    if re.search(r"[0-9A-Za-z\-\+\.\_\*\[\]\(\)~@#\$%&=:/\\]", s):
        return False
    if re.search(r"[^\u4e00-\u9fff·]", s):
        return False
    return True

def match_whitelist(names, whitelist):
    resolved = []
    for n in names:
        if n in whitelist:
            resolved.append(n)
            continue
        # Fuzzy match
        matches = difflib.get_close_matches(n, whitelist, n=1, cutoff=0.7) 
        if matches:
            resolved.append(matches[0])
    return list(set(resolved))

def ocr_names(path, reader=None):
    try:
        import easyocr
    except Exception:
        messagebox.showerror("错误", "未检测到 easyocr，请执行: pip install easyocr")
        return []
    
    # Use detect.imread_safe to handle non-ASCII paths on Windows
    img_array = detect.imread_safe(path)
    
    target = path
    if img_array is not None:
        try:
            # 1. Convert to Grayscale to reduce noise
            target = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
            
            # 2. Resize/Upscale image to improve recognition of small text
            h, w = target.shape[:2]
            scale = 1.0
            if w < 2000:
                scale = 1.5
            
            if scale > 1.0:
                target = cv2.resize(target, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
                
            # Add padding to avoid edge issues
            target = cv2.copyMakeBorder(target, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=[255, 255, 255])
        except Exception:
            # Fallback to original image if processing fails
            target = img_array

    if reader is None:
        reader = easyocr.Reader(["ch_sim"], gpu=True)
        
    # 3. Use mag_ratio to further help with small text detection
    results = reader.readtext(target, mag_ratio=1.2)
    names = []
    seen = set()
    for _, text, conf in results:
        # 4. Lower confidence threshold (from 0.5 to 0.2)
        # Since we have a strict whitelist, we can tolerate lower OCR confidence
        if conf < 0.2:
            continue
        text = text.strip()
        # Clean text
        text = re.sub(r"[^\u4e00-\u9fff·]", "", text)
        if filter_text(text):
            if text not in seen:
                seen.add(text)
                names.append(text)
    return names

def load_whitelist_from_xlsx(xlsx_path):
    p = xlsx_path
    if p.startswith("/"):
        p = p[1:]
    p = os.path.normpath(p.replace("/", "\\"))
    if not os.path.exists(p):
        # Try to find in current directory or one level up if not found
        # This helps with PyInstaller --onedir structure
        base = os.path.basename(p)
        candidates = [
            os.path.join(os.path.dirname(p), base),
            os.path.join(os.getcwd(), base),
            os.path.join(os.path.dirname(sys.executable), base) if getattr(sys, 'frozen', False) else None,
            os.path.join(os.path.dirname(sys.executable), "_internal", base) if getattr(sys, 'frozen', False) else None,
            os.path.join(os.getcwd(), "picture_recognize", base),
            os.path.join(os.path.dirname(os.getcwd()), "picture_recognize", base),
             # Handle typical dist structure
            os.path.join(os.path.dirname(sys.executable), "picture_recognize", base) if getattr(sys, 'frozen', False) else None,
            # Handle PyInstaller 6+ _internal structure
            os.path.join(os.path.dirname(sys.executable), "_internal", "picture_recognize", base) if getattr(sys, 'frozen', False) else None
        ]
        
        found = False
        for c in candidates:
            if c and os.path.exists(c):
                p = c
                found = True
                break
        
        if not found:
            # Debug info
            # messagebox.showerror("错误", f"未找到名单文件: {p}\nCWD: {os.getcwd()}")
            messagebox.showerror("错误", "未找到名单文件")
            return set()
            
    try:
        with zipfile.ZipFile(p) as z:
            with z.open("xl/sharedStrings.xml") as f:
                tree = ET.parse(f)
    except Exception:
        messagebox.showerror("错误", "无法读取名单文件")
        return set()
    root = tree.getroot()
    wl = set()
    for si in root.findall(".//{*}si"):
        texts = []
        t = si.find("{*}t")
        if t is not None and t.text:
            texts.append(t.text)
        else:
            for r in si.findall("{*}r"):
                t2 = r.find("{*}t")
                if t2 is not None and t2.text:
                    texts.append(t2.text)
        if texts:
            s = "".join(texts).strip()
            if filter_text(s):
                wl.add(s)
    return wl

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("干员识别演示")
        self.geometry("640x520")
        self.upload_path = None
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        xlsx_rel_path = os.path.join(base_dir, "Arknights_Operators.xlsx")
        self.whitelist = load_whitelist_from_xlsx(xlsx_rel_path)
        frm = ttk.Frame(self)
        frm.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        top = ttk.Frame(frm)
        top.pack(fill=tk.X)
        ttk.Button(top, text="上传图片", command=self.upload).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="识别干员", command=self.recognize).pack(side=tk.LEFT, padx=6)
        mid = ttk.Frame(frm)
        mid.pack(fill=tk.BOTH, expand=True, pady=8)
        self.canvas = tk.Label(mid)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        bottom = ttk.Frame(frm)
        bottom.pack(fill=tk.BOTH)
        self.count_label = ttk.Label(bottom, text="干员总数: 0")
        self.count_label.pack(anchor=tk.W)
        self.listbox = tk.Listbox(bottom, height=10)
        self.listbox.pack(fill=tk.BOTH, expand=True, pady=6)
        self.img_ref = None
        self.path_label = ttk.Label(frm, text="")
        self.path_label.pack(fill=tk.X, anchor=tk.W)

    def recognize(self):
        if not self.upload_path:
            messagebox.showinfo("提示", "请先上传图片")
            return
        if not detect.is_selection_screen(self.upload_path):
            messagebox.showinfo("提示", "未检测到选人界面")
            return
        names = ocr_names(self.upload_path)
        names = match_whitelist(names, self.whitelist)
        self.listbox.delete(0, tk.END)
        for n in names:
            self.listbox.insert(tk.END, n)
        self.count_label.configure(text=f"干员总数: {len(names)}")
        self.path_label.configure(text=f"来源: {self.upload_path}")

    def upload(self):
        path = filedialog.askopenfilename(filetypes=[("Image", "*.png;*.jpg;*.jpeg;*.bmp")])
        if not path:
            return
        self.upload_path = path
        try:
            pil = Image.open(path)
        except Exception:
            messagebox.showerror("错误", "无法加载图片")
            return
        w, h = pil.size
        max_w, max_h = 600, 300
        scale = min(max_w / w, max_h / h, 1.0)
        nw, nh = int(w * scale), int(h * scale)
        pil = pil.resize((nw, nh), Image.LANCZOS)
        self.img_ref = ImageTk.PhotoImage(pil)
        self.canvas.configure(image=self.img_ref)
        self.path_label.configure(text=f"来源: {path}")

def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
