# -*- coding: utf-8 -*-
"""
🔤 품사별 듣기 음성 검수 — Whisper large-v3 로 받아 적어 원문과 대조 (audit_listen.py 와 같은 방식)
  한국어 문장 / 일본어 여성·남성 문장 / 원형(여성, 천천히) 모두 확인 · audit_pos.jsonl 에 바로 기록(이어서 하기)
결과: src/audit_pos.txt
"""
import difflib, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from build import _tagger, analyzer_reading
from build_listen import VOICE, tts_text, ko_tts
from build_pos import cpath, BASE_RATE, POS, base_tts
from audit_listen import norm_ja, norm_ko
import gram_src as G
from build_gram import parse
LOG = os.path.join(HERE, 'audit_pos.jsonl')

def jobs():
    tagger = _tagger()
    meta = {r[0]: r for r in parse(G.VERBS_N5, 5) + parse(G.VERBS_N4, 4) + parse(G.ADJS_N5, 5) + parse(G.ADJS_N4, 4)}
    for t, name, L in POS:
        for w, j, y, k in L:
            tt = tts_text(tagger, j, y, [], w); base = base_tts(meta[w][1])
            yield dict(id=w, kind='k', want=k, fn=cpath(VOICE['k'], ko_tts(k)), lang='ko')
            for v in ('f', 'm'): yield dict(id=w, kind=v, want=y, tts=tt, fn=cpath(VOICE[v], tt), lang='ja')
            yield dict(id=w, kind='base', want=meta[w][1], tts=base, fn=cpath(VOICE['f'], base, BASE_RATE), lang='ja')

def main():
    from faster_whisper import WhisperModel
    model = WhisperModel('large-v3', device='cuda', compute_type='float16')
    tagger = _tagger(); done = set()
    if os.path.exists(LOG):
        for line in open(LOG, encoding='utf-8'): r = json.loads(line); done.add((r['id'], r['kind']))
    todo = [j for j in jobs() if (j['id'], j['kind']) not in done]
    print(f'전체 {len(todo) + len(done)}개 · 남은 {len(todo)}개', flush=True)
    with open(LOG, 'a', encoding='utf-8') as out:
        for n, j in enumerate(todo, 1):
            segs, _ = model.transcribe(j['fn'], language=j['lang'], beam_size=1, condition_on_previous_text=False,
                                       without_timestamps=True, max_new_tokens=80, repetition_penalty=1.2, no_repeat_ngram_size=4)
            h = ''.join(s.text for s in segs).strip()
            if j['lang'] == 'ja': got = norm_ja(analyzer_reading(tagger, h)); score = difflib.SequenceMatcher(None, norm_ja(j['want']), got).ratio()
            else: got = ''; score = difflib.SequenceMatcher(None, norm_ko(j['want']), norm_ko(h)).ratio()
            r = {k: v for k, v in j.items() if k not in ('fn', 'lang')}; r.update(got=h, got_kana=got, score=round(score, 3))
            out.write(json.dumps(r, ensure_ascii=False) + '\n'); out.flush()
            if n % 200 == 0: print(f'{len(done) + n}', flush=True)
    rows = [json.loads(l) for l in open(LOG, encoding='utf-8')]
    rows.sort(key=lambda r: r['score'])
    lines = [f'검수 {len(rows)}개 · 0.9 미만 {sum(r["score"] < 0.9 for r in rows)}개'] + \
            [f"{r['score']:.2f} {r['id']} [{r['kind']}] 원문:{r['want']} | 들림:{r['got']}" + (f" | 입력:{r['tts']}" if 'tts' in r else '') for r in rows if r['score'] < 0.9]
    open(os.path.join(HERE, 'audit_pos.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print(lines[0], flush=True)

if __name__ == '__main__':
    main()
