"""
文档访问工具集

封装文档结构访问能力，供 AI 通过 Function Calling 调用。
支持 AI 主动查询文档结构、图表上下文、段落内容等，
从而更准确地理解文档并放置图表。
"""
import json
from typing import Dict, List, Any, Optional
from src.logger import log_info, log_error, log_warning
from src.utils import extract_json_from_text, extract_caption


class DocumentTools:
    """文档访问工具集，供 AI 通过 function calling 调用"""

    def __init__(self, elements: Dict, document_info: Dict, client=None, model_name: str = None):
        """
        初始化工具集

        Args:
            elements: 提取的文档元素（paragraphs, tables, images, formulas, order）
            document_info: 文档信息（title, type, section）
            client: OpenAI 客户端，用于预生成图表描述
            model_name: AI 模型名称
        """
        self.elements = elements
        self.document_info = document_info
        self.client = client
        self.model_name = model_name

        # 构建索引映射
        self.order_map = self._build_order_map()
        self.paragraph_map = {p['id']: p for p in elements.get('paragraphs', [])}
        self.table_map = {t['id']: t for t in elements.get('tables', [])}
        self.image_map = {i['id']: i for i in elements.get('images', [])}
        self.formula_map = {f['id']: f for f in elements.get('formulas', [])}

        # 识别连续图表组
        self.consecutive_groups = self._identify_consecutive_charts()

        # 预生成图表描述
        self.chart_descriptions = self._pre_generate_descriptions()

    def _build_order_map(self) -> Dict[str, int]:
        """构建元素 ID 到顺序索引的映射"""
        return {item['id']: i for i, item in enumerate(self.elements.get('order', []))}

    def _identify_consecutive_charts(self) -> List[List[str]]:
        """识别连续出现的图表/公式组"""
        consecutive_groups = []
        current_group = []

        for item in self.elements.get('order', []):
            if item['type'] in ('table', 'image', 'formula'):
                current_group.append(item['id'])
            else:
                if current_group:
                    consecutive_groups.append(current_group)
                    current_group = []

        if current_group:
            consecutive_groups.append(current_group)

        return consecutive_groups

    def _pre_generate_descriptions(self) -> Dict[str, Dict]:
        """预生成所有图表的描述信息。

        以"连续图表组"为单位进行识别：一组中连续出现的图表（中间没有段落文字）
        上下文相同，视为同一索引的不同子图表，统一用组前后更完整的段落语义来命名，
        从而提升识别准确度。
        """
        if not self.client or not self.model_name:
            return self._generate_default_descriptions()

        chart_info_map = {}

        for group in self.consecutive_groups:
            group_descriptions = self._identify_group(group)
            if not group_descriptions:
                continue
            for cid, g in group_descriptions.items():
                typ = ('表格' if cid in self.table_map else '图片' if cid in self.image_map else '公式')
                msg = (
                    f"图表识别 [组{'/'.join(group)}] {cid} ({typ}) → {g['description']}"
                    f"{('，题注：' + g['caption']) if g.get('caption') else ''}"
                )
                log_info(msg)
                print(f"[INFO] {msg}")
            chart_info_map.update(group_descriptions)

        log_info(f"预生成图表描述完成，共 {len(chart_info_map)} 个")
        return chart_info_map

    def _extract_group_context(
        self,
        group: List[str],
        before_count: int = 2,
        after_count: int = 2,
        max_len: int = 600
    ) -> Dict:
        """提取整个连续图表组共同的前后段落上下文。

        以组为单位，向前向后收集段落，尽量给出完整语义（而非截断的一两段），
        便于推断这组图表的统一含义。
        """
        if not group or group[0] not in self.order_map:
            return {'before': [], 'after': []}

        first_idx = self.order_map[group[0]]
        last_idx = self.order_map.get(group[-1], first_idx)

        # 组前段落：从组第一个元素往前收集
        before = []
        for i in range(first_idx - 1, max(0, first_idx - 40), -1):
            item = self.elements['order'][i]
            if item['type'] == 'paragraph':
                para = self.paragraph_map.get(item['id'])
                if para and para['text']:
                    before.append({'id': item['id'], 'text': para['text'][:max_len]})
                    if len(before) >= before_count:
                        break
        before.reverse()

        # 组后段落：从组最后一个元素往后收集（保持文档正向顺序，首项为紧邻图表的下文）
        after = []
        for i in range(last_idx + 1, min(len(self.elements['order']), last_idx + 40)):
            item = self.elements['order'][i]
            if item['type'] == 'paragraph':
                para = self.paragraph_map.get(item['id'])
                if para and para['text']:
                    after.append({'id': item['id'], 'text': para['text'][:max_len]})
                    if len(after) >= after_count:
                        break

        return {'before': before, 'after': after}

    def _identify_group(self, group: List[str]) -> Dict[str, Dict]:
        """识别并命名为一个连续图表组内的所有图表。"""
        if not group:
            return {}

        ctx = self._extract_group_context(group)
        # 拆分为"紧邻段"（正上/正下方紧邻图表的那一段）与"更远段"，紧邻段权重最高
        # 单图组只给紧邻段，不给更远段落，避免被远处无关内容带偏
        near_before_text = ctx['before'][-1]['text'] if ctx['before'] else ''
        far_before_text = ' | '.join(p['text'] for p in ctx['before'][:-1]) if len(group) > 1 else ''
        after_text = ' | '.join(p['text'] for p in ctx['after'])
        nearest_para = ctx['before'][-1]['id'] if ctx['before'] else ''
        caption = extract_caption(ctx['after'][0]['text']) if ctx['after'] and ctx['after'][0]['text'] else ''
        anchor_text = ' | '.join([p['text'] for p in ctx['after']] + [p['text'] for p in ctx['before']])

        # 组织组内各图表
        group_items = []
        for cid in group:
            if cid in self.table_map:
                chart_type = '表格'
                content = self._summarize_table_content(self.table_map[cid])
            elif cid in self.image_map:
                chart_type = '图片'
                content = ''
            elif cid in self.formula_map:
                chart_type = '公式'
                content = ''
            else:
                continue
            group_items.append({
                'id': cid,
                'type': chart_type,
                'content': content
            })

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
{group_desc}
{chr(10).join(item_lines)}

