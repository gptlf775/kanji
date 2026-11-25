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
# 2단계(학습용 완성 카드): src/content_g{7..10}_qN.json (작성 기준: src/AUTHORING_ms2.md) — 있으면 1단계 카드를 글자별로 대체
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

S2_FIELDS = ('e', 't', 'p', 'o', 'oc', 'mm', 'ad', 'tip', 'sent')   # 2단계(학습용 완성 카드) 필수 항목
_CM = _TG = None

def is_full(it):
    """2단계 내용이 작성된 항목인가 (하나라도 있으면 2단계로 보고 전부 검사)"""
    return any(f in it for f in ('mm', 'o', 'sent'))

def common():
    global _CM
    if _CM is None:
        p = os.path.join(REF_DIR, 'freq', 'common_words.json')
        _CM = json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}
    return _CM

LV = json.load(open(os.path.join(HERE, 'kanken_ms.json'), encoding='utf-8'))['levels']   # 글자 → 급 (코스 배정)
_FH = None
def fuhyo():
    """상용한자표 부표 127어 [(단어, 읽기)] — src/fuhyo.txt"""
    global _FH
    if _FH is None:
        lines = [l for l in open(os.path.join(HERE, 'fuhyo.txt'), encoding='utf-8-sig') if not l.startswith('#')]
        _FH = [tuple(x.split(':')) for x in ' '.join(lines).split()]
    return _FH

def tagger():
    global _TG
    if _TG is None:
        from build import _tagger
        _TG = _tagger() or False
    return _TG or None

