# -*- coding: utf-8 -*-
"""
중학·고등 코스 1단계(찾아보기용 기본 카드) 빌드 + 자동 검증
  입력: src/content_g{7..10}_p*.json (작성 기준: src/AUTHORING_ms1.md), src/kanken_ms.json(코스 배정)
        원천데이터 jouyou.json · kanjidic2.xml · kvg/ · ref/libhangul_hanja.txt · JMdict_e.gz
  출력: data/g{7..10}.js (basic=true — 학습(오늘의 공부)에는 아직 안 나오고 찾아보기·카드에만)
        src/verify_g{7..10}.txt
  검증: 글자 목록 = 한자검정 급별 목록 · 훈음 형식과 한국음 · 핵심 읽기 ∈ 상용한자표 음훈 ·
        예시 단어가 JMdict에 실제로 있는 (표기, 읽기)인지 · 단어 읽기 안에 그 한자 읽기가 있는지 · 획 수
사용: python build_ms.py 7            (코스 전체 빌드)
      python build_ms.py --check 파일  (작성 중인 파일 하나만 검사, 출력 안 함)
"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from build import REF_DIR, ROOT, parse_readings, kata2hira, variants, kvg_paths, write_index
sys.stdout.reconfigure(encoding='utf-8')

COURSE = {'4級': 7, '3級': 8, '準2級': 9, '2級': 10}
CNAME = {7: '중1', 8: '중2', 9: '중3', 10: '고등'}
KNAME = {'4級': '4급', '3級': '3급', '準2級': '준2급', '2級': '2급'}
ROWS = [('あ행', 'アイウエオ'), ('か행', 'カキクケコガギグゲゴ'), ('さ행', 'サシスセソザジズゼゾ'), ('た행', 'タチツテトダヂヅデド'), ('な행', 'ナニヌネノ'),
        ('は행', 'ハヒフヘホバビブベボパピプペポ'), ('ま행', 'マミムメモ'), ('や행', 'ヤユヨ'), ('ら행', 'ラリルレロ'), ('わ행', 'ワヲン')]
_JM = None
VAR_EXTRA = {'𠮟': ['叱']}   # KANJIDIC2에 이체자 연결이 없는 글자 (𠮟 = 叱의 이체자, 상용한자표 字体)

def jm():
    """JMdict (표기, 읽기) 색인 — 흔한 말이 아니어도 사전에 있으면 OK"""
    global _JM
    if _JM is None:
        from analyze_freq import load_jmdict
        _JM = load_jmdict()
    return _JM

def ko_sounds(c, KD, HD):
    """이 글자의 한국음 후보: KANJIDIC2 korean_h + libhangul(본자·이체자)"""
    s = set(KD.get(c, {}).get('ko', []))
    for v in [c] + KD.get(c, {}).get('var', []) + VAR_EXTRA.get(c, []):
        s |= {snd for snd, m in HD.get(v, []) if m}
    return s

def ko_means(c, KD, HD):
    return ' '.join(m for v in [c] + KD.get(c, {}).get('var', []) + VAR_EXTRA.get(c, []) for _, m in HD.get(v, []))

def theme_of(rds):
    first = next((r for r in rds if r['on'] and not r['rare']), None) or next((r for r in rds if not r['rare']), rds[0])
    head = first['stem'][0]
    if not first['on']:
        head = chr(ord(head) + 0x60) if 'ぁ' <= head <= 'ゖ' else head
    return next((n for n, ks in ROWS if head in ks), 'わ행')

def check_items(items, J, KD, HD, errors, warns, infos):
    for it in items:
        k = it.get('k', '?')
        if k not in J:
            errors.append(f'{k}: 상용한자표에 없는 글자'); continue
        hun = it.get('hun', '')
        if len(hun.split()) < 2:
            errors.append(f'{k}: 훈음 "{hun}" 이 "뜻 음" 형식이 아님')
        else:
            sounds = hun.split()[-1].split('/')
            ok = ko_sounds(k, KD, HD)
            for s in sounds:
                if s not in ok:
                    (warns if it.get('t') != '국자' else infos).append(f'{k}: 한국음 "{s}" 이(가) 사전 후보 {sorted(ok)} 에 없음')
            mean = ' '.join(hun.split()[:-1])
            hm = ko_means(k, KD, HD)
            if hm and mean not in hm:
                infos.append(f'{k}: 훈 "{mean}" 이 libhangul 뜻 후보에 그대로 있지 않음 (현대 대표훈이면 OK) — {hm[:80]}')
        if not it.get('m') or re.search(r'[ぁ-ヶ]', it.get('m', '')):
            errors.append(f'{k}: 뜻(m) 비어 있거나 일본 글자 포함')
        rds = parse_readings(J[k]['rd']); rset = {r['r'] for r in rds}; rmap = {r['r']: r for r in rds}
        core = it.get('core', [])
        if not (1 <= len(core) <= 2):
            errors.append(f'{k}: 핵심 읽기(core) 1~2개 (현재 {len(core)})')
        for c in core:
            if c not in rset:
                errors.append(f'{k}: 핵심 읽기 "{c}" 가 상용한자표 음훈 {sorted(rset)} 에 없음')
        exs = it.get('ex', [])
        if not (1 <= len(exs) <= 5):
            errors.append(f'{k}: 예시 단어 {len(exs)}개 (1~5개, 보통 3~4개)')
        elif len(exs) < 2:
            infos.append(f'{k}: 예시 단어 1개')
        for e in exs:
            if len(e) != 4:
                errors.append(f'{k}: 예시 형식 오류 {e} ([단어, 히라가나 읽기, 상용 읽기 표기, 한국어 뜻])'); continue
            w, y, r, m = e
            if k not in w: errors.append(f'{k}: 예시 "{w}" 에 해당 한자 없음')
            if re.search(r'[ァ-ヶ\sー]', y): errors.append(f'{k}: 예시 "{w}" 읽기 "{y}" 는 히라가나만')
            if not m or re.search(r'[ぁ-ヶ]', m): errors.append(f'{k}: 예시 "{w}" 뜻 비었거나 일본 글자 포함')
            if r not in rmap:
                errors.append(f'{k}: 예시 "{w}" 의 읽기 표기 "{r}" 가 음훈 {sorted(rset)} 에 없음'); continue
            stem = kata2hira(rmap[r]['stem'])
            if not any(f in y for f, _ in variants(stem)):
                errors.append(f'{k}: 예시 "{w}({y})" 안에 읽기 "{stem}" 이 없음')
            if (w, y) not in jm():
                errors.append(f'{k}: 예시 "{w}({y})" 가 JMdict 사전에 없음 (표기·읽기 확인)')
        used = {e[2] for e in exs if len(e) == 4}
        for r in rds:
            if not r['rare'] and r['r'] not in used:
                infos.append(f'{k}: 읽기 "{r["r"]}" 의 예시 없음')

def load_parts(g):
    items = []
    for f in sorted(os.listdir(HERE)):
        if re.match(rf'^content_g{g}_p\d+\.json$', f):
            items += json.load(open(os.path.join(HERE, f), encoding='utf-8'))['items']
    return items

def main(argv):
    from prep_ms import kanjidic, hangul_dict
    J = json.load(open(os.path.join(REF_DIR, 'jouyou.json'), encoding='utf-8'))
    KD, HD = kanjidic(), hangul_dict()
    lv = json.load(open(os.path.join(HERE, 'kanken_ms.json'), encoding='utf-8'))['levels']
    errors, warns, infos = [], [], []
    if argv[0] == '--check':
        items = json.load(open(argv[1], encoding='utf-8'))['items']
        check_items(items, J, KD, HD, errors, warns, infos)
        print(f'{argv[1]}: {len(items)}자 · 오류 {len(errors)} · 경고 {len(warns)} · 참고 {len(infos)}')
        for x in errors: print('ERR', x)
        for x in warns: print('WARN', x)
        for x in infos: print('INFO', x)
        return 1 if errors else 0
    g = int(argv[0])
    official = [k for k, L in lv.items() if COURSE[L] == g]
    items = load_parts(g)
    authored = [it['k'] for it in items]
    if sorted(official) != sorted(authored):
        errors.append(f'글자 목록 불일치: 누락 {"".join(sorted(set(official) - set(authored)))} / 초과 {"".join(sorted(set(authored) - set(official)))}')
    if len(set(authored)) != len(authored):
        errors.append('중복 항목: ' + ''.join(k for k in set(authored) if authored.count(k) > 1))
    check_items(items, J, KD, HD, errors, warns, infos)
    by = {it['k']: it for it in items}
    order = sorted((k for k in official if k in by), key=lambda k: (KD[k]['freq'], k))   # 빈도순
    themes, out = {}, []
    for k in order:
        it, rds = by[k], parse_readings(J[k]['rd'])
        th = theme_of(rds)
        themes.setdefault(th, []).append(k)
        paths = kvg_paths(k)
        if len(paths) != J[k]['sc']:
            errors.append(f'{k}: 획순 {len(paths)}획 ≠ 상용한자표 {J[k]["sc"]}획')
        exs = []
        for w, y, r, m in it['ex']:
            stem = kata2hira(next(x for x in rds if x['r'] == r)['stem'])
            cand = [(y.find(f), len(f), ch) for f, ch in variants(stem) if f in y]
            hs, hl, ch = min(cand, key=lambda c: abs(c[0] - w.find(k) / max(1, len(w)) * len(y))) if cand else (0, 0, False)
            info = jm().get((w, y))
            exs.append(dict(w=w, y=y, r=r, m=m, hs=hs, hl=hl, ch=ch, rare=next(x for x in rds if x['r'] == r)['rare'], cm=bool(info and info[0])))
        o = dict(k=k, g=g, sc=J[k]['sc'], rad=J[k]['rad'], theme=th, hun=it['hun'], m=it['m'], rd=rds, ex=exs, sp=[], st=paths,
                 core=it['core'], kk=KNAME[lv[k]], basic=True)
        if it.get('t'): o['t'] = it['t']
        out.append(o)
    rows = [n for n, _ in ROWS if n in themes]
    data = dict(grade=g, themes=[dict(name=n, e='', ks=''.join(themes[n])) for n in rows], items=sorted(out, key=lambda o: (rows.index(o['theme']), order.index(o['k']))))
    js = f'window.KANJI_GRADES=window.KANJI_GRADES||{{}};window.KANJI_GRADES[{g}]=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n'
    rep = [f'[{CNAME[g]} 코스] 공식 {len(official)}자 / 작성 {len(authored)}자 / 예시 {sum(len(o["ex"]) for o in out)}개',
           f'오류 {len(errors)}건, 경고 {len(warns)}건, 참고 {len(infos)}건']
    rep += ['ERR ' + e for e in errors] + ['WARN ' + w for w in warns] + ['INFO ' + i for i in infos]
    open(os.path.join(HERE, f'verify_g{g}.txt'), 'w', encoding='utf-8').write('\n'.join(rep) + '\n')
    print('\n'.join(rep[:2 + len(errors) + len(warns)]))
    if errors:
        return 1
    open(os.path.join(ROOT, 'data', f'g{g}.js'), 'w', encoding='utf-8').write(js)
    write_index()
    print('data size:', len(js.encode('utf-8')), 'bytes')
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
