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
import hashlib, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# 원천데이터 폴더: 환경변수 KANJI_REF, 없으면 앱 폴더 옆 '일본어한자_원천데이터'
REF_DIR = os.environ.get('KANJI_REF') or os.path.join(os.path.dirname(ROOT), '일본어한자_원천데이터')
TYPES = {'상형', '지사', '회의', '형성', '가차', '회의 겸 형성', '국자'}  # 글자 구성 유형 허용값

def load_content(grade):
    """content_gN.json 한 파일, 또는 content_gN_themes.json + content_gN_p*.json 여러 파일을 합침"""
    one = os.path.join(HERE, f'content_g{grade}.json')
    if os.path.exists(one):
        return json.load(open(one, encoding='utf-8'))
    th = json.load(open(os.path.join(HERE, f'content_g{grade}_themes.json'), encoding='utf-8'))
    parts = sorted((f for f in os.listdir(HERE) if re.match(rf'^content_g{grade}_p\d+\.json$', f)),
                   key=lambda f: int(re.findall(r'_p(\d+)', f)[0]))
    items = []
    for f in parts:
        items += json.load(open(os.path.join(HERE, f), encoding='utf-8'))['items']
    return dict(grade=grade, themes=th['themes'], items=items)

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

OC_VALUES = {'확실', '통설', '불확실'}   # 유래 신뢰도

def _tagger():
    """예문 읽기 대조용 형태소 분석기 (없으면 None — 검사 생략)"""
    try:
        import fugashi
        return fugashi.Tagger()
    except Exception:
        return None

def analyzer_reading(tagger, sent):
    """형태소 분석기가 본 문장 읽기(히라가나). 숫자+月·日本 등은 틀리게 읽으므로 '참고용'으로만 사용"""
    out = []
    for w in tagger(sent):
        kana = getattr(w.feature, 'kana', None)
        out.append(kata2hira(kana) if kana and kana != '*' else w.surface)
    return ''.join(out)

def check_v2(k, it, rds, exs, J, common, tagger, errors, warns, infos):
    """2차 설계 항목 검증 — core·caution·sent·confuse·oc·kr"""
    rset = {r['r'] for r in rds}
    core = it.get('core', [])
    if not (1 <= len(core) <= 3):
        errors.append(f'{k}: 핵심 읽기(core)는 1~3개여야 함 (현재 {len(core)})')
    for c in core:
        if c not in rset:
            errors.append(f'{k}: 핵심 읽기 "{c}" 가 상용한자표 음훈 {sorted(rset)} 에 없음')
    n = len(it.get('ex', []))
    avail = sum(1 for x in common if k in x.split('|')[0])   # 이 한자가 든 흔한 말 수
    if n < 3 and n >= 1 and avail < 3:
        infos.append(f'{k}: 대표 단어 {n}개 — 흔한 말이 {avail}개뿐이라 억지로 채우지 않음')
    elif not (3 <= n <= 7):
        warns.append(f'{k}: 대표 단어 {n}개 (3~7개 권장)')
    for e in exs:
        if not e['cm']:
            infos.append(f'{k}: 대표 단어 "{e["w"]}({e["y"]})" 는 JMdict 흔한 말 표시 없음')
    words = {e['w'] for e in exs}
    for w, note in it.get('kr', []):
        if w not in words:
            errors.append(f'{k}: 한국어 뜻 차이(kr) 단어 "{w}" 가 대표 단어에 없음')
        if not note:
            errors.append(f'{k}: 한국어 뜻 차이(kr) "{w}" 설명 비어 있음')
    for c in it.get('caution', []):
        if len(c) != 3 or k not in c[0] or re.search(r'[ァ-ヶ\s]', c[1]):
            errors.append(f'{k}: 주의할 읽기 형식 오류 {c} ([단어, 히라가나 읽기, 한 줄 설명])')
    sents = it.get('sent', [])
    if not sents:
        errors.append(f'{k}: 예문(sent) 없음')
    for s in sents:
        if len(s) != 4:
            errors.append(f'{k}: 예문 형식 오류 (필요: [문장, 히라가나 읽기, 한국어 번역, 대상 단어])'); continue
        jp, yomi, ko, tw = s
        if tw not in jp:
            errors.append(f'{k}: 예문 "{jp}" 에 대상 단어 "{tw}" 없음')
        ex = next((e for e in exs if e['w'] == tw), None)
        if not ex:
            errors.append(f'{k}: 예문 대상 단어 "{tw}" 가 대표 단어(ex)에 없음')
        elif ex['y'] not in yomi.replace(' ', ''):
            errors.append(f'{k}: 예문 읽기에 대상 단어 읽기 "{ex["y"]}" 가 없음')
        if re.search(r'[ァ-ヶ]', yomi) and not re.search(r'[ァ-ヶ]', jp):
            errors.append(f'{k}: 예문 읽기에 가타카나 (원문이 가타카나가 아니면 히라가나로)')
        if tagger:
            ar = analyzer_reading(tagger, jp)
            mine = yomi.replace(' ', '')
            if kata2hira(ar) != kata2hira(mine):
                infos.append(f'{k}: 예문 읽기 확인 필요 — 작성 "{mine}" / 분석기 "{ar}"')
    for c in it.get('confuse', []):
        if len(c) != 2 or c[0] == k or not c[1]:
            errors.append(f'{k}: 혼동 한자 형식 오류 {c} ([한자, 한 줄 차이])')
    if it.get('oc') not in OC_VALUES:
        errors.append(f'{k}: 유래 신뢰도(oc)는 {sorted(OC_VALUES)} 중 하나')