def check_full(k, it, rds, errors, warns, infos):
    """2단계 항목 검사 — 초등 build.py 와 같은 기준 (필수 항목·유형·형성자 소리·sp + check_v2)"""
    from build import TYPES, check_v2
    for f in S2_FIELDS:
        if not it.get(f):
            errors.append(f'{k}: 2단계 필수 항목 "{f}" 비어 있음')
    if it.get('t') not in TYPES:
        errors.append(f'{k}: 구성 유형 "{it.get("t")}" 은 허용값 {sorted(TYPES)} 이 아님')
    if '형성' in (it.get('t') or '') and '소리' not in (it.get('p') or ''):
        errors.append(f'{k}: 형성자인데 구성(p)에 "소리 ○○" 표시가 없음')
    e = it.get('e', '')
    if not e or re.search(r'[가-힣ぁ-ヶ一-鿿A-Za-z0-9]', e) or len(e) > 8:
        errors.append(f'{k}: 이모지(e) "{e}" 는 이모지 1개')
    for f in ('o', 'mm', 'ad', 'tip'):
        if re.search(r'[ァ-ヶ]{2,}', it.get(f, '')) and f in ('mm',):
            infos.append(f'{k}: {f} 에 가타카나 — 어린이용 이야기에 일본 글자가 꼭 필요한지 확인')
    if len(it.get('mm', '')) > 90:
        warns.append(f'{k}: 외우기 이야기(mm) {len(it["mm"])}자 — 1~2문장(90자 이내)로')
    if len(it.get('o', '')) > 200:
        warns.append(f'{k}: 유래(o) {len(it["o"])}자 — 1~3문장(200자 이내)로')
    for s in it.get('sp', []):
        if len(s) != 4 or k not in s[0] or re.search(r'[ァ-ヶ\s]', s[1]):
            errors.append(f'{k}: 특별 읽기(sp) 형식 오류 {s} ([단어, 히라가나 읽기, 뜻, 설명])')
    # 상용한자표 부표(src/fuhyo.txt)와 대조: 이 글자가 든 부표 단어가 sp에 빠졌거나 읽기가 다르면 오류
    sp = {s[0]: s[1] for s in it.get('sp', []) if len(s) == 4}
    for w, y in fuhyo():
        if k in w and w not in sp and not (w + '歳' in sp):
            errors.append(f'{k}: 부표 특별 읽기 "{w}({y})" 가 sp에 없음')
        elif k in w and sp.get(w) != y:
            errors.append(f'{k}: 부표 "{w}" 읽기는 {y} (sp: {sp.get(w)})')
    cm = common()
    exs = [dict(w=e[0], y=e[1], cm=f'{e[0]}|{e[1]}' in cm) for e in it.get('ex', []) if len(e) >= 4]
    # '흔한 말이 몇 개인가'는 상용 읽기로 읽는 말만 셈 (危虞 きぐ처럼 상용표 밖 읽기는 예시로 못 쓰므로)
    forms = {f for r in rds for f, _ in variants(kata2hira(r['stem']))}
    cm_k = {key: v for key, v in cm.items() if k in key.split('|')[0] and any(f in key.split('|')[-1] for f in forms)}
    check_v2(k, it, rds, exs, None, cm_k, tagger(), errors, warns, infos)

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
        full = is_full(it)
        if full:
            check_full(k, it, rds, errors, warns, infos)   # core 1~3개·sent 등은 여기서
            for s in it.get('sent', []):
                tw = s[3] if len(s) > 3 else ''   # 대상 단어 안의 글자(脂肪의 脂 등)는 단어째 배우므로 제외
                # 예문 속 다른 한자는 초등 + 이 글자보다 앞 코스(중2 카드면 중1까지)만
                hard = [c for c in (s[0] if s else '') if '一' <= c <= '鿿' and c != k and c not in tw
                        and J.get(c, {}).get('g') not in tuple('123456') and not (c in LV and k in LV and COURSE[LV[c]] < COURSE[LV[k]])]
                if hard:
                    warns.append(f'{k}: 예문에 아직 안 배운 한자 {"".join(hard)} — 히라가나로')
        elif not (1 <= len(core) <= 2):
            errors.append(f'{k}: 핵심 읽기(core) 1~2개 (현재 {len(core)})')
        for c in core:
            if c not in rset and not full:
                errors.append(f'{k}: 핵심 읽기 "{c}" 가 상용한자표 음훈 {sorted(rset)} 에 없음')
        exs = it.get('ex', [])
        if not (1 <= len(exs) <= (6 if full else 5)):
            errors.append(f'{k}: 예시 단어 {len(exs)}개 (1~{6 if full else 5}개, 보통 3~4개)')
        elif len(exs) < 2:
            infos.append(f'{k}: 예시 단어 1개')
        if full and core and not any(len(e) >= 3 and e[2] in core for e in exs):
            errors.append(f'{k}: 핵심 읽기 {core} 로 읽는 예시 단어가 하나도 없음')
        for e in exs:
            if len(e) == 5 and full and e[4] in (0, 1):
                e = e[:4]
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

def load_parts(g, stage2=True):
    """1단계 content_g{g}_pN.json 에 2단계 content_g{g}_qN.json 을 글자별로 덮어씀 (2단계가 있는 글자만)"""
    items = []
    for f in sorted(os.listdir(HERE)):
        if re.match(rf'^content_g{g}_p\d+\.json$', f):
            items += json.load(open(os.path.join(HERE, f), encoding='utf-8'))['items']
    if stage2:
        full = {}
        for f in sorted(os.listdir(HERE)):
            if re.match(rf'^content_g{g}_q\d+\.json$', f):
                full.update({it['k']: it for it in json.load(open(os.path.join(HERE, f), encoding='utf-8-sig'))['items']})
        items = [full.get(it['k'], it) for it in items] + [it for k, it in full.items() if k not in {x['k'] for x in items}]
    return items

def diff_stage1(items, infos):
    """2단계에서 1단계 값(hun·m·core)을 바꾼 글자 — 보고용"""
    base = {}
    for g in (7, 8, 9, 10):
        base.update({it['k']: it for it in load_parts(g, stage2=False)})
    for it in items:
        b = base.get(it['k'])
        if b:
            for f in ('hun', 'm', 'core'):
                if b.get(f) != it.get(f):
                    infos.append(f'{it["k"]}: 1단계 {f} 변경 {b.get(f)} → {it.get(f)}')

