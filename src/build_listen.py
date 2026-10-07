# -*- coding: utf-8 -*-
"""
🎧 듣기 빌드 → data/listen.js + data/audio/chNN.mp3
  ① 검증: 챕터당 10문장, [ ] 짝, 읽기는 가나만, 형태소 분석기 읽기 대조
           (분석기와 다른 낱말은 음성 문장에서 내 읽기(가나)로 바꿔 넣음 → 日本=にほん, 方=かた 등 잘못 읽기 방지)
  ② 어휘 수준: 단어장(N5·N4 목록)에 없는 낱말은 참고로 표시
  ③ 음성: 한국어(SunHi) → 일본어 여성(Nanami) → 일본어 남성(Keita), edge-tts (원천데이터/tts_cache 에 저장해 재사용)
  ④ 챕터마다 mp3 하나로 이어 붙이고 문장별 시작 시각을 기록 (화면 잠금 중에도 이어 듣기)
사용: python build_listen.py
"""
import asyncio, hashlib, json, os, re, subprocess, sys, wave
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build import REF_DIR, ROOT, _tagger, kata2hira, write_index
from listen_src import CHAPTERS

VOICE = {'k': 'ko-KR-SunHiNeural', 'f': 'ja-JP-NanamiNeural', 'm': 'ja-JP-KeitaNeural'}
CACHE = os.path.join(REF_DIR, 'tts_cache')
OUT = os.path.join(ROOT, 'data', 'audio')
SR = 24000
GAP = {'lead': 0.4, 'title': 1.0, 'k': 0.7, 'f': 0.7, 'm': 1.6}   # 쉬는 시간(초): 한국어 뒤·여성 뒤·남성 뒤(다음 문장 전)
KBPS = '40k'
VOL = 100                                 # 권 파일 하나에 넣을 챕터 수 (100챕터 ≈ 3시간 ≈ 58MB, GitHub 파일 한도 100MB 안) — 권이 나뉘면 잠금 중 다음 권으로 못 넘어감

strip = lambda j: j.replace('[', '').replace(']', '')
ko_tts = lambda k: k.replace('…', '')        # 한국어 음성: 말줄임표는 이상하게 읽혀서 뺌

# 챕터 제목 안내 (한국어 음성): 한국어 음성은 い·な 같은 일본 글자와 ①② 를 건너뛰고 읽으므로 한국어로 바꿔 읽힘
TITLE_KO = {'い형용사': '이 형용사', 'な형용사': '나 형용사', '①': '첫 번째', '②': '두 번째', 'N4': '엔포', '·': ', ', '~': ''}
def title_tts(ci, t):
    a, _, b = t.partition(' — ')
    s = a + (', ' + b if b and re.fullmatch(r'[가-힣 ·]+', b) else '')     # '— 가능형'처럼 한국어면 함께 읽음
    for k, v in TITLE_KO.items(): s = s.replace(k, v)
    s = re.sub(r'\s+', ' ', s).strip()
    if re.search(r'[^가-힣0-9 ,.()]', s): raise ValueError(f'챕터 {ci} 제목에 한국어 음성이 못 읽는 글자: {s}')
    return f'챕터 {ci}. {s}.'

# 음성 엔진이 문맥에 따라 다른 읽기로 읽는 한자 (음성 인식 검수로 확인: 町→ちょう, 何時→いつ, 温める→ぬくめる,
# 十分→じゅっぷん, 開く→ひらく, 辛い→つらい …) — 이 글자가 든 낱말은 항상 작성한 읽기(가나)로 넘김
FORCE_CHARS = set('何町温辛開注描')
FORCE_WORDS = {'十分', '十部'}
NOUNISH = {'名詞', '接頭辞', '接尾辞', '代名詞'}
# 분석기는 わたくし·にっぽん 으로 보지만 음성 엔진은 わたし·にほん 으로 바르게 읽는 낱말 → 한자 그대로 (가나로 바꾸면 앞뒤와 붙어 오히려 잘못 끊김)
KEEP_RE = re.compile(r'(私|日本)(人|語|たち)?')
# 음성 인식 검수에서 걸린 문장: 음성용 문장을 직접 지정 (화면 문장은 그대로)
TTS_FIX = {'銀行は九時から三時までです。': '銀行は、くじから三時までです。',   # わ+くじ 가 '枠'로 붙어 들림
           '道を間違えたみたいです。': 'みちを間違えたみたいです。'}             # 남성 음성이 '日曜'처럼 읽음

