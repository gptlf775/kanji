# -*- coding: utf-8 -*-
"""
가나 획순 자료 빌드 + 검증 → data/kana.js
  입력: 원천데이터/kvg_kana/*.svg (KanjiVG 가나 획순, CC BY-SA 3.0)
  검증: 획 수가 일본 교과서 획 수와 같은지 (청음 46자 × 2 + 탁음·반탁음·작은 글자·ヴ·ー)
사용: python build_kana.py
"""
import json, os, re, sys, unicodedata
from build import REF_DIR, ROOT, write_index

KDIR = os.path.join(REF_DIR, 'kvg_kana')
# 교과서 획 수 (청음)
HIRA = 'あ3い2う2え2お3か3き4く1け3こ2さ3し1す2せ3そ1た4ち2つ1て1と2な4に3ぬ2ね2の1は3ひ1ふ4へ1ほ4ま3み2む3め2も3や3ゆ2よ2ら2り2る1れ2ろ1わ2を3ん1'
KATA = 'ア2イ2ウ3エ3オ3カ2キ3ク2ケ3コ2サ3シ3ス2セ2ソ2タ3チ3ツ3テ3ト2ナ2ニ2ヌ2ネ4ノ1ハ2ヒ2フ1ヘ1ホ4マ2ミ3ム2メ2モ3ヤ2ユ2ヨ3ラ2リ2ル2レ1ロ3ワ2ヲ3ン2'
SMALL = dict(zip('ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ', 'あいうえおつやゆよわアイウエオツヤユヨワカケ'))

def expected():
    exp = {c: int(d) for s in (HIRA, KATA) for c, d in re.findall(r'(\D)(\d)', s)}
    for c in list(exp):
        for add, mark in ((2, '゙'), (1, '゚')):   # 탁점 2획, 반탁점 1획
            cc = unicodedata.normalize('NFC', c + mark)
            if len(cc) == 1: exp[cc] = exp[c] + add
    for s, b in SMALL.items(): exp[s] = exp[b]
    exp.update({'ヴ': 5, 'ゔ': 4, 'ー': 1})
    return exp

def paths(ch):
    s = open(os.path.join(KDIR, f'{ord(ch):05x}.svg'), encoding='utf-8').read()
    ps = re.findall(r'<path id="kvg:[0-9a-f]+-s(\d+)"[^>]*\sd="([^"]+)"', s)
    ps.sort(key=lambda p: int(p[0]))
    return [re.sub(r'\s+', ' ', d).strip() for _, d in ps]

def main():
    exp, out, errs = expected(), {}, []
    for ch, n in sorted(exp.items()):
        try: ps = paths(ch)
        except FileNotFoundError: errs.append(f'{ch}: 파일 없음'); continue
        if len(ps) != n: errs.append(f'{ch}: KanjiVG {len(ps)}획 / 교과서 {n}획')
        out[ch] = ps
    js = 'window.KANA_KVG=' + json.dumps(out, ensure_ascii=False, separators=(',', ':')) + ';\n'
    open(os.path.join(ROOT, 'data', 'kana.js'), 'w', encoding='utf-8').write(js)
    write_index()
    print(f'가나 {len(out)}자 · 획 수 불일치·누락 {len(errs)}건 · {len(js.encode())} bytes')
    for e in errs: print('ERR', e)
    return 1 if errs else 0

if __name__ == '__main__':
    sys.exit(main())
