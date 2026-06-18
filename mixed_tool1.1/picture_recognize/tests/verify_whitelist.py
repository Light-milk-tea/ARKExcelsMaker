import os
import sys

# Ensure we can import from parent directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from gui_recognize_ops import load_whitelist_from_xlsx

xlsx_path = os.path.join(PARENT_DIR, "四星队名单.xlsx")
wl = load_whitelist_from_xlsx(xlsx_path)
print(f"whitelist_count={len(wl)}")
print("sample=", sorted(list(wl))[:10])

