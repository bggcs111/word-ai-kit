"""
AI 处理模块
负责调用 AI API 进行文本润色和模板内容生成
"""
import re
import json
from typing import Dict, List, Tuple, Any, Optional
from openai import OpenAI
from src.constants import AI_SYSTEM_PROMPT, AI_USER_PROMPT_TEMPLATE, DOCUMENT_TYPE_STYLE_TEMPLATES
from src.template import TemplateDefinition
from src.utils import clean_ai_json_response, extract_json_from_text


class AIProcessor:
    """AI 处理器"""
    
    def __init__(self, client: OpenAI, model_name: str):
        """
        初始化 AI 处理器
        
        Args:
            client: OpenAI 客户端
            model_name: 模型名称
        """
        self.client = client
        self.model_name = model_name
    
    def process_paragraphs(
        self, 
        paragraphs: Dict, 
        current_order: List[str], 
        document_info: Dict = None,
        user_prompt: str = None,
        user_doc_type: str = None
    ) -> Tuple[Dict, List, bool]:
        """
        调用 AI 处理段落

        Args:
            paragraphs: 段落字典
            current_order: 当前元素顺序
            document_info: 文档信息字典（可选），包含：
                - title: 文档标题
                - type: 文档类型
                - section: 当前章节
            user_prompt: 用户自定义提示词（可选）
            user_doc_type: 用户自定义文档类型（可选）

        Returns:
            (polished_paragraphs, new_order, document_title, title_from_first_paragraph, success)
            document_title: 文档标题（如果首段是标题则保持原文，否则生成新标题）
            title_from_first_paragraph: 首段是否是标题
            success 为 False 表示 AI 调用失败
        """
        # 构建段落内容
        para_details = self._build_paragraph_details(paragraphs, current_order)

        # 提取文档信息
        if document_info is None:
            document_info = {}

        # 使用原始标题或由 AI 生成
        doc_title = document_info.get('title', '未知')
        
        # 优先使用用户指定的文档类型，如果没有则保持原文风格
        if user_doc_type and user_doc_type.strip():
            doc_type = user_doc_type.strip()
        else:
            doc_type = '保持原文风格'
        
        current_section = document_info.get('section', '未知章节')

        # 根据文档类型动态选择风格要求模板
        document_type_style = DOCUMENT_TYPE_STYLE_TEMPLATES.get(doc_type, DOCUMENT_TYPE_STYLE_TEMPLATES.get('其他'))

        # 构建用户提示词部分（如果有）
        if user_prompt and user_prompt.strip():
            user_prompt_section = f"{user_prompt.strip()}"
        else:
            user_prompt_section = "无特殊要求，按文档类型默认风格处理。"

        # 构建提示词（统一模板）
        prompt = AI_USER_PROMPT_TEMPLATE.format(
            document_title=doc_title,
            document_type=doc_type,
            current_section=current_section,
            element_order=', '.join(current_order),
            paragraph_details='\n'.join(para_details),
            document_type_style=document_type_style,
            user_prompt_section=user_prompt_section
        )
        
        # 调用 AI
        result = self._call_ai(prompt)
        
        # 如果 AI 调用失败，返回空结果
        if not result:
            return {}, current_order, "", False, False, {}, [], {}
        
        # 解析结果
        polished, new_order, document_title, title_from_first_paragraph, generated_chapter_titles, generated_chart_titles, chart_title_paragraphs = self._parse_ai_response(result, paragraphs, current_order)
        
        # 注意：章节标题不替换正文段落，由builder单独处理插入
        # generated_chapter_titles 会传递给builder，在适当位置插入为独立段落
        
        return polished, new_order, document_title, title_from_first_paragraph, True, generated_chart_titles, chart_title_paragraphs, generated_chapter_titles
    
    def _build_paragraph_details(self, paragraphs: Dict, current_order: List[str]) -> List[str]:
        """构建段落详细信息列表，为图表周围的段落添加上下文标记"""
        para_details = []
        
        # 先遍历一遍，标记哪些段落是图表标题候选
        chart_title_candidates = self._identify_chart_title_candidates(current_order, paragraphs)
        
        for i, elem_id in enumerate(current_order):
            if elem_id.startswith('P'):
                # 提取段落文本（处理元组格式）
                para_data = paragraphs[elem_id]
                if isinstance(para_data, tuple):
                    text = para_data[0]
                    formula_run_indices = para_data[5] if len(para_data) >= 6 else None
                    
                    # 如果有公式，插入占位符
                    if formula_run_indices:
                        text = self._insert_formula_placeholders(text, formula_run_indices)
                else:
                    text = para_data
                
                # 添加图表上下文标记
                context_mark = ""
                if elem_id in chart_title_candidates:
                    chart_info = chart_title_candidates[elem_id]
                    if chart_info['type'] == 'table_title':
                        context_mark = " [表格标题候选：此段落位于表格上方，请根据内容提炼表格标题，格式为'表 X 标题内容']"
                    elif chart_info['type'] == 'image_title':
                        context_mark = " [图片标题候选：此段落位于图片上方，请根据内容提炼图片标题，格式为'图 X 标题内容']"
                
                para_details.append(f"[{elem_id}] {text}{context_mark}")
            else:
                para_details.append(f"[{elem_id}]")
        return para_details
    
    def _identify_chart_title_candidates(self, current_order: List[str], paragraphs: Dict) -> Dict:
        """
        识别可能是图表标题的段落
        
        Returns:
            {para_id: {'type': 'table_title'|'image_title', 'chart_id': 'T1'|'I1'}}
        """
        candidates = {}
        
        for i, elem_id in enumerate(current_order):
            # 表格：前面的段落可能是表格标题
            if elem_id.startswith('T'):
                for j in range(i - 1, max(0, i - 3), -1):
                    prev_id = current_order[j]
                    if prev_id.startswith('P'):
                        candidates[prev_id] = {'type': 'table_title', 'chart_id': elem_id}
                        break
            
            # 图片：前面的段落可能是图片标题
            if elem_id.startswith('I'):
                for j in range(i - 1, max(0, i - 3), -1):
                    prev_id = current_order[j]
                    if prev_id.startswith('P'):
                        candidates[prev_id] = {'type': 'image_title', 'chart_id': elem_id}
                        break
        
        return candidates
    
    def _insert_formula_placeholders(self, text: str, formula_run_indices: List[int]) -> str:
        """
        在文本中插入公式占位符
        
        Args:
            text: 原始文本
            formula_run_indices: 公式位置索引列表（每个值表示公式在哪个 run 之后）
            
        Returns:
            包含占位符的文本
        """
        if not formula_run_indices:
            return text
        
        # 统计有多少个公式在开头（索引为 -1）
        formulas_at_start = sum(1 for idx in formula_run_indices if idx == -1)
        
        # 计算文本段数量 = 公式数量 + 1
        text_segments_count = len(formula_run_indices) + 1
        
        # 将文本分割成对应数量的段
        segments = self._split_text_for_placeholders(text, text_segments_count)
        
        # 按顺序构建结果：文本段 + 占位符交替
        # 使用特殊格式：{{FORMULA#ID#}} 其中 ID 是唯一标识符
        result_parts = []
        segment_idx = 0
        formula_idx = 0
        
        # 处理在开头的公式（索引为 -1）
        while formula_idx < len(formula_run_indices) and formula_run_indices[formula_idx] == -1:
            # 使用双花括号 + 特殊标识符，避免与正文混淆
            result_parts.append(f"{{{{FORMULA#{formula_idx + 1}#}}}}")
            formula_idx += 1
        
        # 添加第一段文本
        if segment_idx < len(segments):
            result_parts.append(segments[segment_idx])
            segment_idx += 1
        
        # 交替添加占位符和文本段
        remaining_formulas = len(formula_run_indices) - formula_idx
        
        for i in range(remaining_formulas):
            # 添加占位符 - 使用双花括号和#号包围数字
            result_parts.append(f"{{{{FORMULA#{formula_idx + 1}#}}}}")
            formula_idx += 1
            
            # 添加下一段文本
            if segment_idx < len(segments):
                result_parts.append(segments[segment_idx])
                segment_idx += 1
        
        result = ''.join(result_parts)
        return result
    
    def _split_text_for_placeholders(self, text: str, num_segments: int) -> List[str]:
        """
        将文本分割成指定数量的段，用于占位符插入
        
        Args:
            text: 要分割的文本
            num_segments: 段数
            
        Returns:
            文本段列表
        """
        if num_segments <= 0:
            return [text]
        
        if num_segments == 1:
            return [text]
        
        # 简单策略：按字符数平均分割
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
    
    def _call_ai(self, prompt: str) -> str:
        """调用 AI API"""
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": AI_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
            )
            
            result = response.choices[0].message.content.strip()
            return result
            
        except Exception as e:
            error_message = str(e)
            
            # 检查是否是 API Key 错误
            if "api_key" in error_message.lower() or "authentication" in error_message.lower() or "unauthorized" in error_message.lower() or "invalid_api_key" in error_message.lower() or "401" in error_message:
                print(f"❌ AI 调用失败：API Key 无效或认证失败")
            elif "connection" in error_message.lower() or "timeout" in error_message.lower():
                print(f"❌ AI 调用失败：网络连接问题")
            else:
                print(f"❌ AI 调用失败：{error_message}")
            
            return ""
    
    def _parse_ai_response(self, result: str, paragraphs: Dict, current_order: List[str]) -> Tuple[Dict, List, str, bool, Dict, Dict, List]:
        """解析 AI 响应（使用工具函数）
        
        Returns:
            (polished_paragraphs, new_order, document_title, title_from_first_paragraph, generated_chapter_titles, generated_chart_titles, chart_title_paragraphs)
        """
        data = extract_json_from_text(result)
        if not data:
            return {}, current_order, "", False, {}, {}, []
        
        polished = data.get('polished_paragraphs', {})
        new_order = data.get('new_order', current_order)
        document_title = data.get('document_title', '')
        title_from_first_paragraph = data.get('title_from_first_paragraph', False)
        generated_chapter_titles = data.get('generated_chapter_titles', {})
        generated_chart_titles = data.get('generated_chart_titles', {})
        chart_title_paragraphs = data.get('chart_title_paragraphs', [])
        
        # 验证 new_order 是否包含所有元素
        if set(new_order) != set(current_order):
            return polished, current_order, document_title, title_from_first_paragraph, generated_chapter_titles, generated_chart_titles, chart_title_paragraphs
        
        # 确保所有段落都有润色版本（包括图表标题段落）
        self._ensure_all_paragraphs_polished(polished, paragraphs, current_order)
        
        return polished, new_order, document_title, title_from_first_paragraph, generated_chapter_titles, generated_chart_titles, chart_title_paragraphs
    
    def _ensure_all_paragraphs_polished(self, polished: Dict, paragraphs: Dict, current_order: List[str]):
        """确保所有段落都有润色版本"""
        expected_paragraphs = [elem_id for elem_id in current_order if elem_id.startswith('P')]
        
        for pid in expected_paragraphs:
            if pid not in polished:
                para_data = paragraphs[pid]
                if isinstance(para_data, tuple):
                    polished[pid] = para_data[0]
                else:
                    polished[pid] = para_data
    
    def generate_template_content(
        self, 
        paragraphs: Dict, 
        current_order: List[str], 
        template: TemplateDefinition,
        document_info: Dict = None
    ) -> Optional[Dict[str, Any]]:
        """
        根据模板生成内容
        
        Args:
            paragraphs: 段落字典
            current_order: 当前元素顺序
            template: 模板定义对象
            document_info: 文档信息字典
            
        Returns:
            AI 生成的内容字典，如果失败返回 None
        """
        # 构建文档内容摘要
        doc_summary = self._build_document_summary(paragraphs, current_order)
        
        # 提取文档信息
        if document_info is None:
            document_info = {}
        
        doc_title = document_info.get('title', '未知')
        doc_type = document_info.get('type', '其他类型')
        
        # 构建提示词
        prompt = self._build_template_prompt(template, doc_summary, doc_title, doc_type)
        
        # 调用 AI
        result = self._call_ai(prompt)
        
        # 如果 AI 调用失败，返回 None
        if not result:
            return None
        
        # 解析结果
        content = self._parse_template_response(result, template)
        
        return content
    
    def _build_document_summary(self, paragraphs: Dict, current_order: List[str]) -> str:
        """构建文档内容摘要"""
        summary_parts = []
        
        for elem_id in current_order:
            if elem_id.startswith('P'):
                para_data = paragraphs[elem_id]
                if isinstance(para_data, tuple):
                    text = para_data[0]
                else:
                    text = para_data
                
                if text:
                    # 截取前 200 字作为摘要
                    summary_parts.append(f"[{elem_id}] {text[:200]}...")
        
        return '\n'.join(summary_parts)
    
    def _build_template_prompt(
        self, 
        template: TemplateDefinition, 
        doc_summary: str, 
        doc_title: str, 
        doc_type: str
    ) -> str:
        """
        构建模板内容生成提示词
        
        Args:
            template: 模板定义
            doc_summary: 文档摘要
            doc_title: 文档标题
            doc_type: 文档类型
            
        Returns:
            提示词字符串
        """
        prompt_parts = [
            "你是专业文档编辑和写作专家。你的任务是根据提供的文档内容和模板结构，生成符合模板要求的新文档。",
            "",
            f"## 原文档信息",
            f"- **文档标题**: {doc_title}",
            f"- **文档类型**: {doc_type}",
            "",
            "## 原文档内容摘要",
            doc_summary,
            "",
            "## 目标文档模板",
            f"### 模板名称：{template.name}",
            f"### 模板描述：{template.description}",
            "",
            "### 模板结构要求：",
        ]
        
        # 添加模板结构说明
        for i, elem in enumerate(template.structure, 1):
            elem_desc = self._format_element_description_for_prompt(elem)
            prompt_parts.append(f"\n{i}. {elem_desc}")
        
        # 添加输出格式说明
        prompt_parts.extend([
            "",
            "## 任务要求",
            "1. 分析原文档内容，提取关键信息",
            "2. 根据模板结构，将内容填充到对应的章节中",
            "3. 保持原文档的核心信息和数据",
            "4. 提升文字质量，修正语法错误和错别字",
            "5. 根据文档类型采用相应的写作风格",
            "6. 输出严格的 JSON 格式结果",
            "",
            "## 输出格式（严格 JSON）",
            "```json",
            "{",
            '  "content": {',
            '    "content_key_1": "内容 1",',
            '    "content_key_2": "内容 2",',
            '    ...',
            '  }',
            "}",
            "```",
            "",
            "## 注意事项",
            "- 只输出 JSON 格式结果，不要有任何额外说明",
            "- 确保 JSON 格式正确，可以被解析",
            "- 如果原文档缺少某些内容，可以基于已有信息合理推断",
            "- 保持专业术语的准确性",
            f"- 根据文档类型（{doc_type}）采用相应的写作风格",
            "",
            "请开始生成内容："
        ])
        
        return '\n'.join(prompt_parts)
    
    def _format_element_description_for_prompt(self, elem) -> str:
        """格式化元素描述用于提示词"""
        type_names = {
            'title': '文档标题',
            'heading': '章节标题',
            'paragraph': '段落',
            'table': '表格',
            'list': '列表',
            'image': '图片'
        }
        
        type_name = type_names.get(elem.elem_type.value, '未知类型')
        desc = f"**{type_name}**"
        
        if elem.content_key:
            desc += f" [内容键：`{elem.content_key}`]"
        
        if elem.description:
            desc += f" - {elem.description}"
        
        if elem.level and elem.elem_type.value == 'heading':
            desc += f" (级别：{elem.level})"
        
        if elem.numbering:
            desc += f" (编号：{elem.numbering})"
        
        return desc
    
    def _parse_template_response(self, result: str, template: TemplateDefinition) -> Dict[str, Any]:
        """
        解析模板内容生成响应
        
        Args:
            result: AI 返回的结果
            template: 模板定义
            
        Returns:
            内容字典
        """
        # 解析 JSON（使用工具函数）
        data = extract_json_from_text(result)
        if not data:
            return {}
        
        try:
            content = data.get('content', {})
            
            # 验证内容键名
            expected_keys = template.get_content_keys()
            missing_keys = [key for key in expected_keys if key not in content]
            
            if missing_keys:
                # 为缺失的键提供空值
                for key in missing_keys:
                    content[key] = ""
            
            return content
            
        except Exception as e:
            return {}