def main(argv):
    from prep_ms import kanjidic, hangul_dict
    J = json.load(open(os.path.join(REF_DIR, 'jouyou.json'), encoding='utf-8'))
    KD, HD = kanjidic(), hangul_dict()
    lv = json.load(open(os.path.join(HERE, 'kanken_ms.json'), encoding='utf-8'))['levels']
    errors, warns, infos = [], [], []
    if argv[0] == '--check':
        items = json.load(open(argv[1], encoding='utf-8-sig'))['items']
        check_items(items, J, KD, HD, errors, warns, infos)
        ks = [it.get('k') for it in items]
        if len(set(ks)) != len(ks):
            errors.append('중복 항목: ' + ''.join(k for k in set(ks) if ks.count(k) > 1))
        diff_stage1(items, infos)
        print(f'{argv[1]}: {len(items)}자 (2단계 {sum(map(is_full, items))}자) · 오류 {len(errors)} · 경고 {len(warns)} · 참고 {len(infos)}')
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
        krs = dict((w, n) for w, n in it.get('kr', []))
        for w, y, r, m, *rest in it['ex']:
            stem = kata2hira(next(x for x in rds if x['r'] == r)['stem'])
            cand = [(y.find(f), len(f), ch) for f, ch in variants(stem) if f in y]
            hs, hl, ch = min(cand, key=lambda c: abs(c[0] - w.find(k) / max(1, len(w)) * len(y))) if cand else (0, 0, False)
            info = jm().get((w, y))
            ex = dict(w=w, y=y, r=r, m=m, hs=hs, hl=hl, ch=ch, rare=next(x for x in rds if x['r'] == r)['rare'], cm=bool(info and info[0]))
            if rest and rest[0]: ex['amb'] = True        # 다른 읽기도 맞는 단어 → 읽기 문제에서 제외
            if w in krs: ex['kr'] = krs[w]               # 한국어와 뜻이 다른 한자어
            exs.append(ex)
        o = dict(k=k, g=g, sc=J[k]['sc'], rad=J[k]['rad'], theme=th, hun=it['hun'], m=it['m'], rd=rds, ex=exs, sp=[], st=paths,
                 core=it['core'], kk=KNAME[lv[k]], basic=True)
        if it.get('t'): o['t'] = it['t']
        if is_full(it):     # 2단계 완성 카드 → 학습(오늘의 공부)에 나옴 (basic 없음)
            del o['basic']
            o.update(e=it['e'], t=it['t'], p=it['p'], o=it['o'], oc=it['oc'], mm=it['mm'], ad=it['ad'], tip=it.get('tip', ''),
                     sp=[dict(w=a, y=b, m=c, n=d) for a, b, c, d in it.get('sp', [])],
                     caution=[dict(w=a, y=b, n=c) for a, b, c in it.get('caution', [])],
                     sent=[dict(j=a, y=b, ko=c, w=d) for a, b, c, d in it.get('sent', [])],
                     confuse=[dict(k=a, n=b) for a, b in it.get('confuse', [])])
        out.append(o)
    rows = [n for n, _ in ROWS if n in themes]
    data = dict(grade=g, themes=[dict(name=n, e='', ks=''.join(themes[n])) for n in rows], items=sorted(out, key=lambda o: (rows.index(o['theme']), order.index(o['k']))))
    js = f'window.KANJI_GRADES=window.KANJI_GRADES||{{}};window.KANJI_GRADES[{g}]=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n'
    rep = [f'[{CNAME[g]} 코스] 공식 {len(official)}자 / 작성 {len(authored)}자 (학습용 완성 {sum(1 for o in out if not o.get("basic"))}자) / 예시 {sum(len(o["ex"]) for o in out)}개',
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
