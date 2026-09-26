"""
工具调用处理器

实现基于 Function Calling 的文档处理流程。
AI 可以主动调用工具查询文档结构、图表上下文等信息，
从而更准确地理解文档并生成结构。
"""
import json
from typing import Dict, List, Any, Optional
from openai import OpenAI
from src.logger import log_info, log_error, log_warning
from src.utils import extract_json_from_text
from src.document_tools import DocumentTools, TOOL_DEFINITIONS


class ToolCallingProcessor:
    """工具调用处理器"""

    def __init__(self, client: OpenAI, model_name: str, max_tool_calls: int = 30):
        """
        初始化工具调用处理器

        Args:
            client: OpenAI 客户端
            model_name: 模型名称
            max_tool_calls: 最大工具调用次数，防止无限循环
        """
        self.client = client
        self.model_name = model_name
        self.max_tool_calls = max_tool_calls
        self.user_prompt = ""  # 当前用户提示词，用于检测保留图表意图

    @staticmethod
    def _user_wants_keep_charts(user_prompt: str) -> bool:
        """检测用户提示中是否有明确要求保留图表/图片/公式的意图。"""
        if not user_prompt:
            return False
        up = user_prompt.lower()
        # 包含"保留所有"、"保留.*图表"、"保留.*图片"、"保留.*公式"等明确保留意图
        keywords = [
            "保留所有", "保留全部", "保留.*图表", "保留.*图片", "保留.*公式",
            "保留核心.*图表", "保留核心.*图片", "保留核心.*公式",
            "保留.*必要.*图表", "保留.*必要.*图片", "保留.*必要.*公式",
            "保留所有图表", "保留所有图片", "保留所有公式",
        ]
        import re
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
        处理文档，支持多轮工具调用

        Args:
            source_content: 源文档内容
            document_info: 文档信息
            user_prompt: 用户的自然语言要求

        Returns:
            生成的内容结构，失败返回 None
        """
        log_info("开始工具调用模式处理")
        self.user_prompt = user_prompt

        # 提取元素
        elements = self._extract_elements(source_content)
        total_non_text = len(elements['tables']) + len(elements['images']) + len(elements['formulas'])
        log_info(
            f"提取到 {len(elements['paragraphs'])} 个段落, "
            f"{len(elements['tables'])} 个表格, "
            f"{len(elements['images'])} 个图片, "
            f"{len(elements['formulas'])} 个公式"
        )

        # 初始化工具集
        doc_tools = DocumentTools(elements, document_info, self.client, self.model_name)

        # 构建初始消息
        messages = [
            {
                "role": "system",
                "content": self._build_system_prompt()
            },
            {
                "role": "user",
                "content": self._build_initial_prompt(elements, document_info, user_prompt, doc_tools)
            }
        ]

        # 工具调用循环
        tool_call_count = 0
        final_result = None

        while tool_call_count < self.max_tool_calls:
            try:
                log_info(f"工具调用循环第 {tool_call_count + 1} 轮")

                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    temperature=0.4,
                )

                message = response.choices[0].message

                # 如果 AI 决定调用工具
                if message.tool_calls:
                    # 添加 assistant 消息（包含工具调用）
                    messages.append(message)

                    # 执行每个工具调用
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        try:
                            arguments = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError:
                            arguments = {}

                        log_info(f"AI 调用工具：{tool_name}({arguments})")

                        # 执行工具
                        result = doc_tools.execute_tool(tool_name, arguments)
                        result_json = json.dumps(result, ensure_ascii=False)

                        log_info(f"工具返回结果长度：{len(result_json)} 字符")

                        # 添加工具结果到消息
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result_json
                        })

                    tool_call_count += 1
                else:
                    # AI 生成最终结果（不再调用工具）
                    final_result = message.content
                    log_info(f"AI 生成最终结果，长度：{len(final_result)} 字符")
                    break

            except Exception as e:
                log_error(f"工具调用循环异常：{e}")
                return None

        if tool_call_count >= self.max_tool_calls:
            log_warning(f"达到最大工具调用次数 {self.max_tool_calls}，强制结束")

        if not final_result:
            log_error("未获得最终结果")
            return None

        # 解析最终结果
        generated_data = extract_json_from_text(final_result)
        if not generated_data:
            log_error(f"无法解析最终结果 JSON")
            return None

        structure = generated_data.get('structure', [])
        if not structure:
            log_error("生成的结构为空")
            return None

        # 验证并修复结构
        structure = self._validate_and_fix_structure(structure, elements)

        log_info(f"工具调用模式处理完成，共 {len(structure)} 个元素，工具调用 {tool_call_count} 次")

        return {
            'structure': structure,
            'tables': elements['tables'],
            'images': elements['images'],
            'formulas': elements['formulas'],
            'document_title': generated_data.get('document_title', '')
        }

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return """你是专业的文档编辑和写作专家。你可以根据用户要求重写文档，保留原文核心内容，并合理复用原文的图表公式。

