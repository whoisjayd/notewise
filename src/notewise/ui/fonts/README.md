# Bundled PDF font

`NotoSans-{Regular,Bold,Italic,BoldItalic}.ttf` are static instances (wght 400/700,
wdth 100) of the Google Fonts "Noto Sans" variable font, generated with
`fontTools.varLib.instancer` from:

- `ofl/notosans/NotoSans[wdth,wght].ttf`
- `ofl/notosans/NotoSans-Italic[wdth,wght].ttf`

in <https://github.com/google/fonts>, licensed under the SIL Open Font License 1.1
(see `OFL.txt`, which permits redistributing modified/instanced versions).

They cover Latin, Cyrillic, Greek, Vietnamese, and Devanagari; they do not cover
Arabic, Hebrew, or CJK scripts. `notewise/pipeline/_documents.py` uses these for
PDF export instead of fpdf2's Latin-1-only core fonts; text outside their
coverage falls back to a Markdown file.
