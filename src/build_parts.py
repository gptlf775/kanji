# -*- coding: utf-8 -*-
"""
🧩 부품 찾기 자료 빌드 → data/parts.js
  KanjiVG 의 부품 묶음(<g kvg:element="隹">)에서 '글자마다 어떤 부품이 몇 번째 획인지'만 뽑음
  형식: {"集":[["隹",0,1,2,3,4,5,6,7],["木",8,9,10,11]], ...}  (획 번호는 0부터, it.st 순서와 같음)
  획 모양은 앱의 it.st 를 그대로 쓰므로 여기에는 번호만 넣음
  1획 부품은 뺌 (너무 흔해서 찾기에 쓸모없음)
검증: 1026자 전부 처리 · 획 번호가 획 수 안에 있음 · it.st 와 획 경로 일치 · 隹 포함 글자가 교재 자료의 12자와 같음
사용: python build_parts.py
"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from build import REF_DIR, ROOT, kvg_paths, write_index

TAG = re.compile(r'<g\b([^>]*)>|</g>|<path\b[^>]*id="kvg:[0-9a-f]+-s(\d+)"[^>]*/?>')

def parts_of(ch):
    s = open(os.path.join(REF_DIR, 'kvg', f'{ord(ch):05x}.svg'), encoding='utf-8').read()
    s = s[s.index('<g id="kvg:'):]
    stack, parts = [], {}
    for m in TAG.finditer(s):
        t = m.group(0)
        if t.startswith('</g'): stack.pop(); continue
        if t.startswith('<g'):
            e = re.search(r'kvg:element="([^"]+)"', m.group(1))
            stack.append(e.group(1) if e else None); continue
        n = int(m.group(2)) - 1
        for depth, e in enumerate(stack):                 # 맨 바깥 묶음 = 글자 자신 → 뺌. 나뉜 조각(kvg:part)은 같은 이름으로 합쳐짐
            if depth and e and e != ch: parts.setdefault(e, []).append(n)
    return [[e] + sorted(set(v)) for e, v in parts.items() if len(set(v)) >= 2]

def main():
    errors, out, items = [], {}, []
    for g in range(1, 11):                     # 초등 1~6 + 중학·고등 7~10 (있는 파일만)
        fn = os.path.join(ROOT, 'data', f'g{g}.js')
        if not os.path.exists(fn): continue
        s = open(fn, encoding='utf-8').read()
        m = re.search(r'=\s*(\{.*\})\s*;?\s*$', s, re.S)
        items += json.loads(m.group(1))['items']
    for it in items:
        k = it['k']
        ps = parts_of(k)
        for p in ps:
            if any(i >= len(it['st']) for i in p[1:]): errors.append(f'{k}: {p[0]} 획 번호가 획 수({len(it["st"])})를 넘음')
        if kvg_paths(k) != it['st']: errors.append(f'{k}: 앱의 획 자료와 KanjiVG 순서가 다름')
        if ps: out[k] = ps
    fam = {}
    for k, ps in out.items():
        for p in ps: fam.setdefault(p[0], []).append(k)
    chu = set(fam.get('隹', []))
    if not set('集進雑難権確観曜推準護奮') <= chu: errors.append('隹 포함 글자에 초등 12자가 빠짐: ' + ''.join(sorted(chu)))
    if len(items) not in (1026, 2136): errors.append(f'글자 수 {len(items)} (1026 또는 2136이어야 함)')
    if errors:
        print('\n'.join('ERR ' + e for e in errors[:30])); return 1
    js = 'window.KPARTS=' + json.dumps(out, ensure_ascii=False, separators=(',', ':')) + ';\n'
    fn = os.path.join(ROOT, 'data', 'parts.js')
    open(fn, 'w', encoding='utf-8', newline='').write(js)
    write_index()
    inst = sum(len(v) for v in out.values())
    rep = f'글자 {len(out)}/{len(items)} · 부품 {len(fam)}종 · 사례 {inst}개 · {os.path.getsize(fn) / 1024:.0f}KB · 오류 0건'
    sys.stdout.reconfigure(encoding='utf-8')
    print(rep)
    print('많은 부품', ' '.join(f'{e}{len(v)}' for e, v in sorted(fam.items(), key=lambda x: -len(x[1]))[:40]))
    return 0

if __name__ == '__main__':
    sys.exit(main())
