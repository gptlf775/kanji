# -*- coding: utf-8 -*-
"""
단어장 강세(고저 악센트) → data/accent.js (window.ACC = {"표기|읽기": "1" 또는 "0,2"})
  자료: Kanjium accents.txt (Uros O., CC BY-SA 4.0) — 원천데이터/kanjium/accents.txt
        형식: 표기 \t 읽기 \t 악센트. 번호 = 높은 소리가 끝나는 박 위치 (0 = 평판: 떨어지지 않음)
        품사마다 다르면 "(名;形動)0,(副)1" 처럼 적혀 있음 → 단어장 품사(명사·な형용사·부사·동사…)에 맞는 것을 고름
  찾는 순서: (표기, 읽기) 그대로 → ○○する 는 ○○의 악센트 → 가나로 쓰는 말(する=為る 등)은 JMdict에서 그 읽기의
            가장 흔한 한자 표기 → 같은 읽기의 악센트가 한 가지뿐일 때
사용: python build_accent.py
"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from build import REF_DIR, ROOT, kata2hira, write_index
sys.stdout.reconfigure(encoding='utf-8')
# 자료에서 하나로 정해지지 않는 아주 흔한 말 — 표준 악센트(NHK 사전 등과 같은 값)가 분명한 것만 직접 지정
MANUAL = {'する|する': '0', 'そして|そして': '0', 'それから|それから': '0', 'それで|それで': '0', 'それに|それに': '0', 'アメリカ|アメリカ': '0', 'お酒|おさけ': '0'}
CAT_TAG = {'n': '名', 'na': '形動', 'adv': '副', 'v': '動', 'i': '形', 'etc': ''}

def pick(a, cat):
    """'(名;形動)0,(副)1' → 품사에 맞는 번호들. 표시가 없으면 그대로"""
    if '(' not in a: return a
    segs = re.findall(r'\(([^)]*)\)([0-9,]+)', a)
    tag = CAT_TAG.get(cat, '')
    for tags, nums in segs:
        if tag and tag in tags.split(';'): return nums.strip(',')
    return segs[0][1].strip(',') if segs else None

def uk_pairs():
    """JMdict 에서 '보통 가나로 씀'(uk) 표시가 있는 (한자 표기, 읽기) — する=為る·いる=居る·この=此の 처럼 가나로만 쓰는 말의 한자 표기"""
    import gzip, xml.etree.ElementTree as ET
    out = set()
    with gzip.open(os.path.join(REF_DIR, 'JMdict_e.gz'), 'rb') as f:
        for ev, el in ET.iterparse(f, events=('end',)):
            if el.tag != 'entry': continue
            if any('usually written using kana' in (m.text or '') for m in el.iter('misc')):
                kebs = [k.text for k in el.iter('keb')]
                for r in el.iter('r_ele'):
                    reb = r.find('reb').text
                    restr = [x.text for x in r.findall('re_restr')]
                    for k in (restr or kebs): out.add((k, reb))
            el.clear()
    return out

def main():
    UK = uk_pairs()
    A, byy = {}, {}
    for line in open(os.path.join(REF_DIR, 'kanjium', 'accents.txt'), encoding='utf-8'):
        p = line.rstrip('\n').split('\t')
        if len(p) < 3 or not re.search(r'[0-9]', p[2]): continue
        w, y = p[0], kata2hira(p[1] or p[0])
        A.setdefault((w, y), p[2]); byy.setdefault(y, []).append((w, p[2]))
    s = open(os.path.join(ROOT, 'data', 'vocab.js'), encoding='utf-8').read()
    V = json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))['words']
    out, miss, how = {}, [], {'그대로': 0, 'する': 0, '흔한 한자 표기': 0, '같은 읽기 하나': 0}
    for x in V:
        w, y, cat = x[0], kata2hira(x[1]), x[2]
        a = A.get((w, y)); h = '그대로'
        if not a and w.endswith('する') and len(w) > 2: a = A.get((w[:-2], y[:-2])); h = 'する'
        if not a and re.fullmatch(r'[ぁ-ゖァ-ヺー]+', w):
            a = A.get((y, y)) or A.get((x[1], y))
            if not a:   # 가나로 쓰는 말 → 같은 읽기의 한자 표기 중 JMdict '보통 가나로 씀'인 것. 악센트가 하나로 정해질 때만 (틀린 표시보다 표시 안 함)
                cand = {pick(ka, cat) for kw, ka in byy.get(y, []) if (kw, y) in UK}
                cand.discard(None)
                if len(cand) == 1: a = cand.pop(); h = '흔한 한자 표기'
            if not a and len({pick(ka, cat) for _, ka in byy.get(y, [])}) == 1: a = byy[y][0][1]; h = '같은 읽기 하나'
        a = pick(a, cat) if a else None
        if not a and f'{x[0]}|{x[1]}' in MANUAL: a = MANUAL[f'{x[0]}|{x[1]}']; h = '그대로'
        if a: out[f'{x[0]}|{x[1]}'] = a; how[h] += 1
        else: miss.append(x[0])
    js = 'window.ACC=' + json.dumps(out, ensure_ascii=False, separators=(',', ':')) + ';\n'
    open(os.path.join(ROOT, 'data', 'accent.js'), 'w', encoding='utf-8').write(js)
    write_index()
    print(f'강세: 단어장 {len(V)}개 중 {len(out)}개 ({len(out) / len(V) * 100:.1f}%) · 없음 {len(miss)}개 · {len(js.encode())} bytes · {how}')
    print('없음:', ' '.join(miss))

if __name__ == '__main__':
    sys.exit(main())
