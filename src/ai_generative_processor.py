"""
AI生成式模板处理器
新策略：AI理解原文→按模板生成新内容（不照搬原文）
"""
import json
from typing import Dict, List, Any, Optional
from openai import OpenAI
from src.template import TemplateDefinition, ElementType
from src.logger import log_info, log_error, log_warning
from src.utils import extract_json_from_text


class AIGenerativeTemplateProcessor:
    """AI生成式模板处理器"""
    
    def __init__(self, client: OpenAI, model_name: str):
        self.client = client
        self.model_name = model_name
    
    def process_with_template(
        self,
        source_content: Dict[str, Any],
        template: TemplateDefinition,
        source_docs_info: Dict[str, Any] = None
    ) -> Optional[Dict[str, Any]]:
        """
        使用模板处理源文档（新策略）
        
        流程：
        1. 解析文档，提取段落、图表
        2. AI理解原文整体内容
        3. AI按模板要求生成新文档结构
        4. 返回生成结果
        
        Args:
            source_content: 源文档内容
            template: 模板定义
            source_docs_info: 源文档信息
            
        Returns:
            生成的内容结构
        """
        log_info(f"开始AI生成式模板处理，模板：{template.name}")
        
        # 提取源文档内容（段落和图表）
        elements = self._extract_elements(source_content)
        if not elements['paragraphs'] and not elements['tables'] and not elements['images']:
            log_error("源文档没有可处理的内容")
            return None
        
        log_info(f"提取到 {len(elements['paragraphs'])} 个段落, {len(elements['tables'])} 个表格, {len(elements['images'])} 个图片")
        
        # 提取模板章节
        chapters = self._extract_chapters(template)
        if not chapters:
            log_error("模板没有章节标题")
            return None
        
        log_info(f"模板包含 {len(chapters)} 个章节")
        
        # AI理解原文并生成新文档结构
        generated_structure = self._ai_generate_document(
            elements=elements,
            chapters=chapters,
            template=template,
            source_docs_info=source_docs_info
        )
        
        if not generated_structure:
            log_error("AI生成失败")
            return None
        
        log_info(f"AI生成完成，共 {len(generated_structure['structure'])} 个元素")
        
        return generated_structure
    
    def _extract_elements(self, source_content: Dict) -> Dict:
        """提取源文档所有元素
        
        注意：多文档上传时，元素ID已经包含文档名前缀（如"文档1::T1"）
        这样可以避免ID冲突，确保图表准确匹配
        """
        elements = source_content.get('elements', [])
        paragraphs = source_content.get('paragraphs', {})
        
        result = {
            'paragraphs': [],  # [{id, text}]
            'tables': [],      # [{id, content}]
            'images': [],      # [{id, content}]
            'order': []        # 原始顺序
        }
        
        for elem_type, elem_id, content in elements:
            result['order'].append({'type': elem_type, 'id': elem_id})
            
            if elem_type == 'paragraph' and elem_id in paragraphs:
                data = paragraphs[elem_id]
                text = data[0] if isinstance(data, tuple) else data
                if text is not None:
                    result['paragraphs'].append({
                        'id': elem_id,
                        'text': text
                    })
            elif elem_type == 'table':
                # 表格ID可能包含文档名前缀（如"文档1::T1"）
                result['tables'].append({
                    'id': elem_id,
                    'content': content
                })
            elif elem_type == 'image':
                # 图片ID可能包含文档名前缀（如"文档1::I1"）
                result['images'].append({
                    'id': elem_id,
                    'content': content
                })
        
        return result
    
    def _extract_chapters(self, template: TemplateDefinition) -> List[Dict]:
        """提取模板章节"""
        chapters = []
        
        for elem in template.structure:
            if elem.element_type == ElementType.HEADING:
                chapters.append({
                    "order": elem.order,
                    "title": elem.placeholder_text,
                    "level": elem.heading_level or 1,
                    "description": elem.description or "",
                    "style_name": elem.style_name
                })
        
        return sorted(chapters, key=lambda c: c['order'])
    
    def _ai_extract_chart_descriptions(
        self,
        elements: Dict,
        order_map: Dict
    ) -> Dict[str, Dict]:
        """
        使用AI提炼图表主题描述（更智能更准确）
        
        批量处理所有图表，提取图表内容和上文段落，使用AI提炼简洁的主题描述
        
        Args:
            elements: 所有元素
            order_map: 元素顺序映射
            
        Returns:
            图表信息映射（如{"T1": {"description": "系统架构表格", "nearest_paragraph_id": "P5"}}）
        """
        # 如果没有图表，直接返回空字典
        if not elements['tables'] and not elements['images']:
            return {}
        
        # 构建图表信息列表（包含内容和上文段落）
        chart_info_list = []
        
        # 预处理：识别连续出现的图表（作为同一引用位置处理）
        consecutive_chart_groups = self._identify_consecutive_charts(elements, order_map)
        
        for table in elements['tables']:
            table_id = table['id']
            
            # 提取表格内容摘要（更详细）
            table_content_summary = ""
            if table['content'] and isinstance(table['content'], list) and len(table['content']) > 0:
                # 提取前5行的内容作为摘要
                rows_summary = []
                for row in table['content'][:5]:
                    if row:
                        cells_summary = [str(cell)[:30] for cell in row[:5]]
                        rows_summary.append(", ".join(cells_summary))
                table_content_summary = "; ".join(rows_summary)
            
            # 提取图表上面的段落（上文）
            context_before_list = []
            
            if table_id in order_map:
                idx = order_map[table_id]
                
                # 上文段落提取：精细规则
                context_before_list = self._extract_context_before_with_rules(
                    elements=elements,
                    order_map=order_map,
                    chart_idx=idx,
                    consecutive_chart_groups=consecutive_chart_groups,
                    chart_id=table_id
                )
            
            # 获取最近的段落ID（列表最后一个元素）
            nearest_paragraph_id = context_before_list[-1]['id'] if context_before_list else ''
            
            chart_info_list.append({
                'id': table_id,
                'type': '表格',
                'content': table_content_summary,
                'context_before': ' | '.join([p['text'] for p in context_before_list]) if context_before_list else '',
                'nearest_paragraph_id': nearest_paragraph_id
            })
        
        for image in elements['images']:
            image_id = image['id']
            
            # 提取图表上面的段落（上文）
            context_before_list = []
            
            if image_id in order_map:
                idx = order_map[image_id]
                
                # 上文段落提取：精细规则
                context_before_list = self._extract_context_before_with_rules(
                    elements=elements,
                    order_map=order_map,
                    chart_idx=idx,
                    consecutive_chart_groups=consecutive_chart_groups,
                    chart_id=image_id
                )
            
            # 获取最近的段落ID（列表最后一个元素）
            nearest_paragraph_id = context_before_list[-1]['id'] if context_before_list else ''
            
            chart_info_list.append({
                'id': image_id,
                'type': '图片',
                'content': '',  # 图片没有文本内容
                'context_before': ' | '.join([p['text'] for p in context_before_list]) if context_before_list else '',
                'nearest_paragraph_id': nearest_paragraph_id
            })
        
        # 构建AI提示词（批量处理所有图表）
        chart_info_text = []
        for chart in chart_info_list:
            info = f"{chart['type']} [{chart['id']}]:"
            if chart['content']:
                info += f"\n  内容摘要：{chart['content']}"
            if chart['context_before']:
                info += f"\n  上文段落：{chart['context_before']}"
            chart_info_text.append(info)
        
        prompt = f"""你是专业的文档分析专家。请根据以下图表的内容和上文段落，提炼每个图表的主题描述。

=== 图表信息（共 {len(chart_info_list)} 个）===
{chr(10).join(chart_info_text)}

=== 任务要求 ===
1. **提炼主题**：根据图表的内容和上文段落，提炼简洁的主题描述（如"系统架构表格"、"硬件设计图"）
2. **描述简洁**：描述应该简洁、专业，不超过15个字
3. **主题准确**：描述应该准确反映图表的主题，便于后续选择和匹配
4. **适应各种风格**：可以适应各种风格的文档（技术文档、学术论文、调研报告、自媒体文章等）

=== 输出格式 ===
只输出 JSON，格式如下：
{{
  "图表ID": "主题描述",
  "T1": "系统架构表格",
  "I1": "硬件设计图"
}}

=== 注意事项 ===
- 只输出 JSON，不要输出其他文字或说明
- 描述应该简洁、专业，不超过15个字
- 如果无法判断主题，使用默认描述（表格："数据表格"，图片："示意图"）

请开始提炼："""
        
        try:
            # 调用AI提炼图表主题
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system", 
                        "content": "你是专业的文档分析专家。擅长根据图表的内容和上文段落，提炼简洁、专业的主题描述。"
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # 低温度，确保输出稳定
            )
            
            result = response.choices[0].message.content.strip()
            log_info(f"AI提炼图表主题响应长度：{len(result)} 字符")
            
            # 解析 JSON
            descriptions = extract_json_from_text(result)
            
            # 构建返回结果：包含描述和段落ID
            chart_info_map = {}
            for chart in chart_info_list:
                chart_id = chart['id']
                description = descriptions.get(chart_id, "数据表格" if chart['type'] == '表格' else "示意图")
                chart_info_map[chart_id] = {
                    'description': description,
                    'nearest_paragraph_id': chart['nearest_paragraph_id']
                }
            
            if not descriptions:
                log_warning("无法解析AI提炼的图表主题JSON，使用默认描述")
            
            log_info(f"AI提炼图表主题完成，共 {len(chart_info_map)} 个图表")
            
            return chart_info_map
            
        except Exception as e:
            log_error(f"AI提炼图表主题失败：{e}")
            # 使用默认描述
            chart_info_map = {}
            for chart in chart_info_list:
                if chart['type'] == '表格':
                    chart_info_map[chart['id']] = {
                        'description': "数据表格",
                        'nearest_paragraph_id': chart['nearest_paragraph_id']
                    }
                else:
                    chart_info_map[chart['id']] = {
                        'description': "示意图",
                        'nearest_paragraph_id': chart['nearest_paragraph_id']
                    }
            return chart_info_map
    
    def _ai_generate_document(
        self,
        elements: Dict,
        chapters: List[Dict],
        template: TemplateDefinition,
        source_docs_info: Dict[str, Any] = None
    ) -> Optional[Dict[str, Any]]:
        """
        AI理解原文并生成新文档结构
        
        核心思路：
        1. 将原文内容完整提供给AI
        2. AI理解整体结构和核心内容
        3. AI按模板要求生成新文档（不照搬原文）
        4. 使用占位符标记图表位置
        """
        
        # 构建原文内容摘要（段落文本，图表索引）
        para_texts = []
        for para in elements['paragraphs']:
            # 截取前200字符，避免提示词过长
            text_preview = para['text'][:200]
            if len(para['text']) > 200:
                text_preview += "..."
            # 段落ID可能包含文档名前缀（如"文档1::P1"）
            para_texts.append(f"[{para['id']}]: {text_preview}")
        
        # 构建图表索引（预处理提炼图表内容描述，避免多文档冲突）
        chart_index = []
        
        # 构建元素顺序映射，用于查找图表周围的段落
        order_map = {}
        for i, item in enumerate(elements['order']):
            order_map[item['id']] = i
        
        # 预处理提炼图表内容描述（使用AI提炼，更通用更灵活）
        chart_info_map = self._ai_extract_chart_descriptions(elements, order_map)
        
        # 构建图表索引（包含描述和对应的原文段落ID）
        for table in elements['tables']:
            table_id = table['id']
            info = chart_info_map.get(table_id, {'description': "数据表格", 'nearest_paragraph_id': ''})
            table_desc = info['description']
            nearest_para_id = info['nearest_paragraph_id']
            if nearest_para_id:
                chart_index.append(f"表格 [{table_id}] - {table_desc}（原文位置：段落[{nearest_para_id}]后面）")
            else:
                chart_index.append(f"表格 [{table_id}] - {table_desc}")
        
        for image in elements['images']:
            image_id = image['id']
            info = chart_info_map.get(image_id, {'description': "示意图", 'nearest_paragraph_id': ''})
            image_desc = info['description']
            nearest_para_id = info['nearest_paragraph_id']
            if nearest_para_id:
                chart_index.append(f"图片 [{image_id}] - {image_desc}（原文位置：段落[{nearest_para_id}]后面）")
            else:
                chart_index.append(f"图片 [{image_id}] - {image_desc}")
        
        # 构建模板章节描述
        chapter_desc = []
        for chapter in chapters:
            desc = f"- [{chapter['order']}] {chapter['title']}（级别：{chapter['level']}级标题）"
            if chapter['description']:
                desc += f"，说明：{chapter['description']}"
            chapter_desc.append(desc)
        
        # 构建提示词
        prompt = f"""你是专业的文档编辑和内容生成专家。请仔细理解以下原文内容，然后按照模板要求生成新的文档结构。

=== 原文内容（共 {len(elements['paragraphs'])} 个段落）===
{chr(10).join(para_texts[:50])}  # 限制前50个段落，避免提示词过长

=== 原文图表索引（共 {len(chart_index)} 个）===
{chr(10).join(chart_index) if chart_index else '无图表'}

=== 模板章节要求（共 {len(chapters)} 个章节）===
{chr(10).join(chapter_desc)}

=== 任务要求 ===
1. **理解原文**：仔细理解原文的整体结构、核心内容、关键信息
2. **按模板生成**：按照模板的章节要求，生成新的文档内容
3. **不照搬原文**：重新组织内容，使其更连贯、更自然，但保持核心内容不变
4. **图表不丢失**：使用占位符标记图表位置，格式为 {{TABLE#完整ID#}} 或 {{IMAGE#完整ID#}}
5. **图表ID准确**：必须使用图表索引中的完整ID（包含文档名前缀，如"文档1::T1"），不能使用简化ID
6. **内容准确**：确保生成的内容与原文核心内容一致，不偏离原意

=== 段落结构要求（重要）===
1. **分段清晰**：每个章节根据内容情况可以有多个段落（建议3-5个段落），避免文字冗长难读
2. **层次分明**：段落之间应该有逻辑层次，可以使用序号或过渡词
3. **条理清晰**：每个段落应该有明确的主题，段落之间应该有逻辑过渡，避免一大段文字

=== 图表分布要求（重要）===
1. **穿插分布**：图表应该穿插在段落中间，而不是一股脑放在章节末尾
2. **每段最多1个图表**：每个段落后面最多放置1个图表，避免连续多个图表堆在一起
3. **相关段落后面**：图表必须放在与其主题最相关的段落后面，图表前面必须有引导文字（如"如表X所示..."）
4. **自然过渡**：图表后面应该有说明文字，继续展开讨论
5. **避免交叉错乱**：图表必须放在与其主题最相关的段落后面，不能放在其他段落的后面（如"系统架构表格"必须放在讨论系统架构的段落后面，不能放在讨论硬件设计的段落后面）

=== 图表选择方法（重要）===
- **优先根据原文段落ID匹配**：图表索引中标注了每个图表的"原文位置"，如"（原文位置：段落[P5]后面）"，表示该图表在原文中位于段落P5后面。生成新文档时，应该优先将图表放在与原文段落内容相似的段落后面
- **根据描述辅助判断**：图表索引中包含提炼的描述（如"系统架构表格"、"硬件设计图片"），可以作为辅助判断依据
- **主题匹配**：如果当前段落提到"系统架构"，应该选择"系统架构表格"或"系统架构图片"
- **避免交叉错乱**：多个图表描述相近时，必须根据原文段落ID来区分，不能混淆。例如：表格T1对应段落P5，表格T2对应段落P10，即使描述相似，也不能交叉放置

=== 输出格式 ===
只输出 JSON，格式如下：
{{
  "structure": [
    {{
      "type": "heading",
      "order": 0,
      "title": "系统概述",
      "level": 1
    }},
    {{
      "type": "paragraph",
      "text": "这里是生成的段落内容..."
    }},
    {{
      "type": "table",
      "id": "文档1::T1"
    }},
    {{
      "type": "paragraph",
      "text": "继续的段落内容..."
    }},
    {{
      "type": "image",
      "id": "文档1::I1"
    }}
  ]
}}

=== 注意事项 ===
- structure 数组按顺序排列文档元素
- heading 元素包含 order, title, level 字段
- paragraph 元素包含 text 字段（生成的文字内容）
- table 元素包含 id 字段（引用原文表格，必须使用完整ID）
- image 元素包含 id 字段（引用原文图片，必须使用完整ID）
- 图表 id 必须与图表索引中的完整ID完全一致（包含文档名前缀）
- 必须包含所有模板章节（按模板顺序）
- 每个章节至少要有一些内容（不能为空）
- 所有原文图表都必须被引用，不能丢失
- 不要输出任何其他文字或说明

请开始生成："""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system", 
                        "content": "你是专业的文档编辑和内容生成专家。擅长理解原文核心内容，按照模板要求重新组织内容，生成连贯、自然、准确的文档。"
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # 适中的温度，既准确又自然
            )
            
            result = response.choices[0].message.content.strip()
            log_info(f"AI生成响应长度：{len(result)} 字符")
            
            # 解析 JSON
            generated_data = extract_json_from_text(result)
            if not generated_data:
                log_error(f"无法解析 JSON：{result[:200]}")
                return None
            
            structure = generated_data.get('structure', [])
            if not structure:
                log_error("AI生成的结构为空")
                return None
            
            # 验证生成的结构
            validation_result = self._validate_generated_structure(
                structure=structure,
                chapters=chapters,
                elements=elements
            )
            
            if not validation_result['valid']:
                log_warning(f"AI生成结构验证失败：{validation_result['issues']}")
                # 尝试修复
                structure = self._fix_generated_structure(
                    structure=structure,
                    chapters=chapters,
                    elements=elements
                )
            
            # 返回生成结果（包含图表数据）
            return {
                'structure': structure,
                'tables': elements['tables'],
                'images': elements['images']
            }
            
        except Exception as e:
            log_error(f"AI生成失败：{e}")
            return None
    
    def _validate_generated_structure(
        self,
        structure: List[Dict],
        chapters: List[Dict],
        elements: Dict
    ) -> Dict:
        """
        验证AI生成的结构
        
        检查：
        1. 是否包含所有模板章节
        2. 是否引用了所有原文图表
        3. 每个章节是否有内容
        4. 图表ID是否准确匹配（包含文档名前缀）
        """
        issues = []
        
        # 检查章节
        generated_orders = set()
        for item in structure:
            if item.get('type') == 'heading':
                generated_orders.add(item.get('order'))
        
        expected_orders = set(c['order'] for c in chapters)
        missing_orders = expected_orders - generated_orders
        if missing_orders:
            issues.append(f"缺少章节：{missing_orders}")
        
        # 检查图表（使用完整ID，包含文档名前缀）
        referenced_tables = set()
        referenced_images = set()
        for item in structure:
            if item.get('type') == 'table':
                table_id = item.get('id')
                referenced_tables.add(table_id)
                # 检查图表ID是否存在于原文中
                if table_id not in [t['id'] for t in elements['tables']]:
                    issues.append(f"表格ID不存在：{table_id}")
            elif item.get('type') == 'image':
                image_id = item.get('id')
                referenced_images.add(image_id)
                # 检查图表ID是否存在于原文中
                if image_id not in [i['id'] for i in elements['images']]:
                    issues.append(f"图片ID不存在：{image_id}")
        
        original_tables = set(t['id'] for t in elements['tables'])
        original_images = set(i['id'] for i in elements['images'])
        
        missing_tables = original_tables - referenced_tables
        missing_images = original_images - referenced_images
        
        if missing_tables:
            issues.append(f"缺少表格：{missing_tables}")
        if missing_images:
            issues.append(f"缺少图片：{missing_images}")
        
        # 检查章节内容
        chapter_has_content = {}
        current_order = None
        for item in structure:
            if item.get('type') == 'heading':
                current_order = item.get('order')
                chapter_has_content[current_order] = False
            elif item.get('type') in ('paragraph', 'table', 'image') and current_order:
                chapter_has_content[current_order] = True
        
        empty_chapters = [order for order, has_content in chapter_has_content.items() if not has_content]
        if empty_chapters:
            issues.append(f"空章节：{empty_chapters}")
        
        # 检查图表分布（是否有连续多个图表）
        consecutive_charts = 0
        max_consecutive = 0
        for item in structure:
            if item.get('type') in ('table', 'image'):
                consecutive_charts += 1
                max_consecutive = max(max_consecutive, consecutive_charts)
            else:
                consecutive_charts = 0
        
        if max_consecutive > 2:
            issues.append(f"图表分布不合理：连续{max_consecutive}个图表堆在一起，建议穿插分布")
        
        # 检查段落结构（是否有章节只有一大段文字）
        chapter_paragraphs = {}
        current_order = None
        for item in structure:
            if item.get('type') == 'heading':
                current_order = item.get('order')
                chapter_paragraphs[current_order] = []
            elif item.get('type') == 'paragraph' and current_order:
                text = item.get('text', '')
                chapter_paragraphs[current_order].append(len(text))
        
        for order, para_lengths in chapter_paragraphs.items():
            if len(para_lengths) == 1 and para_lengths[0] > 300:
                issues.append(f"章节{order}只有一大段文字（{para_lengths[0]}字），建议分段")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues
        }
    
    def _fix_generated_structure(
        self,
        structure: List[Dict],
        chapters: List[Dict],
        elements: Dict
    ) -> List[Dict]:
        """
        修复AI生成的结构
        
        修复：
        1. 添加缺失的章节
        2. 添加缺失的图表（使用完整ID）
        3. 为空章节添加内容
        4. 修正错误的图表ID（如果AI使用了简化ID，尝试匹配完整ID）
        """
        fixed_structure = structure.copy()
        
        # 先修正错误的图表ID（如果AI使用了简化ID，尝试匹配完整ID）
        for item in fixed_structure:
            if item.get('type') == 'table':
                table_id = item.get('id')
                # 如果图表ID不存在，尝试匹配完整ID
                if table_id not in [t['id'] for t in elements['tables']]:
                    # 检查是否是简化ID（如"T1"），尝试匹配完整ID（如"文档1::T1"）
                    matching_tables = [t for t in elements['tables'] if t['id'].endswith(f"::{table_id}")]
                    if matching_tables:
                        # 使用第一个匹配的完整ID
                        item['id'] = matching_tables[0]['id']
                        log_info(f"修正表格ID：{table_id} -> {item['id']}")
            
            elif item.get('type') == 'image':
                image_id = item.get('id')
                # 如果图表ID不存在，尝试匹配完整ID
                if image_id not in [i['id'] for i in elements['images']]:
                    # 检查是否是简化ID（如"I1"），尝试匹配完整ID（如"文档1::I1"）
                    matching_images = [i for i in elements['images'] if i['id'].endswith(f"::{image_id}")]
                    if matching_images:
                        # 使用第一个匹配的完整ID
                        item['id'] = matching_images[0]['id']
                        log_info(f"修正图片ID：{image_id} -> {item['id']}")
        
        # 添加缺失的章节
        generated_orders = set()
        for item in fixed_structure:
            if item.get('type') == 'heading':
                generated_orders.add(item.get('order'))
        
        expected_orders = set(c['order'] for c in chapters)
        missing_orders = expected_orders - generated_orders
        
        for order in sorted(missing_orders):
            chapter = next((c for c in chapters if c['order'] == order), None)
            if chapter:
                fixed_structure.append({
                    'type': 'heading',
                    'order': order,
                    'title': chapter['title'],
                    'level': chapter['level']
                })
                # 为空章节添加占位内容
                fixed_structure.append({
                    'type': 'paragraph',
                    'text': f"（待补充内容）"
                })
        
        # 添加缺失的图表（使用完整ID，放在最后一个章节）
        referenced_tables = set()
        referenced_images = set()
        for item in fixed_structure:
            if item.get('type') == 'table':
                referenced_tables.add(item.get('id'))
            elif item.get('type') == 'image':
                referenced_images.add(item.get('id'))
        
        original_tables = set(t['id'] for t in elements['tables'])
        original_images = set(i['id'] for i in elements['images'])
        
        missing_tables = original_tables - referenced_tables
        missing_images = original_images - referenced_images
        
        # 在最后添加缺失的图表（使用完整ID）
        for table_id in sorted(missing_tables):
            fixed_structure.append({
                'type': 'table',
                'id': table_id  # 使用完整ID
            })
        
        for image_id in sorted(missing_images):
            fixed_structure.append({
                'type': 'image',
                'id': image_id  # 使用完整ID
            })
        
        log_info(f"修复完成，添加了 {len(missing_orders)} 个章节, {len(missing_tables)} 个表格, {len(missing_images)} 个图片")
        
        # 自动调整图表分布（将连续的图表分散到不同段落后面）
        fixed_structure = self._adjust_chart_distribution(fixed_structure)
        
        return fixed_structure
    
    def _adjust_chart_distribution(self, structure: List[Dict]) -> List[Dict]:
        """
        自动调整图表分布
        
        将连续的图表分散到不同段落后面，避免一股脑堆在一起
        
        Args:
            structure: 原始结构
            
        Returns:
            调整后的结构
        """
        # 检查是否有连续多个图表（>2个）
        consecutive_charts = 0
        max_consecutive = 0
        for item in structure:
            if item.get('type') in ('table', 'image'):
                consecutive_charts += 1
                max_consecutive = max(max_consecutive, consecutive_charts)
            else:
                consecutive_charts = 0
        
        # 如果图表分布合理，不需要调整
        if max_consecutive <= 2:
            return structure
        
        log_info(f"检测到图表分布不合理（连续{max_consecutive}个图表），开始自动调整...")
        
        # 分离段落和图表
        paragraphs = []
        charts = []
        other_items = []
        
        for item in structure:
            if item.get('type') == 'paragraph':
                paragraphs.append(item)
            elif item.get('type') in ('table', 'image'):
                charts.append(item)
            else:
                other_items.append(item)  # heading 等其他元素
        
        # 如果没有段落或图表，直接返回
        if not paragraphs or not charts:
            return structure
        
        # 重新构建结构：将图表穿插到段落后面
        adjusted_structure = []
        chart_index = 0
        
        # 先添加第一个heading（如果有）
        if other_items and other_items[0].get('type') == 'heading':
            adjusted_structure.append(other_items[0])
            other_items = other_items[1:]
        
        # 将图表穿插到段落后面
        for i, para in enumerate(paragraphs):
            adjusted_structure.append(para)
            
            # 每个段落后面最多放置1个图表
            if chart_index < len(charts):
                # 计算应该放置图表的位置（均匀分布）
                # 例如：3个段落，4个图表 → 段落0放图表0，段落1放图表1，段落2放图表2和图表3
                charts_per_para = len(charts) / len(paragraphs)
                expected_chart_index = int((i + 1) * charts_per_para)
                
                # 如果当前图表索引小于预期索引，放置图表
                while chart_index < expected_chart_index and chart_index < len(charts):
                    adjusted_structure.append(charts[chart_index])
                    chart_index += 1
        
        # 将剩余的图表放在最后
        while chart_index < len(charts):
            adjusted_structure.append(charts[chart_index])
            chart_index += 1
        
        # 添加剩余的其他元素（heading等）
        for item in other_items:
            adjusted_structure.append(item)
        
        # 验证调整后的结构是否合理
        consecutive_charts = 0
        max_consecutive = 0
        for item in adjusted_structure:
            if item.get('type') in ('table', 'image'):
                consecutive_charts += 1
                max_consecutive = max(max_consecutive, consecutive_charts)
            else:
                consecutive_charts = 0
        
        log_info(f"图表分布调整完成，最大连续图表数：{max_consecutive}")
        
        return adjusted_structure
    
    def _identify_consecutive_charts(
        self,
        elements: Dict,
        order_map: Dict
    ) -> List[List[str]]:
        """
        识别连续出现的图表（作为同一引用位置处理）
        
        Args:
            elements: 所有元素
            order_map: 元素顺序映射
            
        Returns:
            连续图表组的列表（如 [["T1", "I1"], ["T2"]]）
        """
        consecutive_groups = []
        current_group = []
        
        # 按顺序遍历所有元素
        for item in elements['order']:
            if item['type'] in ('table', 'image'):
                # 如果是图表，添加到当前组
                current_group.append(item['id'])
            else:
                # 如果不是图表（段落），结束当前组
                if current_group:
                    consecutive_groups.append(current_group)
                    current_group = []
        
        # 处理末尾的图表组
        if current_group:
            consecutive_groups.append(current_group)
        
        log_info(f"识别到 {len(consecutive_groups)} 个图表组")
        return consecutive_groups
    
    def _extract_context_before_with_rules(
        self,
        elements: Dict,
        order_map: Dict,
        chart_idx: int,
        consecutive_chart_groups: List[List[str]],
        chart_id: str
    ) -> List[Dict]:
        """
        提取上文段落（应用精细规则）
        
        规则：
        1. 图和表只提取距离最近的上文2段落
        2. 例外情况：当前图表和上文最近图表之间只有一个段落，则上文只提取一个段落
        3. 连续出现的图或表作为同一引用位置处理
        
        Args:
            elements: 所有元素
            order_map: 元素顺序映射
            chart_idx: 当前图表索引
            consecutive_chart_groups: 连续图表组
            chart_id: 当前图表ID
            
        Returns:
            上文段落列表 [{id, text}]，最近的段落排在最后
        """
        context_before_list = []
        
        # 查找当前图表所属的连续图表组
        current_group_idx = -1
        for i, group in enumerate(consecutive_chart_groups):
            if chart_id in group:
                current_group_idx = i
                break
        
        # 查找上一个图表组（如果存在）
        prev_chart_group_idx = -1
        if current_group_idx > 0:
            prev_chart_group_idx = current_group_idx - 1
        
        # 查找上一个图表组的最后一个图表的索引
        prev_chart_last_idx = -1
        if prev_chart_group_idx >= 0:
            prev_chart_group = consecutive_chart_groups[prev_chart_group_idx]
            prev_chart_last_id = prev_chart_group[-1]  # 组中最后一个图表
            if prev_chart_last_id in order_map:
                prev_chart_last_idx = order_map[prev_chart_last_id]
        
        # 计算当前图表和上一个图表组之间的段落数量
        paragraphs_between = 0
        if prev_chart_last_idx >= 0:
            for i in range(prev_chart_last_idx + 1, chart_idx):
                item = elements['order'][i]
                if item['type'] == 'paragraph':
                    paragraphs_between += 1
        
        # 应用规则：
        # 1. 如果当前图表和上文最近图表之间只有一个段落，则上文只提取一个段落
        # 2. 否则，提取最近的2个段落
        max_paragraphs = 2
        if paragraphs_between == 1:
            max_paragraphs = 1
        
        # 向前查找段落（最多提取 max_paragraphs 个）
        for i in range(chart_idx - 1, max(0, chart_idx - 20), -1):
            item = elements['order'][i]
            if item['type'] == 'paragraph':
                para = next((p for p in elements['paragraphs'] if p['id'] == item['id']), None)
                if para:
                    context_before_list.append({
                        'id': item['id'],
                        'text': para['text'][:150]
                    })
                    if len(context_before_list) >= max_paragraphs:
                        break
        
        # 反转列表，保持顺序（从远到近）
        context_before_list.reverse()
        
        return context_before_list
    
