import re
import sys
import csv
import argparse
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import json
from urllib.parse import quote
import html as htmlmod
import os

DEFAULT_BLOCK_WORDS = ["精一", "无核", "一级", "无精英", "精1", "1级", "无六星"]


def generate_stages(theme: str, normal_count: int = 8, ex_count: int = 8, s_count: int = 0):
    stages = []
    for i in range(1, normal_count + 1):
        stages.append(f"{theme}-{i}")
    for i in range(1, ex_count + 1):
        base = f"{theme}-EX-{i}"
        stages.append(base)
        stages.append(f"{base}突袭")
    for i in range(1, (s_count or 0) + 1):
        base = f"{theme}-S-{i}"
        stages.append(base)
        stages.append(f"{base}突袭")
    return stages


def extract_bv(url: str):
    m = re.search(r"BV[0-9A-Za-z]+", url)
    return m.group(0) if m else ""

def normalize_url(url: str):
    s = (url or "").strip()
    if not s:
        return ""
    # Try matching pure BV code (case insensitive)
    m = re.fullmatch(r"(?i)BV[0-9A-Za-z]+", s)
    if m:
        # Always use uppercase BV for standard URL
        bv = m.group(0)
        if bv.lower().startswith("bv"):
            bv = "BV" + bv[2:]
        return f"https://www.bilibili.com/video/{bv}"
    return s


def _candidate_cookie_dirs():
    dirs = []
    try:
        dirs.append(Path(__file__).resolve().parent)
    except Exception:
        pass

    if getattr(sys, "frozen", False):
        try:
            exe_dir = Path(sys.executable).resolve().parent
            dirs.append(exe_dir)
            dirs.append(exe_dir / "_internal")
        except Exception:
            pass

    unique_dirs = []
    seen = set()
    for d in dirs:
        try:
            key = str(d.resolve())
        except Exception:
            key = str(d)
        if key not in seen:
            seen.add(key)
            unique_dirs.append(d)
    return unique_dirs


def get_bili_cookie():
    ck = (os.getenv("BILI_COOKIE") or "").strip()
    if ck:
        return ck

    for base in _candidate_cookie_dirs():
        for name in ("local_cookie.txt", "cookie.txt"):
            try:
                p = (base / name).resolve()
                if p.exists():
                    t = p.read_text(encoding="utf-8", errors="ignore").strip()
                    if t:
                        return t
            except Exception:
                continue
    return ""


def has_bili_cookie():
    return bool(get_bili_cookie())


def _read_url(url: str, timeout: int = 30, cookie: str = ""):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.bilibili.com/",
            "Origin": "https://www.bilibili.com",
        }
        ck = (cookie or "").strip() or (_get_cookie() or "")
        if ck:
            headers["Cookie"] = ck
        req = Request(url, headers=headers)
        with urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="ignore")
    except (HTTPError, URLError):
        return ""

def _parse_json_maybe_jsonp(s: str):
    if not s:
        return {}
    t = s.strip()
    if t.startswith("{") or t.startswith("["):
        try:
            return json.loads(t)
        except Exception:
            return {}
    m = re.search(r'\(\s*({[\s\S]*})\s*\)$', t)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            return {}
    return {}

def _get_cookie():
    return get_bili_cookie()


