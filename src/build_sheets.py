# -*- coding: utf-8 -*-
"""
📄 한 장 공략 저장용 그림 → data/sheets/ID.png (A4 세로 794×1123 CSS px × 3배 = 2382×3369)
  앱 화면(index.html?sheet=ID)을 헤드리스 크롬으로 찍음 → 앱에서 보는 것과 저장 그림이 같음
  검증: 그림 크기, 내용이 A4 한 장(1123px)을 넘지 않는지 (넘으면 아래가 잘리므로 오류)
사용: python build_sheets.py [ID ...]   (ID 없으면 전부)
"""
import functools, http.server, os, re, subprocess, sys, tempfile, threading
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from build import ROOT, write_index

CHROME = next((p for p in (r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                           r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe') if os.path.exists(p)), None)
W, H, SCALE = 794, 1123, 3
OUT = os.path.join(ROOT, 'data', 'sheets')

def sheet_ids():
    s = open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()
    block = s[s.index('const GSHEETS = ['):]; block = block[:block.index('];')]
    return re.findall(r"\{ id: '(\w+)'", block)

def chrome(*args):
    with tempfile.TemporaryDirectory() as prof:
        return subprocess.run([CHROME, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
                               f'--user-data-dir={prof}', '--virtual-time-budget=8000', *args],
                              capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)

def main(ids):
    if not CHROME: print('ERR 크롬·엣지를 찾지 못함'); return 1
    allids = sheet_ids(); ids = ids or allids
    bad = [i for i in ids if i not in allids]
    if bad: print('ERR 없는 ID:', bad); return 1
    os.makedirs(OUT, exist_ok=True)
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    handler = functools.partial(Quiet, directory=ROOT)
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler); port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    errors = []
    try:
        for i in ids:
            url = f'http://127.0.0.1:{port}/index.html?sheet={i}'
            # 1) 내용 높이 확인: 페이지가 끝나면 제목을 READY로 바꾸므로 DOM을 받아 .gspage 높이를 읽음
            dom = chrome('--dump-dom', f'--window-size={W},{H}', url).stdout
            m = re.search(r'<title>READY (\d+)</title>', dom)
            if not m: errors.append(f'{i}: 화면이 다 그려지지 않음'); continue
            if int(m.group(1)) > H: errors.append(f'{i}: 내용 높이 {m.group(1)}px > A4 {H}px (아래가 잘림)'); continue
            # 2) 그림 찍기
            png = os.path.join(OUT, f'{i}.png')
            if os.path.exists(png): os.remove(png)
            chrome(f'--screenshot={png}', f'--window-size={W},{H}', f'--force-device-scale-factor={SCALE}', url)
            if not os.path.exists(png): errors.append(f'{i}: 그림을 만들지 못함'); continue
            with open(png, 'rb') as f: head = f.read(24)
            pw, ph = int.from_bytes(head[16:20], 'big'), int.from_bytes(head[20:24], 'big')
            ok = (pw, ph) == (W * SCALE, H * SCALE)
            print(f'{i}.png {pw}×{ph} {os.path.getsize(png) / 1e6:.2f}MB' + ('' if ok else '  ← 크기 다름'))
            if not ok: errors.append(f'{i}: 그림 크기 {pw}×{ph}')
    finally:
        srv.shutdown()
    if errors: print('\n'.join('ERR ' + e for e in errors)); return 1
    write_index()
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
