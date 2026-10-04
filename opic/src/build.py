# -*- coding: utf-8 -*-
"""
누구나 오픽 — 콘텐츠 빌드·검증 → ../data/opic.js
  입력: content/q_*.json (질문·IM2/IH 모범 답변), content/core.json (레벨·레슨·말하기 도구·표현·불규칙 동사·이야기 틀)
  검증: 필수 항목·형식, 답변 단어 수(IM2 70~110 / IH 140~200, ±10% 넘으면 오류), 덩어리 표현이 본문에 있는지,
        직업·학교 언급(인물 설정 위반), 롤플레이 질문하기의 물음표 수, 문제 해결의 대안 표현, id 중복
사용: python build.py
"""
import glob, hashlib, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TYPES = {'intro', 'desc', 'routine', 'past', 'compare', 'rp_ask', 'rp_solve', 'rp_exp'}
CLUSTERS = {'home', 'show', 'park', 'travel', 'surprise', 'roleplay'}
JOB = re.compile(r"\b(my (job|boss|company|office|coworkers?|colleagues?|manager|team leader|school|university|class(es)?|professor)|at work|after work|my workplace|my career)\b", re.I)
words = lambda sents: sum(len(re.findall(r"[A-Za-z0-9'’-]+", e)) for e, _ in sents)

def main():
    errors, warns, infos = [], [], []
    qs, seen = [], set()
    for f in sorted(glob.glob(os.path.join(HERE, 'content', 'q_*.json'))):
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception as e:
            errors.append(f'{os.path.basename(f)}: JSON 오류 {e}'); continue
        for it in d.get('items', []):
            i = it.get('id', '?')
            tag = f'{os.path.basename(f)}:{i}'
            if i in seen: errors.append(f'{tag}: id 중복')
            seen.add(i)
            for k in ('id', 'cluster', 'topic', 'type', 'q', 'qko', 'tip', 'im2', 'ih', 'chunks'):
                if not it.get(k): errors.append(f'{tag}: "{k}" 없음')
            if it.get('type') not in TYPES: errors.append(f'{tag}: type "{it.get("type")}" 허용 안 됨')
            if it.get('cluster') not in CLUSTERS: errors.append(f'{tag}: cluster "{it.get("cluster")}" 허용 안 됨')
            ok = True
            for lv in ('im2', 'ih'):
                s = it.get(lv) or []
                if not all(isinstance(x, list) and len(x) == 2 and x[0] and x[1] for x in s):
                    errors.append(f'{tag}: {lv} 문장 형식 오류 ([영어, 한국어])'); ok = False; continue
                n = words(s)
                lo, hi = (70, 110) if lv == 'im2' else (140, 200)
                if n < lo * 0.9 or n > hi * 1.1: errors.append(f'{tag}: {lv} {n}단어 (기준 {lo}~{hi})')
                elif n < lo or n > hi: warns.append(f'{tag}: {lv} {n}단어 (기준 {lo}~{hi}, 허용 범위 안)')
                text = ' '.join(e for e, _ in s)
                m = JOB.search(text)
                if m: errors.append(f'{tag}: {lv} 직업·학교 언급 "{m.group(0)}" (인물 설정: 일 경험 없음)')
                if it.get('type') == 'rp_ask' and text.count('?') < 3: errors.append(f'{tag}: {lv} 질문하기인데 물음표 {text.count("?")}개 (3개 이상)')
            if ok:
                body = (' '.join(e for e, _ in it['im2'] + it['ih'])).lower().replace('’', "'")
                for c in it.get('chunks', []):
                    if not (isinstance(c, list) and len(c) == 2): errors.append(f'{tag}: chunk 형식 오류 {c}'); continue
                    if c[0].lower().replace('’', "'") not in body: errors.append(f'{tag}: 덩어리 "{c[0]}" 가 답변에 없음')
                if not (4 <= len(it.get('chunks', [])) <= 6): warns.append(f'{tag}: 덩어리 {len(it.get("chunks", []))}개 (4~6)')
            qs.append(it)
    core_p = os.path.join(HERE, 'content', 'core.json')
    core = json.load(open(core_p, encoding='utf-8')) if os.path.exists(core_p) else {}
    if not core: warns.append('core.json 없음')
    for k in ('levels', 'lessons', 'tools', 'chunks', 'verbs', 'storyTemplate'):
        if core and not core.get(k): errors.append(f'core.json: "{k}" 없음')
    # 이야기 틀과 답변의 story 연결
    sids = {s.get('id') for s in core.get('storyTemplate', [])}
    for it in qs:
        if it.get('story') and sids and it['story'] not in sids: warns.append(f'{it["id"]}: story {it["story"]} 가 이야기 틀에 없음')
    from collections import Counter
    cc = Counter(q['cluster'] for q in qs); tc = Counter(q['type'] for q in qs)
    data = dict(qs=qs, core=core)
    js = 'window.OPIC=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n'
    os.makedirs(os.path.join(ROOT, 'data'), exist_ok=True)
    open(os.path.join(ROOT, 'data', 'opic.js'), 'w', encoding='utf-8').write(js)
    ver = hashlib.md5(js.encode('utf-8')).hexdigest()[:8]
    open(os.path.join(ROOT, 'data', 'ver.js'), 'w', encoding='utf-8').write(f'window.OPIC_VER={json.dumps(ver)};\n')
    rep = [f'질문 {len(qs)}개 · 묶음 {dict(cc)} · 유형 {dict(tc)}',
           f'모범 답변 문장: IM2 {sum(len(q.get("im2", [])) for q in qs)} · IH {sum(len(q.get("ih", [])) for q in qs)}',
           f'core: 레슨 {len(core.get("lessons", []))} · 도구 {len(core.get("tools", []))} · 표현 {len(core.get("chunks", []))} · 동사 {len(core.get("verbs", []))}',
           f'오류 {len(errors)}건, 경고 {len(warns)}건'] + ['ERR ' + e for e in errors] + ['WARN ' + w for w in warns]
    txt = '\n'.join(rep)
    open(os.path.join(HERE, 'verify.txt'), 'w', encoding='utf-8').write(txt + '\n')
    print(txt); print('data size:', len(js.encode('utf-8')), 'bytes · ver', ver)
    return 1 if errors else 0

if __name__ == '__main__':
    sys.exit(main())
