# -*- coding: utf-8 -*-
"""
단어장 1단계 — JLPT N5·N4 단어 목록(Tanos, CC BY)에 JMdict 품사·빈도를 붙여 작업 목록을 만든다.
입력: ../일본어한자_원천데이터/jlpt/open-anki-jlpt-decks_n5.csv, _n4.csv  (Tanos 목록을 CSV로 정리한 공개 저장소)
출력: ../일본어한자_원천데이터/jlpt/vocab_work.json  — [{w, y, en, lv, pos:[...], nf, cm}]
한국어 뜻은 vocab_ko.py 에 직접 작성하고, build_vocab.py 가 합쳐서 data/vocab.js 를 만든다.
"""
import csv, gzip, json, os, re, sys
import xml.etree.ElementTree as ET
HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(os.path.dirname(os.path.dirname(HERE)), '일본어한자_원천데이터')
sys.path.insert(0, HERE)
from build_gram import pos_code

COMMON = {'news1', 'ichi1', 'spec1', 'spec2', 'gai1'}

def pos_code2(d):
    c = pos_code(d)
    if c: return c
    if d.startswith('noun (common)') or d.startswith('noun'): return 'n'
    if d.startswith('pronoun'): return 'pn'
    if d.startswith('adverb') and 'taking the' not in d: return 'adv'
    if d.startswith('adverb taking'): return 'adv-to'
    if d.startswith('interjection'): return 'int'
    if d.startswith('conjunction'): return 'conj'
    if d.startswith('pre-noun adjectival'): return 'adj-pn'
    if "nouns which may take the genitive" in d: return 'adj-no'
    if d.startswith('expressions'): return 'exp'
    if d.startswith('counter'): return 'ctr'
    if d.startswith('suffix'): return 'suf'
    if d.startswith('prefix'): return 'pref'
    if d.startswith('particle'): return 'prt'
    if d.startswith('numeric'): return 'num'
    if d.startswith('auxiliary'): return 'aux'
    return 'other'

def load():
    by_wy, by_y = {}, {}
    with gzip.open(os.path.join(REF, 'JMdict_e.gz'), 'rb') as f:
        for ev, el in ET.iterparse(f, events=('end',)):
            if el.tag != 'entry': continue
            senses = el.findall('sense')
            first = [pos_code2(p.text or '') for p in senses[0].findall('pos')] if senses else []
            allp = [pos_code2(p.text or '') for s in senses for p in s.findall('pos')]
            pos = list(dict.fromkeys(first + allp))
            kebs = [(k.findtext('keb'), {p.text for p in k.findall('ke_pri')}) for k in el.findall('k_ele')]
            for r in el.findall('r_ele'):
                reb = r.findtext('reb'); rp = {p.text for p in r.findall('re_pri')}
                restr = {x.text for x in r.findall('re_restr')}
                info = lambda pri: dict(pos=pos, nf=min([int(p[2:]) for p in pri if p.startswith('nf')] or [99]), cm=bool(pri & COMMON))
                cur = by_y.get(reb)
                v = info(rp | (kebs[0][1] if kebs else set()))
                if not cur or (v['cm'], -v['nf']) > (cur['cm'], -cur['nf']): by_y[reb] = v
                for keb, kp in kebs:
                    if restr and keb not in restr: continue
                    v = info(kp | rp)
                    cur = by_wy.get((keb, reb))
                    if not cur or (v['cm'], -v['nf']) > (cur['cm'], -cur['nf']): by_wy[(keb, reb)] = v
            el.clear()
    return by_wy, by_y

def main():
    rows, seen = [], set()
    for lv in (5, 4):
        with open(os.path.join(REF, 'jlpt', f'open-anki-jlpt-decks_n{lv}.csv'), encoding='utf-8') as f:
            for r in csv.DictReader(f):
                w, y, en = r['expression'].strip(), r['reading'].strip(), r['meaning'].strip()
                if (w, y) in seen: continue
                seen.add((w, y)); rows.append(dict(w=w, y=y, en=en, lv=lv))
    print('단어', len(rows))
    by_wy, by_y = load()
    miss = 0
    for r in rows:
        wq, yq = r['w'].replace('～', '').replace('~', ''), r['y'].replace('～', '').replace('~', '')
        yq = yq.split(';')[0].split('、')[0].strip()
        v = by_wy.get((wq, yq)) or (by_y.get(yq) if not re.search(r'[一-鿿]', wq) else None) or by_y.get(yq)
        if not v: miss += 1; v = dict(pos=[], nf=99, cm=False)
        r.update(pos=v['pos'], nf=v['nf'], cm=v['cm'])
    json.dump(rows, open(os.path.join(REF, 'jlpt', 'vocab_work.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print('JMdict 못 찾음', miss)

if __name__ == '__main__':
    main()
