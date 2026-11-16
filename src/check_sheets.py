# -*- coding: utf-8 -*-
"""
📄 한 장 공략 읽기 검사: 시트 안의 꾹 누르기 자료(data-y = 읽기)를 형태소 분석기 읽기와 대조
  앱 화면(index.html?sheet=ID&dump=1)을 헤드리스 크롬으로 열어 [표기, 읽기] 목록을 받은 뒤,
  한자가 든 표기마다 분석기 읽기와 작성 읽기가 다르면 '확인 필요'로 출력 (분석기도 틀릴 수 있어 사람이 판단)
  읽기에 한자가 섞였거나 비어 있으면 오류
사용: python check_sheets.py [ID ...]
"""
import functools, http.server, json, re, sys, threading
from html import unescape
sys.stdout.reconfigure(encoding='utf-8')
from build import ROOT, _tagger, analyzer_reading, kata2hira
from build_sheets import chrome, sheet_ids, W, H

HAN = re.compile(r'[一-鿿々]')
norm = lambda s: re.sub(r'[\s・·、。？?！!～~＋+\-=（）()「」]', '', kata2hira(s))

def pairs(dom):
    """data-y 가 붙은 요소의 [보이는 글자, 읽기] — 덤프된 DOM에서 간단히 뽑음"""
    out = []
    for m in re.finditer(r'<(span|td|th)\b([^>]*?)\sdata-y="([^"]*)"[^>]*>(.*?)</\1>', dom, re.S):
        inner = re.sub(r'<small>.*?</small>', '', m.group(4), flags=re.S)       # 작은 글씨(읽기·설명)는 표기에서 뺌
        inner = re.sub(r'<span class="gsr">.*?</span>', '', inner, flags=re.S) if 'gsr' in inner and HAN.search(inner) else inner
        txt = unescape(re.sub(r'<[^>]+>', '', inner)).strip()
        out.append((txt, unescape(m.group(3))))
    return out

def main(ids):
    tagger = _tagger()
    if not tagger: print('ERR 형태소 분석기(fugashi)를 불러오지 못함'); return 1
    ids = ids or sheet_ids()
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=ROOT)); port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    errs, warns, n = [], [], 0
    try:
        for i in ids:
            dom = chrome('--dump-dom', f'--window-size={W},{H}', f'http://127.0.0.1:{port}/index.html?sheet={i}').stdout
            if 'READY' not in dom: errs.append(f'{i}: 화면이 다 그려지지 않음'); continue
            for txt, y in pairs(dom):
                n += 1
                if not y.strip(): errs.append(f'{i}: 읽기 없음 — {txt}'); continue
                if HAN.search(y): errs.append(f'{i}: 읽기에 한자 — {txt} / {y}'); continue
                if not HAN.search(txt): continue
                a = analyzer_reading(tagger, re.sub(r'[\s・·]', '', txt))
                if norm(a) != norm(y): warns.append(f'{i}: {txt} — 작성 {y} / 분석기 {a}')
    finally:
        srv.shutdown()
    print(f'낱말 {n}개 검사 · 오류 {len(errs)} · 확인 필요 {len(warns)}')
    for e in errs: print('ERR', e)
    for w in warns: print('CHK', w)
    return 1 if errs else 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