你可以使用以下工具来查询文档信息：
- get_document_structure: 获取文档整体结构概览
- get_chart_context: 获取指定图表的完整上下文（前后文段落）
- get_paragraph_text: 获取指定段落的完整文本
- get_chart_description: 获取图表的 AI 生成描述
- get_element_order: 获取文档元素的原始顺序

工作流程建议：
1. **图表含义已预生成**：系统已为每个图表/公式识别出"含义"与"题注"，并随初始提示一并给出。你**无需**逐个调用 get_chart_context 去了解每个图表，直接依据列表中的"含义/题注"即可判断它该配哪段文字。
2. **只对含义存疑的图表**才调用 get_chart_context 补查上下文；最多调用几次即可，避免过多工具调用。
3. 必要时调用 get_paragraph_text 验证特定段落内容。
4. 理解充分后，直接在最终回复中生成包含图表占位符的 JSON 结构。

输出要求：
- 最终输出必须是严格的 JSON 格式
- 使用占位符插入图表：{{TABLE#ID#}}、{{IMAGE#ID#}}、{{FORMULA#ID#}}
- **按需选择图表**：依据图表"含义/题注"与正文语义，只放入确实被正文讨论、解释或提及的表格/图片/公式，使其紧跟描述该图表主题的文字；**语义无关的图表可不使用**，不必为凑齐所有图表而硬塞
- 被引用的每个图表只能出现一次，ID 必须与给定列表完全一致
- 图表前后应有引导或说明文字，且保持对应关系准确
- structure 数组按最终文档顺序排列

请开始处理文档。"""

    def _build_initial_prompt(
        self,
        elements: Dict,
        document_info: Dict[str, Any],
        user_prompt: str,
        doc_tools=None
    ) -> str:
        """构建初始用户提示词"""
        doc_title = document_info.get('title', '未知')
        doc_type = document_info.get('type', '其他类型')

        # 生成段落预览：均匀采样覆盖全篇，避免只给前 20 段导致后半部分对位错乱。
        # 段数不多时全给；段数多时按数量比例均匀抽样，保证开头/中段/末尾都有。
        paragraphs = elements['paragraphs']
        preview_max = 80  # 上限段落数，防止超长文档撑爆上下文
        if len(paragraphs) <= preview_max:
            sample_idx = list(range(len(paragraphs)))
        else:
            step = len(paragraphs) / preview_max
            sample_idx = [int(i * step) for i in range(preview_max)]
        para_previews = []
        for idx in sample_idx:
            para = paragraphs[idx]
            preview = para['text'][:150]
            if len(para['text']) > 150:
                preview += "..."
            para_previews.append(f"[{para['id']}]: {preview}")

        # 生成图表列表（按原文出现顺序混排，附带题注 caption，帮助 AI 保持图表相对顺序并定位语义）
        chart_descs = doc_tools.chart_descriptions if doc_tools else {}

        def _chart_label(typ):
            return {'table': '表格', 'image': '图片', 'formula': '公式'}.get(typ, '')

        def _nearest_text(tid_):
            # 取该图表就近锚定的原文段落文本，帮助 AI 判断应配哪段文字
            para_id = chart_descs.get(tid_, {}).get('nearest_paragraph_id', '')
            if not para_id:
                return ''
            nearest_para = paragraph_map.get(para_id)
            if nearest_para and nearest_para.get('text'):
                txt = nearest_para['text'][:80]
                return (txt + '...') if len(nearest_para['text']) > 80 else txt
            return ''

        paragraph_map = {p['id']: p for p in elements.get('paragraphs', [])}

        chart_list = []
        for it in elements.get('order', []):
            label = _chart_label(it.get('type'))
            tid = it.get('id')
            if not label or not tid:
                continue
            info = chart_descs.get(tid, {})
            desc = info.get('description', '')
            cap = info.get('caption', '')
            tags = []
            if desc:
                tags.append(f"含义：{desc}")
            if cap:
                tags.append(f"题注：{cap}")
            near = _nearest_text(tid)
            if near:
                tags.append(f"就近段落：{near}")
            chart_list.append(f"{label} [{tid}]" + (' - ' + '，'.join(tags) if tags else ''))

        # 兼容：若 order 无效则按分组列出
        if not chart_list:
            def _fmt(tid_):
                info = chart_descs.get(tid_, {})
                tags = []
                if info.get('description'):
                    tags.append(f"含义：{info['description']}")
                if info.get('caption'):
                    tags.append(f"题注：{info['caption']}")
                return f"[{tid_}]" + (' - ' + '，'.join(tags) if tags else '')
            for table in elements['tables']:
                chart_list.append(f"表格 {_fmt(table['id'])}")
            for image in elements['images']:
                chart_list.append(f"图片 {_fmt(image['id'])}")
            for formula in elements['formulas']:
                chart_list.append(f"公式 {_fmt(formula['id'])}")

        prompt = f"""请根据以下用户要求重写文档。

=== 用户要求（最高优先级） ===
{user_prompt if user_prompt else '保持原文核心内容，进行通顺、连贯的重写。'}

=== 原文档信息 ===
- 文档标题：{doc_title}
- 文档类型：{doc_type}
- 段落数量：{len(elements['paragraphs'])}
- 图表数量：{len(chart_list)}

=== 段落预览（前 20 段）===
{chr(10).join(para_previews) if para_previews else '无'}

=== 图表列表（每个条目含"含义"与"题注"，即对该图表的主题识别）===
{chr(10).join(chart_list) if chart_list else '无'}

=== 任务要求 ===
1. **严格遵循用户要求**：用户的风格、结构、内容等要求具有最高优先级。
2. **保留核心内容**：不得脱离原文核心信息，不得编造原文没有的关键内容。
3. **重新组织文章**：可以根据用户要求调整章节、段落结构，使文章结构合理、前后连贯。
4. **复用图表公式（按语义主题匹配放置）**：
   - 必须使用占位符在合理位置插入原文的表格、图片、公式。
   - 表格占位符：{{{{TABLE#完整ID#}}}}；图片占位符：{{{{IMAGE#完整ID#}}}}；公式占位符：{{{{FORMULA#完整ID#}}}}。
   - 完整 ID 必须与列表中完全一致。
   - **放置规则（最关键）**：根据每个图表的"含义/题注"与文章某个句子、段落表达的语义主题进行匹配，
     把它放到"描述、解释或提及该图表主题"的文字旁边，前后要有与该图表语义一致的引导或说明文字。
     **禁止把图表放在与它含义/题注完全无关的文字旁边。**
   - 位置不需与原文一致：图表的先后顺序、锚定段落均可随新文章结构自由调整，只要图表与所在处文字的语义主题匹配即可。
   - 每个表格/图片/公式前后都应有引导或说明文字，不能连续堆叠多个。
    5. **{'必须保留其中的全部或部分图表公式' if self._user_wants_keep_charts(self.user_prompt) else '按需选择图表（不必全部使用）'}**：
   {'用户明确要求保留图表/图片/公式，因此你必须在生成的文章中保留原文的图表公式，不得全部丢弃；具体保留哪些由你根据正文语义自行判断——与正文主题相关的应当保留并放到语义匹配的位置，确实无法融入的可舍弃，但应尽量多保留。' if self._user_wants_keep_charts(self.user_prompt) else '只引用与正文语义相关、确实被正文讨论/解释/提及的图表；与正文无关的图表可不使用，不要为了凑齐而硬塞。但应尽量多保留与主题相关的图表，避免全部丢弃。凡是被引用的图表，必须与它旁边的文字语义主题匹配，ID 与列表中完全一致。'}
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

请使用工具查询图表上下文（get_chart_context 可查看每个图表前后的段落），理解图表与文本的关系后，生成最终结构。"""

        return prompt

    def _extract_elements(self, source_content: Dict) -> Dict:
        """
        提取源文档所有元素，把行内公式也提取为可引用的公式条目。
        （复用 NaturalLanguageProcessor 的逻辑）
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
                    # 在原文中插入公式占位符
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
        """在文本中按 run 位置插入公式占位符"""
        if not formula_run_indices or not fids:
            return text

        text_segments_count = len(formula_run_indices) + 1
        segments = self._split_text_for_placeholders(text, text_segments_count)

        result_parts = []
        segment_idx = 0
        formula_idx = 0

        while formula_idx < len(formula_run_indices) and formula_run_indices[formula_idx] == -1:
            result_parts.append(f"{{{{FORMULA#{fids[formula_idx]}#}}}}")
            formula_idx += 1

        if segment_idx < len(segments):
            result_parts.append(segments[segment_idx])
            segment_idx += 1

        remaining_formulas = len(formula_run_indices) - formula_idx
        for i in range(remaining_formulas):
            result_parts.append(f"{{{{FORMULA#{fids[formula_idx]}#}}}}")
            formula_idx += 1

            if segment_idx < len(segments):
                result_parts.append(segments[segment_idx])
                segment_idx += 1

        return ''.join(result_parts)

    def _split_text_for_placeholders(self, text: str, num_segments: int) -> List[str]:
        """将文本分割成指定数量的段"""
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

    def _validate_and_fix_structure(self, structure: List[Dict], elements: Dict) -> List[Dict]:
        """
        验证并修复 AI 生成的结构
        （复用 NaturalLanguageProcessor 的逻辑）
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
        """如果 ID 不存在，尝试匹配完整 ID"""
        if not item_id:
            return item_id
        if item_id in valid_ids:
            return item_id
        matches = [vid for vid in valid_ids if vid.endswith(f"::{item_id}")]
        if matches:
            return matches[0]
        return item_id

    def _adjust_chart_distribution(self, structure: List[Dict]) -> List[Dict]:
        """将连续的非文本元素穿插到段落之间

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

        # 文字元素（段落 / 标题）与图表元素分开，但文字元素保留原顺序
        text_items = [item for item in structure if item.get('type') in ('paragraph', 'heading')]
        charts = [item for item in structure if item.get('type') in ('table', 'image', 'formula')]
        # 其它非常规元素（一般很少），按其原相对位置随图表一起处理
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