def tts_text(tagger, j, y, infos, tag):
    """음성용 문장: 분석기 읽기와 작성 읽기(y)를 낱말마다 맞춰 보고,
    ① 읽기가 다른 낱말 ② 잘못 읽기 쉬운 한자가 든 낱말은 '낱말 전체'를 작성 읽기 가나로 바꿈
    (誕生日처럼 이어진 명사는 한 낱말로 묶어 통째로 — 한 글자만 바꾸면 '誕生び'처럼 어색하게 읽힘)
    ③ 가나로 바꾼 낱말 바로 앞·뒤의 조사 は·へ 는 소리대로 わ·え 로 (가나끼리 붙어 '하·헤'로 읽히는 것 방지)"""
    sent = strip(j); mine = y.replace(' ', ''); mh = kata2hira(mine)
    if sent in TTS_FIX:
        infos.append(f'{tag}: 음성 문장 직접 지정 → {TTS_FIX[sent]}'); return TTS_FIX[sent]
    toks = []
    for w in tagger(sent):
        k = getattr(w.feature, 'kana', None)
        toks.append(dict(s=w.surface, r=kata2hira(k) if k and k != '*' else w.surface, p=getattr(w.feature, 'pos1', '')))
    segs, pos, i = [], 0, 0          # seg = [시작 토큰, 끝 토큰, 작성 읽기 조각, 읽기 일치 여부]
    while i < len(toks):
        r = toks[i]['r']
        if mh.startswith(r, pos):
            segs.append([i, i + 1, mine[pos:pos + len(r)], True]); pos += len(r); i += 1; continue
        found = None
        for k in range(1, 4):        # 다른 낱말: 이어지는 낱말 k개를 묶어, 그다음 낱말 읽기와 다시 맞는 길이 L을 찾음
            nxt = toks[i + k]['r'] if i + k < len(toks) else None
            for L in range(1, 16):
                if (nxt is None and pos + L == len(mh)) or (nxt is not None and nxt and mh.startswith(nxt, pos + L)):
                    found = (k, L); break
            if found or nxt is None: break
        if not found: raise ValueError(f'{tag}: 읽기 맞추기 실패 "{sent}" / {y}')
        k, L = found
        segs.append([i, i + k, mine[pos:pos + L], False]); pos += L; i += k
    if pos != len(mh): raise ValueError(f'{tag}: 읽기 길이 불일치 "{sent}" / {y}')
    # 이어진 명사(한자·숫자 포함)는 한 낱말로 묶기
    isnoun = lambda g: all(toks[t]['p'] in NOUNISH for t in range(g[0], g[1])) and re.search(r'[一-龯々0-9]', ''.join(toks[t]['s'] for t in range(g[0], g[1])))
    groups = []
    for g in segs:
        if groups and isnoun(g) and isnoun(groups[-1][-1]): groups[-1].append(g)
        else: groups.append([g])
    pieces = []                       # [표기, 가나로 바꿨는지, 조사 は·へ 인지]
    for grp in groups:
        surf = ''.join(toks[t]['s'] for g in grp for t in range(g[0], g[1])); kana = ''.join(g[2] for g in grp)
        kanji = re.search(r'[一-龯々]', surf)
        use_kana = kanji and (any(not g[3] for g in grp) or set(surf) & FORCE_CHARS or any(w in surf for w in FORCE_WORDS))
        # 읽기가 다른 부분이 私·日本 뿐이면(毎日日本語 등) 한자 그대로 — 음성 엔진은 이 낱말을 바르게 읽고, 가나로 바꾸면 끊어 읽기가 틀어짐
        bad = [''.join(toks[t]['s'] for t in range(g[0], g[1])) for g in grp if not g[3]]
        if use_kana and bad and all(KEEP_RE.fullmatch(x) for x in bad) and not set(surf) & FORCE_CHARS: use_kana = False
        part = len(grp) == 1 and grp[0][1] - grp[0][0] == 1 and toks[grp[0][0]]['p'] == '助詞' and surf in ('は', 'へ')
        if use_kana and kana != surf: infos.append(f'{tag}: {surf} → 음성은 {kana}')
        pieces.append([kana if use_kana else surf, bool(use_kana), part and surf])
    out = []
    for n, (txt, kn, part) in enumerate(pieces):
        prev_k = n > 0 and pieces[n - 1][1]; next_k = n + 1 < len(pieces) and pieces[n + 1][1]
        if part == 'は' and next_k: txt = 'は、'          # わ로 바꾸면 뒤 가나와 붙어 다른 말로 들림(わ+らいげつ → 笑い) → は 뒤에 쉼표
        elif part == 'へ' and (prev_k or next_k): txt = 'え'
        out.append(txt)
    return ''.join(out)

