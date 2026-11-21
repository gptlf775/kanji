# -*- coding: utf-8 -*-
"""
중학·고등 코스(1단계: 찾아보기용 기본 카드) 원천 자료 준비
  대상: 상용한자 2,136자 중 초등 1,026자를 뺀 1,110자
  코스 배정 = 한자검정(漢検) 급수 (공식 급별 한자표에서 추출, 누적 글자 수 1,339/1,623/1,951/2,136과 일치 확인)
    7 = 중1 (4급 313자) · 8 = 중2 (3급 284자) · 9 = 중3 (준2급 328자) · 10 = 고등 (2급 185자)
하는 일
  ① jouyou.json 에 빠진 '猶' 보충 (KANJIDIC2 획수·부수, 상용한자표 음훈 ユウ)
  ② KanjiVG 획순 내려받기 (원천데이터/kvg/) + 획 수 = 상용한자표 획수 검사
  ③ JMdict 흔한 말 + JmdictFurigana 로 한자별 단어 후보·핵심 읽기 (원천데이터/freq/freq_ms.json)
  ④ 한국 훈음 후보: libhangul 한자 사전(BSD) — 신자체에 뜻이 없으면 KANJIDIC2 이체자(정자)의 뜻으로
  ⑤ 작성용 참고 파일 원천데이터/ref/ref_g7~10.txt
사용: python prep_ms.py
"""
import concurrent.futures, json, os, re, sys, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from build import REF_DIR, ROOT, parse_readings, kata2hira, variants
sys.stdout.reconfigure(encoding='utf-8')

COURSE = {'4級': 7, '3級': 8, '準2級': 9, '2級': 10}
CNAME = {7: '중1', 8: '중2', 9: '중3', 10: '고등'}
KVG_URL = 'https://raw.githubusercontent.com/KanjiVG/kanjivg/master/kanji/{:05x}.svg'

def kanjidic():
    """KANJIDIC2 → {글자: dict(sc, rad_no, ko, en, freq, var=[이체자])}"""
    x = open(os.path.join(REF_DIR, 'kanjidic2.xml'), encoding='utf-8').read()
    out = {}
    for m in re.finditer(r'<character>\s*<literal>([^<]+)</literal>(.*?)</character>', x, re.S):
        c, b = m.group(1), m.group(2)
        var = []
        for t, v in re.findall(r'<variant var_type="(jis208|jis212|jis213)">([^<]+)</variant>', b):
            try:
                p = [int(n) for n in v.split('-')]
                ku, ten = p[-2], p[-1]
                raw = (b'\x8f' if t == 'jis212' else b'') + bytes([ku + 0xA0, ten + 0xA0])
                var.append(raw.decode('euc_jp'))
            except Exception:
                pass
        sc = re.search(r'<stroke_count>(\d+)</stroke_count>', b)
        out[c] = dict(sc=int(sc.group(1)) if sc else 0,
                      ko=re.findall(r'<reading r_type="korean_h">([^<]+)</reading>', b),
                      en=re.findall(r'<meaning>([^<]+)</meaning>', b),
                      freq=int(re.search(r'<freq>(\d+)</freq>', b).group(1)) if '<freq>' in b else 9999,
                      var=var)
    return out

def hangul_dict():
    """libhangul hanja.txt → {한자: [(음, 뜻 문자열)]}"""
    d = {}
    for line in open(os.path.join(REF_DIR, 'ref', 'libhangul_hanja.txt'), encoding='utf-8'):
        if line.startswith('#') or line.count(':') < 2:
            continue
        snd, ch, mean = line.rstrip('\n').split(':', 2)
        if len(ch) == 1:
            d.setdefault(ch, []).append((snd, mean))
    return d