def write_index():
    """data/index.js — 준비된 학년 목록 + 파일 내용 해시(=버전). 앱이 주소에 붙여 서버 캐시(최대 10분)의 옛 파일을 피함.
    활용어·단어장·가나 획순 자료(gram.js·vocab.js·kana.js)의 버전도 함께 기록 (build_gram.py·build_kana.py 도 이 함수를 씀)"""
    dd = os.path.join(ROOT, 'data')
    avail = sorted(int(f[1:-3]) for f in os.listdir(dd) if re.match(r'^g\d\.js$', f))
    md5 = lambda p: hashlib.md5(open(p, 'rb').read()).hexdigest()[:8]
    ver = {str(g): md5(os.path.join(dd, f'g{g}.js')) for g in avail}
    fv = lambda name: md5(os.path.join(dd, name)) if os.path.exists(os.path.join(dd, name)) else ''
    open(os.path.join(dd, 'index.js'), 'w', encoding='utf-8').write(
        f'window.KANJI_AVAILABLE={json.dumps(avail)};window.KANJI_VER={json.dumps(ver)};'
        f'window.GRAM_VER={json.dumps(fv("gram.js"))};window.VOCAB_VER={json.dumps(fv("vocab.js"))};window.KANA_VER={json.dumps(fv("kana.js"))};window.LISTEN_VER={json.dumps(fv("listen.js"))};window.POS_VER={json.dumps(fv("pos.js"))};\n')

