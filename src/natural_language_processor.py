"""
自然语言润色处理器

新策略：完全依据用户用自然语言描述的风格、结构等要求，对原文进行重写。
- 不套用任何预设润色模板或文档类型风格。
- 保留原文核心内容。
- 识别并复用原文中的图片、表格、公式，按合理位置插入新文章。
"""
import json
import re
from copy import deepcopy
from typing import Dict, List, Any, Optional
from openai import OpenAI
from src.logger import log_info, log_error, log_warning
from src.utils import extract_json_from_text, extract_caption


class NaturalLanguageProcessor:
    """自然语言润色处理器"""

    def __init__(self, client: OpenAI, model_name: str, use_tool_calling: bool = True):
        """
        初始化自然语言处理器

        Args:
            client: OpenAI 客户端
            model_name: 模型名称
            use_tool_calling: 是否使用工具调用模式（默认 True）
        """
        self.client = client
        self.model_name = model_name
        self.use_tool_calling = use_tool_calling
        self.user_prompt = ""  # 用于检测保留图表意图

        if use_tool_calling:
            from src.tool_calling_processor import ToolCallingProcessor
            self.tool_processor = ToolCallingProcessor(client, model_name)
            log_info("使用工具调用模式处理文档")
        else:
            self.tool_processor = None
            log_info("使用传统模式处理文档")

    @staticmethod
    def _user_wants_keep_charts(user_prompt: str) -> bool:
        """检测用户提示中是否有明确要求保留图表/图片/公式的意图。"""
        if not user_prompt:
            return False
        up = user_prompt.lower()
        keywords = [
            "保留所有", "保留全部", "保留.*图表", "保留.*图片", "保留.*公式",
            "保留核心.*图表", "保留核心.*图片", "保留核心.*公式",
            "保留.*必要.*图表", "保留.*必要.*图片", "保留.*必要.*公式",
            "保留所有图表", "保留所有图片", "保留所有公式",
        ]
        for kw in keywords:
            if re.search(kw, up):
                return True
        return False

    def process(
        self,
        source_content: Dict[str, Any],
        document_info: Dict[str, Any],
        user_prompt: str
    ) -> Optional[Dict[str, Any]]:
        """
        处理源文档，按用户自然语言要求生成新文档结构。

        Args:
            source_content: 源文档内容（elements, paragraphs）
            document_info: 文档信息
            user_prompt: 用户的自然语言要求

        Returns:
            生成的内容结构，失败返回 None
        """
        # 如果使用工具调用模式，委托给 ToolCallingProcessor
        if self.use_tool_calling and self.tool_processor:
            try:
                result = self.tool_processor.process(source_content, document_info, user_prompt)
                if result:
                    return result
                log_warning("工具调用模式失败，回退到传统模式")
            except Exception as e:
                log_error(f"工具调用模式异常：{e}，回退到传统模式")

        # 传统模式处理
        log_info("开始自然语言润色处理")
        self.user_prompt = user_prompt

        elements = self._extract_elements(source_content)
        total_non_text = len(elements['tables']) + len(elements['images']) + len(elements['formulas'])
        log_info(
            f"提取到 {len(elements['paragraphs'])} 个段落, "
            f"{len(elements['tables'])} 个表格, "
            f"{len(elements['images'])} 个图片, "
            f"{len(elements['formulas'])} 个公式"
        )

        generated = self._ai_generate_document(
            elements=elements,
            document_info=document_info,
            user_prompt=user_prompt
        )

        if not generated:
            log_error("AI 生成失败")
            return None

        structure = generated.get('structure', [])
        if not structure:
            log_error("AI 生成的结构为空")
            return None

        # 验证并修复结构
        structure = self._validate_and_fix_structure(structure, elements)

        log_info(f"自然语言润色完成，共 {len(structure)} 个元素")

        return {
            'structure': structure,
            'tables': elements['tables'],
            'images': elements['images'],
            'formulas': elements['formulas'],
            'document_title': generated.get('document_title', '')
        }

    def _extract_elements(self, source_content: Dict) -> Dict:
        """
        提取源文档所有元素，把行内公式也提取为可引用的公式条目。
        """
        raw_elements = source_content.get('elements', [])
        paragraphs = source_content.get('paragraphs', {})

        result = {
            'paragraphs': [],
            'tables': [],
            'images': [],
            'formulas': [],
            'order': []
        }

        formula_counter = 0

        for elem_type, elem_id, content in raw_elements:
            result['order'].append({'type': elem_type, 'id': elem_id})

            if elem_type == 'paragraph' and elem_id in paragraphs:
                data = paragraphs[elem_id]
                if isinstance(data, tuple):
                    text = data[0] if data[0] else ""
                    formula_runs = data[1]
                    original_para = data[2]
                    all_runs = data[3]
                    omath_elements = data[4] if len(data) > 4 else None
                    formula_run_indices = data[5] if len(data) > 5 else None
                else:
                    text = data if data else ""
                    formula_runs = None
                    original_para = None
                    all_runs = None
                    omath_elements = None
                    formula_run_indices = None

                # 如果段落包含行内公式，把公式提取为可引用元素，并在文本中插入占位符
                if formula_run_indices and omath_elements:
                    fids = []
                    for idx, omath in enumerate(omath_elements):
                        formula_counter += 1
                        fid = f"F{formula_counter}"
                        fids.append(fid)
                        result['formulas'].append({
                            'id': fid,
                            'kind': 'inline',
                            'omath': omath,
                            'original_paragraph_id': elem_id,
                            'original_para': original_para,
                            'all_runs': all_runs,
                            'formula_runs': formula_runs
                        })
                    # 在原文中插入公式占位符，便于 AI 识别行内公式位置
                    text = self._insert_formula_placeholders(text, formula_run_indices, fids)

                if text is not None:
                    result['paragraphs'].append({'id': elem_id, 'text': text})

            elif elem_type == 'table':
                result['tables'].append({'id': elem_id, 'content': content})
            elif elem_type == 'image':
                result['images'].append({'id': elem_id, 'content': content})
            elif elem_type == 'formula':
                formula_counter += 1
                fid = f"F{formula_counter}"
                result['formulas'].append({
                    'id': fid,
                    'kind': 'standalone',
                    'content': content
                })

        return result

    def _insert_formula_placeholders(
        self,
        text: str,
        formula_run_indices: List[int],
        fids: List[str]
    ) -> str:
        """
        在文本中按 run 位置插入公式占位符，便于 AI 识别行内公式位置。
        占位符格式：{{FORMULA#FID#}}
        """
        if not formula_run_indices or not fids:
            return text

        # 计算文本段数量 = 公式数量 + 1
        text_segments_count = len(formula_run_indices) + 1
        segments = self._split_text_for_placeholders(text, text_segments_count)

        result_parts = []
        segment_idx = 0
        formula_idx = 0

        # 处理在开头的公式
        while formula_idx < len(formula_run_indices) and formula_run_indices[formula_idx] == -1:
            result_parts.append(f"{{{{FORMULA#{fids[formula_idx]}#}}}}")
            formula_idx += 1

        # 添加第一段文本
        if segment_idx < len(segments):
            result_parts.append(segments[segment_idx])
            segment_idx += 1

        # 交替添加占位符和文本段
        remaining_formulas = len(formula_run_indices) - formula_idx
        for i in range(remaining_formulas):
            result_parts.append(f"{{{{FORMULA#{fids[formula_idx]}#}}}}")
            formula_idx += 1

            if segment_idx < len(segments):
                result_parts.append(segments[segment_idx])
                segment_idx += 1

        return ''.join(result_parts)

    def _split_text_for_placeholders(self, text: str, num_segments: int) -> List[str]:
        """
        将文本分割成指定数量的段，用于占位符插入。
        简单策略：按字符数平均分割。
        """
        if num_segments <= 0:
            return [text]
        if num_segments == 1:
            return [text]

        total_len = len(text)
        segment_len = total_len // num_segments
        segments = []

        for i in range(num_segments):
            start = i * segment_len
            if i == num_segments - 1:
                segments.append(text[start:])
            else:
                end = start + segment_len
                segments.append(text[start:end])

        return segments

    def _ai_generate_document(
        self,
        elements: Dict,
        document_info: Dict[str, Any],
        user_prompt: str
    ) -> Optional[Dict[str, Any]]:
        """
        调用 AI 按用户自然语言要求生成新文档结构。
        """
        para_texts = []
        for para in elements['paragraphs']:
            preview = para['text'][:250]
            if len(para['text']) > 250:
                preview += "..."
            para_texts.append(f"[{para['id']}]: {preview}")

        order_map = {item['id']: i for i, item in enumerate(elements['order'])}

        # 让 AI 先提炼图表/公式的主题描述
        chart_formula_info = self._ai_extract_chart_and_formula_descriptions(elements, order_map)

        chart_index = []
        for table in elements['tables']:
            info = chart_formula_info.get(table['id'], {'description': "数据表格", 'nearest_paragraph_id': ''})
            desc = info['description']
            nearest = info['nearest_paragraph_id']
            caption = info.get('caption', '')
            cap_str = f"，题注：{caption}" if caption else ""
            pos = f"（原文位置：段落[{nearest}]后面）" if nearest else ""
            chart_index.append(f"表格 [{table['id']}] - {desc}{cap_str}{pos}")

        for image in elements['images']:
            info = chart_formula_info.get(image['id'], {'description': "示意图", 'nearest_paragraph_id': ''})
            desc = info['description']
            nearest = info['nearest_paragraph_id']
            caption = info.get('caption', '')
            cap_str = f"，题注：{caption}" if caption else ""
            pos = f"（原文位置：段落[{nearest}]后面）" if nearest else ""
            chart_index.append(f"图片 [{image['id']}] - {desc}{cap_str}{pos}")

        for formula in elements['formulas']:
            info = chart_formula_info.get(formula['id'], {'description': "公式", 'nearest_paragraph_id': ''})
            desc = info['description']
            nearest = info['nearest_paragraph_id']
            caption = info.get('caption', '')
            cap_str = f"，题注：{caption}" if caption else ""
            pos = f"（原文位置：段落[{nearest}]后面）" if nearest else ""
            chart_index.append(f"公式 [{formula['id']}] - {desc}{cap_str}{pos}")

        doc_title = document_info.get('title', '未知')
        doc_type = document_info.get('type', '其他类型')

        prompt = f"""你是专业的文档编辑和写作专家。请根据用户要求对以下文档进行重写和润色。

=== 用户要求（最高优先级） ===
{user_prompt if user_prompt else '保持原文核心内容，进行通顺、连贯的重写。'}

=== 原文档信息 ===
- 文档标题：{doc_title}
- 文档类型：{doc_type}

=== 原文段落（共 {len(elements['paragraphs'])} 个）===
{chr(10).join(para_texts[:80])}

=== 原文图表公式索引（共 {len(chart_index)} 个）===
{chr(10).join(chart_index) if chart_index else '无'}

=== 任务要求 ===
1. **严格遵循用户要求**：用户的风格、结构、内容等要求具有最高优先级。
2. **保留核心内容**：不得脱离原文核心信息，不得编造原文没有的关键内容。
3. **重新组织文章**：可以根据用户要求调整章节、段落结构，使文章结构合理、前后连贯。
4. **复用图表公式（放置位置必须语义匹配）**：
   - 必须使用占位符在合理位置插入原文的表格、图片、公式。
   - 表格占位符：{{{{TABLE#完整ID#}}}}
   - 图片占位符：{{{{IMAGE#完整ID#}}}}
   - 公式占位符：{{{{FORMULA#完整ID#}}}}
   - 完整 ID 必须与索引中完全一致（例如 T1、I1、F1，或多文档前缀形式）。
   - **放置规则（最关键）**：根据每个图表的"含义/题注"与文章句子、段落的语义主题进行匹配，
     把图表放到"描述、解释或提及该图表主题"的文字旁边，前后要有与该图表语义一致的引导或说明文字。
     **禁止把图表放在与它含义/题注完全无关的文字旁边。**
   - 位置不需与原文完全一致：图表的先后顺序、锚定段落可随新文章结构调整，只要图表与所在处文字语义主题匹配即可。
   - 每个表格/图片/公式前后都应有引导或说明文字，不能连续堆叠多个。
5. **{'必须保留其中的全部或部分图表公式' if self._user_wants_keep_charts(self.user_prompt) else '按需选择图表（不必全部使用）'}**：
   {'用户明确要求保留图表/图片/公式，因此你必须在生成的文章中保留原文的图表公式，不得全部丢弃；具体保留哪些由你根据正文语义自行判断——与正文主题相关的应当保留并放到语义匹配的位置，确实无法融入的可舍弃，但应尽量多保留。' if self._user_wants_keep_charts(self.user_prompt) else '只引用与正文语义相关、确实被正文讨论/解释/提及的图表；与正文无关的图表可不使用，不要为了凑齐而硬塞。但应尽量多保留与主题相关的图表，避免全部丢弃。凡是被引用的图表，必须与它旁边的文字语义主题匹配，ID 与索引中完全一致。'}
   **若用户明确要求按原文顺序全部保留、或指定某图表必须出现，则以用户要求为准。**

=== 输出格式（严格 JSON）===
{{
  "document_title": "生成后的文档标题",
  "structure": [
    {{"type": "heading", "title": "章节标题", "level": 1}},
    {{"type": "paragraph", "text": "段落内容..."}},
    {{"type": "table", "id": "T1"}},
    {{"type": "image", "id": "I1"}},
    {{"type": "formula", "id": "F1"}},
    {{"type": "paragraph", "text": "继续段落内容..."}}
  ]
}}

=== 注意事项 ===
- 只输出 JSON，不要输出任何其他文字或说明。
- structure 数组按最终文档顺序排列。
- heading 的 level 取 1-6。
- 如果用户没有要求特定结构，可保持与原文相似的章节安排，但文字必须重新生成。
- 被引用的每个表格/图片/公式只能出现一次。

请开始生成："""

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "你是专业的文档编辑和写作专家。擅长根据用户要求重写文档，保留原文核心内容，并合理复用原文的图表公式。只输出 JSON。"
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,
            )

            result = response.choices[0].message.content.strip()
            log_info(f"AI 生成响应长度：{len(result)} 字符")

            generated_data = extract_json_from_text(result)
            if not generated_data:
                log_error(f"无法解析 JSON：{result[:200]}")
                return None

            return generated_data

        except Exception as e:
            log_error(f"AI 生成失败：{e}")
            return None

    def _ai_extract_chart_and_formula_descriptions(
        self,
        elements: Dict,
        order_map: Dict
    ) -> Dict[str, Dict]:
        """
        使用 AI 批量提炼表格、图片、公式的主题描述。
        以"连续图表组"为单位，结合整组前后更完整的段落语义来推断图表名称，
        提升识别准确度。
        """
        if not elements['tables'] and not elements['images'] and not elements['formulas']:
            return {}

        consecutive_groups = self._identify_consecutive_charts(elements, order_map)
        chart_info_map = {}

        for group in consecutive_groups:
            group_descriptions = self._identify_group(elements, order_map, group)
            if group_descriptions:
                chart_info_map.update(group_descriptions)

        log_info(f"AI 提炼图表公式主题完成，共 {len(chart_info_map)} 个")
        return chart_info_map

    def _identify_group(self, elements: Dict, order_map: Dict, group: List[str]) -> Dict[str, Dict]:
        """识别并命名为一个连续图表组内的所有图表。"""
        if not group:
            return {}

        before, after = self._extract_group_context(elements, order_map, group)
        # 拆分为"紧邻段"（正上/正下方紧邻图表的那一段）与"更远段"，紧邻段权重最高
        # 单图组只给紧邻段，不给更远段落，避免被远处无关内容带偏
        near_before_text = before[-1]['text'] if before else ''
        far_before_text = ' | '.join(p['text'] for p in before[:-1]) if len(group) > 1 else ''
        after_text = ' | '.join(p['text'] for p in after)
        nearest_para = before[-1]['id'] if before else ''
        caption = extract_caption(after[0]['text']) if after and after[0]['text'] else ''

        # 组织组内各图表
        group_items = []
        for cid in group:
            if cid in {t['id'] for t in elements['tables']}:
                chart_type = '表格'
                table = next(t for t in elements['tables'] if t['id'] == cid)
                content = ""
                if table['content'] and isinstance(table['content'], list) and len(table['content']) > 0:
                    rows = []
                    for row in table['content'][:5]:
                        if row:
                            rows.append(", ".join([str(c) for c in row[:5]][:30]))
                    content = "; ".join(rows)
            elif cid in {i['id'] for i in elements['images']}:
                chart_type = '图片'
                content = ""
            elif cid in {f['id'] for f in elements['formulas']}:
                chart_type = '公式'
                content = ""
            else:
                continue
            group_items.append({'id': cid, 'type': chart_type, 'content': content})

        if not group_items:
            return {}

        is_multi = len(group_items) > 1
        item_lines = []
        for it in group_items:
            line = f"{it['type']} [{it['id']}]"
            if it['content']:
                line += f"\n    内容摘要：{it['content']}"
            item_lines.append(line)

        group_desc = (
            "以下这组图表连续出现，中间没有文字间隔，属于同一说明语境下的不同子图表，"
            "它们对应的含义/名称应基于同一组前后文推断，且大概率彼此相关。"
            if is_multi else "单个图表："
        )

        prompt = f"""你是专业的文档分析专家。请根据图文关系，准确推断每个图表/公式的名称与含义。

=== 紧邻上文段落（本图正上方紧邻的文字 —— 最权威的本图说明，优先依据它）===
{near_before_text if near_before_text else '（无）'}

=== 更早的上文段落（距图稍远的背景文字，仅在紧邻段无法判断时参考）===
{far_before_text if far_before_text else '（无）'}

=== 下文段落（图表之后的文字 —— 常为下一节标题或下一图说明，仅供参考）===
{after_text if after_text else '（无）'}

=== 待识别图表/公式 ===
{chr(10).join(item_lines)}

=== 任务要求 ===
1. **以"紧邻上文段落"为最优先依据**：紧邻本图正上方的文字常以"下面的图片是……""如下图所示""报错如下所示""见下图，……"等句式直接说明本图内容，应据此命名。"更早的上文段落"只在紧邻段不足以判断时才作背景参考，**绝不能让它们覆盖紧邻段给出的明确语义**。例如紧邻上文是"做设计检查，报错如下所示"，就应命名为"设计检查报错信息"，即使更早段落提到过"生成HDL文件"。
2. **下文段落仅在"用图内指代词回指本图"时才采信**：图表之后的正文通常属于"下一张图/下一节"（如标题"设计检查"、句子"下面是设计的完整模块图"是对再下一张图的说明），**不要直接拿它给当前图命名**。仅当出现以下几种情形时才把下文中**指代本图的那部分**纳入推导：
   - 下文以"图/表/公式 + 编号 + 标题"（如图1-1 系统架构、表2 参数表、Figure 3.2）这样的标准题注句式开头；
   - 下文出现"上图""如上图""见上图""上图所示""下图(参考上图)"等**回指本图**的词语，且其后描述了本图内容（此时可就该句补充/确认本图名称）。
3. **下文中与上文无关或相矛盾的描述一律忽略，以上文为准**：若下文没有明确回指本图，或所描述内容与上文对本图的说明不相干、相冲突，则完全忽略下文，只依据上文命名。
4. 尽量使用贴近原文的准确名称（例如"3分量RGB输入像素分布图"、"寄存器地址映射表"、"运动学公式"），
   不要笼统地写"示意图"、"图片"、"数据表"。
5. 若同一组有多个图表且上方只有一句总说明，则**这些图都是该说明对应的图**，应给出相近/从属的名称（如"DeepSeek给出的配置建议（图1）"、"DeepSeek给出的配置建议（图2）"），不要为它们臆造下文提到的不相关内容。
6. 名称用词专业、准确，改为名词短语，长度不限但不要写成句子。
7. 只输出 JSON，键为上面的图表 ID，值为名称。格式如下：
{{
  "I1": "3分量RGB输入像素分布图"
}}
若某个图表无法判断，值为"图片"或"表格"或"公式"即可。

请开始："""

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "你是专业的文档分析专家，擅长根据上下文推断图表名称。只输出 JSON。"
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
            )

            result = response.choices[0].message.content.strip()
            descriptions = extract_json_from_text(result)

            group_result = {}
            for it in group_items:
                cid = it['id']
                default_desc = "数据表格" if it['type'] == '表格' else ("示意图" if it['type'] == '图片' else "公式")
                group_result[cid] = {
                    'description': descriptions.get(cid, default_desc) if descriptions else default_desc,
                    'nearest_paragraph_id': nearest_para,
                    'caption': caption
                }

            for cid, g in group_result.items():
                msg = (
                    f"图表识别 [组{'/'.join(group)}] {cid} ({it['type']}) → {g['description']}"
                    f"{('，题注：' + g['caption']) if g.get('caption') else ''}"
                )
                log_info(msg)
                print(f"[INFO] {msg}")
            return group_result

        except Exception as e:
            log_error(f"AI 提炼图表公式主题失败：{e}")
            group_result = {}
            for it in group_items:
                cid = it['id']
                default_desc = "数据表格" if it['type'] == '表格' else ("示意图" if it['type'] == '图片' else "公式")
                group_result[cid] = {
                    'description': default_desc,
                    'nearest_paragraph_id': nearest_para,
                    'caption': caption
                }
            return group_result

    def _extract_group_context(
        self,
        elements: Dict,
        order_map: Dict,
        group: List[str],
        before_count: int = 2,
        after_count: int = 2,
        max_len: int = 600
    ) -> tuple:
        """提取整个连续图表组共同的前后段落上下文。"""
        if not group or group[0] not in order_map:
            return [], []

        first_idx = order_map[group[0]]
        last_idx = order_map.get(group[-1], first_idx)
        para_by_id = {p['id']: p for p in elements['paragraphs']}

        before = []
        for i in range(first_idx - 1, max(0, first_idx - 40), -1):
            item = elements['order'][i]
            if item['type'] == 'paragraph':
                para = para_by_id.get(item['id'])
                if para and para['text']:
                    before.append({'id': item['id'], 'text': para['text'][:max_len]})
                    if len(before) >= before_count:
                        break
        before.reverse()

        after = []
        for i in range(last_idx + 1, min(len(elements['order']), last_idx + 40)):
            item = elements['order'][i]
            if item['type'] == 'paragraph':
                para = para_by_id.get(item['id'])
                if para and para['text']:
                    after.append({'id': item['id'], 'text': para['text'][:max_len]})
                    if len(after) >= after_count:
                        break

        return before, after

    def _identify_consecutive_charts(self, elements: Dict, order_map: Dict) -> List[List[str]]:
        """识别连续出现的图表/公式组。"""
        consecutive_groups = []
        current_group = []

        for item in elements['order']:
            if item['type'] in ('table', 'image', 'formula'):
                current_group.append(item['id'])
            else:
                if current_group:
                    consecutive_groups.append(current_group)
                    current_group = []

        if current_group:
            consecutive_groups.append(current_group)

        return consecutive_groups

    def _validate_and_fix_structure(self, structure: List[Dict], elements: Dict) -> List[Dict]:
        """
        验证并修复 AI 生成的结构：
        1. 补齐缺失的表格/图片/公式。
        2. 修正简化 ID。
        3. 避免连续多个非文本元素堆叠。
        """
        fixed = [dict(item) for item in structure]

        # 修正简化的图表/公式 ID
        for item in fixed:
            if item.get('type') == 'table':
                item['id'] = self._match_full_id(item.get('id'), [t['id'] for t in elements['tables']])
            elif item.get('type') == 'image':
                item['id'] = self._match_full_id(item.get('id'), [i['id'] for i in elements['images']])
            elif item.get('type') == 'formula':
                item['id'] = self._match_full_id(item.get('id'), [f['id'] for f in elements['formulas']])

        referenced_tables = {item.get('id') for item in fixed if item.get('type') == 'table'}
        referenced_images = {item.get('id') for item in fixed if item.get('type') == 'image'}
        referenced_formulas = {item.get('id') for item in fixed if item.get('type') == 'formula'}

        missing_tables = [t['id'] for t in elements['tables'] if t['id'] not in referenced_tables]
        missing_images = [i['id'] for i in elements['images'] if i['id'] not in referenced_images]
        missing_formulas = [f['id'] for f in elements['formulas'] if f['id'] not in referenced_formulas]

        if missing_tables or missing_images or missing_formulas:
            log_warning(
                f"未引用图表（按需选择，不强制补齐）：表格{len(missing_tables)} "
                f"图片{len(missing_images)} 公式{len(missing_formulas)}"
            )

        # 仅打散连续的非文本元素（保留标题/段落原顺序，不清空语义锚点）
        fixed = self._adjust_chart_distribution(fixed)
        return fixed

    def _match_full_id(self, item_id: str, valid_ids: List[str]) -> str:
        """如果 ID 不存在，尝试匹配完整 ID（兼容简化 ID）。"""
        if not item_id:
            return item_id
        if item_id in valid_ids:
            return item_id
        matches = [vid for vid in valid_ids if vid.endswith(f"::{item_id}")]
        if matches:
            return matches[0]
        return item_id

    def _adjust_chart_distribution(self, structure: List[Dict]) -> List[Dict]:
        """将连续的非文本元素穿插到段落之间。

        仅当出现连续 2 个以上的图表时才需要处理，否则保持原顺序。
        重新分配时保留 heading/段落等"文字元素"的原始相对顺序，
        只把"连续图表"均匀地拆散插入到文字元素之间，避免图表堆叠、
        同时不把章节标题挪到文末。
        """
        max_consecutive = 0
        current = 0
        for item in structure:
            if item.get('type') in ('table', 'image', 'formula'):
                current += 1
                max_consecutive = max(max_consecutive, current)
            else:
                current = 0

        if max_consecutive <= 2:
            return structure

        # 文字元素（段落 / 标题）保留原顺序，图表元素单独拆散插入
        text_items = [item for item in structure if item.get('type') in ('paragraph', 'heading')]
        charts = [item for item in structure if item.get('type') in ('table', 'image', 'formula')]
        others = [item for item in structure if item.get('type') not in ('paragraph', 'heading', 'table', 'image', 'formula')]

        if not text_items or not charts:
            return structure

        adjusted = []
        chart_index = 0
        charts_per_text = len(charts) / len(text_items)

        for i, text_item in enumerate(text_items):
            adjusted.append(text_item)
            expected = int((i + 1) * charts_per_text)
            while chart_index < expected and chart_index < len(charts):
                adjusted.append(charts[chart_index])
                chart_index += 1

        # 剩余图表 + 其它非常规元素追加到末尾
        while chart_index < len(charts):
            adjusted.append(charts[chart_index])
            chart_index += 1
        adjusted.extend(others)
        return adjusted
