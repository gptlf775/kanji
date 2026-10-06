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
VOL = 50                                  # 권 파일 하나에 넣을 챕터 수 (50챕터 ≈ 96분 ≈ 29MB, GitHub 파일 한도 100MB 안)

strip = lambda j: j.replace('[', '').replace(']', '')

def tts_text(tagger, j, y, infos, tag):
    """분석기 낱말 읽기와 내 읽기(y)를 맞춰 보고, 다른 낱말은 내 읽기 가나로 바꾼 음성용 문장"""
    sent = strip(j); mine = y.replace(' ', ''); mh = kata2hira(mine)
    toks = [(w.surface, kata2hira(k) if (k := getattr(w.feature, 'kana', None)) and k != '*' else w.surface) for w in tagger(sent)]
    out, pos, i = [], 0, 0
    while i < len(toks):
        surf, r = toks[i]; r = kata2hira(r)
        if mh.startswith(r, pos):
            out.append(surf); pos += len(r); i += 1; continue
        # 다른 낱말: 이어지는 낱말 k개를 묶어 보며, 그다음 낱말 읽기와 다시 맞는 길이 L을 찾음 (日本+人 → にほんじん)
        found = None
        for k in range(1, 4):
            nxt = kata2hira(toks[i + k][1]) if i + k < len(toks) else None
            for L in range(1, 16):
                if (nxt is None and pos + L == len(mh)) or (nxt is not None and nxt and mh.startswith(nxt, pos + L)):
                    found = (k, L); break
            if found or nxt is None: break
        if not found: raise ValueError(f'{tag}: 읽기 맞추기 실패 "{sent}" / {y}')
        k, L = found
        surfs = ''.join(s for s, _ in toks[i:i + k]); ar = ''.join(kata2hira(x) for _, x in toks[i:i + k])
        out.append(mine[pos:pos + L]); infos.append(f'{tag}: {surfs} → 분석기 {ar} / 작성 {mine[pos:pos + L]} (음성은 작성 읽기로)')
        pos += L; i += k
    if pos != len(mh): raise ValueError(f'{tag}: 읽기 길이 불일치 "{sent}" / {y}')
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
        if len(ch['s']) != 10: errors.append(f'챕터 {ci}: 문장 {len(ch["s"])}개 (10개여야 함)')
        title_ko = ch['t'].split(' — ')[0]
        items = [('k', f'챕터 {ci}. {title_ko}.')]
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
            for v, t in (('k', s['k']), ('f', s['tt']), ('m', s['tt'])): jobs.append((VOICE[v], t, cache_path(VOICE[v], t)))
    if errors:
        print('\n'.join('ERR ' + e for e in errors)); return 1
    todo = [j for j in {j[2]: j for j in jobs}.values() if not os.path.exists(j[2])]
    print(f'음성 {len(set(j[2] for j in jobs))}개 중 새로 만들 것 {len(todo)}개')
    if todo: asyncio.run(synth(todo))
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
            for v, txt in (('k', s['k']), ('f', s['tt']), ('m', s['tt'])):
                at.append(round(t, 2)); add(pcm(cache_path(VOICE[v], txt))); add(silence(GAP[v]))
            at.append(round(t, 2))
            out_s.append(dict(j=s['j'], y=s['y'], k=s['k'], at=at))
        chapters.append(dict(n=ci, t=ch['t'], g=ch['g'], dur=round(t, 2), s=out_s, raw=b''.join(buf)))
    # 권(vol) 파일: 챕터 VOL개를 mp3 하나로 이어 붙임 — 아이폰은 화면이 꺼진 동안 새 파일을 불러오지 못하므로,
    # 챕터가 바뀌어도 같은 파일 안에서 위치만 옮기게 함. off = 권 파일 안에서 챕터가 시작하는 시각(초)
    for f in os.listdir(OUT):
        if f.endswith('.mp3'): os.remove(os.path.join(OUT, f))
    size = 0
    for vi in range(0, len(chapters), VOL):
        vol = chapters[vi:vi + VOL]; name = f'vol{vi // VOL + 1:02d}.mp3'
        off = 0.0
        for c in vol:
            c['off'] = round(off, 3); off += len(c['raw']) / 2 / SR
        wav = os.path.join(CACHE, '_' + name[:-4] + '.wav'); mp3 = os.path.join(OUT, name)
        with wave.open(wav, 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(b''.join(c['raw'] for c in vol))
        # 고정 비트레이트(CBR) — 긴 파일에서도 위치 이동이 정확함
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', wav, '-ac', '1', '-ar', str(SR), '-codec:a', 'libmp3lame', '-b:a', KBPS, mp3], check=True)
        h = hashlib.md5(open(mp3, 'rb').read()).hexdigest()[:8]; size += os.path.getsize(mp3)
        for c in vol:
            c['v'] = f'data/audio/{name}?v={h}'; del c['raw']
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
