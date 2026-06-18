import os
import subprocess
import sys

def build():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    entry_point = os.path.join(base_dir, "integrated_gui.py")
    
    # Dependencies that might be hidden or dynamic
    hidden_imports = [
        "yt_dlp",
        "bili_capture", 
        "detect", 
        "gui_recognize_ops",
        "easyocr",
        "imageio_ffmpeg",
        "cv2",
        "numpy",
        "PIL",
        "openpyxl"
    ]
    
    # Construct command
    # Use python -m PyInstaller to ensure we use the installed module
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--console",
        "--name", "MixedTool",
        "--clean",
    ]
    
    # Add data
    # Syntax: source;dest
    # We need to make sure paths are relative to base_dir or absolute
    res_src = os.path.join(base_dir, "picture_recognize", "res")
    xlsx_src = os.path.join(base_dir, "picture_recognize", "四星队名单.xlsx")
    
    if os.path.exists(res_src):
        cmd.extend(["--add-data", f"{res_src};picture_recognize/res"])
    if os.path.exists(xlsx_src):
        cmd.extend(["--add-data", f"{xlsx_src};picture_recognize"])
    
    # Add EasyOCR models
    easyocr_model_dir = os.path.join(os.path.expanduser("~"), ".EasyOCR", "model")
    if os.path.exists(easyocr_model_dir):
        print(f"Found EasyOCR models at: {easyocr_model_dir}")
        cmd.extend(["--add-data", f"{easyocr_model_dir};models"])
    else:
        print("Warning: EasyOCR models not found in default location. User might need to download them.")
        
    # Add import paths
    cmd.extend(["--paths", os.path.join(base_dir, "pictures_get")])
    cmd.extend(["--paths", os.path.join(base_dir, "picture_recognize")])
    
    # Add hidden imports
    for hidden in hidden_imports:
        cmd.extend(["--hidden-import", hidden])
        
    cmd.append(entry_point)
    
    print("Starting build process...")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        subprocess.check_call(cmd)
        print("\n" + "="*50)
        print("Build Successful!")
        print(f"Your standalone application is in: {os.path.join(base_dir, 'dist', 'MixedTool')}")
        print("You can copy this 'MixedTool' folder to any Windows computer and run 'MixedTool.exe'.")
        print("="*50)
    except subprocess.CalledProcessError:
        print("\n" + "="*50)
        print("Build Failed.")
        print("Please ensure PyInstaller is installed: pip install pyinstaller")
        print("="*50)

if __name__ == "__main__":
    build()