def main():
    jpath = os.path.join(REF_DIR, 'jouyou.json')
    J = json.load(open(jpath, encoding='utf-8'))
    KD = kanjidic()
    # ① 猶 보충 (상용한자표: 猶 ユウ, 12획, 부수 犬)
    if '猶' not in J:
        J['猶'] = dict(rad='犬', sc=KD['猶']['sc'], g='S', rd='ユウ')
        json.dump(J, open(jpath, 'w', encoding='utf-8'), ensure_ascii=False)
        print('jouyou.json 에 猶 보충')
    S = [k for k, v in J.items() if v['g'] == 'S']
    lv = json.load(open(os.path.join(HERE, 'kanken_ms.json'), encoding='utf-8'))['levels']
    assert len(S) == 1110 and set(S) == set(lv), f'글자 목록 불일치 {len(S)} / {len(lv)}'
    # ② KanjiVG
    kdir = os.path.join(REF_DIR, 'kvg')
    def fetch(c):
        fn = os.path.join(kdir, f'{ord(c):05x}.svg')
        if os.path.exists(fn):
            return c, 'have'
        try:
            data = urllib.request.urlopen(KVG_URL.format(ord(c)), timeout=30).read()
            open(fn, 'wb').write(data); return c, 'ok'
        except Exception as e:
            return c, f'ERR {e}'
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        res = list(ex.map(fetch, S))
    bad = [r for r in res if r[1].startswith('ERR')]
    print('KanjiVG', sum(1 for r in res if r[1] == 'ok'), '받음 ·', sum(1 for r in res if r[1] == 'have'), '이미 있음 · 실패', bad)
    from build import kvg_paths
    mism = []
    for c in S:
        try:
            n = len(kvg_paths(c))
            if n != J[c]['sc']: mism.append(f'{c}({n}/{J[c]["sc"]})')
        except Exception as e:
            mism.append(f'{c}(없음)')
    print('획 수 불일치', len(mism), ' '.join(mism))
    # ③ 단어 후보 (analyze_freq.py 와 같은 기준: JMdict 흔한 말 news1·ichi1·spec1·spec2·gai1)
    from analyze_freq import load_jmdict
    print('JMdict 읽는 중…'); jm = load_jmdict()
    furi = json.load(open(os.path.join(REF_DIR, 'JmdictFurigana.json'), encoding='utf-8-sig'))
    Sset = set(S); rd_of = {k: parse_readings(J[k]['rd']) for k in S}
    bucket = {k: {} for k in S}
    for e in furi:
        info = jm.get((e['text'], e['reading']))
        if not info or not info[0]:
            continue
        ks = [c for c in e['text'] if '一' <= c <= '鿿' or c == '𠮟']
        if not ks or any(c not in J for c in ks):
            continue
        for seg in e['furigana']:
            ch = seg['ruby']
            if len(ch) != 1 or ch not in Sset or not seg.get('rt'):
                continue
            rt = kata2hira(seg['rt'])
            for r in rd_of[ch]:
                if any(rt == f for f, _ in variants(kata2hira(r['stem']))):
                    bucket[ch].setdefault(r['r'], []).append((e['text'], e['reading'], info[1], info[2])); break
    voc = open(os.path.join(ROOT, 'data', 'vocab.js'), encoding='utf-8').read()
    V = json.loads(voc[voc.index('=') + 1:voc.rindex(';')])['words']
    vko = {(r[0], r[1]): r[3] for r in V}
    freq = {}
    for k in S:
        cnt = {r: len(v) for r, v in bucket[k].items()}
        total = sum(cnt.values()) or 1
        core, acc = [], 0
        for r in sorted(cnt, key=lambda r: -cnt[r]):
            if len(core) >= 2 or (core and acc / total >= 0.7): break
            core.append(r); acc += cnt[r]
        cands, seen = [], set()
        for r, ws in bucket[k].items():
            for w, y, nf, en in ws:
                if (w, y) in seen: continue
                seen.add((w, y)); cands.append(dict(w=w, y=y, r=r, nf=nf, en=en, ko=vko.get((w, y), '')))
        cands.sort(key=lambda c: (not c['ko'], c['nf'], len(c['w'])))   # 단어장에 있는 말 먼저, 그다음 흔한 순
        freq[k] = dict(cnt=cnt, core=core, cands=cands[:20])
    json.dump(freq, open(os.path.join(REF_DIR, 'freq', 'freq_ms.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    # ④ 한국 훈음 후보
    HD = hangul_dict()
    def ko_cands(c):
        out = [f'{s}:{m}' for s, m in HD.get(c, []) if m]
        if not out:
            for v in KD[c]['var']:
                out += [f'[{v}] {s}:{m}' for s, m in HD.get(v, []) if m]
        return out
    # ⑤ 작성용 참고 파일 (코스별)
    nohun = []
    for g in (7, 8, 9, 10):
        ks = sorted((k for k in S if COURSE[lv[k]] == g), key=lambda k: KD[k]['freq'])
        lines = [f'# {CNAME[g]} 코스 ({[l for l, v in COURSE.items() if v == g][0]}) {len(ks)}자 — 빈도순',
                 '# 글자 | 획수 | 부수 | 음훈(괄호=드문 읽기) | 한국음(KANJIDIC2) | 훈음 후보(libhangul) | 영어뜻 | 핵심 읽기 후보 | 단어 후보(표기·읽기·상용읽기·영어·[단어장 뜻])']
        for k in ks:
            kc = ko_cands(k)
            if not kc: nohun.append(k)
            f = freq[k]
            words = ' / '.join(f"{c['w']}·{c['y']}·{c['r']}·{c['en']}" + (f"·[{c['ko']}]" if c['ko'] else '') for c in f['cands'][:10])
            lines.append(f"{k} | {J[k]['sc']} | {J[k]['rad']} | {J[k]['rd']} | {'/'.join(KD[k]['ko'])} | {' ‖ '.join(kc)[:300]} | {'; '.join(KD[k]['en'][:6])} | {','.join(f['core'])} | {words}")
        open(os.path.join(REF_DIR, 'ref', f'ref_g{g}.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
        print(f'ref_g{g}.txt {len(ks)}자')
    print('훈음 후보 없음', len(nohun), ''.join(nohun))
    print('흔한 단어 0개', sum(1 for k in S if not freq[k]['cands']), ''.join(k for k in S if not freq[k]['cands']))

if __name__ == '__main__':
    main()
