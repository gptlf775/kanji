# -*- coding: utf-8 -*-
"""
음성 구간 색인 → data/clips.js (window.CLIPS = {f:[파일 주소…], m:{글: [파일 번호, 시작, 끝]}})
  앱의 speak(글)은 이 색인에 있으면 녹음 음성(신경망 음성) 구간을 재생하고, 없으면 휴대폰 기본 음성으로 읽음
  · 단어장 1,415단어: data/vocd.js(단어 듣기 파일 voc01.mp3)의 '여성 일본어' 구간 — 새 파일 없음
      글 = 표기, 표기|읽기, 읽기(같은 읽기의 단어가 하나뿐일 때만 — 雨·飴처럼 소리가 같은 말은 읽기만으로 고르지 않음)
  · 문법장 예문·빈칸 문제 정답 문장: src/bun_audio.json(build_bun_audio.py, bun01.mp3)
      글 = 문장, 읽기(띄어쓰기 뺀 것도)
사용: python build_clips.py
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from build import ROOT, kata2hira, write_index
sys.stdout.reconfigure(encoding='utf-8')

def main():
    s = open(os.path.join(ROOT, 'data', 'vocd.js'), encoding='utf-8').read()
    V = json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))
    files, m = [V['v']], {}
    ycount = {}
    for it in V['items']: ycount[kata2hira(it['y'])] = ycount.get(kata2hira(it['y']), 0) + 1
    for it in V['items']:
        a = it['at']; seg = [0, a[2], round(a[3] - 0.25, 2)]          # 여성 구간 (남성 시작 직전까지, 뒤 여백 조금 덜어 냄)
        m.setdefault(it['w'], seg); m[f'{it["w"]}|{it["y"]}'] = seg
        if ycount[kata2hira(it['y'])] == 1: m.setdefault(it['y'], seg)
    nv = len(V['items'])
    bp = os.path.join(HERE, 'bun_audio.json'); nb = 0
    if os.path.exists(bp):
        B = json.load(open(bp, encoding='utf-8'))
        files.append(B['v'])
        for it in B['items']:
            seg = [1] + it['at']
            for k in (it['j'], it['y'].replace(' ', '').replace('　', '')): m.setdefault(k, seg)   # 앱이 띄어쓰기를 빼고도 찾음
            nb += 1
    js = 'window.CLIPS=' + json.dumps(dict(f=files, m=m), ensure_ascii=False, separators=(',', ':')) + ';\n'
    open(os.path.join(ROOT, 'data', 'clips.js'), 'w', encoding='utf-8').write(js)
    write_index()
    print(f'음성 구간 색인: 단어 {nv} · 문법 문장 {nb} · 열쇠 {len(m)}개 · {len(js.encode())} bytes')

if __name__ == '__main__':
    sys.exit(main())
