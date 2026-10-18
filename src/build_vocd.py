# -*- coding: utf-8 -*-
"""
📒 단어 듣기 빌드 → data/vocd.js + data/audio/voc01.mp3
  단어 하나 = 한국어 뜻 → 일본어 여성 → 일본어 남성
  파일 하나에 모두 이어 붙이고 단어마다 시각(at)을 기록 → 앱은 같은 파일 안에서 위치만 옮겨 '섞어서 무한 재생'
  (아이폰은 화면이 꺼진 동안 새 파일을 못 불러오므로 파일 하나로 — build_pos.py 와 같은 방식)
  일본어 음성: 표기 그대로 읽히는지 분석기로 대조(build_listen.tts_text) → 다르게 읽힐 낱말은 가나로
  검증: 단어장(vocab.js)의 모든 단어가 들어갔는지, 잘린 음성 재생성, 한국어 음성이 못 읽는 글자
사용: python build_vocd.py
"""
import asyncio, hashlib, json, os, re, sys, wave
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from build import _tagger, ROOT, write_index
from build_listen import VOICE, CACHE, OUT, SR, KBPS, tts_text, pcm, silence
from build_pos import cpath, synth, too_short, kata
import subprocess

GAP = {'lead': 0.4, 'k': 0.6, 'f': 0.7, 'm': 1.3}

def ko_word(k):
    """한국어 뜻 음성: '벌써·이미·더' → '벌써, 이미, 더' · 괄호 설명도 쉼표로 이어 읽음 · ~ 는 뺌"""
    s = k.replace('…', '').replace('~', '').replace('～', '')
    s = re.sub(r'\s*[(（]\s*', ', ', s).replace(')', '').replace('）', '')
    s = re.sub(r'\s*[·/]\s*', ', ', s)
    s = re.sub(r'(,\s*)+', ', ', s).strip(' ,')
    return s + '.'

# 낱말 하나만 읽힐 때 엉뚱하게 읽히는 것 (음성 검수 결과 vocd_kana.txt) → 가나로
FORCE_KANA = {tuple(l.strip().split('|')) for l in open(os.path.join(HERE, 'vocd_kana.txt'), encoding='utf-8') if l.strip() and not l.startswith('#')}

def ja_word(tagger, w, y, infos):
    """일본어 음성: 표기를 분석기 읽기와 대조 → 다르면 작성 읽기(가나). 가나 낱말이 は·へ로 시작하면 가타카나 (조사로 읽힘 방지)"""
    if (w, y) in FORCE_KANA: t = y
    else:
        try: t = tts_text(tagger, w, y, infos, f'voc:{w}')
        except ValueError: t = y
    if re.fullmatch(r'[ぁ-ゖー]+', t) and t[0] in 'はへ': t = kata(t)
    return t + '。'

def main():
    errors, infos = [], []
    s = open(os.path.join(ROOT, 'data', 'vocab.js'), encoding='utf-8').read()
    V = json.loads(s[s.index('=') + 1:s.rindex(';')])['words']
    tagger = _tagger()
    items, jobs = [], []
    for r in V:
        w, y, c, k, lv = r[:5]
        kt = ko_word(k)
        if re.search(r'[぀-ヿ一-鿿]', kt): errors.append(f'{w}: 한국어 뜻에 일본 글자 — {k}'); continue
        jt = ja_word(tagger, w, y, infos)
        items.append(dict(w=w, y=y, k=k, c=c, lv=lv, kt=kt, jt=jt))
        jobs += [(VOICE['k'], kt, cpath(VOICE['k'], kt), ''), (VOICE['f'], jt, cpath(VOICE['f'], jt), ''), (VOICE['m'], jt, cpath(VOICE['m'], jt), '')]
    if len(items) != len(V): errors.append(f'단어장 {len(V)}개 중 {len(items)}개만 들어감')
    if errors:
        print('\n'.join('ERR ' + e for e in errors)); return 1
    uniq = list({j[2]: j for j in jobs}.values())
    todo = [j for j in uniq if not os.path.exists(j[2])]
    print(f'음성 {len(uniq)}개 중 새로 만들 것 {len(todo)}개', flush=True)
    if todo: asyncio.run(synth(todo))
    for attempt in range(4):
        bad = [j for j in uniq if too_short(j[2], j[1])]
        if not bad: break
        print(f'잘린 음성 {len(bad)}개 → 다시 만듦 ({attempt + 1}회차)', flush=True)
        for j in bad:
            for f in (j[2], j[2][:-4] + '.wav'):
                if os.path.exists(f): os.remove(f)
        asyncio.run(synth(bad))
    else:
        print(f'ERR 잘린 음성이 계속 남음: {len(bad)}개 — ' + ', '.join(j[1] for j in bad[:10])); return 1
    wav = os.path.join(CACHE, '_voc01.wav'); mp3 = os.path.join(OUT, 'voc01.mp3'); t = 0.0
    with wave.open(wav, 'wb') as wv:
        wv.setnchannels(1); wv.setsampwidth(2); wv.setframerate(SR)
        def add(b):
            nonlocal t
            wv.writeframes(b); t += len(b) / 2 / SR
        for it in items:
            at = [round(t, 2)]; add(silence(GAP['lead']))
            for v, txt in (('k', it['kt']), ('f', it['jt']), ('m', it['jt'])):
                at.append(round(t, 2)); add(pcm(cpath(VOICE[v], txt)))
                if v != 'm': add(silence(GAP[v]))
            at.append(round(t, 2)); add(silence(GAP['m'])); at.append(round(t, 2))
            it['at'] = at                            # [시작, 한국어, 여성, 남성, 남성 끝, 끝]
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', wav, '-ac', '1', '-ar', str(SR), '-codec:a', 'libmp3lame', '-b:a', KBPS, mp3], check=True)
    h = hashlib.md5(open(mp3, 'rb').read()).hexdigest()[:8]
    out = [{k: v for k, v in it.items() if k not in ('kt', 'jt')} for it in items]
    js = 'window.VOCD=' + json.dumps(dict(v=f'data/audio/voc01.mp3?v={h}', dur=round(t, 2), items=out), ensure_ascii=False, separators=(',', ':')) + ';\n'
    open(os.path.join(ROOT, 'data', 'vocd.js'), 'w', encoding='utf-8').write(js)
    write_index()
    kana = sum(1 for it in items if it['jt'][:-1] != it['w'])
    rep = [f'단어 {len(items)} · {t / 60:.1f}분 · {os.path.getsize(mp3) / 1e6:.1f}MB · 일본어를 가나로 넘긴 것 {kana}개',
           f'오류 0건, 참고 {len(infos)}건'] + ['INFO ' + i for i in infos]
    open(os.path.join(HERE, 'verify_vocd.txt'), 'w', encoding='utf-8').write('\n'.join(rep) + '\n')
    print('\n'.join(rep[:2]))
    return 0

if __name__ == '__main__':
    sys.exit(main())
