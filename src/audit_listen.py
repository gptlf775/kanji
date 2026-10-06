# -*- coding: utf-8 -*-
"""
🎧 듣기 음성 검수 — 만들어진 음성을 음성 인식(Whisper large-v3)으로 받아 적어 원문과 대조
  일본어(여성·남성): 받아 적은 글 → 형태소 분석기 읽기(가나) ↔ 작성한 읽기(가나)
  한국어·챕터 제목: 받아 적은 글 ↔ 원문 (띄어쓰기·문장부호 무시)
  - 한 개씩 끝날 때마다 audit_listen.jsonl 에 바로 기록 → 진행 상황이 보이고, 중간에 멈춰도 이어서 함
  - 짧은 음성에서 같은 말을 되풀이하는 인식 오류를 막으려고 출력 길이·반복을 제한
  결과: src/audit_listen.txt (닮은 정도가 낮은 순)
사용: python audit_listen.py
"""
import difflib, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from build import _tagger, analyzer_reading, kata2hira
from build_listen import VOICE, cache_path, tts_text, title_tts, ko_tts
from listen_src import CHAPTERS

PUNCT = re.compile(r'[\s。、．，,.!！?？「」『』…・〜～\-"\'“”‘’()（）:：;；]')
def norm_ja(s): return PUNCT.sub('', kata2hira(s))
def norm_ko(s): return PUNCT.sub('', s)
LOG = os.path.join(HERE, 'audit_listen.jsonl')

def jobs():
    tagger = _tagger()
    for ci, ch in enumerate(CHAPTERS, 1):
        tk = title_tts(ci, ch['t'])
        yield dict(id=f'{ci}-제목', kind='title', want=tk, fn=cache_path(VOICE['k'], tk), lang='ko')
        for si, (j, y, k) in enumerate(ch['s'], 1):
            tt = tts_text(tagger, j, y, [], f'{ci}-{si}')
            for v in ('f', 'm'):
                yield dict(id=f'{ci}-{si}', kind=v, want=y, tts=tt, fn=cache_path(VOICE[v], tt), lang='ja')
            yield dict(id=f'{ci}-{si}', kind='k', want=k, fn=cache_path(VOICE['k'], ko_tts(k)), lang='ko')

def main():
    from faster_whisper import WhisperModel
    model = WhisperModel('large-v3', device='cuda', compute_type='float16')
    tagger = _tagger()
    done = set()
    if os.path.exists(LOG):
        for line in open(LOG, encoding='utf-8'):
            r = json.loads(line); done.add((r['id'], r['kind']))
    todo = [j for j in jobs() if (j['id'], j['kind']) not in done]
    total = len(todo) + len(done)
    print(f'전체 {total}개 · 이미 {len(done)}개 · 남은 {len(todo)}개', flush=True)
    with open(LOG, 'a', encoding='utf-8') as out:
        for n, j in enumerate(todo, 1):
            segs, _ = model.transcribe(j['fn'], language=j['lang'], beam_size=1, condition_on_previous_text=False,
                                       without_timestamps=True, max_new_tokens=80, repetition_penalty=1.2, no_repeat_ngram_size=4)
            h = ''.join(s.text for s in segs).strip()
            if j['lang'] == 'ja':
                got = norm_ja(analyzer_reading(tagger, h)); score = difflib.SequenceMatcher(None, norm_ja(j['want']), got).ratio()
            else:
                got = h; score = difflib.SequenceMatcher(None, norm_ko(j['want']), norm_ko(h)).ratio()
            r = {k: v for k, v in j.items() if k not in ('fn', 'lang')}
            r.update(got=h, got_kana=got if j['lang'] == 'ja' else '', score=round(score, 3))
            out.write(json.dumps(r, ensure_ascii=False) + '\n'); out.flush()
            if n % 100 == 0: print(f'{len(done) + n}/{total}', flush=True)
    rows = [json.loads(l) for l in open(LOG, encoding='utf-8')]
    rows.sort(key=lambda r: r['score'])
    head = f'검수 {len(rows)}개 · 닮은 정도 0.9 미만 {sum(r["score"] < 0.9 for r in rows)}개'
    lines = [head] + [f"{r['score']:.2f} {r['id']} [{r['kind']}] 원문: {r['want']} | 들린 것: {r['got']}" + (f" ({r['got_kana']}) | 음성 입력: {r['tts']}" if r['kind'] in ('f', 'm') else '')
                      for r in rows if r['score'] < 0.9]
    open(os.path.join(HERE, 'audit_listen.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print(head, flush=True)

if __name__ == '__main__':
    main()
