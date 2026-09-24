# -*- coding: utf-8 -*-
"""
일본 초등 한자 앱 — 데이터 빌드 + 자동 검증
입력:
  - src/content_gN.json      : 작성한 설명·예시 (학년별)
  - 원천데이터(REF_DIR)      : jouyou.json(상용한자표 음훈·학년), kd_grades.json(KANJIDIC2 한국음),
                               kvg/*.svg(KanjiVG 획순)
출력:
  - data/gN.js               : 앱이 읽는 학년별 데이터
  - src/verify_gN.txt        : 검증 보고서
사용: python build.py 1   (학년 번호)
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REF_DIR = os.environ.get('KANJI_REF', '')  # 원천데이터 폴더 (환경변수로 지정)

def kata2hira(s):
    # 가타카나 → 히라가나 (U+30A1~30F6 → -0x60)
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)

DAKU = {}
for a, b in zip('かきくけこさしすせそたちつてとはひふへほ', 'がぎぐげござじずぜぞだぢづでどばびぶべぼ'):
    DAKU[a] = [b]
for a, b in zip('はひふへほ', 'ぱぴぷぺぽ'):
    DAKU[a].append(b)

def variants(stem):
    """연탁(첫 글자 탁음화)·촉음화(마지막 く/き/つ/ち→っ) 변형 목록. 반환: [(형태, 변형여부)]"""
    out = [(stem, False)]
    firsts = [stem] + [d + stem[1:] for d in DAKU.get(stem[0], [])]
    for f in firsts:
        if f != stem:
            out.append((f, True))
        if len(f) >= 2 and f[-1] in 'くきつち':
            out.append((f[:-1] + 'っ', True))
    return out

def parse_readings(rd):
    """상용한자표 '音訓' 문자열 → [{r:표기, stem, okuri, on, rare}]"""
    res = []
    for x in rd.split('、'):
        x = x.strip()
        if not x:
            continue
        rare = x.startswith('（') or x.startswith('(')
        x = x.strip('（）()')
        on = bool(re.match(r'^[ァ-ヶー]+$', x))
        stem, _, okuri = x.partition('-')
        res.append(dict(r=x, stem=stem, okuri=okuri, on=on, rare=rare))
    return res

def kvg_paths(ch):
    fn = os.path.join(REF_DIR, 'kvg', f'{ord(ch):05x}.svg')
    s = open(fn, encoding='utf-8').read()
    paths = re.findall(r'<path id="kvg:[0-9a-f]+-s(\d+)"[^>]*\sd="([^"]+)"', s)
    paths.sort(key=lambda p: int(p[0]))
    return [re.sub(r'\s+', ' ', d).strip() for _, d in paths]

def main(grade):
    J = json.load(open(os.path.join(REF_DIR, 'jouyou.json'), encoding='utf-8'))
    KD = json.load(open(os.path.join(REF_DIR, 'kd_grades.json'), encoding='utf-8'))
    C = json.load(open(os.path.join(HERE, f'content_g{grade}.json'), encoding='utf-8'))
    report, errors, warns = [], [], []

    official = [k for k, v in J.items() if v['g'] == str(grade)]
    authored = [it['k'] for it in C['items']]
    theme_ks = ''.join(t['ks'] for t in C['themes'])
    # ① 글자 목록 검증: 공식 배당표와 정확히 일치하는가
    if sorted(official) != sorted(authored):
        errors.append(f'글자 목록 불일치: 누락 {set(official)-set(authored)} / 초과 {set(authored)-set(official)}')
    if len(set(authored)) != len(authored):
        errors.append('중복 항목 있음')
    if sorted(theme_ks) != sorted(official):
        errors.append(f'주제 묶음 불일치: 누락 {set(official)-set(theme_ks)} / 중복·초과 {[c for c in theme_ks if theme_ks.count(c)>1 or c not in official]}')

    by_k = {it['k']: it for it in C['items']}
    out_items = []
    n_ex = n_changed = 0
    for k in theme_ks:  # 학습 순서 = 주제 묶음 순서
        it = by_k[k]
        rds = parse_readings(J[k]['rd'])
        rmap = {r['r']: r for r in rds}
        # ② 한국 음 검증: 훈음의 마지막 음절(들)이 KANJIDIC2 한국음에 포함되는가
        ko_sounds = it['hun'].split()[-1].split('/')
        for s in ko_sounds:
            if s not in KD[k]['ko']:
                warns.append(f'{k}: 한국음 "{s}" 이(가) KANJIDIC2 {KD[k]["ko"]} 에 없음')
        exs = []
        for w, yomi, tgt, mean, *rest in it['ex']:
            amb = bool(rest and rest[0])   # 5번째 값 1 = 다른 읽기도 맞는 단어 → 읽기 문제에서 제외
            n_ex += 1
            if k not in w:
                errors.append(f'{k}: 예시 "{w}" 에 해당 한자 없음')
            r = rmap.get(tgt)
            if not r:
                errors.append(f'{k}: 예시 "{w}" 의 읽기 "{tgt}" 가 상용한자표 음훈 {[x["r"] for x in rds]} 에 없음')
                continue
            stem_h = kata2hira(r['stem'])
            hit = None
            for form, changed in variants(stem_h):
                pos = yomi.find(form)
                if pos >= 0:
                    hit = (pos, len(form), changed)
                    break
            if not hit:
                errors.append(f'{k}: 예시 "{w}({yomi})" 안에서 읽기 "{stem_h}" 를 찾지 못함')
                continue
            if hit[2]:
                n_changed += 1
            ex = dict(w=w, y=yomi, r=tgt, m=mean, hs=hit[0], hl=hit[1], ch=hit[2], rare=r['rare'])
            if amb:
                ex['amb'] = True
            exs.append(ex)
        for w, yomi, mean, note in it.get('sp', []):
            if k not in w:
                errors.append(f'{k}: 특별 읽기 "{w}" 에 해당 한자 없음')
        paths = kvg_paths(k)
        # ③ 획수 검증: KanjiVG 획 수 = 상용한자표 총획
        if len(paths) != J[k]['sc']:
            errors.append(f'{k}: 획순 데이터 {len(paths)}획 ≠ 상용한자표 {J[k]["sc"]}획')
        theme = next(t['name'] for t in C['themes'] if k in t['ks'])
        out_items.append(dict(
            k=k, g=grade, sc=J[k]['sc'], rad=J[k]['rad'], theme=theme,
            hun=it['hun'], m=it['m'], e=it.get('e', ''), t=it['t'], p=it['p'],
            o=it['o'], mm=it['mm'], ad=it['ad'], tip=it.get('tip', ''),
            rd=rds, ex=exs,
            sp=[dict(w=a, y=b, m=c, n=d) for a, b, c, d in it.get('sp', [])],
            st=paths))

    data = dict(grade=grade, themes=C['themes'], items=out_items)
    js = f'window.KANJI_GRADES=window.KANJI_GRADES||{{}};window.KANJI_GRADES[{grade}]=' + \
         json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n'
    open(os.path.join(ROOT, 'data', f'g{grade}.js'), 'w', encoding='utf-8').write(js)
    # 준비된 학년 목록 (앱이 없는 파일을 요청하지 않도록)
    avail = sorted(int(f[1:-3]) for f in os.listdir(os.path.join(ROOT, 'data')) if re.match(r'^g\d\.js$', f))
    open(os.path.join(ROOT, 'data', 'index.js'), 'w', encoding='utf-8').write(f'window.KANJI_AVAILABLE={json.dumps(avail)};\n')

    report.append(f'[{grade}학년] 공식 {len(official)}자 / 작성 {len(authored)}자 / 예시 {n_ex}개 (소리 변화 {n_changed}개)')
    report.append(f'오류 {len(errors)}건, 경고 {len(warns)}건')
    report += ['ERR ' + e for e in errors] + ['WARN ' + w for w in warns]
    txt = '\n'.join(report)
    open(os.path.join(HERE, f'verify_g{grade}.txt'), 'w', encoding='utf-8').write(txt + '\n')
    print(txt)
    print('data size:', len(js.encode('utf-8')), 'bytes')
    return 1 if errors else 0

if __name__ == '__main__':
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 1))
