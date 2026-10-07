# -*- coding: utf-8 -*-
"""음성을 다시 만든 뒤: 검수 기록(jsonl)에서 음성 파일이 그대로인 항목만 남김 → 바뀐 음성만 다시 검수"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from build_listen import VOICE, cache_path, ko_tts
from build_pos import cpath, BASE_RATE

def reseed(log, jobs, fn_of):
    path = os.path.join(HERE, log)
    rows = []
    if os.path.exists(path):
        for l in open(path, encoding='utf-8'):
            try: rows.append(json.loads(l))
            except Exception: pass
    have = {(r['id'], r['kind']): r for r in rows}
    keep, todo = [], 0
    for j in jobs():
        r = have.get((j['id'], j['kind']))
        if r and fn_of(r) == j['fn']: keep.append(r)
        else: todo += 1
    open(path, 'w', encoding='utf-8').write(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in keep))
    print(f'{log}: 재사용 {len(keep)} · 다시 검수 {todo}')

def listen_fn(r):
    if r['kind'] in ('f', 'm'): return cache_path(VOICE[r['kind']], r['tts'])
    if r['kind'] == 'k': return cache_path(VOICE['k'], ko_tts(r['want']))
    return cache_path(VOICE['k'], r['want'])

def pos_fn(r):
    if r['kind'] in ('f', 'm'): return cpath(VOICE[r['kind']], r['tts'])
    if r['kind'] == 'base': return cpath(VOICE['f'], r['tts'], BASE_RATE)
    return cpath(VOICE['k'], ko_tts(r['want']))

if __name__ == '__main__':
    import audit_listen, audit_pos
    reseed('audit_listen.jsonl', audit_listen.jobs, listen_fn)
    reseed('audit_pos.jsonl', audit_pos.jobs, pos_fn)
