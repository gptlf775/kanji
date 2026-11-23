# -*- coding: utf-8 -*-
"""
상용 밖 한자(표외자) 찾아보기 카드 — 단어장(N5·N4)에 나오는데 상용한자 2,136자에 없는 글자
  왜: 단어장의 嬉しい를 보고 嬉를 손글씨·검색으로 찾으면 '없음'이 나왔음 → 찾아서 비슷한 상용한자로 이어 주기
  출력: data/g11.js (g=11, basic=True · hy=True — 학습·한자 목록에는 안 나오고 찾아보기·손글씨에만)
  자료: 훈음·뜻 = libhangul/KANJIDIC2 대조 후 작성 · 읽기 = KANJIDIC2(상용 아님) · 획순 = KanjiVG(원천데이터/kvg_hyogai)
  검사: 예시 단어가 JMdict에 있는지 · 단어장에 그 단어가 있는지 · 한국음이 사전 후보에 있는지
사용: python build_hyogai.py
"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from build import REF_DIR, ROOT, parse_readings, kata2hira, write_index
sys.stdout.reconfigure(encoding='utf-8')

# k, 훈음, 뜻, 부수, 읽기(KANJIDIC2 — 상용한자표 아님), 예시 [단어, 읽기, 읽기 표기, 뜻], 이어 줄 상용한자, 한 줄 설명
CARDS = [
    ('嬉', '즐길 희', '기쁘다, 즐기다', '女', 'キ、うれ-しい', [['嬉しい', 'うれしい', 'うれ-しい', '기쁘다']], '喜',
     '女 + 喜(기쁠 희). 嬉しい(うれしい)는 아주 흔한 말이지만 嬉는 상용한자가 아니라서 공문서·교과서는 うれしい로 가나 표기. 喜(よろこぶ)와 다른 글자'),
    ('嘘', '불 허', '거짓말', '口', 'キョ、うそ', [['嘘', 'うそ', 'うそ', '거짓말']], '虚',
     '口 + 虚(빌 허). 嘘(うそ)는 흔한 말이지만 상용한자가 아니라 うそ로 가나 표기가 많음. 虚(キョ, 중학)와 소리 부분이 같음'),
    ('飴', '엿 이', '엿, 사탕', '食', 'イ、あめ', [['飴', 'あめ', 'あめ', '사탕, 엿']], '台',
     '飠(먹을 식) + 台(소리). 飴(あめ, 사탕)는 雨(あめ, 비)와 소리가 같고 높낮이가 다름'),
    ('碗', '주발 완', '사발, 공기', '石', 'ワン', [['茶碗', 'ちゃわん', 'ワン', '밥공기, 찻잔']], '腕',
     '石 + 宛(소리 ワン). 茶碗(ちゃわん)은 상용한자표 밖이라 茶わん으로도 씀. 腕(팔 완, 중1)과 소리 부분이 같음'),
    ('醤', '장 장', '간장, 장', '酉', 'ショウ', [['醤油', 'しょうゆ', 'ショウ', '간장']], '将',
     '酉(술·발효) + 将(소리 ショウ). 정자 醬. 醤油(しょうゆ)는 상용한자표 밖이라 しょう油로도 씀'),
    ('鹸', '잿물 감', '잿물, 알칼리', '鹵', 'ケン', [['石鹸', 'せっけん', 'ケン', '비누']], '険',
     '鹵(소금밭) + 㑒(소리). 정자 鹼. 石鹸(せっけん)은 상용한자표 밖이라 せっけん·石けん으로 씀. 한국음은 감'),
    ('噌', '떠들썩할 쟁', '(된장 味噌에 쓰는 글자)', '口', 'ソ、ソウ', [['味噌', 'みそ', 'ソ', '된장']], '増',
     '口 + 曽(소리). 일본어에서는 거의 味噌(みそ, 된장) 한 말에만 씀. 상용한자표 밖이라 みそ로 가나 표기가 많음'),
    ('噛', '깨물 교', '씹다, 물다', '口', 'ゴウ、か-む', [['噛む', 'かむ', 'か-む', '씹다, 물다']], '歯',
     '口 + 齒(이)의 모양. 정자 嚙. 噛む(かむ)는 상용한자표 밖이라 かむ로 가나 표기가 많음'),
    ('濡', '적실 유', '젖다, 적시다', '水', 'ジュ、ぬ-れる', [['濡れる', 'ぬれる', 'ぬ-れる', '젖다']], '需',
     '氵(물) + 需(소리 ジュ). 濡れる(ぬれる)는 상용한자표 밖이라 ぬれる로 가나 표기가 많음. 需(구할 수, 중2)와 소리 부분이 같음'),
]

def kvg(ch):
    s = open(os.path.join(REF_DIR, 'kvg_hyogai', f'{ord(ch):05x}.svg'), encoding='utf-8').read()
    p = sorted(re.findall(r'<path id="kvg:[0-9a-f]+-s(\d+)"[^>]*\sd="([^"]+)"', s), key=lambda p: int(p[0]))
    return [re.sub(r'\s+', ' ', d).strip() for _, d in p]

def main():
    from prep_ms import kanjidic, hangul_dict
    from build_ms import jm
    KD, HD = kanjidic(), hangul_dict()
    J = json.load(open(os.path.join(REF_DIR, 'jouyou.json'), encoding='utf-8'))
    vs = open(os.path.join(ROOT, 'data', 'vocab.js'), encoding='utf-8').read()
    V = {(w[0], w[1]) for w in json.loads(vs[vs.index('=') + 1:].rstrip().rstrip(';'))['words']}
    err, items = [], []
    for k, hun, m, rad, rd, ex, link, note in CARDS:
        if k in J: err.append(f'{k}: 상용한자임')
        snd = hun.split()[-1]
        if snd not in KD.get(k, {}).get('ko', []) + [s for s, _ in HD.get(k, [])]: err.append(f'{k}: 한국음 {snd} 사전 후보 아님')
        if link not in J: err.append(f'{k}: 이어 줄 글자 {link} 가 상용한자 아님')
        rds = parse_readings(rd); rmap = {r['r']: r for r in rds}
        exs = []
        for w, y, r, mm in ex:
            if (w, y) not in jm(): err.append(f'{k}: {w}({y}) JMdict에 없음')
            if (w, y) not in V: err.append(f'{k}: {w}({y}) 단어장에 없음')
            stem = kata2hira(rmap[r]['stem']); hs = y.find(stem)
            if hs < 0: err.append(f'{k}: {w}({y}) 안에 읽기 {stem} 없음')
            exs.append(dict(w=w, y=y, r=r, m=mm, hs=max(hs, 0), hl=len(stem), ch=False, rare=False, cm=True))
        st = kvg(k)
        items.append(dict(k=k, g=11, sc=len(st), rad=rad, theme='상용 밖', hun=hun, m=m, rd=rds, ex=exs, sp=[], st=st,
                          core=[ex[0][2]], basic=True, hy=True, link=link, note=note))
    if err:
        print('\n'.join('ERR ' + e for e in err)); return 1
    data = dict(grade=11, themes=[dict(name='상용 밖', e='', ks=''.join(i['k'] for i in items))], items=items)
    js = 'window.KANJI_GRADES=window.KANJI_GRADES||{};window.KANJI_GRADES[11]=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n'
    open(os.path.join(ROOT, 'data', 'g11.js'), 'w', encoding='utf-8').write(js)
    write_index()
    print(f'상용 밖 {len(items)}자 → data/g11.js ({len(js.encode())} bytes): ' + ''.join(i['k'] for i in items))
    return 0

if __name__ == '__main__':
    sys.exit(main())
