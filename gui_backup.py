import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import stage_excel
import auto_fill_helper
from pathlib import Path
import csv
import json
import re
from datetime import datetime
import threading
import os
import sys

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("表格生成器-轻茗yo")
        self.root.geometry("1000x700")
        
        # Data storage
        self.rows = []  # List of dicts: 关卡, 链接, 人数, 阵容, 备注
        self.current_sort = None
        
        self._init_ui()
        
    def _init_ui(self):
        # Top Frame: Config
        config_frame = ttk.LabelFrame(self.root, text="参数设置", padding="10")
        config_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(config_frame, text="关卡主题:").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.theme_var = tk.StringVar(value="UR")
        ttk.Entry(config_frame, textvariable=self.theme_var, width=10).grid(row=0, column=1, padx=5)
        
        ttk.Label(config_frame, text="普通关卡数:").grid(row=0, column=2, padx=5, sticky=tk.W)
        self.normal_count_var = tk.IntVar(value=8)
        ttk.Spinbox(config_frame, from_=0, to=100, textvariable=self.normal_count_var, width=5).grid(row=0, column=3, padx=5)
        
        ttk.Label(config_frame, text="EX关卡数:").grid(row=0, column=4, padx=5, sticky=tk.W)
        self.ex_count_var = tk.IntVar(value=8)
        ttk.Spinbox(config_frame, from_=0, to=100, textvariable=self.ex_count_var, width=5).grid(row=0, column=5, padx=5)
        
        ttk.Label(config_frame, text="S关卡数:").grid(row=0, column=6, padx=5, sticky=tk.W)
        self.s_count_var = tk.IntVar(value=5)
        self.s_spin = ttk.Spinbox(config_frame, from_=0, to=100, textvariable=self.s_count_var, width=5)
        self.s_spin.grid(row=0, column=7, padx=5)
        
        self.s_exists_var = tk.BooleanVar(value=True)
        self.s_check = ttk.Checkbutton(config_frame, text="存在S关", variable=self.s_exists_var, command=self._toggle_s_count)
        self.s_check.grid(row=0, column=8, padx=5)
        
        ttk.Button(config_frame, text="生成关卡列表", command=self.generate_stages).grid(row=0, column=9, padx=10)
        
        # Middle Frame: Table
        table_frame = ttk.Frame(self.root, padding="10")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10)
        
        columns = ("关卡", "链接", "作者名", "人数", "阵容", "备注")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        
        # Define headings and column widths
        self.tree.heading("关卡", text="关卡")
        self.tree.column("关卡", width=80, anchor=tk.CENTER)
        
        self.tree.heading("链接", text="链接 (双击打开)")
        self.tree.column("链接", width=250)
        
        self.tree.heading("作者名", text="作者名")
        self.tree.column("作者名", width=100)
        
        self.tree.heading("人数", text="人数")
        self.tree.column("人数", width=60, anchor=tk.CENTER)
        
        self.tree.heading("阵容", text="阵容")
        self.tree.column("阵容", width=150)
        
        self.tree.heading("备注", text="备注")
        self.tree.column("备注", width=150)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind events
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", self.on_double_click)
        
        # Bottom Frame: Edit Area
        edit_frame = ttk.LabelFrame(self.root, text="编辑选中行", padding="10")
        edit_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.edit_vars = {
            "关卡": tk.StringVar(),
            "链接": tk.StringVar(),
            "作者名": tk.StringVar(),
            "人数": tk.StringVar(),
            "阵容": tk.StringVar(),
            "备注": tk.StringVar()
        }
        
        # Layout for edit fields
        # Row 1
        ttk.Label(edit_frame, text="关卡:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(edit_frame, textvariable=self.edit_vars["关卡"], state="readonly", width=15).grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(edit_frame, text="链接:").grid(row=0, column=2, sticky=tk.W)
        ttk.Entry(edit_frame, textvariable=self.edit_vars["链接"], width=50).grid(row=0, column=3, columnspan=3, padx=5, pady=2, sticky=tk.W)
        
        # Row 2
        ttk.Label(edit_frame, text="作者名:").grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(edit_frame, textvariable=self.edit_vars["作者名"], width=15).grid(row=1, column=1, padx=5, pady=2)

        ttk.Label(edit_frame, text="人数:").grid(row=1, column=2, sticky=tk.W)
        ttk.Entry(edit_frame, textvariable=self.edit_vars["人数"], width=15).grid(row=1, column=3, padx=5, pady=2)
        
        ttk.Label(edit_frame, text="阵容:").grid(row=1, column=4, sticky=tk.W)
        ttk.Entry(edit_frame, textvariable=self.edit_vars["阵容"], width=20).grid(row=1, column=5, padx=5, pady=2)

        # Row 3
        ttk.Label(edit_frame, text="备注:").grid(row=2, column=0, sticky=tk.W)
        ttk.Entry(edit_frame, textvariable=self.edit_vars["备注"], width=20).grid(row=2, column=1, padx=5, pady=2)
        
        # Buttons
        btn_frame = ttk.Frame(edit_frame)
        btn_frame.grid(row=0, column=6, rowspan=3, padx=20)
        
        ttk.Button(btn_frame, text="保存修改", command=self.save_edit).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="清空此行", command=self.clear_row).pack(fill=tk.X, pady=2)

        # Action Bar
        action_frame = ttk.Frame(self.root, padding="10")
        action_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(action_frame, text="导入 Excel/CSV", command=self.import_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="联网补全信息", command=self.preview_info).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="生成最终 Excel", command=self.generate_file).pack(side=tk.RIGHT, padx=5)
        
        # Status Bar
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _toggle_s_count(self):
        if self.s_exists_var.get():
            self.s_spin.config(state=tk.NORMAL)
        else:
            self.s_spin.config(state=tk.DISABLED)

    def generate_stages(self):
        theme = self.theme_var.get().strip().upper()
        if not theme:
            messagebox.showerror("错误", "请输入关卡主题")
            return
            
        if messagebox.askyesno("确认", "生成新列表将清空当前表格数据，是否继续？"):
            self.rows = []
            self.tree.delete(*self.tree.get_children())
            
            stages = stage_excel.generate_stages(
                theme,
                self.normal_count_var.get(),
                self.ex_count_var.get(),
                self.s_count_var.get() if self.s_exists_var.get() else 0
            )
            
            for s in stages:
                row = {"关卡": s, "链接": "", "作者名": "", "人数": "", "阵容": "", "备注": ""}
                self.rows.append(row)
                self.tree.insert("", tk.END, values=(s, "", "", "", "", ""))
            
            self.status_var.set(f"已生成 {len(stages)} 个关卡")

    def on_select(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        
        item = self.tree.item(selected[0])
        vals = item['values']
        if not vals: 
            return
            
        # Update edit vars
        # Note: vals corresponds to columns defined in treeview
        # ("关卡", "链接", "人数", "阵容", "备注")
        # However, treeview values might convert numbers to str automatically or handling empty strings differently.
        # It's safer to map by index.
        
        self.edit_vars["关卡"].set(vals[0] or "")
        self.edit_vars["链接"].set(vals[1] or "")
        self.edit_vars["作者名"].set(vals[2] or "")
        self.edit_vars["人数"].set(vals[3] or "")
        self.edit_vars["阵容"].set(vals[4] or "")
        self.edit_vars["备注"].set(vals[5] or "")

    def on_double_click(self, event):
        # Open link in browser if valid
        selected = self.tree.selection()
        if not selected:
            return
        item = self.tree.item(selected[0])
        link = (item['values'][1] or "").strip()
        # Try normalize (handle BV codes)
        link = stage_excel.normalize_url(link)
        if link.startswith("http"):
            import webbrowser
            webbrowser.open(link)

    def save_edit(self):
        selected = self.tree.selection()
        if not selected:
            return
            
        idx = self.tree.index(selected[0])
        
        new_vals = (
            self.edit_vars["关卡"].get(),
            self.edit_vars["链接"].get(),
            self.edit_vars["人数"].get(),
            self.edit_vars["阵容"].get(),
            self.edit_vars["备注"].get()
        )
        
        # Update UI
        self.tree.item(selected[0], values=new_vals)
        
        # Update Data
        if 0 <= idx < len(self.rows):
            self.rows[idx]["关卡"] = new_vals[0]
            self.rows[idx]["链接"] = new_vals[1]
            self.rows[idx]["人数"] = new_vals[2]
            self.rows[idx]["阵容"] = new_vals[3]
            self.rows[idx]["备注"] = new_vals[4]
            
        self.status_var.set(f"已更新关卡 {new_vals[0]}")

    def clear_row(self):
        self.edit_vars["链接"].set("")
        self.edit_vars["作者名"].set("")
        self.edit_vars["人数"].set("")
        self.edit_vars["阵容"].set("")
        self.edit_vars["备注"].set("")
        self.save_edit()

    def import_file(self):
        path = filedialog.askopenfilename(filetypes=[("Excel/CSV Files", "*.xlsx *.csv")])
        if not path:
            return
            
        try:
            p = Path(path)
            imported_rows = []
            if p.suffix.lower() == ".xlsx":
                import openpyxl
                wb = openpyxl.load_workbook(p)
                ws = wb.active
                # Basic header detection
                header = []
                for i, r in enumerate(ws.iter_rows(values_only=True)):
                    vals = [(str(v).strip() if v is not None else "") for v in r]
                    if i == 0:
                        header = vals
                        continue
                    if not any(vals): continue
                    
                    entry = {}
                    for idx, h in enumerate(header):
                        key = (h or "").strip()
                        if key:
                            entry[key] = vals[idx] if idx < len(vals) else ""
                    
                    stage = entry.get("关卡", "")
                    if stage:
                        # Fallback for link: if empty, try BV column
                        link = entry.get("链接", "")
                        if not link:
                            bv_val = entry.get("BV号", "")
                            if bv_val:
                                link = bv_val
                        
                        imported_rows.append({
                            "关卡": stage,
                            "链接": link,
                            "作者名": entry.get("作者名", ""),
                            "人数": entry.get("人数", ""),
                            "阵容": entry.get("阵容", ""),
                            "备注": entry.get("备注", "")
                        })
                        
            elif p.suffix.lower() == ".csv":
                with p.open("r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for entry in reader:
                        stage = entry.get("关卡", "")
                    if stage:
                        # Fallback for link: if empty, try BV column
                        link = entry.get("链接", "")
                        if not link:
                            bv_val = entry.get("BV号", "")
                            if bv_val:
                                link = bv_val
                        
                        imported_rows.append({
                            "关卡": stage,
                            "链接": link,
                            "作者名": entry.get("作者名", ""),
                            "人数": entry.get("人数", ""),
                            "阵容": entry.get("阵容", ""),
                            "备注": entry.get("备注", "")
                        })

            # Merge or Replace?
            # Strategy: If current list is empty, replace. If not, merge by stage name.
            if not self.rows:
                # Infer theme
                theme = self._infer_theme(imported_rows)
                if theme:
                    self.theme_var.set(theme)
                
                self.rows = imported_rows
                # Update Tree
                self.tree.delete(*self.tree.get_children())
                for r in self.rows:
                    self.tree.insert("", tk.END, values=(
                        r.get("关卡", ""),
                        r.get("链接", ""),
                        r.get("作者名", ""),
                        r.get("人数", ""),
                        r.get("阵容", ""),
                        r.get("备注", "")
                    ))
                self.status_var.set(f"已导入 {len(imported_rows)} 行")
            else:
                # Merge
                count = 0
                mapping = {r["关卡"]: r for r in imported_rows}
                for i, r in enumerate(self.rows):
                    s = r["关卡"]
                    if s in mapping:
                        src = mapping[s]
                        if src.get("链接"): r["链接"] = src["链接"]
                        if src.get("作者名"): r["作者名"] = src["作者名"]
                        if src.get("人数"): r["人数"] = src["人数"]
                        if src.get("阵容"): r["阵容"] = src["阵容"]
                        if src.get("备注"): r["备注"] = src["备注"]
                        # Update Tree Item
                        # Treeview items are stored as children.
                        # Assuming index matches.
                        child_id = self.tree.get_children()[i]
                        self.tree.item(child_id, values=(
                            r["关卡"], r["链接"], r["作者名"], r["人数"], r["阵容"], r["备注"]
                        ))
                        count += 1
                self.status_var.set(f"已合并更新 {count} 行")
                
        except Exception as e:
            messagebox.showerror("导入失败", str(e))

    def _infer_theme(self, rows):
        stat = {}
        for r in rows:
            s = r.get("关卡", "")
            if not s: continue
            parts = s.split("-", 1)
            if parts:
                t = parts[0].upper()
                if t: stat[t] = stat.get(t, 0) + 1
        if not stat: return ""
        return max(stat.items(), key=lambda kv: kv[1])[0]

    def preview_info(self):
        # Fetch author/BV for rows with links
        # This can be slow, run in thread?
        
        self.status_var.set("正在获取视频信息...")
        self.root.update()
        
        def task():
            count = 0
            total = len(self.rows)
            for i, r in enumerate(self.rows):
                raw_url = r.get("链接", "")
                # Try normalizing even if it's just a BV code
                url = stage_excel.normalize_url(raw_url)
                
                if url and "bilibili" in url:
                    r["链接"] = url
                    
                    stage_name = r.get("关卡", "")
                    self.root.after(0, lambda s=f"正在处理 ({i+1}/{total}): {stage_name}": self.status_var.set(s))
                    
                    # Fetch author
                    if not r.get("作者名"):
                        author = stage_excel.fetch_author(url)
                        r["作者名"] = author
                    
                    # Fetch details (count and lineup) if missing
                    if not r.get("人数") or not r.get("阵容"):
                        def step_cb(msg):
                            self.root.after(0, lambda s=f"({i+1}/{total}) {stage_name}: {msg}": self.status_var.set(s))
                        
                        cnt, lineup = auto_fill_helper.fetch_video_details(url, status_callback=step_cb)
                        if cnt is not None:
                            if not r.get("人数"):
                                r["人数"] = str(cnt)
                            if not r.get("阵容"):
                                r["阵容"] = lineup

                    # Update Tree
                    self.root.after(0, lambda idx=i: self._update_row_info(idx))
                    count += 1
            
            self.root.after(0, lambda: self.status_var.set(f"链接标准化及信息补全完成，共处理 {count} 行"))

        threading.Thread(target=task, daemon=True).start()

    def _update_row_info(self, idx):
        # Update row data
        if 0 <= idx < len(self.rows):
            r = self.rows[idx]
            # Update Tree
            children = self.tree.get_children()
            if idx < len(children):
                vals = list(self.tree.item(children[idx], "values"))
                vals[1] = r.get("链接", "")
                vals[2] = r.get("作者名", "")
                vals[3] = r.get("人数", "")
                vals[4] = r.get("阵容", "")
                self.tree.item(children[idx], values=vals)

    def generate_file(self):
        if not self.rows:
            messagebox.showwarning("提示", "表格为空")
            return

        try:
            self.status_var.set("正在生成文件...")
            self.root.update()
            
            export_rows = []
            for r in self.rows:
                url = stage_excel.normalize_url(r.get("链接", ""))
                bv = stage_excel.extract_bv(url) if url else ""
                # Author is already in row data or fetched via preview
                author = r.get("作者名", "")
                
                # If author is missing but we have url, try fetch now?
                # User might not have clicked Preview.
                if url and not author:
                    author = stage_excel.fetch_author(url)
                    r["作者名"] = author # Update internal data too
                
                export_rows.append({
                    "关卡": r.get("关卡", ""),
                    "链接": url,
                    "人数": r.get("人数", ""),
                    "阵容": r.get("阵容", ""),
                    "备注": r.get("备注", ""),
                    "BV号": bv,
                    "作者名": author
                })
            
            # Filename: Theme + Time (precise to minute)
            theme = self.theme_var.get().strip() or "Unknown"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            filename = f"{theme}_{timestamp}"
            
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = str(Path(__file__).parent)
                
            output_dir = (Path(base_dir) / "excels").resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            
            xlsx_path = output_dir / f"{filename}.xlsx"
            fmt = stage_excel.write_xlsx(export_rows, xlsx_path)
            saved_path = xlsx_path
            if not fmt:
                csv_path = output_dir / f"{filename}.csv"
                stage_excel.write_csv(export_rows, csv_path)
                saved_path = csv_path
                
            self.status_var.set("生成完成")
            messagebox.showinfo("成功", f"文件已保存到:\n{str(saved_path)}")
            
        except Exception as e:
            messagebox.showerror("生成失败", str(e))
            self.status_var.set("生成失败")

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
