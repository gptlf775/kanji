# -*- coding: utf-8 -*-
"""
음성 검수 결과 거르기: 받아 적은 글을 숫자→한자·표기 차이(友達/友だち 등)로 맞춘 뒤에도 다른 것만 보여 줌
사용: python audit_review.py listen [시작 문장 번호]   /   python audit_review.py pos
"""
import difflib, json, re, sys, os
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
K = '〇一二三四五六七八九'
def kan(n):
    n = int(n)
    if n == 0: return '〇'
    out = ''
    for v, c in ((10000, '万'), (1000, '千'), (100, '百'), (10, '十')):
        q, n = divmod(n, v)
        if q: out += ('' if q == 1 and v != 10000 else kan(q)) + c
    return out + (K[n] if n else '')
P = re.compile(r'[\s。、．，,.!！?？「」『』…・〜～\-"\'“”‘’()（）:：;；]')
VAR = {'友達': '友だち', '子供': '子ども', '面白': 'おもしろ', '欲し': 'ほし', '嬉し': 'うれし', '綺麗': 'きれい', '街': '町', 'ゴミ': 'ごみ',
       '頃': 'ごろ', '撮': '取', '未知': '道', 'お寿司': 'おすし', '寿司': 'すし', '分かる': 'わかる', '分から': 'わから', '分かり': 'わかり'}
def norm(s):
    s = re.sub(r'\d+', lambda m: kan(m.group()), s)
    for a, b in VAR.items(): s = s.replace(a, b)
    return P.sub('', s)

def main(kind, start=0):
    if kind == 'listen':
        from listen_src import CHAPTERS
        src = {f'{ci}-{si}': j.replace('[', '').replace(']', '') for ci, c in enumerate(CHAPTERS, 1) for si, (j, y, k) in enumerate(c['s'], 1)}
        rows = [json.loads(l) for l in open(os.path.join(HERE, 'audit_listen.jsonl'), encoding='utf-8')]
        rows = [r for r in rows if r['kind'] == 'title' or int(r['id'].split('-')[1]) >= start]
    else:
        from pos_src import POS
        src = {w: j.replace('[', '').replace(']', '') for _, _, L in POS for w, j, y, k in L}
        rows = [json.loads(l) for l in open(os.path.join(HERE, 'audit_pos.jsonl'), encoding='utf-8')]
    left = []
    for r in rows:
        if r['score'] >= 0.9 or r['kind'] == 'title': continue
        if r['kind'] in ('f', 'm'):
            s2 = difflib.SequenceMatcher(None, norm(src[r['id']]), norm(r['got'])).ratio()
            if s2 < 0.9: left.append(f"{r['score']:.2f}/{s2:.2f} {r['id']} [{r['kind']}] 원문:{src[r['id']]} | 들림:{r['got']} | 입력:{r.get('tts')}")
        else:
            left.append(f"{r['score']:.2f} {r['id']} [{r['kind']}] 원문:{r['want']} | 들림:{r['got']}")
    print(f'남은 의심 {len(left)}'); print('\n'.join(left))

if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 0)
