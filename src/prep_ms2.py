# -*- coding: utf-8 -*-
"""
중학·고등 코스 2단계(학습용 완성 카드) 작성용 참고 파일 만들기
  입력: src/content_g{G}_p*.json (1단계 카드), 원천데이터/ref/ref_g{G}.txt (prep_ms.py 결과),
        data/parts.js (부품 — KanjiVG), 원천데이터 jouyou.json
  출력: 원천데이터/ref/ref_g{G}_qN.txt — 한 줄 = 한 글자, 탭 3칸
        ① 1단계 카드 JSON ② 상용한자표·사전 정보(ref_g{G}.txt 한 줄) ③ 소리 가족 힌트
사용: python prep_ms2.py 7 4     (중1을 4묶음으로)
"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from build import REF_DIR, ROOT, parse_readings, kata2hira
sys.stdout.reconfigure(encoding='utf-8')

def main(g, n):
    items = []
    for f in sorted(os.listdir(HERE)):
        if re.match(rf'^content_g{g}_p\d+\.json$', f):
            items += json.load(open(os.path.join(HERE, f), encoding='utf-8'))['items']
    J = json.load(open(os.path.join(REF_DIR, 'jouyou.json'), encoding='utf-8'))
    ref = {}
    for line in open(os.path.join(REF_DIR, 'ref', f'ref_g{g}.txt'), encoding='utf-8'):
        if line.startswith('#') or ' | ' not in line: continue
        ref[line.split(' | ')[0]] = line.rstrip('\n')
    s = open(os.path.join(ROOT, 'data', 'parts.js'), encoding='utf-8').read()
    P = json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))
    ons = lambda c: {kata2hira(r['stem']) for r in parse_readings(J[c]['rd']) if r['on'] and not r['rare']} if c in J else set()
    elem = [c for c, v in J.items() if v['g'] in '123456' and len(v['g']) == 1]
    parts_of = lambda c: {p[0] for p in P.get(c, [])}
    lines = []
    for it in items:
        k = it['k']; my_on = ons(k); hints = []
        for part in sorted(parts_of(k)):
            fam = [c for c in elem if c != k and (part in parts_of(c) or c == part) and ons(c) & my_on]
            if part in J and ons(part) & my_on and part not in fam: fam.insert(0, part)
            if fam:
                hints.append(f'{part}: ' + ' '.join(f'{c}({"·".join(sorted(ons(c) & my_on))})' for c in fam[:8]))
        lines.append(json.dumps(it, ensure_ascii=False) + '\t' + ref.get(k, k) + '\t' + ('소리 가족 후보 — ' + ' / '.join(hints) if hints else '소리 가족 후보 없음'))
    size = -(-len(lines) // n)
    for i in range(n):
        part = lines[i * size:(i + 1) * size]
        open(os.path.join(REF_DIR, 'ref', f'ref_g{g}_q{i + 1}.txt'), 'w', encoding='utf-8').write('\n'.join(part) + '\n')
        print(f'ref_g{g}_q{i + 1}.txt {len(part)}자: {"".join(json.loads(l.split(chr(9))[0])["k"] for l in part)}')

if __name__ == '__main__':
    main(int(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 4)
