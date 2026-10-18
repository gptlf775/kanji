# -*- coding: utf-8 -*-
"""
📒 단어 듣기 음성 검수 — Whisper large-v3 로 받아 적어 원문과 대조 (audit_pos.py 와 같은 방식)
  한국어 뜻 / 일본어 여성·남성 모두 확인 · audit_vocd.jsonl 에 바로 기록(이어서 하기)
  단어 하나는 아주 짧아서 받아쓰기가 흔들림 → 일본어는 '읽기(가나)'로 바꿔 대조, 점수 0.9 미만만 목록에
결과: src/audit_vocd.txt
"""
import difflib, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from build import _tagger, analyzer_reading, ROOT
from build_listen import VOICE
from build_pos import cpath
from build_vocd import ko_word, ja_word
from audit_listen import norm_ja, norm_ko
LOG = os.path.join(HERE, 'audit_vocd.jsonl')

def jobs():
    tagger = _tagger()
    s = open(os.path.join(ROOT, 'data', 'vocab.js'), encoding='utf-8').read()
    for r in json.loads(s[s.index('=') + 1:s.rindex(';')])['words']:
        w, y, c, k = r[:4]
        kt, jt = ko_word(k), ja_word(tagger, w, y, [])
        yield dict(id=f'{w}|{y}', kind='k', want=k, fn=cpath(VOICE['k'], kt), lang='ko')
        for v in ('f', 'm'): yield dict(id=f'{w}|{y}', kind=v, want=y, tts=jt, fn=cpath(VOICE[v], jt), lang='ja')

def main():
    from faster_whisper import WhisperModel
    model = WhisperModel('large-v3', device='cuda', compute_type='float16')
    tagger = _tagger(); done = set()
    if os.path.exists(LOG):
        for line in open(LOG, encoding='utf-8'): r = json.loads(line); done.add((r['id'], r['kind'], r.get('tts', '')))
    todo = [j for j in jobs() if (j['id'], j['kind'], j.get('tts', '')) not in done]
    print(f'전체 {len(todo) + len(done)}개 · 남은 {len(todo)}개', flush=True)
    with open(LOG, 'a', encoding='utf-8') as out:
        for n, j in enumerate(todo, 1):
            segs, _ = model.transcribe(j['fn'], language=j['lang'], beam_size=5, condition_on_previous_text=False,
                                       without_timestamps=True, max_new_tokens=40)
            h = ''.join(s.text for s in segs).strip()
            if j['lang'] == 'ja': got = norm_ja(analyzer_reading(tagger, h)); score = difflib.SequenceMatcher(None, norm_ja(j['want']), got).ratio()
            else: got = ''; score = difflib.SequenceMatcher(None, norm_ko(j['want']), norm_ko(h)).ratio()
            r = {k: v for k, v in j.items() if k not in ('fn', 'lang')}; r.update(got=h, got_kana=got, score=round(score, 3))
            out.write(json.dumps(r, ensure_ascii=False) + '\n'); out.flush()
            if n % 300 == 0: print(f'{len(done) + n}', flush=True)
    rows = {}
    for l in open(LOG, encoding='utf-8'):
        r = json.loads(l); rows[(r['id'], r['kind'], r.get('tts', ''))] = r     # 같은 음성은 마지막 결과만
    cur = {(j['id'], j['kind'], j.get('tts', '')) for j in jobs()}
    rows = sorted((r for k, r in rows.items() if k in cur), key=lambda r: r['score'])
    ja_bad = [r for r in rows if r['kind'] != 'k' and r['score'] < 0.9]
    lines = [f"검수 {len(rows)}개 · 일본어 0.9 미만 {len(ja_bad)}개 · 한국어 0.8 미만 {sum(r['kind'] == 'k' and r['score'] < 0.8 for r in rows)}개"] + \
            [f"{r['score']:.2f} {r['id']} [{r['kind']}] 원문:{r['want']} | 들림:{r['got']}" + (f" | 입력:{r['tts']}" if 'tts' in r else '')
             for r in rows if (r['kind'] != 'k' and r['score'] < 0.9) or (r['kind'] == 'k' and r['score'] < 0.8)]
    open(os.path.join(HERE, 'audit_vocd.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print(lines[0], flush=True)

if __name__ == '__main__':
    main()
