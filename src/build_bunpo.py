# -*- coding: utf-8 -*-
"""
📗 문법장 빌드 + 검증
  입력: src/bunpo_plan.json (뼈대 — bunpo_plan.py) · src/bunpo_q*.json (내용 — AUTHORING_bunpo.md)
  출력: data/bunpo.js (window.BUNPO) · src/verify_bunpo.txt
  검사: 뼈대 항목이 빠짐없이 작성됐는지 · 필수 필드 · 예문 2개 · 읽기는 히라가나 · 문형이 예문에 보이는지(참고)
        · 예문 읽기를 형태소 분석기와 대조(참고) · 예문 단어가 단어장 수준인지(참고)
사용: python build_bunpo.py            (전체 빌드)
      python build_bunpo.py --check 파일 (작성 중인 파일 하나만 검사)
"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from build import ROOT, kata2hira, _tagger, analyzer_reading, write_index
sys.stdout.reconfigure(encoding='utf-8')

def plan():
    return json.load(open(os.path.join(HERE, 'bunpo_plan.json'), encoding='utf-8'))

_VW = None
def vocab_words():
    """단어장 + 활용어 동사·형용사·부사 + 초등 한자 예시 단어의 기본형 집합 (예문 단어 수준 참고용)"""
    global _VW
    if _VW is None:
        s = open(os.path.join(ROOT, 'data', 'vocab.js'), encoding='utf-8').read()
        V = json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))['words']
        s = open(os.path.join(ROOT, 'data', 'gram.js'), encoding='utf-8').read()
        G = json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))
        _VW = {x[0] for x in V} | {x[1] for x in V} | {x[0][:-2] for x in V if x[0].endswith('する')}
        _VW |= {x[0] for x in G['verbs'] + G['adjs'] + G['advs']} | {x[1] for x in G['verbs'] + G['adjs'] + G['advs']}
    return _VW

def check(items, P, errors, warns, infos, tg):
    pid = {x['id']: x for x in P['items']}
    VW = vocab_words()
    for it in items:
        i = it.get('id', '?'); pl = pid.get(i)
        if not pl: errors.append(f'{i}: 뼈대에 없는 id'); continue
        if it.get('p') != pl['p']: errors.append(f'{i}: 문형 p 가 뼈대와 다름 ({it.get("p")} ≠ {pl["p"]})')
        for f in ('m', 'c', 'd'):
            if not (it.get(f) or '').strip(): errors.append(f'{i} {pl["p"]}: "{f}" 비어 있음')
        if len(it.get('d', '')) > 260: warns.append(f'{i} {pl["p"]}: 설명 d {len(it["d"])}자 — 1~3문장으로')
        for c in it.get('cmp', []):
            if len(c) != 2 or not c[0] or not c[1]: errors.append(f'{i}: cmp 형식 오류 {c}')
        ex = it.get('ex', [])
        if len(ex) != 2: errors.append(f'{i} {pl["p"]}: 예문 {len(ex)}개 (정확히 2개)')
        for e in ex:
            if len(e) != 3 or not all(e): errors.append(f'{i}: 예문 형식 오류 {e}'); continue
            jp, yo, ko = e
            if re.search(r'[一-鿿]', yo): errors.append(f'{i}: 읽기에 한자 "{yo}"')
            if re.search(r'[ァ-ヺ]', yo) and not re.search(r'[ァ-ヺ]', jp): errors.append(f'{i}: 읽기에 가타카나 (문장이 가타카나가 아니면 히라가나로) "{yo}"')
            if re.search(r'[ぁ-ゖァ-ヺ]', ko): errors.append(f'{i}: 번역에 일본 글자 "{ko}"')
            if len(jp) > 45: warns.append(f'{i}: 예문이 김 ({len(jp)}자) "{jp}"')
            if tg:
                ar = kata2hira(analyzer_reading(tg, jp)); mine = kata2hira(yo.replace(' ', '').replace('　', ''))
                if ar != mine: infos.append(f'{i}: 읽기 확인 필요 — 작성 "{mine}" / 분석기 "{ar}"')
                hard = []
                for w in tg(jp):
                    lem = getattr(w.feature, 'lemma', None) or w.surface; pos = getattr(w.feature, 'pos1', '')
                    if pos in ('名詞', '動詞', '形容詞', '副詞') and re.search(r'[一-鿿]', w.surface) and lem not in VW and w.surface not in VW and not re.match(r'^[一-鿿]$', w.surface):
                        hard.append(w.surface)
                if hard: infos.append(f'{i}: 단어장 밖 단어(참고) {"·".join(hard)} — "{jp}"')

BLANK = '（　　）'
def check_q(qs, P, errors, warns, infos, tg):
    """빈칸 연습 문제 검사 (AUTHORING_bpq.md)"""
    pid = {x['id']: x for x in P['items']}
    cards = {x['id']: x for x in load_parts()}
    for q in qs:
        i = q.get('id', '?'); z = q.get('qz') or {}
        if i not in pid: errors.append(f'{i}: 뼈대에 없는 id'); continue
        s, a, ch, y, ko, why = (z.get(k) for k in ('s', 'a', 'ch', 'y', 'ko', 'why'))
        if not all([s, a, ch, y, ko, why]): errors.append(f'{i} {pid[i]["p"]}: 필드 비어 있음'); continue
        if s.count(BLANK) != 1: errors.append(f'{i}: 빈칸 {BLANK} 이 정확히 한 번이어야 함 — "{s}"'); continue
        if not isinstance(ch, list) or len(ch) != 3 or len(set(ch)) != 3 or a in ch or not all(ch):
            errors.append(f'{i}: 오답 ch는 서로 다른 3개, 정답과 달라야 함 {ch} / 정답 {a}')
        full = s.replace(BLANK, a)
        if re.search(r'[一-鿿]', y): errors.append(f'{i}: 읽기에 한자 "{y}"')
        if re.search(r'[ァ-ヺ]', y) and not re.search(r'[ァ-ヺ]', full): errors.append(f'{i}: 읽기에 가타카나 "{y}"')
        if re.search(r'[ぁ-ゖァ-ヺ]', ko): errors.append(f'{i}: 번역에 일본 글자 "{ko}"')
        if len(why) > 140: warns.append(f'{i}: 해설 {len(why)}자 — 짧게')
        c = cards.get(i)
        if c and any(full.replace('、', '').replace('。', '') == e[0].replace('、', '').replace('。', '') for e in c['ex']):
            warns.append(f'{i}: 문제 문장이 카드 예문과 같음 — 새로 만들기')
        if tg:
            ar = kata2hira(analyzer_reading(tg, full)); mine = kata2hira(y.replace(' ', '').replace('　', ''))
            if ar != mine: infos.append(f'{i}: 읽기 확인 필요 — 작성 "{mine}" / 분석기 "{ar}"')

def load_q():
    qs = {}
    for f in sorted(os.listdir(HERE)):
        if re.match(r'^bpq_q\d+\.json$', f):
            for q in json.load(open(os.path.join(HERE, f), encoding='utf-8-sig'))['items']: qs[q['id']] = q['qz']
    return qs

def load_parts():
    items = []
    for f in sorted(os.listdir(HERE)):
        if re.match(r'^bunpo_q\d+\.json$', f):
            items += json.load(open(os.path.join(HERE, f), encoding='utf-8-sig'))['items']
    return items

def main(argv):
    P = plan(); tg = _tagger(); errors, warns, infos = [], [], []
    if argv and argv[0] == '--checkq':
        qs = json.load(open(argv[1], encoding='utf-8-sig'))['items']
        check_q(qs, P, errors, warns, infos, tg)
        print(f'{argv[1]}: {len(qs)}문제 · 오류 {len(errors)} · 경고 {len(warns)} · 참고 {len(infos)}')
        for x in errors: print('ERR', x)
        for x in warns: print('WARN', x)
        for x in infos: print('INFO', x)
        return 1 if errors else 0
    if argv and argv[0] == '--check':
        items = json.load(open(argv[1], encoding='utf-8-sig'))['items']
        check(items, P, errors, warns, infos, tg)
        print(f'{argv[1]}: {len(items)}항목 · 오류 {len(errors)} · 경고 {len(warns)} · 참고 {len(infos)}')
        for x in errors: print('ERR', x)
        for x in warns: print('WARN', x)
        for x in infos: print('INFO', x)
        return 1 if errors else 0
    items = load_parts(); by = {x['id']: x for x in items}
    miss = [x['id'] + ' ' + x['p'] for x in P['items'] if x['id'] not in by]
    if miss: errors.append(f'작성 안 된 항목 {len(miss)}개: ' + ' / '.join(miss[:20]))
    check(items, P, errors, warns, infos, tg)
    QZ = load_q()   # 빈칸 연습 문제 (있는 것만 붙임)
    if QZ:
        check_q([dict(id=k, qz=v) for k, v in QZ.items()], P, errors, warns, infos, tg)
    out = []
    for pl in P['items']:
        it = by.get(pl['id'])
        if not it: continue
        o = dict(id=pl['id'], g=pl['g'], lv=pl['lv'], p=pl['p'], m=it['m'], c=it['c'], d=it['d'], ex=it['ex'])
        if pl['tag']: o['tag'] = pl['tag']
        if it.get('cmp'): o['cmp'] = it['cmp']
        z = QZ.get(pl['id'])
        if z: o['qz'] = [z['s'], z['a'], z['ch'], z['y'], z['ko'], z['why']]   # [문장, 정답, 오답3, 읽기, 번역, 해설]
        out.append(o)
    rep = [f'[문법장] 뼈대 {len(P["items"])} · 작성 {len(out)} · 연습 문제 {sum(1 for o in out if o.get("qz"))} · 오류 {len(errors)} · 경고 {len(warns)} · 참고 {len(infos)}']
    rep += ['ERR ' + x for x in errors] + ['WARN ' + x for x in warns] + ['INFO ' + x for x in infos]
    open(os.path.join(HERE, 'verify_bunpo.txt'), 'w', encoding='utf-8').write('\n'.join(rep) + '\n')
    print('\n'.join(rep[:1 + len(errors) + len(warns)]))
    if errors: return 1
    js = 'window.BUNPO=' + json.dumps(dict(groups=P['groups'], items=out), ensure_ascii=False, separators=(',', ':')) + ';\n'
    open(os.path.join(ROOT, 'data', 'bunpo.js'), 'w', encoding='utf-8').write(js)
    write_index()
    print('data/bunpo.js', len(js.encode()), 'bytes')
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