=== 任务要求 ===
1. **以"紧邻上文段落"为最优先依据**：紧邻本图正上方的文字常以"下面的图片是……""如下图所示""报错如下所示""见下图，……"等句式直接说明本图内容，应据此命名。"更早的上文段落"只在紧邻段不足以判断时才作背景参考，**绝不能让它们覆盖紧邻段给出的明确语义**。例如紧邻上文是"做设计检查，报错如下所示"，就应命名为"设计检查报错信息"，即使更早段落提到过"生成HDL文件"。
2. **下文段落仅在"用图内指代词回指本图"时才采信**：图表之后的正文通常属于"下一张图/下一节"（如标题"设计检查"、句子"下面是设计的完整模块图"是对再下一张图的说明），**不要直接拿它给当前图命名**。仅当出现以下几种情形时才把下文中**指代本图的那部分**纳入推导：
   - 下文以"图/表/公式 + 编号 + 标题"（如图1-1 系统架构、表2 参数表、Figure 3.2）这样标准题注句式开头；
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
                    'caption': caption,
                    'anchor_text': anchor_text,
                    'context_after': after_text
                }
            return group_result

        except Exception as e:
            log_error(f"识别图表组描述失败：{e}")
            group_result = {}
            for it in group_items:
                cid = it['id']
                default_desc = "数据表格" if it['type'] == '表格' else ("示意图" if it['type'] == '图片' else "公式")
                group_result[cid] = {
                    'description': default_desc,
                    'nearest_paragraph_id': nearest_para,
                    'caption': caption,
                    'anchor_text': anchor_text,
                    'context_after': after_text
                }
            return group_result

    def _generate_default_descriptions(self) -> Dict[str, Dict]:
        """生成默认描述（当 AI 不可用时）"""
        chart_info_map = {}

        for table in self.elements.get('tables', []):
            context_before = self._extract_context_before(table['id'], paragraphs_before=2)
            nearest = context_before[-1]['id'] if context_before else ''
            chart_info_map[table['id']] = {
                'description': '数据表格',
                'nearest_paragraph_id': nearest
            }

        for image in self.elements.get('images', []):
            context_before = self._extract_context_before(image['id'], paragraphs_before=2)
            nearest = context_before[-1]['id'] if context_before else ''
            chart_info_map[image['id']] = {
                'description': '示意图',
                'nearest_paragraph_id': nearest
            }

        for formula in self.elements.get('formulas', []):
            context_before = self._extract_context_before(formula['id'], paragraphs_before=2)
            nearest = context_before[-1]['id'] if context_before else ''
            chart_info_map[formula['id']] = {
                'description': '公式',
                'nearest_paragraph_id': nearest
            }

        return chart_info_map

    def _summarize_table_content(self, table: Dict) -> str:
        """生成表格内容摘要"""
        content = table.get('content')
        if not content or not isinstance(content, list) or len(content) == 0:
            return ""

        rows_summary = []
        for row in content[:5]:
            if row:
                cells_summary = [str(cell)[:30] for cell in row[:5]]
                rows_summary.append(", ".join(cells_summary))
        return "; ".join(rows_summary)

    def _extract_context_before(self, chart_id: str, paragraphs_before: int = 2) -> List[Dict]:
        """提取图表前方的段落上下文"""
        if chart_id not in self.order_map:
            return []

        chart_idx = self.order_map[chart_id]
        context_before_list = []

        # 找到当前图表所在的连续组
        current_group_idx = -1
        for i, group in enumerate(self.consecutive_groups):
            if chart_id in group:
                current_group_idx = i
                break

        # 找到前一个图表组的最后位置
        prev_chart_last_idx = -1
        if current_group_idx > 0:
            prev_group = self.consecutive_groups[current_group_idx - 1]
            prev_id = prev_group[-1]
            if prev_id in self.order_map:
                prev_chart_last_idx = self.order_map[prev_id]

        # 计算两个图表组之间的段落数量
        paragraphs_between = 0
        if prev_chart_last_idx >= 0:
            for i in range(prev_chart_last_idx + 1, chart_idx):
                item = self.elements['order'][i]
                if item['type'] == 'paragraph':
                    paragraphs_between += 1

        # 根据段落数量决定提取数量
        max_paragraphs = paragraphs_before if paragraphs_between > 1 else 1

        # 向前搜索段落
        for i in range(chart_idx - 1, max(0, chart_idx - 20), -1):
            item = self.elements['order'][i]
            if item['type'] == 'paragraph':
                para = self.paragraph_map.get(item['id'])
                if para:
                    context_before_list.append({'id': item['id'], 'text': para['text'][:200]})
                    if len(context_before_list) >= max_paragraphs:
                        break

        context_before_list.reverse()
        return context_before_list

    def _extract_context_after(self, chart_id: str, paragraphs_after: int = 1) -> List[Dict]:
        """提取图表后方的段落上下文"""
        if chart_id not in self.order_map:
            return []

        chart_idx = self.order_map[chart_id]
        context_after_list = []

        # 找到当前图表所在的连续组
        current_group_idx = -1
        for i, group in enumerate(self.consecutive_groups):
            if chart_id in group:
                current_group_idx = i
                break

        # 找到当前组的最后一个元素
        current_group = self.consecutive_groups[current_group_idx]
        last_id = current_group[-1]
        last_idx = self.order_map.get(last_id, chart_idx)

        # 向后搜索段落
        for i in range(last_idx + 1, min(len(self.elements['order']), last_idx + 20)):
            item = self.elements['order'][i]
            if item['type'] == 'paragraph':
                para = self.paragraph_map.get(item['id'])
                if para:
                    context_after_list.append({'id': item['id'], 'text': para['text'][:200]})
                    if len(context_after_list) >= paragraphs_after:
                        break

        return context_after_list

    # ========== 工具方法 ==========

    def get_document_structure(self) -> Dict:
        """
        工具：获取文档整体结构概览

        Returns:
            包含段落、表格、图片、公式数量和 ID 列表的字典
        """
        return {
            "document_title": self.document_info.get('title', '未知'),
            "document_type": self.document_info.get('type', '其他类型'),
            "total_paragraphs": len(self.elements.get('paragraphs', [])),
            "total_tables": len(self.elements.get('tables', [])),
            "total_images": len(self.elements.get('images', [])),
            "total_formulas": len(self.elements.get('formulas', [])),
            "paragraph_ids": [p['id'] for p in self.elements.get('paragraphs', [])],
            "table_ids": [t['id'] for t in self.elements.get('tables', [])],
            "image_ids": [i['id'] for i in self.elements.get('images', [])],
            "formula_ids": [f['id'] for f in self.elements.get('formulas', [])]
        }

    def get_chart_context(self, chart_id: str, paragraphs_before: int = 2, paragraphs_after: int = 1) -> Dict:
        """
        工具：获取指定图表的上下文

        Args:
            chart_id: 图表 ID（如 T1, I1, F1）
            paragraphs_before: 向前查看的段落数量，默认 2
            paragraphs_after: 向后查看的段落数量，默认 1

        Returns:
            包含图表类型、描述、前后文段落的字典
        """
        # 确定图表类型
        chart_type = None
        if chart_id in self.table_map:
            chart_type = '表格'
            chart_data = self.table_map[chart_id]
        elif chart_id in self.image_map:
            chart_type = '图片'
            chart_data = self.image_map[chart_id]
        elif chart_id in self.formula_map:
            chart_type = '公式'
            chart_data = self.formula_map[chart_id]
        else:
            return {"error": f"未找到图表 {chart_id}"}

        # 获取描述
        desc_info = self.chart_descriptions.get(chart_id, {'description': '未知', 'nearest_paragraph_id': ''})

        # 获取上下文
        context_before = self._extract_context_before(chart_id, paragraphs_before)
        context_after = self._extract_context_after(chart_id, paragraphs_after)

        # 获取表格内容摘要
        content_summary = ""
        if chart_type == '表格':
            content_summary = self._summarize_table_content(chart_data)

        return {
            "chart_id": chart_id,
            "chart_type": chart_type,
            "description": desc_info['description'],
            "nearest_paragraph_id": desc_info['nearest_paragraph_id'],
            "content_summary": content_summary,
            "context_before": context_before,
            "context_after": context_after
        }

    def get_paragraph_text(self, paragraph_id: str) -> Dict:
        """
        工具：获取指定段落的完整文本

        Args:
            paragraph_id: 段落 ID（如 P1, P2）

        Returns:
            包含段落 ID 和完整文本的字典
        """
        para = self.paragraph_map.get(paragraph_id)
        if not para:
            return {"error": f"未找到段落 {paragraph_id}"}

        return {
            "paragraph_id": paragraph_id,
            "text": para['text']
        }

    def get_chart_description(self, chart_id: str) -> Dict:
        """
        工具：获取图表的 AI 生成描述

        Args:
            chart_id: 图表 ID

        Returns:
            包含图表描述的字典
        """
        desc_info = self.chart_descriptions.get(chart_id)
        if not desc_info:
            return {"error": f"未找到图表 {chart_id} 的描述"}

        return {
            "chart_id": chart_id,
            "description": desc_info['description'],
            "nearest_paragraph_id": desc_info['nearest_paragraph_id'],
            "caption": desc_info.get('caption', ''),
            "anchor_text": desc_info.get('anchor_text', '')
        }

    def get_element_order(self) -> Dict:
        """
        工具：获取文档元素的原始顺序

        Returns:
            包含元素顺序列表的字典
        """
        return {
            "element_order": self.elements.get('order', [])
        }

    def execute_tool(self, tool_name: str, arguments: Dict) -> Dict:
        """
        统一工具执行入口

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果
        """
        try:
            if tool_name == "get_document_structure":
                return self.get_document_structure()
            elif tool_name == "get_chart_context":
                return self.get_chart_context(**arguments)
            elif tool_name == "get_paragraph_text":
                return self.get_paragraph_text(**arguments)
            elif tool_name == "get_chart_description":
                return self.get_chart_description(**arguments)
            elif tool_name == "get_element_order":
                return self.get_element_order()
            else:
                return {"error": f"未知工具：{tool_name}"}
        except Exception as e:
            log_error(f"工具执行失败 {tool_name}: {e}")
            return {"error": str(e)}


