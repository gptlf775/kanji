# -*- coding: utf-8 -*-
"""
📗 문법장 음성 빌드 → data/audio/bun01.mp3 + src/bun_audio.json (문장별 [시작, 끝])
  대상: 문법장 예문 2개씩(480) + 빈칸 연습 정답 문장(240) — 여성 음성(ja-JP-NanamiNeural) 한 번씩
  읽기: 작성 읽기(y)와 형태소 분석기를 맞춰, 잘못 읽힐 낱말은 가나로 (build_listen.tts_text — 다른 듣기와 같은 방식)
  앱은 data/clips.js(build_clips.py)로 문장 → 파일·구간을 찾아 그 부분만 재생 (휴대폰 기본 음성 대신)
사용: python build_bun_audio.py  → 이어서 python build_clips.py
"""
import asyncio, hashlib, json, os, re, subprocess, sys, wave
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from build import _tagger, ROOT
from build_listen import VOICE, CACHE, OUT, SR, KBPS, tts_text, pcm, silence
from build_pos import cpath, synth, too_short
sys.stdout.reconfigure(encoding='utf-8')
LEAD, TAIL = 0.15, 0.35          # 문장 앞뒤 여백(초) — 구간 재생 때 앞이 잘리지 않게

def sentences():
    s = open(os.path.join(ROOT, 'data', 'bunpo.js'), encoding='utf-8').read()
    B = json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))
    out, seen = [], set()
    for it in B['items']:
        rows = [(e[0], e[1]) for e in it['ex']]
        if it.get('qz'): rows.append((it['qz'][0].replace('（　　）', it['qz'][1]), it['qz'][3]))
        for j, y in rows:
            if j not in seen: seen.add(j); out.append(dict(id=it['id'], j=j, y=y))
    return out

def main():
    os.makedirs(CACHE, exist_ok=True)
    tagger = _tagger(); infos, errors = [], []
    S = sentences()
    for x in S:
        try: x['t'] = tts_text(tagger, x['j'], x['y'], infos, x['id'])
        except ValueError as e: x['t'] = x['y'].replace(' ', ''); infos.append(f'{x["id"]}: 읽기 맞추기 실패 → 가나 전체로 — {x["j"]}')
    jobs = list({cpath(VOICE['f'], x['t']): (VOICE['f'], x['t'], cpath(VOICE['f'], x['t']), '') for x in S}.values())
    todo = [j for j in jobs if not os.path.exists(j[2])]
    print(f'문장 {len(S)} · 음성 {len(jobs)}개 중 새로 만들 것 {len(todo)}개', flush=True)
    if todo: asyncio.run(synth(todo))
    for attempt in range(4):
        bad = [j for j in jobs if too_short(j[2], j[1])]
        if not bad: break
        print(f'잘린 음성 {len(bad)}개 → 다시 ({attempt + 1})', flush=True)
        for j in bad:
            for f in (j[2], j[2][:-4] + '.wav'):
                if os.path.exists(f): os.remove(f)
        asyncio.run(synth(bad))
    else:
        errors.append(f'잘린 음성이 계속 남음 {len(bad)}개')
    if errors: print('\n'.join('ERR ' + e for e in errors)); return 1
    wav = os.path.join(CACHE, '_bun01.wav'); mp3 = os.path.join(OUT, 'bun01.mp3'); t = 0.0
    with wave.open(wav, 'wb') as wv:
        wv.setnchannels(1); wv.setsampwidth(2); wv.setframerate(SR)
        for x in S:
            a = round(t, 2); b = silence(LEAD) + pcm(cpath(VOICE['f'], x['t'])) + silence(TAIL)
            wv.writeframes(b); t += len(b) / 2 / SR; x['at'] = [a, round(t, 2)]
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', wav, '-ac', '1', '-ar', str(SR), '-codec:a', 'libmp3lame', '-b:a', KBPS, mp3], check=True)
    h = hashlib.md5(open(mp3, 'rb').read()).hexdigest()[:8]
    json.dump(dict(v=f'data/audio/bun01.mp3?v={h}', dur=round(t, 2), items=[dict(j=x['j'], y=x['y'], at=x['at']) for x in S]),
              open(os.path.join(HERE, 'bun_audio.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    rep = [f'문법장 음성: 문장 {len(S)} · {t / 60:.1f}분 · {os.path.getsize(mp3) / 1e6:.1f}MB · 가나로 바꿔 읽힌 낱말 {sum(1 for i in infos if "음성은" in i)}건', f'참고 {len(infos)}건']
    open(os.path.join(HERE, 'verify_bun_audio.txt'), 'w', encoding='utf-8').write('\n'.join(rep + ['INFO ' + i for i in infos]) + '\n')
    print('\n'.join(rep))
    return 0

if __name__ == '__main__':
    sys.exit(main())
