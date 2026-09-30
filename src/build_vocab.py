# -*- coding: utf-8 -*-
"""
단어장 빌드·검증 → data/vocab.js
  원본: JLPT N5·N4 단어 목록 — Jonathan Waller, tanos.co.uk (CC BY) · CSV 정리: open-anki-jlpt-decks (GitHub)
        → vocab_prep.py 가 JMdict 품사·빈도를 붙여 ../일본어한자_원천데이터/jlpt/vocab_work.json 으로 만듦
  한국어 뜻: 활용어 목록(gram_src.py)과 겹치는 동사·형용사는 그 뜻, 나머지는 src/vocab_ko.txt (직접 작성)
  정렬(많이 쓰는 순): JMdict 빈도 순위(nf, 신문 기준) — 표시 없으면 흔한 말 40 / 그 밖 70, N5는 8만큼 앞으로(기초 생활어 보정)
사용: python build_vocab.py
"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REF = os.path.join(os.path.dirname(ROOT), '일본어한자_원천데이터')
sys.path.insert(0, HERE)
from vocab_norm import normalize, merge_variants, gram_index, category, norm_pair
from build import write_index

CAT_NAME = {'n': '명사', 'v': '동사', 'i': 'い형용사', 'na': 'な형용사', 'adv': '부사', 'etc': '기타'}

def main():
    errors, infos = [], []
    gram = gram_index()
    rows = json.load(open(os.path.join(REF, 'jlpt', 'vocab_work.json'), encoding='utf-8'))
    rows, dropped = normalize(rows)
    rows = merge_variants(rows, gram)
    ko = {}
    kp = os.path.join(HERE, 'vocab_ko.txt')
    for n, line in enumerate(open(kp, encoding='utf-8').read().strip().splitlines(), 1):
        parts = line.split('|')
        if len(parts) != 3: errors.append(f'vocab_ko.txt {n}행 형식 오류: {line}'); continue
        w, y, k = parts
        w, y = norm_pair(w, y)                      # 원본 목록과 같은 정리를 한국어 뜻 열쇠에도
        if (w, y) in ko:
            if k.strip() != ko[(w, y)]: ko[(w, y)] += ' · ' + k.strip()   # 같은 말 두 줄(キロ 킬로그램·킬로미터) → 합침
            continue
        ko[(w, y)] = k.strip()
    words = []
    gcat = {k: v[:2] for k, v in gram.items()}
    for r in rows:
        key = (r['w'], r['y'])
        k = gram[key][2] if key in gram else ko.get(key)
        if k: k = re.sub(r'\s*\(★[^)]*\)', '', k)      # 활용어 목록의 ★ 메모는 단어장에서 뺌
        if not k: errors.append(f'한국어 뜻 없음: {r["w"]}({r["y"]})'); continue
        if re.search(r'[A-Za-z]{3,}', k) and not re.search(r'(TV|CD|DVD|PC|OK)', k): infos.append(f'영어가 섞인 뜻: {r["w"]} = {k}')
        if re.search(r'[぀-ヿ]', k): infos.append(f'가나가 섞인 뜻: {r["w"]} = {k}')
        cat, g = category(r, gcat)
        nf = r['nf'] if r['nf'] < 99 else (40 if r['cm'] else 70)
        score = nf - (8 if r['lv'] == 5 else 0)
        words.append(dict(w=r['w'], y=r['y'], c=cat, k=k, lv=r['lv'], g=g, s=score, n=len(r['w'])))
    unused = set(ko) - {(w['w'], w['y']) for w in words}
    for u in sorted(unused): infos.append(f'vocab_ko.txt 에만 있고 목록에 없는 말: {u[0]}({u[1]})')
    # 기초어(vocab_core.txt)는 적힌 순서대로 맨 위, 나머지는 빈도 점수 순
    core = [l.strip() for l in open(os.path.join(HERE, 'vocab_core.txt'), encoding='utf-8') if l.strip() and not l.startswith('#')]
    pos = {}
    for i, c in enumerate(core):
        cw, cy = (c.split('|') + [None])[:2]
        hit = [x for x in words if x['w'] == cw and (cy is None or x['y'] == cy)] or [x for x in words if x['y'] == cw]
        if not hit: infos.append(f'기초어 "{c}" 가 단어 목록에 없음'); continue
        for x in hit[:1]:
            pos.setdefault((x['w'], x['y']), i)
    for x in words:
        x['core'] = pos.get((x['w'], x['y']), 10**6)
    words.sort(key=lambda x: (x['core'], x['s'], -x['lv'], x['n']))
    infos.insert(0, f'기초어 우선 배치 {len(pos)}개')
    out = [[x['w'], x['y'], x['c'], x['k'], x['lv'], x['g']] for x in words]
    data = dict(src='JLPT N5·N4 단어 목록: Jonathan Waller (tanos.co.uk, CC BY) · 한국어 뜻·품사 정리: 이 앱', words=out)
    js = 'window.VOCAB=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n'
    open(os.path.join(ROOT, 'data', 'vocab.js'), 'w', encoding='utf-8').write(js)
    write_index()
    from collections import Counter
    cc = Counter(CAT_NAME[x[2]] for x in out)
    rep = [f'단어 {len(out)} (N5 {sum(1 for x in out if x[4] == 5)} · N4 {sum(1 for x in out if x[4] == 4)}) · 제외(문형·접사) {len(dropped)}',
           '품사: ' + ', '.join(f'{k} {v}' for k, v in cc.most_common()),
           '상위 30: ' + ' '.join(x[0] for x in out[:30]),
           f'오류 {len(errors)}건, 참고 {len(infos)}건'] + ['ERR ' + e for e in errors] + ['INFO ' + i for i in infos]
    txt = '\n'.join(rep)
    open(os.path.join(HERE, 'verify_vocab.txt'), 'w', encoding='utf-8').write(txt + '\n')
    print(txt); print('data size:', len(js.encode('utf-8')), 'bytes')
    return 1 if errors else 0

if __name__ == '__main__':
    sys.exit(main())
