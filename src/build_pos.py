# -*- coding: utf-8 -*-
"""
🎧 품사별 듣기 빌드 → data/pos.js + data/audio/pos01.mp3
  낱말 하나 = 한국어 문장 → 일본어 여성 → 일본어 남성 → 원형(일본어 여성, 조금 천천히)
  파일 하나에 모두 이어 붙이고 낱말마다 시각(at)을 기록 → 앱은 같은 파일 안에서 위치만 옮겨 '섞어서 무한 재생'
  (아이폰은 화면이 꺼진 동안 새 파일을 못 불러오므로 파일 하나로)
  검증: 활용어 목록의 모든 동사·형용사에 문장이 하나씩 있는지, 읽기 대조(build_listen.tts_text), 잘린 음성 재생성
사용: python build_pos.py
"""
import asyncio, hashlib, json, os, re, subprocess, sys, wave
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from build import _tagger, ROOT, write_index
from build_listen import VOICE, CACHE, OUT, SR, KBPS, tts_text, ko_tts, pcm, silence, strip
import gram_src as G
from build_gram import parse
from pos_src import POS

BASE_RATE = '-15%'                      # 원형은 조금 천천히
GAP = {'lead': 0.5, 'k': 0.6, 'f': 0.6, 'm': 0.8, 'tail': 1.6}

def cpath(voice, text, rate=''):
    return os.path.join(CACHE, hashlib.sha1(f'{voice}|{text}|{rate}'.encode()).hexdigest()[:16] + '.mp3') if rate else \
           os.path.join(CACHE, hashlib.sha1(f'{voice}|{text}'.encode()).hexdigest()[:16] + '.mp3')

async def synth(jobs):
    import edge_tts
    sem = asyncio.Semaphore(4)
    async def one(voice, text, fn, rate):
        async with sem:
            for attempt in range(3):
                try:
                    c = edge_tts.Communicate(text, voice, rate=rate) if rate else edge_tts.Communicate(text, voice)
                    await c.save(fn + '.part'); os.replace(fn + '.part', fn); return
                except Exception:
                    if attempt == 2: raise
                    await asyncio.sleep(2)
    await asyncio.gather(*(one(*j) for j in jobs))

# 원형 음성: は·へ로 시작하는 가나 낱말은 음성 엔진이 첫 글자를 조사(わ·え)로 읽음 (はいる → わいる) → 가타카나로 넘김
kata = lambda s: ''.join(chr(ord(c) + 0x60) if 'ぁ' <= c <= 'ゖ' else c for c in s)
base_tts = lambda y: (kata(y) if y[0] in 'はへ' else y) + '。'

def too_short(fn, text):
    return len(pcm(fn)) / 2 / SR < 0.35 + 0.045 * len(re.sub(r'[\s、。，．！？!?…「」]', '', text))

def main():
    errors, infos = [], []
    verbs = parse(G.VERBS_N5, 5) + parse(G.VERBS_N4, 4); adjs = parse(G.ADJS_N5, 5) + parse(G.ADJS_N4, 4)
    meta = {r[0]: r for r in verbs + adjs}           # 표기 → [표기, 읽기, 그룹/품사, 뜻, 급수]
    tagger = _tagger()
    items, jobs = [], []
    for t, name, L in POS:
        want = [r[0] for r in (verbs if t == 'v' else [a for a in adjs if a[2] == t])]
        got = [x[0] for x in L]
        for w in want:
            if w not in got: errors.append(f'{name}: {w} 문장 없음')
        for w, j, y, k in L:
            if w not in meta: errors.append(f'{name}: {w} 활용어 목록에 없음'); continue
            if j.count('[') != j.count(']'): errors.append(f'{w}: [ ] 짝'); continue
            try: tt = tts_text(tagger, j, y, infos, f'{t}:{w}')
            except ValueError as e: errors.append(str(e)); continue
            m = meta[w]; base = base_tts(m[1])
            items.append(dict(t=t, w=w, wy=m[1], ko=m[3], g=m[2] if t == 'v' else '', lv=m[4], j=j, y=y, k=k, tt=tt, base=base))
            jobs += [(VOICE['k'], ko_tts(k), cpath(VOICE['k'], ko_tts(k)), ''), (VOICE['f'], tt, cpath(VOICE['f'], tt), ''),
                     (VOICE['m'], tt, cpath(VOICE['m'], tt), ''), (VOICE['f'], base, cpath(VOICE['f'], base, BASE_RATE), BASE_RATE)]
    if errors:
        print('\n'.join('ERR ' + e for e in errors)); return 1
    uniq = list({j[2]: j for j in jobs}.values())
    todo = [j for j in uniq if not os.path.exists(j[2])]
    print(f'음성 {len(uniq)}개 중 새로 만들 것 {len(todo)}개')
    if todo: asyncio.run(synth(todo))
    for attempt in range(4):
        bad = [j for j in uniq if too_short(j[2], j[1])]
        if not bad: break
        print(f'잘린 음성 {len(bad)}개 → 다시 만듦 ({attempt + 1}회차)')
        for j in bad:
            for f in (j[2], j[2][:-4] + '.wav'):
                if os.path.exists(f): os.remove(f)
        asyncio.run(synth(bad))
    else:
        print(f'ERR 잘린 음성이 계속 남음: {len(bad)}개'); return 1
    # 이어 붙이기 (파일 하나)
    wav = os.path.join(CACHE, '_pos01.wav'); mp3 = os.path.join(OUT, 'pos01.mp3'); t = 0.0
    with wave.open(wav, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        def add(b):
            nonlocal t
            w.writeframes(b); t += len(b) / 2 / SR
        for it in items:
            at = [round(t, 2)]; add(silence(GAP['lead']))
            for v, txt, rate in (('k', ko_tts(it['k']), ''), ('f', it['tt'], ''), ('m', it['tt'], ''), ('b', it['base'], BASE_RATE)):
                at.append(round(t, 2)); add(pcm(cpath(VOICE['f' if v == 'b' else v], txt, rate)))
                if v != 'b': add(silence(GAP[v]))
            at.append(round(t, 2)); add(silence(GAP['tail'])); at.append(round(t, 2))
            it['at'] = at                            # [시작, 한국어, 여성, 남성, 원형, 원형 끝, 끝]
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', wav, '-ac', '1', '-ar', str(SR), '-codec:a', 'libmp3lame', '-b:a', KBPS, mp3], check=True)
    h = hashlib.md5(open(mp3, 'rb').read()).hexdigest()[:8]
    out = [{k: v for k, v in it.items() if k not in ('tt', 'base')} for it in items]
    js = 'window.POSD=' + json.dumps(dict(v=f'data/audio/pos01.mp3?v={h}', dur=round(t, 2), items=out), ensure_ascii=False, separators=(',', ':')) + ';\n'
    open(os.path.join(ROOT, 'data', 'pos.js'), 'w', encoding='utf-8').write(js)
    write_index()
    rep = [f'낱말 {len(items)} (い {sum(i["t"] == "i" for i in items)} · な {sum(i["t"] == "na" for i in items)} · 동사 {sum(i["t"] == "v" for i in items)}) · {t / 60:.1f}분 · {os.path.getsize(mp3) / 1e6:.1f}MB',
           f'오류 0건, 참고 {len(infos)}건'] + ['INFO ' + i for i in infos]
    open(os.path.join(HERE, 'verify_pos.txt'), 'w', encoding='utf-8').write('\n'.join(rep) + '\n')
    print('\n'.join(rep[:2]))
    return 0

if __name__ == '__main__':
    sys.exit(main())
