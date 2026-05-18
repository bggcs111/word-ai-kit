"""
AI 处理模块
负责调用 AI API 进行文本润色
"""
import re
import json
from typing import Dict, List, Tuple, Any
from openai import OpenAI
from src.constants import AI_SYSTEM_PROMPT, AI_USER_PROMPT_TEMPLATE


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
    
    def process_paragraphs(self, paragraphs: Dict, current_order: List[str], document_info: Dict = None) -> Tuple[Dict, List, bool]:
        """
        调用 AI 处理段落
        
        Args:
            paragraphs: 段落字典
            current_order: 当前元素顺序
            document_info: 文档信息字典（可选），包含：
                - title: 文档标题
                - type: 文档类型
                - section: 当前章节
                
        Returns:
            (polished_paragraphs, new_order, success)
            success 为 False 表示 AI 调用失败
        """
        # 构建段落内容
        para_details = self._build_paragraph_details(paragraphs, current_order)
        
        # 提取文档信息
        if document_info is None:
            document_info = {}
        
        doc_title = document_info.get('title', '未知')
        doc_type = document_info.get('type', '其他类型')
        current_section = document_info.get('section', '未知章节')
        
        # 构建提示词
        prompt = AI_USER_PROMPT_TEMPLATE.format(
            document_title=doc_title,
            document_type=doc_type,
            current_section=current_section,
            element_order=', '.join(current_order),
            paragraph_details='\n'.join(para_details)
        )
        
        # 调用 AI
        result = self._call_ai(prompt)
        
        # 如果 AI 调用失败，返回空结果
        if not result:
            return {}, current_order, False
        
        # 解析结果
        polished, new_order = self._parse_ai_response(result, paragraphs, current_order)
        
        return polished, new_order, True
    
    def _build_paragraph_details(self, paragraphs: Dict, current_order: List[str]) -> List[str]:
        """构建段落详细信息列表"""
        para_details = []
        for elem_id in current_order:
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
                para_details.append(f"[{elem_id}] {text}")
            else:
                para_details.append(f"[{elem_id}]")
        return para_details
    
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
        
        print(f"  准备插入占位符，formula_run_indices: {formula_run_indices}")
        
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
        print(f"  插入占位符：{len(formula_run_indices)} 个公式，文本分割成 {text_segments_count} 段")
        print(f"  带占位符文本：{result[:200]}...")
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
            print(f"⚠️  AI 调用失败：{error_message}")
            
            # 检查是否是 API Key 错误
            if "api_key" in error_message.lower() or "authentication" in error_message.lower() or "unauthorized" in error_message.lower() or "invalid_api_key" in error_message.lower() or "401" in error_message:
                print("❌ 错误原因：API Key 无效或认证失败")
                print("   请检查配置文件中的 API Key 是否正确")
            elif "connection" in error_message.lower() or "timeout" in error_message.lower():
                print("❌ 错误原因：网络连接问题")
                print("   请检查网络连接或 API 服务是否可用")
            else:
                print(f"❌ 错误类型：{type(e).__name__}")
            
            return ""
    
    def _parse_ai_response(self, result: str, paragraphs: Dict, current_order: List[str]) -> Tuple[Dict, List]:
        """解析 AI 响应"""
        # 清理 markdown 代码块标记
        result = re.sub(r'^```json\s*', '', result)
        result = re.sub(r'^```\s*', '', result)
        result = re.sub(r'\s*```$', '', result)
        
        # 提取 JSON
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if not json_match:
            print(f"无法解析 JSON: {result[:200]}")
            return {}, current_order
        
        data = json.loads(json_match.group())
        polished = data.get('polished_paragraphs', {})
        new_order = data.get('new_order', current_order)
        
        # 验证 new_order 是否包含所有元素
        if set(new_order) != set(current_order):
            return polished, current_order
        
        # 确保所有段落都有润色版本
        self._ensure_all_paragraphs_polished(polished, paragraphs, current_order)
        
        return polished, new_order
    
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
