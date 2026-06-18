import os
import subprocess
import sys

def build():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    entry_point = os.path.join(base_dir, "gui.py")
    
    # Dependencies
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
        "openpyxl",
        "stage_excel",
        "auto_fill_helper"
    ]
    
    # Construct command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--console", # Keep console for debug, user can change to --windowed later
        "--name", "ExcelsMaker",
        "--clean",
    ]
    
    # Add data
    # We need to recreate the structure expected by auto_fill_helper.py
    # mixed_tool1.1/picture_recognize/四星队名单.xlsx -> mixed_tool1.1/picture_recognize
    
    mixed_tool_dir = os.path.join(base_dir, "mixed_tool1.1")
    pic_rec_dir = os.path.join(mixed_tool_dir, "picture_recognize")
    
    xlsx_src = os.path.join(base_dir, "Arknights_Operators.xlsx")
    res_src = os.path.join(pic_rec_dir, "res")
    
    if os.path.exists(xlsx_src):
        cmd.extend(["--add-data", f"{xlsx_src};."])
    
    if os.path.exists(res_src):
        cmd.extend(["--add-data", f"{res_src};mixed_tool1.1/picture_recognize/res"])

    # Add EasyOCR models
    easyocr_model_dir = os.path.join(os.path.expanduser("~"), ".EasyOCR", "model")
    if os.path.exists(easyocr_model_dir):
        print(f"Found EasyOCR models at: {easyocr_model_dir}")
        cmd.extend(["--add-data", f"{easyocr_model_dir};models"])
    else:
        print("Warning: EasyOCR models not found in default location.")

    # Add import paths
    # We add the subdirectories of mixed_tool1.1 so that 'import bili_capture' works
    cmd.extend(["--paths", os.path.join(mixed_tool_dir, "pictures_get")])
    cmd.extend(["--paths", os.path.join(mixed_tool_dir, "picture_recognize")])
    cmd.extend(["--paths", base_dir])
    
    # Add hidden imports
    for hidden in hidden_imports:
        cmd.extend(["--hidden-import", hidden])
        
    cmd.append(entry_point)
    
    print("Starting build process for ExcelsMaker...")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        subprocess.check_call(cmd)
        print("\n" + "="*50)
        print("Build Successful!")
        print(f"Your application is in: {os.path.join(base_dir, 'dist', 'ExcelsMaker')}")
        print("Run 'ExcelsMaker.exe' to start.")
        print("="*50)
    except subprocess.CalledProcessError:
        print("\n" + "="*50)
        print("Build Failed.")
        print("="*50)

if __name__ == "__main__":
    build()
