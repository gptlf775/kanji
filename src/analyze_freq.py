# -*- coding: utf-8 -*-
"""
2단계 데이터 분석 — JMdict(흔한 말 표시) + JmdictFurigana(단어 속 한자별 읽기)
출력 (원천데이터/freq/):
  - freq_gN.json : 한자별 {읽기별 흔한 단어 수, 읽기 등급(핵심/자주/드묾), 흔한 단어 후보}
  - summary.txt  : 기존 예시 단어 4,096개 중 흔한 말 비율 등
'흔한 말' 기준: JMdict 우선순위 news1·ichi1·spec1·spec2·gai1 (JMdict의 공식 'common' 정의)
"""
import gzip, json, os, re, sys, collections
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REF = os.path.join(os.path.dirname(ROOT), '일본어한자_원천데이터')
OUT = os.path.join(REF, 'freq')
COMMON = {'news1', 'ichi1', 'spec1', 'spec2', 'gai1'}
sys.path.insert(0, HERE)
from build import parse_readings, kata2hira, variants, load_content  # 같은 규칙 재사용

def nf_rank(pris):
    """nfXX(빈도 순위 묶음, 작을수록 흔함) → 숫자. 없으면 99"""
    n = [int(p[2:]) for p in pris if p.startswith('nf')]
    return min(n) if n else 99

def load_jmdict():
    """(표기, 읽기) → (흔한 말 여부, nf 순위, 첫 영어 뜻)"""
    idx = {}
    with gzip.open(os.path.join(REF, 'JMdict_e.gz'), 'rb') as f:
        for ev, el in ET.iterparse(f, events=('end',)):
            if el.tag != 'entry':
                continue
            kebs = [(k.findtext('keb'), [p.text for p in k.findall('ke_pri')]) for k in el.findall('k_ele')]
            gloss = el.findtext('sense/gloss') or ''
            for r in el.findall('r_ele'):
                reb = r.findtext('reb'); rpri = [p.text for p in r.findall('re_pri')]
                restr = {x.text for x in r.findall('re_restr')}
                for keb, kpri in kebs:
                    if restr and keb not in restr:
                        continue
                    pri = set(kpri) & set(rpri) if (kpri and rpri) else set(kpri or rpri)
                    common = bool(pri & COMMON)
                    key = (keb, reb)
                    val = (common, nf_rank(pri), gloss)
                    if key not in idx or (val[0], -val[1]) > (idx[key][0], -idx[key][1]):
                        idx[key] = val
            el.clear()
    return idx

def main():
    os.makedirs(OUT, exist_ok=True)
    J = json.load(open(os.path.join(REF, 'jouyou.json'), encoding='utf-8'))
    K1026 = {k for k, v in J.items() if v['g'] in list('123456')}
    grade = {k: int(J[k]['g']) for k in K1026}
    print('JMdict 읽는 중…'); jm = load_jmdict(); print('  항목', len(jm))
    furi = json.load(open(os.path.join(REF, 'JmdictFurigana.json'), encoding='utf-8-sig'))
    print('  후리가나', len(furi))

    # 한자별: 읽기(상용표 표기) → [(단어, 읽기, nf, 흔한말, 단어 최고 학년, 영어뜻)]
    rd_of = {k: parse_readings(J[k]['rd']) for k in K1026}
    bucket = {k: collections.defaultdict(list) for k in K1026}
    for e in furi:
        text, reading = e['text'], e['reading']
        info = jm.get((text, reading))
        if not info:
            continue
        common, nf, gloss = info
        if not common:
            continue
        ks = [c for c in text if '一' <= c <= '鿿']
        if not ks or any(c not in J for c in ks):   # 상용한자 밖 글자가 섞인 말 제외
            continue
        maxg = max(int(J[c]['g']) if J[c]['g'] != 'S' else 7 for c in ks)
        for seg in e['furigana']:
            ch = seg['ruby']
            if len(ch) != 1 or ch not in K1026 or not seg.get('rt'):
                continue
            rt = kata2hira(seg['rt'])
            # 이 한자의 어떤 상용 읽기인가 (연탁·촉음 변형 허용)
            match = None
            for r in rd_of[ch]:
                stem = kata2hira(r['stem'])
                if any(rt == f for f, _ in variants(stem)):
                    match = r['r']; break
            if match:
                bucket[ch][match].append((text, reading, nf, maxg, gloss))

    # 등급: 흔한 단어 수 기준 — 핵심(상위, 누적 70%까지 최대 3개) / 자주(2개 이상) / 드묾
    result = {}
    for k in K1026:
        cnt = {r: len(v) for r, v in bucket[k].items()}
        total = sum(cnt.values()) or 1
        order = sorted(cnt, key=lambda r: -cnt[r])
        core, acc = [], 0
        for r in order:
            if len(core) >= 3 or (core and acc / total >= 0.7):
                break
            core.append(r); acc += cnt[r]
        freq = [r for r in order if r not in core and cnt[r] >= 2]
        cands = []
        for r, ws in bucket[k].items():
            for w in ws:
                cands.append(dict(w=w[0], y=w[1], r=r, nf=w[2], g=w[3], en=w[4]))
        cands.sort(key=lambda c: (c['nf'], c['g'], len(c['w'])))
        seen, uniq = set(), []
        for c in cands:
            if (c['w'], c['y']) not in seen:
                seen.add((c['w'], c['y'])); uniq.append(c)
        result[k] = dict(cnt=cnt, core=core, freq=freq, cands=uniq[:40])

    # 기존 예시 단어 평가
    lines = []
    for g in range(1, 7):
        C = load_content(g)
        per = {k: v for k, v in result.items() if grade[k] == g}
        json.dump(per, open(os.path.join(OUT, f'freq_g{g}.json'), 'w', encoding='utf-8'), ensure_ascii=False)
        n = com = 0; rare = []
        for it in C['items']:
            for e in it['ex']:
                n += 1
                info = jm.get((e[0], e[1]))
                if info and info[0]:
                    com += 1
                else:
                    rare.append(f"{it['k']}:{e[0]}({e[1]})")
        lines.append(f'{g}학년: 예시 {n}개 중 흔한 말 {com}개 ({com/n*100:.0f}%) · 흔하지 않거나 사전에 없는 말 {n-com}개')
        lines.append('   예: ' + ' '.join(rare[:25]))
    nocore = [k for k in K1026 if not result[k]['core']]
    lines.append(f'흔한 단어가 하나도 없는 한자(핵심 읽기 산출 불가): {len(nocore)}자 {"".join(sorted(nocore))}')
    txt = '\n'.join(lines)
    open(os.path.join(OUT, 'summary.txt'), 'w', encoding='utf-8').write(txt + '\n')
    print(txt)
    for k in '四生下日上行':
        print(k, 'core', result[k]['core'], 'freq', result[k]['freq'], {r: c for r, c in result[k]['cnt'].items()})

if __name__ == '__main__':
    main()
