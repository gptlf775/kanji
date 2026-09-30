# -*- coding: utf-8 -*-
"""단어장 공용: 원본 목록 정리(표기·읽기 정규화, 문법 항목 제외) + 품사 분류"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(os.path.dirname(os.path.dirname(HERE)), '일본어한자_원천데이터')

# 원본 목록의 표기·읽기 오류 바로잡기 (w, y) → (w, y)
FIX = {
    ('十', '(〜を) とお'): ('十', 'とお'),
    ('いただく', '頂く'): ('頂く', 'いただく'),
    ('ごらんになる', ''): ('ご覧になる', 'ごらんになる'),
    ('かまう', ''): ('構う', 'かまう'),
    ('パート (タイム)', 'パート (タイム)'): ('パート', 'パート'),
    ('ゆっくりと', 'ゆっくりと'): ('ゆっくり', 'ゆっくり'),
    ('ラジオカセ', 'ラジオカセ'): ('ラジカセ', 'ラジカセ'),
}

FIX.update({
    ('そうして; そして', 'そうして; そして'): ('そして', 'そして'), ('そうして; そして', 'そうして'): ('そして', 'そして'),
    ('堅; 硬; 固い', 'かたい'): ('固い', 'かたい'),
    ('キロ; キログラム', 'キロ'): ('キロ', 'キロ'), ('キロ; キロメートル', 'キロ'): ('キロ', 'キロ'),
    ('スーパー (マーケット)', 'スーパー (マーケット)'): ('スーパー', 'スーパー'), ('スーパー (マーケット)', 'スーパー(マーケット)'): ('スーパー', 'スーパー'),
})
# JMdict에서 품사를 못 찾았거나 분류가 어색한 말 (표기, 읽기) → (분류, 동사 그룹)
CAT_FIX = {('ゆっくり', 'ゆっくり'): ('adv', ''), ('ご覧になる', 'ごらんになる'): ('v', '1'), ('構う', 'かまう'): ('v', '1'),
           ('あ', 'あ'): ('etc', ''), ('ああ', 'ああ'): ('etc', ''), ('同じ', 'おなじ'): ('etc', ''), ('大きな', 'おおきな'): ('etc', ''), ('小さな', 'ちいさな'): ('etc', ''),
           ('女の子', 'おんなのこ'): ('n', ''), ('男の子', 'おとこのこ'): ('n', ''), ('はず', 'はず'): ('n', ''), ('キロ', 'キロ'): ('n', ''),
           ('役に立つ', 'やくにたつ'): ('v', '1'), ('おいでになる', 'おいでになる'): ('v', '1')}

def norm_pair(w, y):
    """원본 표기·읽기 → 단어장 표기·읽기 (한국어 뜻 파일의 열쇠에도 똑같이 적용)"""
    w, y = FIX.get((w, y), (w, y))
    y = re.sub(r'\s*\(する\)\s*$', 'する', y).replace(' ', '')
    if y.endswith('する') and not w.endswith('する') and not y == 'する':
        w = w + 'する'
    w = w.split(';')[0].strip()                  # '足; 脚' → 足 (첫 표기)
    w = w.replace('御飯', 'ご飯')                 # 요즘 표기
    y = re.split(r'[;、,/]', y)[0]
    return w, y

def normalize(rows):
    out, seen, dropped = [], set(), []
    for r in rows:
        w0, y0 = FIX.get((r['w'], r['y']), (r['w'], r['y']))
        if re.search(r'[～〜~]', w0) or re.search(r'[～〜~]', y0):
            dropped.append(r['w']); continue      # 문형·접사(～てしまう·～区)는 문법 탭에서 다룸
        w, y = norm_pair(r['w'], r['y'])
        if (w, y) in seen: continue
        seen.add((w, y))
        out.append(dict(r, w=w, y=y))
    return out, dropped

def gram_index():
    """활용어 탭(gram_src)의 동사·형용사: (표기, 읽기) → (분류, 그룹, 한국어)"""
    sys.path.insert(0, HERE)
    import gram_src as G
    gram = {}
    for blk, kind in ((G.VERBS_N5, 'v'), (G.VERBS_N4, 'v'), (G.ADJS_N5, None), (G.ADJS_N4, None)):
        for line in blk.strip().splitlines():
            w, y, g, ko = line.split('|')
            gram[(w, y)] = ('v', g, ko) if kind else (g, '', ko)
    return gram

def merge_variants(rows, gram):
    """표기만 다른 같은 말(綺麗→きれい, 終る→終わる, 在る·有る→ある)을 활용어 목록 표기로 통일하고 중복 제거"""
    byy = {}
    for (w, y), v in gram.items(): byy.setdefault(y, []).append((w, v))
    han = lambda s: set(re.findall(r'[一-鿿]', s))
    out, seen = [], set()
    for r in rows:
        w, y = r['w'], r['y']
        if (w, y) not in gram and y in byy:
            for gw, v in byy[y]:
                if gw == y or (han(gw) & han(w)):      # 활용어 쪽이 가나 표기이거나 같은 한자를 공유
                    w = gw; break
        if (w, y) in seen: continue
        seen.add((w, y)); out.append(dict(r, w=w, y=y))
    return out

VG = {'v1': '2', 'v5': '1', 'v5k-s': '1k', 'v5aru': '1a', 'v5r-i': '1r', 'vk': '3k', 'vs-i': '3s'}
def category(r, gram):
    """→ (분류, 동사 그룹). 분류: n 명사 · v 동사 · i い형용사 · na な형용사 · adv 부사 · etc 기타"""
    g = gram.get((r['w'], r['y'])) or CAT_FIX.get((r['w'], r['y']))
    if g: return g
    if r['w'].endswith('する'): return ('v', '3s')
    for p in r['pos']:
        if p in VG: return ('v', VG[p])
        if p in ('adj-i', 'adj-ix'): return ('i', '')
        if p == 'adj-na': return ('na', '')
        if p in ('adv', 'adv-to'): return ('adv', '')
        if p in ('n', 'pn', 'num', 'ctr', 'adj-no'): return ('n', '')
        if p in ('conj', 'exp', 'int', 'adj-pn', 'prt', 'aux', 'suf', 'pref'): return ('etc', '')
    return ('n', '')
