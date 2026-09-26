"""
工具模块 - 提供通用的工具函数
避免代码重复，保持模块间低耦合
"""
import os
import re
import json
from typing import Any, Dict, List

from docx import Document
from docx.shared import Pt


def is_chart_title(text: str) -> bool:
    """判断文本是否是图表标题
    
    Args:
        text: 待检查的文本
        
    Returns:
        是否是图表标题
    """
    # 匹配 "图 X"、"图X"、"表 X"、"表X" 等格式
    chart_title_patterns = [
        r'^图\s*\d+',
        r'^表\s*\d+',
        r'^Figure\s*\d+',
        r'^Table\s*\d+',
        r'^图表\s*\d+'
    ]
    for pattern in chart_title_patterns:
        if re.match(pattern, text.strip(), re.IGNORECASE):
            return True
    return False


def extract_caption(text: str, max_len: int = 40) -> str:
    """从段落文本中提取图/表/公式的题注标题（caption）。

    形如 "图1-1 系统架构"、"表1 参数对比"、"Figure 3.2 ..."、"图：硬件框图" 之类的
    短句，通常紧邻在对应图表元素之后。若识别不到明确题注特征，则返回空字符串，
    避免把图表后文的普通正文误当成题注——图表真实含义应由其前后文语义推断。
    max_len 仅用于截断匹配到的题注正文，不影响是否判为题注。

    Args:
        text: 段落文本
        max_len: 返回的题注最大长度

    Returns:
        提取到的题注文本；若无明确题注特征则返回空字符串
    """
    if not text:
        return ""
    t = text.strip()
    patterns = [
        r'^图\s*[\d.．\-—]*\s*[:：]?\s*.{0,%d}' % max_len,
        r'^表\s*[\d.．\-—]*\s*[:：]?\s*.{0,%d}' % max_len,
        r'^公式\s*[\d.．\-—]*\s*[:：]?\s*.{0,%d}' % max_len,
        r'^Equation\s*[\d.．\-—]*\s*[:：]?\s*.{0,%d}' % max_len,
        r'^(Figure|Table|Fig\.?)\s*[\d.．\-—]*\s*[:：]?\s*.{0,%d}' % max_len,
        r'^图[片示]?[：:]?\s*.{0,20}',
        r'^图示[：:]?\s*.{0,20}',
        r'^[（(]图\s*\d+[）)][：:]?\s*.{0,%d}' % max_len,
    ]
    for p in patterns:
        m = re.match(p, t, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    return ""


def is_document_title_candidate(text: str) -> bool:
    """判断段落是否可能是文档标题
    
    条件：
    1. 结尾没有标点符号（句号、问号、感叹号、逗号、分号、冒号）
    2. 无序号（不以数字开头，如"1."、"一、"等）
    3. 不是图表标题
    4. 长度适中（不超过100字符）
    5. 不是章节名称（即使格式不标准，但带序号的一般是章节）
    
    Args:
        text: 待检查的文本
        
    Returns:
        是否可能是文档标题
    """
    text = text.strip()
    
    # 空文本不是标题
    if not text:
        return False
    
    # 太长不是标题（超过100字符）
    if len(text) > 100:
        return False
    
    # 结尾有标点符号不是标题
    punctuation_endings = ['.', '。', '?', '？', '!', '！', ',', '，', ';', '；', ':', '：']
    if text[-1] in punctuation_endings:
        return False
    
    # 有序号不是标题（扩展检测模式）
    numbered_patterns = [
        r'^\d+\.',              # 1. 开头
        r'^\d+\.\d+',           # 1.1 开头
        r'^\d+\.\d+\.\d+',      # 1.1.1 开头
        r'^\d+\s',              # 1 开头（数字+空格）
        r'^[一二三四五六七八九十]+、',  # 一、开头
        r'^[一二三四五六七八九十]+\.',  # 一.开头
        r'^[一二三四五六七八九十]+\s',  # 一 开头（中文数字+空格）
        r'^\(\d+\)',            # (1) 开头
        r'^（[一二三四五六七八九十\d]+）',  # （一）、（1）开头
        r'^第[一二三四五六七八九十\d]+[章节条款部分]',  # 第一章、第1节、第1部分等
        r'^[（(]\d+[）)]',      # (1) 或 （1）开头
    ]
    for pattern in numbered_patterns:
        if re.match(pattern, text):
            return False
    
    # 检测是否以数字开头（如"1系统设计"），这通常是章节名称
    if re.match(r'^\d', text):
        return False
    
    # 检测是否以中文数字开头（如"一系统设计"），这通常是章节名称
    if re.match(r'^[一二三四五六七八九十]', text):
        return False
    
    # 图表标题不是文档标题
    if is_chart_title(text):
        return False
    
    # 包含常见章节关键词且较短，可能是章节名称而非文档标题
    chapter_keywords = ['概述', '简介', '介绍', '设计', '实现', '方案', '系统', '架构', 
                        '测试', '分析', '总结', '结论', '背景', '目的', '意义', '方法',
                        '流程', '功能', '模块', '组件', '接口', '配置', '部署', '优化',
                        '问题', '解决', '改进', '建议', '展望', '附录', '参考文献']
    # 如果文本较短（<30字符）且包含章节关键词，可能是章节名称
    if len(text) < 30:
        for keyword in chapter_keywords:
            if keyword in text:
                # 进一步检查：如果关键词在文本末尾，更可能是章节名称
                if text.endswith(keyword) or keyword in text[-10:]:
                    return False
    
    return True


def clean_ai_json_response(result: str) -> str:
    """清理AI返回的JSON响应，去除markdown代码块标记
    
    Args:
        result: AI返回的原始文本
        
    Returns:
        清理后的JSON文本
    """
    result = re.sub(r'^```json\s*', '', result)
    result = re.sub(r'^```\s*', '', result)
    result = re.sub(r'\s*```$', '', result)
    return result


def extract_json_from_text(text: str) -> Dict[str, Any]:
    """从文本中提取JSON对象
    
    Args:
        text: 包含JSON的文本
        
    Returns:
        解析后的JSON字典，如果失败返回空字典
    """
    try:
        # 先清理
        clean_text = clean_ai_json_response(text)
        
        # 提取JSON
        json_match = re.search(r'\{.*\}', clean_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            # 尝试直接解析
            return json.loads(clean_text)
    except Exception:
        return {}


def ends_without_punctuation(text: str) -> bool:
    """检查文本是否以标点符号结尾
    
    Args:
        text: 待检查的文本
        
    Returns:
        如果末尾没有标点符号返回True
    """
    text = text.strip()
    if not text:
        return False
    
    # 常见标点符号
    punctuation = r'[。！？；：？.,;:?!…～~""''""（）\[\]【】《》、]'
    
    # 如果末尾不是标点符号，返回True
    return not re.search(punctuation + r'$', text)


def calculate_max_image_width(doc: Document, char_margin: int = 4):
    """计算图片允许的最大宽度，使图片左右留出指定字符数的空白。

    中文字符在 Word 中宽度约等于当前字号（磅），因此 N 个字符的留白
    按 N * 默认字体大小计算。python-docx 内部使用 EMU 为单位，Pt 值在
    运算时会自动转换为 EMU，最终返回的也是 EMU 长度对象。

    Args:
        doc: 正在构建的 Word 文档对象
        char_margin: 单侧留白对应的字符数，默认 4 个字符

    Returns:
        docx.shared.Length: 图片允许的最大宽度（EMU）
    """
    section = doc.sections[0]
    # 页面可用宽度 = 页面宽度 - 左右边距
    usable_width = section.page_width - section.left_margin - section.right_margin

    # 以 Normal 样式的字体大小作为"一个字符"的宽度基准
    font_size = doc.styles['Normal'].font.size
    if font_size is None:
        font_size = Pt(12)

    # 单侧留白 = 字符数 * 字号；两侧共 2 * 字符数 * 字号
    side_margin = Pt(char_margin * font_size.pt)
    max_width = usable_width - 2 * side_margin

    # 防止极端页面设置导致最大宽度过小，至少保留 1 英寸
    min_width = Pt(72)
    if max_width < min_width:
        max_width = min_width

    return max_width


def extract_document_info(filename: str, paragraphs: Dict, current_order: List[str]) -> Dict:
    """提取文档信息（标题/类型/章节），用于 AI 处理时的上下文"""
    doc_info = {
        'title': '',
        'type': '其他类型',
        'section': ''
    }

    title_from_filename = os.path.splitext(filename)[0]
    for prefix in ['processed_', 'output_', 'test_', 'demo_', 'nl_']:
        if title_from_filename.startswith(prefix):
            title_from_filename = title_from_filename[len(prefix):]

    sample_texts = []
    for elem_id in current_order[:15]:
        if elem_id.startswith('P') and elem_id in paragraphs:
            para_data = paragraphs[elem_id]
            if isinstance(para_data, tuple):
                text = para_data[0]
            else:
                text = para_data
            if text:
                sample_texts.append(text)

    combined_text = ' '.join(sample_texts)
    doc_type = identify_document_type(combined_text)
    doc_info['type'] = doc_type

    title_from_content = extract_title_from_content(sample_texts)
    if title_from_content:
        doc_info['title'] = title_from_content
    elif title_from_filename and len(title_from_filename) > 2:
        doc_info['title'] = title_from_filename
    else:
        doc_info['title'] = f'未命名文档（{doc_type}）'

    section_title = identify_section_title(sample_texts)
    if section_title:
        doc_info['section'] = section_title
    else:
        doc_info['section'] = infer_section_from_content(sample_texts, doc_type)

    return doc_info


def identify_document_type(text: str) -> str:
    """根据文本内容识别文档类型"""
    text_lower = text.lower()

    tech_keywords = ['设计', '方案', '系统', '架构', '模块', '接口', '实现', '功能', '技术', '平台', '部署']
    academic_keywords = ['摘要', '关键词', '引言', '结论', '参考文献', '研究', '实验', '分析', '方法', '理论', '模型']
    test_keywords = ['测试', '报告', '结果', '数据', '性能', '验证', '检测', '通过率', '错误', 'bug', '用例']
    survey_keywords = ['调研', '调查', '市场', '趋势', '分析', '现状', '发展', '需求', '用户', '行业']
    project_keywords = ['项目', '计划', '进度', '目标', '任务', '资源', '风险', '预算', '里程碑', '交付']

    scores = {
        '技术方案/设计文档': sum(1 for kw in tech_keywords if kw in text_lower),
        '学术论文': sum(1 for kw in academic_keywords if kw in text_lower),
        '测试报告': sum(1 for kw in test_keywords if kw in text_lower),
        '调研报告': sum(1 for kw in survey_keywords if kw in text_lower),
        '项目文档': sum(1 for kw in project_keywords if kw in text_lower),
    }

    max_score = max(scores.values())
    if max_score > 0:
        for doc_type, score in scores.items():
            if score == max_score:
                return doc_type

    return '其他类型'


def identify_section_title(texts: List[str]) -> str:
    """识别章节标题"""
    for text in texts[:5]:
        if len(text) < 100:
            patterns = [
                r'^(\d+\.?\d*)\s+',
                r'^第 [一二三四五六七八九十]+[章节部分]',
                r'^[A-Z]\.\s+',
                r'^\d+\s+[、.．]',
            ]
            for pattern in patterns:
                if re.match(pattern, text):
                    return text.strip()
    return ''


def extract_title_from_content(texts: List[str]) -> str:
    """从内容中提取文档标题"""
    for text in texts[:3]:
        text_stripped = text.strip()
        if (5 <= len(text_stripped) <= 50 and
            '。' not in text_stripped and
            '！' not in text_stripped and
            '？' not in text_stripped):
            title_keywords = ['设计', '方案', '报告', '论文', '说明', '文档', '系统', '研究']
            if any(kw in text_stripped for kw in title_keywords):
                return text_stripped
    return ''


def infer_section_from_content(texts: List[str], doc_type: str) -> str:
    """根据内容推断章节信息"""
    combined_text = ' '.join(texts).lower()

    if doc_type == '学术论文':
        if any(kw in combined_text for kw in ['摘要', 'abstract']):
            return '摘要部分'
        elif any(kw in combined_text for kw in ['引言', '前言', '背景']):
            return '引言部分'
        elif any(kw in combined_text for kw in ['结论', '总结']):
            return '结论部分'
        elif any(kw in combined_text for kw in ['方法', '实验', '结果']):
            return '正文部分'
    elif doc_type == '技术方案/设计文档':
        if any(kw in combined_text for kw in ['概述', '简介', '背景']):
            return '概述部分'
        elif any(kw in combined_text for kw in ['需求', '目标']):
            return '需求分析'
        elif any(kw in combined_text for kw in ['设计', '方案', '架构']):
            return '设计方案'
        elif any(kw in combined_text for kw in ['实现', '代码']):
            return '实现部分'
    elif doc_type == '测试报告':
        if any(kw in combined_text for kw in ['概述', '简介']):
            return '测试概述'
        elif any(kw in combined_text for kw in ['环境', '配置']):
            return '测试环境'
        elif any(kw in combined_text for kw in ['结果', '数据']):
            return '测试结果'
        elif any(kw in combined_text for kw in ['结论', '建议']):
            return '测试结论'
    elif doc_type == '调研报告':
        if any(kw in combined_text for kw in ['概述', '背景']):
            return '调研背景'
        elif any(kw in combined_text for kw in ['现状', '市场']):
            return '市场现状'
        elif any(kw in combined_text for kw in ['分析', '趋势']):
            return '趋势分析'
        elif any(kw in combined_text for kw in ['结论', '建议']):
            return '调研结论'

    if texts:
        first_text = texts[0].strip() if texts else ''
        if len(first_text) < 30:
            return '开头部分'
        else:
            return '正文部分'
    return '文档主体部分'