def extract_author_from_html(html: str):
    if not html:
        return ""
    m = re.search(r'<meta\s+name=["\']author["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r'"owner"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', html)
    if m:
        return m.group(1).strip()
    m = re.search(r'"upData"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', html)
    if m:
        return m.group(1).strip()
    m = re.search(r'"uploader"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', html)
    if m:
        return m.group(1).strip()
    m = re.search(r'<a[^>]*rel=["\']author["\'][^>]*>([^<]+)</a>', html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


def fetch_author(url: str, cookie: str = ""):
    bv = extract_bv(url)
    html = _read_url(url, cookie=cookie)
    author = extract_author_from_html(html)
    if author:
        return author
    if not bv:
        return ""
    api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bv}"
    data = _read_url(api_url, cookie=cookie)
    try:
        j = json.loads(data)
        owner = j.get("data", {}).get("owner", {})
        name = owner.get("name", "")
        if isinstance(name, str):
            return name.strip()
        return ""
    except Exception:
        return ""

def strip_html(s: str):
    t = re.sub(r"<[^>]+>", "", s or "")
    try:
        t = htmlmod.unescape(t)
    except Exception:
        pass
    return t.strip()

def _is_blocked(title: str, block_words):
    t = (title or "").strip()
    if not t:
        return False
    for w in block_words or []:
        if (w or "") and (w in t):
            return True
    return False

def _has_required(title: str, must_words):
    t = (title or "").strip()
    if not must_words:
        return True
    for w in must_words or []:
        if (w or "") and (w in t):
            return True
    return False

def search_bilibili_videos(keyword: str, limit: int = 1, cookie: str = "", block_words=None, must_words=None):
    res = []
    kw = quote((keyword or "").strip())
    if not kw:
        return res
    url1 = f"https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword={kw}&page=1"
    data1 = _read_url(url1, cookie=cookie)
    try:
        j1 = json.loads(data1)
        items = j1.get("data", {}).get("result", []) or []
        for it in items:
            title = strip_html(it.get("title", "") or "")
            bvid = it.get("bvid") or ""
            author = (it.get("author") or "").strip()
            arcurl = (it.get("arcurl") or "").strip()
            url = normalize_url(bvid) if bvid else (arcurl or "")
            if title and url and not _is_blocked(title, block_words or DEFAULT_BLOCK_WORDS) and _has_required(title, must_words):
                res.append({"title": title, "url": url, "bvid": bvid, "author": author})
                if len(res) >= max(1, limit):
                    break
    except Exception:
        pass
    if not res:
        url2 = f"https://api.bilibili.com/x/web-interface/search/all/v2?keyword={kw}"
        data2 = _read_url(url2, cookie=cookie)
        try:
            j2 = json.loads(data2)
            modules = j2.get("data", {}).get("result", []) or []
            for m in modules:
                if m.get("result_type") == "video":
                    for it in m.get("data", []) or []:
                        title = strip_html(it.get("title", "") or "")
                        bvid = it.get("bvid") or ""
                        author = (it.get("author") or "").strip()
                        url = normalize_url(bvid) if bvid else (it.get("url") or "")
                        if title and url and not _is_blocked(title, block_words or DEFAULT_BLOCK_WORDS) and _has_required(title, must_words):
                            res.append({"title": title, "url": url, "bvid": bvid, "author": author})
                            if len(res) >= max(1, limit):
                                break
                if len(res) >= max(1, limit):
                    break
        except Exception:
            pass
    if not res:
        url_s = f"https://s.search.bilibili.com/cate/search?search_type=video&keyword={kw}&page=1&pagesize={max(1,limit)}"
        data_s = _read_url(url_s, cookie=cookie)
        try:
            js = _parse_json_maybe_jsonp(data_s)
            items = js.get("result", []) or []
            for it in items:
                title = strip_html(it.get("title", "") or "")
                arcurl = (it.get("arcurl") or "").strip()
                bvid = it.get("bvid") or ""
                url = normalize_url(bvid) if bvid else (arcurl or "")
                author = (it.get("author") or "").strip()
                if title and url and not _is_blocked(title, block_words or DEFAULT_BLOCK_WORDS) and _has_required(title, must_words):
                    res.append({"title": title, "url": url, "bvid": bvid, "author": author})
                    if len(res) >= max(1, limit):
                        break
        except Exception:
            pass
    if not res:
        url3 = f"https://search.bilibili.com/all?keyword={kw}"
        html = _read_url(url3, cookie=cookie)
        if html:
            for m in re.finditer(r'<a[^>]+href=["\'](?:https?:)?//www\.bilibili\.com/video/(BV[0-9A-Za-z]+)["\'][^>]*title=["\']([^"\']+)["\']', html):
                bvid = m.group(1)
                title = strip_html(m.group(2))
                if bvid and title and not _is_blocked(title, block_words or DEFAULT_BLOCK_WORDS) and _has_required(title, must_words):
                    res.append({"title": title, "url": f"https://www.bilibili.com/video/{bvid}", "bvid": bvid, "author": ""})
                    if len(res) >= max(1, limit):
                        break
            if len(res) < max(1, limit):
                for m in re.finditer(r'https?://www\.bilibili\.com/video/(BV[0-9A-Za-z]+)', html):
                    bvid = m.group(1)
                    if bvid:
                        res.append({"title": f"视频 {bvid}", "url": f"https://www.bilibili.com/video/{bvid}", "bvid": bvid, "author": ""})
                        if len(res) >= max(1, limit):
                            break
            if len(res) < max(1, limit):
                for m in re.finditer(r'"bvid"\s*:\s*"?(BV[0-9A-Za-z]+)"?\s*,\s*"title"\s*:\s*"([^"]+)"', html):
                    bvid = m.group(1)
                    title = strip_html(m.group(2))
                    if bvid and title and not _is_blocked(title, block_words or DEFAULT_BLOCK_WORDS) and _has_required(title, must_words):
                        res.append({"title": title, "url": f"https://www.bilibili.com/video/{bvid}", "bvid": bvid, "author": ""})
                        if len(res) >= max(1, limit):
                            break
    return res

def search_bilibili_videos_multi(keywords, limit: int = 5, cookie: str = "", block_words=None, must_words=None):
    seen = set()
    merged = []
    for kw in keywords or []:
        for it in search_bilibili_videos(kw, limit=limit, cookie=cookie, block_words=block_words or DEFAULT_BLOCK_WORDS, must_words=must_words):
            key = it.get("bvid") or it.get("url")
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(it)
            if len(merged) >= max(1, limit):
                break
        if len(merged) >= max(1, limit):
            break
    return merged

def generate_base_stages(theme: str, normal_count: int = 8, ex_count: int = 8, s_count: int = 0):
    stages = []
    for i in range(1, normal_count + 1):
        stages.append(f"{theme}-{i}")
    for i in range(1, ex_count + 1):
        stages.append(f"{theme}-EX-{i}")
    for i in range(1, (s_count or 0) + 1):
        stages.append(f"{theme}-S-{i}")
    return stages


def write_xlsx(rows, output_path: Path):
    try:
        import openpyxl
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "四星队表格"
        ws.append(["关卡", "人数", "阵容", "BV号", "作者名", "备注"])
        for r in rows:
            ws.append([r.get("关卡", ""), r.get("人数", ""), r.get("阵容", ""), r.get("BV号", ""), r.get("作者名", ""), r.get("备注", "")])
        wb.save(output_path)
        return "xlsx"
    except Exception:
        return ""


def write_csv(rows, output_path: Path):
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["关卡", "人数", "阵容", "BV号", "作者名", "备注"])
        for r in rows:
            w.writerow([r.get("关卡", ""), r.get("人数", ""), r.get("阵容", ""), r.get("BV号", ""), r.get("作者名", ""), r.get("备注", "")])
    return "csv"