def vocab_set():
    s = open(os.path.join(ROOT, 'data', 'vocab.js'), encoding='utf-8').read()
    words = json.loads(s[s.index('{'):s.rindex('}') + 1])['words']
    return {w[0] for w in words} | {w[1] for w in words}

async def synth(jobs):
    import edge_tts
    sem = asyncio.Semaphore(4)
    async def one(voice, text, fn):
        async with sem:
            for attempt in range(3):
                try:
                    await edge_tts.Communicate(text, voice).save(fn + '.part'); os.replace(fn + '.part', fn); return
                except Exception as e:
                    if attempt == 2: raise
                    await asyncio.sleep(2)
    await asyncio.gather(*(one(v, t, f) for v, t, f in jobs))

def cache_path(voice, text):
    return os.path.join(CACHE, hashlib.sha1(f'{voice}|{text}'.encode()).hexdigest()[:16] + '.mp3')

def pcm(mp3):
    """mp3 → 24kHz 모노 16bit PCM 바이트 (wav 로 한 번 풀어 둠)"""
    wav = mp3[:-4] + '.wav'
    if not os.path.exists(wav):
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', mp3, '-ac', '1', '-ar', str(SR), '-sample_fmt', 's16', wav], check=True)
    with wave.open(wav) as w: return w.readframes(w.getnframes())

silence = lambda sec: b'\x00\x00' * int(SR * sec)