def main(grade):
    J = json.load(open(os.path.join(REF_DIR, 'jouyou.json'), encoding='utf-8'))
    cw_path = os.path.join(REF_DIR, 'freq', 'common_words.json')
    common = json.load(open(cw_path, encoding='utf-8')) if os.path.exists(cw_path) else {}
    tagger = _tagger()
    v2_count = 0
    KD = json.load(open(os.path.join(REF_DIR, 'kd_grades.json'), encoding='utf-8'))
    C = load_content(grade)
    extra = os.path.join(HERE, 'ko_extra.json')   # 한국음 보정 (근거는 파일 안에)
    if os.path.exists(extra):
        for kk, v in json.load(open(extra, encoding='utf-8')).items():
            if kk in KD and isinstance(v, list):
                KD[kk]['ko'] = KD[kk]['ko'] + [v[0]]
    report, errors, warns, infos = [], [], [], []

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
        it = by_k.get(k)
        if not it:
            continue  # 누락은 ①에서 이미 오류로 보고됨
        # ⓪ 필수 항목·형식 검증
        for f in ('hun', 'm', 'e', 't', 'p', 'o', 'mm', 'ad', 'tip', 'ex'):
            if not it.get(f):
                errors.append(f'{k}: 필수 항목 "{f}" 비어 있음')
        if it.get('t') not in TYPES:
            errors.append(f'{k}: 구성 유형 "{it.get("t")}" 은 허용값 {sorted(TYPES)} 이 아님')
        if '형성' in (it.get('t') or '') and '소리' not in (it.get('p') or ''):
            warns.append(f'{k}: 형성자인데 구성(p)에 "소리 ○○" 표시가 없음')
        if len((it.get('hun') or '').split()) < 2:
            warns.append(f'{k}: 훈음 "{it.get("hun")}" 이 "뜻 음" 형식이 아님')
        if len(it.get('ex', [])) < 2 and len(parse_readings(J[k]['rd'])) > 1:
            warns.append(f'{k}: 예시 단어가 {len(it.get("ex", []))}개뿐 (2개 이상 권장)')
        for e in it.get('ex', []):
            if re.search(r'[ァ-ヶ\s]', e[1]):
                errors.append(f'{k}: 예시 "{e[0]}" 의 읽기 "{e[1]}" 에 가타카나/공백 포함 (히라가나만)')
        rds = parse_readings(J[k]['rd'])
        # 주요(드물지 않은) 읽기 중 예시가 하나도 없는 것 → 경고
        used = {e[2] for e in it.get('ex', [])}
        for r in rds:
            if not r['rare'] and r['r'] not in used and not any(u.split('-')[0] == r['stem'] for u in used):
                infos.append(f'{k}: 읽기 "{r["r"]}" 의 예시 없음')
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
            # 후보: 모든 변형 × 모든 위치. 단어 속 한자의 상대 위치에 가장 가까운 것 선택
            # (예: 皇后 こうごう — 后는 앞의 こう가 아니라 뒤의 ごう)
            idx = w.find(k)
            expect = (idx / max(1, len(w))) * len(yomi)
            cands = []
            for form, changed in variants(stem_h):
                start = 0
                while True:
                    pos = yomi.find(form, start)
                    if pos < 0:
                        break
                    cands.append((abs(pos - expect) + (0.5 if changed else 0), pos, len(form), changed))
                    start = pos + 1
            hit = min(cands)[1:] if cands else None
            if not hit:
                errors.append(f'{k}: 예시 "{w}({yomi})" 안에서 읽기 "{stem_h}" 를 찾지 못함')
                continue
            if hit[2]:
                n_changed += 1
            ex = dict(w=w, y=yomi, r=tgt, m=mean, hs=hit[0], hl=hit[1], ch=hit[2], rare=r['rare'],
                      cm=f'{w}|{yomi}' in common)   # cm = JMdict '흔한 말' 여부
            if amb:
                ex['amb'] = True
            kr = next((n for ww, n in it.get('kr', []) if ww == w), None)   # 한국어와 뜻이 다른 한자어
            if kr:
                ex['kr'] = kr
            exs.append(ex)
        for w, yomi, mean, note in it.get('sp', []):
            if k not in w:
                errors.append(f'{k}: 특별 읽기 "{w}" 에 해당 한자 없음')
        paths = kvg_paths(k)
        # ③ 획수 검증: KanjiVG 획 수 = 상용한자표 총획
        if len(paths) != J[k]['sc']:
            errors.append(f'{k}: 획순 데이터 {len(paths)}획 ≠ 상용한자표 {J[k]["sc"]}획')
        theme = next(t['name'] for t in C['themes'] if k in t['ks'])
        v2 = 'core' in it   # 2차 설계 항목이 작성된 글자만 검증
        if v2:
            v2_count += 1
            check_v2(k, it, rds, exs, J, common, tagger, errors, warns, infos)
        out = dict(
            k=k, g=grade, sc=J[k]['sc'], rad=J[k]['rad'], theme=theme,
            hun=it['hun'], m=it['m'], e=it.get('e', ''), t=it['t'], p=it['p'],
            o=it['o'], mm=it['mm'], ad=it['ad'], tip=it.get('tip', ''),
            rd=rds, ex=exs,
            sp=[dict(w=a, y=b, m=c, n=d) for a, b, c, d in it.get('sp', [])],
            st=paths)
        if v2:
            out.update(core=it['core'], oc=it['oc'],
                       caution=[dict(w=a, y=b, n=c) for a, b, c in it.get('caution', [])],
                       sent=[dict(j=a, y=b, ko=c, w=d) for a, b, c, d in it.get('sent', [])],
                       confuse=[dict(k=a, n=b) for a, b in it.get('confuse', [])])
        out_items.append(out)

    data = dict(grade=grade, themes=C['themes'], items=out_items)
    js = f'window.KANJI_GRADES=window.KANJI_GRADES||{{}};window.KANJI_GRADES[{grade}]=' + \
         json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n'
    open(os.path.join(ROOT, 'data', f'g{grade}.js'), 'w', encoding='utf-8').write(js)
    write_index()

    report.append(f'[{grade}학년] 공식 {len(official)}자 / 작성 {len(authored)}자 / 예시 {n_ex}개 (소리 변화 {n_changed}개) / 2차 항목 작성 {v2_count}자')
    report.append(f'오류 {len(errors)}건, 경고 {len(warns)}건, 참고 {len(infos)}건(예시 없는 읽기)')
    report += ['ERR ' + e for e in errors] + ['WARN ' + w for w in warns] + ['INFO ' + i for i in infos]
    txt = '\n'.join(report)
    open(os.path.join(HERE, f'verify_g{grade}.txt'), 'w', encoding='utf-8').write(txt + '\n')
    print(txt)
    print('data size:', len(js.encode('utf-8')), 'bytes')
    return 1 if errors else 0

if __name__ == '__main__':
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 1))
