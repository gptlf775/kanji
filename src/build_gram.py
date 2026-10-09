# -*- coding: utf-8 -*-
"""
활용어 탭 빌드·검증 → data/gram.js
  ① 동사·형용사: JMdict 품사로 그룹·종류 대조 (1=5단 v5*, 2=1단 v1, 3s=する, 3k=来る, i=adj-i, na=adj-na)
     불규칙(行く v5k-s → 1k, いらっしゃる류 v5aru → 1a, ある v5r-i → 1r)은 JMdict 품사로 자동 표시
  ② 예문: 형태소 분석기 읽기와 대조 (다르면 INFO → 사람이 판정. 분석기는 日本·数字 등을 자주 틀림)
  ③ 중복·형식 검사
사용: python build_gram.py
"""
import gzip, json, os, re, sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REF = os.path.join(os.path.dirname(ROOT), '일본어한자_원천데이터')
sys.path.insert(0, HERE)
import gram_src as G
from build import kata2hira, _tagger, analyzer_reading, write_index

def pos_code(desc):
    """JMdict 품사 설명(엔티티가 풀린 글) → 코드"""
    d = desc
    if d.startswith('Ichidan verb'): return 'v1'
    if 'Iku/Yuku special class' in d: return 'v5k-s'
    if '-aru special class' in d: return 'v5aru'
    if "'ru' ending (irregular verb)" in d: return 'v5r-i'
    if d.startswith('Godan verb'): return 'v5'
    if d.startswith('Kuru verb'): return 'vk'
    if 'suru verb - included' in d: return 'vs-i'
    if 'takes the aux. verb suru' in d: return 'vs'
    if 'yoi/ii class' in d: return 'adj-ix'
    if d.startswith('adjective (keiyoushi)'): return 'adj-i'
    if 'keiyodoshi' in d: return 'adj-na'
    if d.startswith('adverb') or d.startswith('adverbial noun'): return 'adv'
    return None

def load_jm():
    """(표기, 읽기) → 품사 코드 집합 / 읽기만 → 품사 코드 집합 / 흔한 말 여부"""
    by_wy, by_y, common = {}, {}, set()
    with gzip.open(os.path.join(REF, 'JMdict_e.gz'), 'rb') as f:
        for ev, el in ET.iterparse(f, events=('end',)):
            if el.tag != 'entry':
                continue
            pos = {c for s in el.findall('sense') for p in s.findall('pos') if (c := pos_code(p.text or ''))}
            kebs = [(k.findtext('keb'), {p.text for p in k.findall('ke_pri')}) for k in el.findall('k_ele')]
            for r in el.findall('r_ele'):
                reb = r.findtext('reb'); rp = {p.text for p in r.findall('re_pri')}
                by_y.setdefault(reb, set()).update(pos)
                if rp & {'news1', 'ichi1', 'spec1', 'spec2', 'gai1'}: common.add((reb, reb))
                restr = {x.text for x in r.findall('re_restr')}
                for keb, kp in kebs:
                    if restr and keb not in restr: continue
                    by_wy.setdefault((keb, reb), set()).update(pos)
                    if (kp | rp) & {'news1', 'ichi1', 'spec1', 'spec2', 'gai1'}: common.add((keb, reb))
            el.clear()
    return by_wy, by_y, common

def parse(block, lv):
    out = []
    for line in block.strip().splitlines():
        w, y, g, ko = line.split('|')
        out.append([w, y, g, ko, lv])
    return out