def main():
    os.makedirs(CACHE, exist_ok=True); os.makedirs(OUT, exist_ok=True)
    errors, infos = [], []
    tagger = _tagger()
    if not tagger: print('형태소 분석기(fugashi) 없음'); return 1
    V = vocab_set()
    jobs, plan = [], []
    for ci, ch in enumerate(CHAPTERS, 1):
        if len(ch['s']) not in (10, 20): errors.append(f'챕터 {ci}: 문장 {len(ch["s"])}개 (10개 또는 20개)')
        try: items = [('k', title_tts(ci, ch['t']))]
        except ValueError as e: errors.append(str(e)); continue
        sents = []
        for si, (j, y, k) in enumerate(ch['s'], 1):
            tag = f'{ci}-{si}'
            if j.count('[') != j.count(']'): errors.append(f'{tag}: [ ] 짝이 안 맞음')
            if re.search(r'[一-龯]', y): errors.append(f'{tag}: 읽기에 한자')
            try: tt = tts_text(tagger, j, y, infos, tag)
            except ValueError as e: errors.append(str(e)); tt = strip(j)
            for w in tagger(strip(j)):
                lem = getattr(w.feature, 'lemma', None) or w.surface
                pos1 = getattr(w.feature, 'pos1', '')
                if pos1 in ('名詞', '動詞', '形容詞') and lem not in V and w.surface not in V and not re.fullmatch(r'[ァ-ヶー・]+', w.surface) and not re.search(r'[0-9０-９]', w.surface):
                    infos.append(f'{tag}: 단어장 밖 낱말 {w.surface}({lem})')
            sents.append(dict(j=j, y=y, k=k, tt=tt))
        plan.append((ci, ch, items, sents))
        for v, t in items: jobs.append((VOICE[v], t, cache_path(VOICE[v], t)))
        for s in sents:
            for v, t in (('k', ko_tts(s['k'])), ('f', s['tt']), ('m', s['tt'])): jobs.append((VOICE[v], t, cache_path(VOICE[v], t)))
    if errors:
        print('\n'.join('ERR ' + e for e in errors)); return 1
    todo = [j for j in {j[2]: j for j in jobs}.values() if not os.path.exists(j[2])]
    print(f'음성 {len(set(j[2] for j in jobs))}개 중 새로 만들 것 {len(todo)}개')
    if todo: asyncio.run(synth(todo))
    # 잘린 음성 검사: 네트워크 문제로 음성이 앞부분만 받아지는 일이 있음 (0.36초짜리 등) → 길이가 글자 수에 비해 너무 짧으면 다시 만듦
    def too_short(v, t, fn):
        sec = len(pcm(fn)) / 2 / SR
        return sec < 0.35 + 0.045 * len(re.sub(r'[\s、。，．！？!?…「」]', '', t))
    for attempt in range(4):
        bad = [j for j in {j[2]: j for j in jobs}.values() if too_short(*j)]
        if not bad: break
        print(f'잘린 음성 {len(bad)}개 → 다시 만듦 ({attempt + 1}회차)')
        for _, _, fn in bad:
            for f in (fn, fn[:-4] + '.wav'):
                if os.path.exists(f): os.remove(f)
        asyncio.run(synth(bad))
    else:
        print(f'ERR 잘린 음성이 계속 남음: {len(bad)}개'); return 1
    chapters = []
    for ci, ch, items, sents in plan:
        buf = [silence(GAP['lead'])]; t = GAP['lead']
        def add(b):
            nonlocal t
            buf.append(b); t += len(b) / 2 / SR
        add(pcm(cache_path(VOICE['k'], items[0][1]))); add(silence(GAP['title']))
        out_s = []
        for s in sents:
            at = []
            for v, txt in (('k', ko_tts(s['k'])), ('f', s['tt']), ('m', s['tt'])):
                at.append(round(t, 2)); add(pcm(cache_path(VOICE[v], txt))); add(silence(GAP[v]))
            at.append(round(t, 2))
            out_s.append(dict(j=s['j'], y=s['y'], k=s['k'], at=at))
        # 챕터 음성은 임시 wav 로 저장 (100챕터를 한꺼번에 메모리에 두지 않음)
        cw = os.path.join(CACHE, f'_ch{ci:03d}.wav')
        with wave.open(cw, 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(b''.join(buf))
        chapters.append(dict(n=ci, t=ch['t'], g=ch['g'], dur=round(t, 2), s=out_s, wav=cw))
    # 권(vol) 파일: 챕터 VOL개를 mp3 하나로 이어 붙임 — 아이폰은 화면이 꺼진 동안 새 파일을 불러오지 못하므로,
    # 챕터가 바뀌어도 같은 파일 안에서 위치만 옮기게 함. off = 권 파일 안에서 챕터가 시작하는 시각(초)
    for f in os.listdir(OUT):
        if f.endswith('.mp3'): os.remove(os.path.join(OUT, f))
    size = 0
    for vi in range(0, len(chapters), VOL):
        vol = chapters[vi:vi + VOL]; name = f'vol{vi // VOL + 1:02d}.mp3'
        off = 0.0
        wav = os.path.join(CACHE, '_' + name[:-4] + '.wav'); mp3 = os.path.join(OUT, name)
        with wave.open(wav, 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
            for c in vol:
                with wave.open(c['wav']) as r: fr = r.readframes(r.getnframes())
                c['off'] = round(off, 3); off += len(fr) / 2 / SR
                w.writeframes(fr)
        # 고정 비트레이트(CBR) — 긴 파일에서도 위치 이동이 정확함
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', wav, '-ac', '1', '-ar', str(SR), '-codec:a', 'libmp3lame', '-b:a', KBPS, mp3], check=True)
        h = hashlib.md5(open(mp3, 'rb').read()).hexdigest()[:8]; size += os.path.getsize(mp3)
        for c in vol:
            c['v'] = f'data/audio/{name}?v={h}'; del c['wav']
    js = 'window.LISTEN=' + json.dumps(dict(ch=chapters, voice='Microsoft Neural (SunHi · Nanami · Keita)'), ensure_ascii=False, separators=(',', ':')) + ';\n'
    open(os.path.join(ROOT, 'data', 'listen.js'), 'w', encoding='utf-8').write(js)
    write_index()
    total = sum(c['dur'] for c in chapters)
    rep = [f'챕터 {len(chapters)} · 문장 {sum(len(c["s"]) for c in chapters)} · 총 {total / 60:.1f}분 · 음성 파일 {size / 1e6:.1f}MB',
           f'오류 0건, 참고 {len(infos)}건'] + ['INFO ' + i for i in infos]
    open(os.path.join(HERE, 'verify_listen.txt'), 'w', encoding='utf-8').write('\n'.join(rep) + '\n')
    print('\n'.join(rep))
    return 0

if __name__ == '__main__':
    sys.exit(main())
