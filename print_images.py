# -*- coding: utf-8 -*-
"""打印每个图表组用于识别的上下文（组前/后段落与组内图表），供确认识别依据"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from src.parser import DocumentParser
from src.natural_language_processor import NaturalLanguageProcessor

doc_path = r"e:\AI\Agent\WordAiKit\word-ai-kit\1.视频加静态字幕.docx"
parser = DocumentParser()
elements, paragraphs, doc = parser.parse(doc_path)

# 不需要 client 也能提取分组与上下文（用 dummy 跑，只调 _extract_group_context / _identify_group 前的部分）
nlp = NaturalLanguageProcessor(client=None, model_name='x', use_tool_calling=False)
edict = nlp._extract_elements({'elements': elements, 'paragraphs': paragraphs})
order_map = {x['id']: i for i, x in enumerate(edict['order'])}

groups = nlp._identify_consecutive_charts(edict, order_map)

def fmt_type(cid):
    if cid in {t['id'] for t in edict['tables']}: return '表格'
    if cid in {i['id'] for i in edict['images']}: return '图片'
    if cid in {f['id'] for f in edict['formulas']}: return '公式'
    return '?'

for gi, group in enumerate(groups, 1):
    before, after = nlp._extract_group_context(edict, order_map, group)
    print(f"\n{'#'*70}")
    print(f"图表组 {gi}  元素: {', '.join(group)}  ({', '.join(fmt_type(g_) for g_ in group)})")
    print(f"{'#'*70}")
    print("① 组前段落（识别依据 - 越靠后越贴近图表）:")
    if before:
        for p in before:
            print(f"   [{p['id']}] {p['text']}")
    else:
        print("   （无）")
    print("② 组后段落（识别依据 - 常含题注）:")
    if after:
        for p in after:
            print(f"   [{p['id']}] {p['text']}")
    else:
        print("   （无）")