def main():
    errors, infos = [], []
    verbs = parse(G.VERBS_N5, 5) + parse(G.VERBS_N4, 4)
    adjs = parse(G.ADJS_N5, 5) + parse(G.ADJS_N4, 4)
    advs = parse(G.ADVS_N5, 5) + parse(G.ADVS_N4, 4)
    seen = set()
    for r in verbs + adjs + advs:
        if (r[0], r[1]) in seen: errors.append(f'중복: {r[0]}({r[1]})')
        seen.add((r[0], r[1]))
        # 읽기에 가타카나·공백이 섞이면 오류 (단, 외래어 ハンサム처럼 표기 = 읽기인 낱말은 허용)
        if re.search(r'[ァ-ヶ\s]', r[1]) and r[0] != r[1]: errors.append(f'{r[0]}: 읽기 "{r[1]}" 에 가타카나·공백')
    print('JMdict 읽는 중…')
    by_wy, by_y, common = load_jm()
    def pos_of(w, y):
        return by_wy.get((w, y)) or (by_y.get(y) if w == y else None) or set()
    for r in verbs:
        w, y, g = r[0], r[1], r[2]
        if g == '3s':
            base, by = w[:-2], y[:-2]
            ok = (w == 'する') or ('vs' in pos_of(base, by))
            if not ok: errors.append(f'{w}: JMdict 에서 する동사(vs) 확인 안 됨 {sorted(pos_of(base, by))}')
            continue
        P = pos_of(w, y)
        if not P: errors.append(f'{w}({y}): JMdict 에 없음'); continue
        want = {'1': lambda p: any(x.startswith('v5') for x in p), '2': lambda p: 'v1' in p, '3k': lambda p: 'vk' in p}[g]
        if not want(P): errors.append(f'{w}({y}): 그룹 {g} 인데 JMdict 품사 {sorted(P)}')
        if g == '1':   # 불규칙 자동 표시
            if 'v5k-s' in P: r[2] = '1k'
            elif 'v5aru' in P: r[2] = '1a'
            elif 'v5r-i' in P: r[2] = '1r'
        if (w, y) not in common: infos.append(f'{w}({y}): JMdict 흔한 말 표시 없음')
    for r in adjs:
        w, y, t = r[0], r[1], r[2]
        P = pos_of(w, y)
        if not P: errors.append(f'{w}({y}): JMdict 에 없음'); continue
        if t == 'i' and not ({'adj-i', 'adj-ix'} & P): errors.append(f'{w}({y}): い형용사인데 JMdict 품사 {sorted(P)}')
        if t == 'na' and 'adj-na' not in P: errors.append(f'{w}({y}): な형용사인데 JMdict 품사 {sorted(P)}')
        if (w, y) not in common: infos.append(f'{w}({y}): JMdict 흔한 말 표시 없음')
    # 부사: JMdict 에 부사(adv) 품사로 있는지 — '一緒に'처럼 명사+に 꼴은 사전 표제어가 없을 수 있어 참고로만
    for r in advs:
        P = pos_of(r[0], r[1]) or by_y.get(r[1], set())
        if 'adv' not in P: infos.append(f'{r[0]}({r[1]}): JMdict 부사 표시 없음 {sorted(P)} (명사·な형용사 + に 꼴일 수 있음)')
    irregular = [f'{r[0]}={r[2]}' for r in verbs if r[2] in ('1k', '1a', '1r')]
    # 예문 읽기
    tagger = _tagger()
    exs = [e for t in G.TABS for s in t.get('secs', []) for e in s.get('ex', [])]
    pats = [dict(p, lv=5) for p in G.PAT_N5] + [dict(p, lv=4) for p in G.PAT_N4]
    exs += [e for p in pats for e in p['ex']]
    for j, y, k in exs:
        if not j or not y or not k: errors.append(f'예문 형식 오류 {j}')
        if tagger:
            ar = kata2hira(analyzer_reading(tagger, j)); mine = kata2hira(y.replace(' ', ''))
            if ar != mine: infos.append(f'예문 읽기 확인 — "{j}" 작성 {mine} / 분석기 {ar}')
    vmap = {r[0]: r for r in verbs}
    demo = []
    VKEYS = ['dict', 'masu', 'nai', 'ta', 'nakatta', 'te', 'tai', 'pot', 'vol', 'ba', 'imp', 'pass', 'caus', 'causp']
    for w in G.DEMO:
        if w not in vmap: errors.append(f'DEMO 동사 {w} 가 목록에 없음'); continue
        ko = G.DEMO_KO.get(w, '').split('|')
        if len(ko) != len(VKEYS): errors.append(f'DEMO_KO {w}: 한국어 {len(ko)}개 (활용형 {len(VKEYS)}개와 같아야 함)'); ko = []
        demo.append(vmap[w][:4] + [dict(zip(VKEYS, ko))])
    if set(G.FORM_KO['v']) != set(VKEYS): errors.append('FORM_KO 동사 활용형 목록 불일치')
    # 용어 사전: 기초 탭 본문에 실제로 나오는 용어인지
    txt_all = json.dumps(G.TABS, ensure_ascii=False) + json.dumps(pats, ensure_ascii=False)
    for t, d, inline in G.GLOSS:
        if not d: errors.append(f'용어 "{t}" 풀이 없음')
        if inline and t not in txt_all: infos.append(f'용어 "{t}" 는 본문에 나오지 않음 (사전에만 표시)')
    data = dict(tabs=G.TABS, demo=demo, verbs=verbs, adjs=adjs, advs=advs, pat=pats, formKo=G.FORM_KO, gloss=G.GLOSS)
    js = 'window.GRAM=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n'
    open(os.path.join(ROOT, 'data', 'gram.js'), 'w', encoding='utf-8').write(js)
    write_index()
    rep = [f'동사 {len(verbs)} (N5 {sum(1 for r in verbs if r[4] == 5)} · N4 {sum(1 for r in verbs if r[4] == 4)}) · 형용사 {len(adjs)} · 부사 {len(advs)} · 문법 패턴 {len(pats)} · 예문 {len(exs)}',
           f'불규칙 자동 표시: {", ".join(irregular)}',
           f'오류 {len(errors)}건, 참고 {len(infos)}건'] + ['ERR ' + e for e in errors] + ['INFO ' + i for i in infos]
    txt = '\n'.join(rep)
    open(os.path.join(HERE, 'verify_gram.txt'), 'w', encoding='utf-8').write(txt + '\n')
    print(txt)
    print('data size:', len(js.encode('utf-8')), 'bytes')
    return 1 if errors else 0

if __name__ == '__main__':
    sys.exit(main())