# ========== 工具定义（供 OpenAI Function Calling 使用）==========

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_document_structure",
            "description": "获取文档整体结构概览，包括所有段落、表格、图片、公式的 ID 和数量",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_chart_context",
            "description": "获取指定图表/公式的上下文，可指定向前和向后查看的段落数量。用于理解图表与文本的关系，确定图表的合理放置位置。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_id": {
                        "type": "string",
                        "description": "图表 ID（如 T1, I1, F1）"
                    },
                    "paragraphs_before": {
                        "type": "integer",
                        "description": "向前查看的段落数量，默认 2"
                    },
                    "paragraphs_after": {
                        "type": "integer",
                        "description": "向后查看的段落数量，默认 1"
                    }
                },
                "required": ["chart_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_paragraph_text",
            "description": "获取指定段落的完整文本内容。用于验证段落内容，确定是否适合在此处插入图表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "paragraph_id": {
                        "type": "string",
                        "description": "段落 ID（如 P1, P2）"
                    }
                },
                "required": ["paragraph_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_chart_description",
            "description": "获取图表/公式的 AI 生成描述（主题、内容概要）。用于快速了解图表内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_id": {
                        "type": "string",
                        "description": "图表 ID"
                    }
                },
                "required": ["chart_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_element_order",
            "description": "获取文档元素的原始顺序，帮助理解图表在原文中的位置关系。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]
