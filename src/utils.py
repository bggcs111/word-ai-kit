"""
工具模块 - 提供通用的工具函数
避免代码重复，保持模块间低耦合
"""
import re
import json
from typing import Any, Dict


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