def interactive_collect(theme: str, normal_count: int, ex_count: int):
    stages = generate_stages(theme, normal_count, ex_count)
    rows = []
    print(f"已生成关卡：{', '.join(stages)}")
    for s in stages:
        print(f"\n填写关卡：{s}")
        url = input("请输入该关卡对应的网址(可留空跳过)：").strip()
        bv = extract_bv(url) if url else ""
        author = fetch_author(url) if url else ""
        if url and not author:
            manual = input("未自动识别作者名，请手动输入作者名(可留空)：").strip()
            author = manual
        people = input("人数(可留空)：").strip()
        lineup = input("阵容(可留空)：").strip()
        note = input("备注(可留空)：").strip()
        rows.append({"关卡": s, "人数": people, "阵容": lineup, "BV号": bv, "作者名": author, "备注": note})
    return rows


def load_mapping_csv(path: Path):
    data = {}
    if not path.exists():
        return data
    with path.open("r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row.get("关卡") or "").strip()
            if key:
                data[key] = {
                    "url": (row.get("链接") or "").strip(),
                    "人数": (row.get("人数") or "").strip(),
                    "阵容": (row.get("阵容") or "").strip(),
                    "备注": (row.get("备注") or "").strip(),
                }
    return data


def build_rows_from_mapping(theme: str, normal_count: int, ex_count: int, mapping: dict, s_count: int = 0):
    stages = generate_stages(theme, normal_count, ex_count, s_count)
    rows = []
    for s in stages:
        entry = mapping.get(s, {})
        url = normalize_url(entry.get("url", ""))
        bv = extract_bv(url) if url else ""
        author = fetch_author(url) if url else ""
        rows.append({
            "关卡": s,
            "人数": entry.get("人数", ""),
            "阵容": entry.get("阵容", ""),
            "BV号": bv,
            "作者名": author,
            "备注": entry.get("备注", ""),
        })
    return rows


def parse_args(argv):
    p = argparse.ArgumentParser(prog="stage_excel", description="生成四星队Excel表格")
    p.add_argument("--theme", "-t", type=str, help="关卡主题，如 UR")
    p.add_argument("--normal-count", type=int, default=8, help="普通关卡数量，默认8")
    p.add_argument("--ex-count", type=int, default=8, help="EX关卡数量，默认8")
    default_dir = (Path(__file__).parent / "excels").resolve()
    default_dir.mkdir(parents=True, exist_ok=True)
    p.add_argument("--output", "-o", type=str, default=str(default_dir / "四星队表格.xlsx"), help="输出文件路径")
    p.add_argument("--from-csv", type=str, help="从映射CSV生成，列：关卡,链接,人数,阵容,备注")
    p.add_argument("--non-interactive", action="store_true", help="非交互模式，需提供--theme和--from-csv")
    return p.parse_args(argv)


def main():
    args = parse_args(sys.argv[1:])
    output_path = Path(args.output).resolve()
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    if args.non_interactive:
        if not args.theme or not args.from_csv:
            print("非交互模式需要 --theme 与 --from-csv")
            sys.exit(2)
        mapping = load_mapping_csv(Path(args.from_csv).resolve())
        rows = build_rows_from_mapping(args.theme.strip(), args.normal_count, args.ex_count, mapping)
    else:
        theme = args.theme.strip() if args.theme else input("请输入关卡主题(如 UR)：").strip()
        rows = interactive_collect(theme, args.normal_count, args.ex_count)
    fmt = write_xlsx(rows, output_path)
    if not fmt:
        csv_path = output_path.with_suffix(".csv") if output_path.suffix.lower() != ".csv" else output_path
        fmt = write_csv(rows, csv_path)
        print(f"已生成 {csv_path}")
    else:
        print(f"已生成 {output_path}")


if __name__ == "__main__":
    main()
