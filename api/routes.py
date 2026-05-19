"""
API 路由模块
"""
import os
import re
import json
from urllib.parse import quote
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
from typing import Dict, List, Optional
from src.logger import log_info, log_error, log_success, log_warning

router = APIRouter()

_config_manager = None


def set_config_manager(manager):
    global _config_manager
    _config_manager = manager


def get_config_manager():
    return _config_manager


def extract_document_info(filename: str, paragraphs: Dict, current_order: List[str]) -> Dict:
    """
    提取文档信息，用于 AI 润色时的上下文
    兼容缺失标题和章节的情况
    
    Args:
        filename: 文件名
        paragraphs: 段落字典
        current_order: 元素顺序
        
    Returns:
        文档信息字典
    """
    doc_info = {
        'title': '',
        'type': '其他类型',
        'section': ''
    }
    
    # 1. 从文件名提取标题（如果文件名有意义）
    title_from_filename = os.path.splitext(filename)[0]
    # 移除常见前缀
    for prefix in ['processed_', 'output_', 'test_', 'demo_']:
        if title_from_filename.startswith(prefix):
            title_from_filename = title_from_filename[len(prefix):]
    
    # 2. 从段落内容识别文档类型
    # 收集前几个段落的内容用于分析
    sample_texts = []
    for elem_id in current_order[:15]:  # 分析前 15 个元素
        if elem_id.startswith('P') and elem_id in paragraphs:
            para_data = paragraphs[elem_id]
            if isinstance(para_data, tuple):
                text = para_data[0]
            else:
                text = para_data
            if text:
                sample_texts.append(text)
    
    combined_text = ' '.join(sample_texts)
    
    # 关键词匹配识别文档类型
    doc_type = identify_document_type(combined_text)
    doc_info['type'] = doc_type
    
    # 3. 尝试从内容中提取标题（如果文件名不够明确）
    title_from_content = extract_title_from_content(sample_texts)
    
    # 优先使用从内容提取的标题，否则使用文件名
    if title_from_content:
        doc_info['title'] = title_from_content
    elif title_from_filename and len(title_from_filename) > 2:
        doc_info['title'] = title_from_filename
    else:
        doc_info['title'] = f'未命名文档（{doc_type}）'
    
    # 4. 识别当前章节（如果有章节标题）
    section_title = identify_section_title(sample_texts)
    if section_title:
        doc_info['section'] = section_title
    else:
        # 如果没有明确章节，根据内容推断
        doc_info['section'] = infer_section_from_content(sample_texts, doc_type)
    
    return doc_info


def identify_document_type(text: str) -> str:
    """
    根据文本内容识别文档类型
    
    Args:
        text: 文本内容
        
    Returns:
        文档类型字符串
    """
    text_lower = text.lower()
    
    # 技术方案/设计文档关键词
    tech_keywords = ['设计', '方案', '系统', '架构', '模块', '接口', '实现', '功能', '技术', '平台', '部署']
    # 学术论文关键词
    academic_keywords = ['摘要', '关键词', '引言', '结论', '参考文献', '研究', '实验', '分析', '方法', '理论', '模型']
    # 测试报告关键词
    test_keywords = ['测试', '报告', '结果', '数据', '性能', '验证', '检测', '通过率', '错误', 'bug', '用例']
    # 调研报告关键词
    survey_keywords = ['调研', '调查', '市场', '趋势', '分析', '现状', '发展', '需求', '用户', '行业']
    # 项目文档关键词
    project_keywords = ['项目', '计划', '进度', '目标', '任务', '资源', '风险', '预算', '里程碑', '交付']
    
    # 计算匹配度
    scores = {
        '技术方案/设计文档': sum(1 for kw in tech_keywords if kw in text_lower),
        '学术论文': sum(1 for kw in academic_keywords if kw in text_lower),
        '测试报告': sum(1 for kw in test_keywords if kw in text_lower),
        '调研报告': sum(1 for kw in survey_keywords if kw in text_lower),
        '项目文档': sum(1 for kw in project_keywords if kw in text_lower),
    }
    
    # 返回得分最高的类型
    max_score = max(scores.values())
    if max_score > 0:
        for doc_type, score in scores.items():
            if score == max_score:
                return doc_type
    
    return '其他类型'


def identify_section_title(texts: List[str]) -> str:
    """
    识别章节标题
    
    Args:
        texts: 文本列表
        
    Returns:
        章节标题字符串
    """
    # 查找包含序号的短段落（可能是章节标题）
    for text in texts[:5]:  # 只检查前 5 个段落
        if len(text) < 100:  # 短段落可能是标题
            # 匹配常见章节序号格式
            patterns = [
                r'^(\d+\.?\d*)\s+',  # 1.1, 1.2.3 等
                r'^第 [一二三四五六七八九十]+[章节部分]',  # 第一章，第二节等
                r'^[A-Z]\.\s+',  # A. B. C. 等
                r'^\d+\s+[、.．]',  # 1、2、等
            ]
            for pattern in patterns:
                if re.match(pattern, text):
                    return text.strip()
    
    return ''


def extract_title_from_content(texts: List[str]) -> str:
    """
    从内容中提取文档标题
    
    Args:
        texts: 文本列表
        
    Returns:
        标题字符串（如果找到）
    """
    # 查找可能是标题的段落
    for text in texts[:3]:  # 只检查前 3 个段落
        text_stripped = text.strip()
        
        # 标题特征：
        # 1. 长度适中（5-50 字）
        # 2. 不包含句号（标题通常没有句号）
        # 3. 可能包含关键词
        if (5 <= len(text_stripped) <= 50 and 
            '。' not in text_stripped and 
            '！' not in text_stripped and
            '？' not in text_stripped):
            
            # 检查是否包含标题关键词
            title_keywords = ['设计', '方案', '报告', '论文', '说明', '文档', '系统', '研究']
            if any(kw in text_stripped for kw in title_keywords):
                return text_stripped
    
    return ''


def infer_section_from_content(texts: List[str], doc_type: str) -> str:
    """
    根据内容推断章节信息
    
    Args:
        texts: 文本列表
        doc_type: 文档类型
        
    Returns:
        推断的章节描述
    """
    combined_text = ' '.join(texts).lower()
    
    # 根据文档类型和内容推断章节
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
    
    # 默认返回
    if texts:
        # 根据第一段内容简单推断
        first_text = texts[0].strip() if texts else ''
        if len(first_text) < 30:
            return f'开头部分'
        else:
            return f'正文部分'
    
    return '文档主体部分'


class ModelConfigRequest(BaseModel):
    """模型配置请求模型"""
    model_name: str
    api_key: str
    base_url: str
    model: str


class TestConfigRequest(BaseModel):
    """测试配置请求模型"""
    model_name: str
    api_key: str
    base_url: str
    model: str


class StoragePathRequest(BaseModel):
    """存储路径请求模型"""
    storage_path: str


class TemplateProcessRequest(BaseModel):
    """模板处理请求模型"""
    template_id: str  # 模板 ID（使用预定义模板）
    template_json: Optional[Dict] = None  # 自定义模板 JSON（可选）


@router.get("/")
async def root():
    """根路由"""
    from src.config import ConfigManager

    config_manager = get_config_manager()
    if config_manager is None:
        config_manager = ConfigManager()

    return {
        "message": "Word 智能处理服务（支持多模型）",
        "current_model": config_manager.get_current_model(),
        "model_name": config_manager.get_current_model_config().get("model", "unknown"),
        "endpoint": "POST /process",
        "功能": ["文字润色", "保留图片/表格/公式"],
        "可用模型": config_manager.get_all_models()
    }


@router.post("/process")
async def process_document(
    files: List[UploadFile] = File(...),
    user_prompt: str = Form(None),
    doc_type: str = Form(None)
):
    """处理上传的 Word 文档（支持多文件）"""
    from src.config import ConfigManager
    from src.parser import DocumentParser
    from src.ai_processor import AIProcessor
    from src.builder import DocumentBuilder
    from openai import OpenAI

    log_info(f"收到文档处理请求：{len(files)} 个文件")

    upload_dir = Path("./uploads")
    upload_dir.mkdir(exist_ok=True)

    input_paths = []
    for file in files:
        file_content = await file.read()
        if len(file_content) > 50 * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"文件 {file.filename} 大小不能超过 50MB")
        safe_filename = Path(file.filename).name
        input_path = upload_dir / safe_filename
        with open(input_path, "wb") as f:
            f.write(file_content)
        input_paths.append((safe_filename, input_path))

    config_manager = get_config_manager()
    if config_manager is None:
        config_manager = ConfigManager()

    current_model = config_manager.get_current_model()
    model_config = config_manager.get_current_model_config()

    if not model_config or not model_config.get("api_key"):
        for _, p in input_paths:
            if p.exists():
                p.unlink()
        raise HTTPException(status_code=500, detail="API 配置无效，请通过 Web 界面配置 API Key")

    try:
        client = OpenAI(
            api_key=model_config["api_key"],
            base_url=model_config["base_url"]
        )
        model_name = model_config["model"]
    except Exception as e:
        for _, p in input_paths:
            if p.exists():
                p.unlink()
        raise HTTPException(status_code=500, detail="AI 服务初始化失败，请检查 API 配置和网络连接")

    all_elements = []
    all_paragraphs = {}
    all_document_info = {}
    element_offset = 0

    for safe_filename, input_path in input_paths:
        parser = DocumentParser()
        elements, paragraphs, _ = parser.parse(str(input_path))

        current_order = [elem[1] for elem in elements]
        document_info = extract_document_info(safe_filename, paragraphs, current_order)
        log_info(f"文档识别：{document_info.get('title', '未知')}")

        if len(input_paths) > 1:
            for key, value in paragraphs.items():
                new_key = safe_filename + "::" + key
                all_paragraphs[new_key] = value
            for elem in elements:
                all_elements.append((elem[0], safe_filename + "::" + elem[1], elem[2]))
        else:
            all_paragraphs.update(paragraphs)
            all_elements.extend(elements)

        all_document_info[safe_filename] = document_info

    merged_order = [elem[1] for elem in all_elements]

    primary_doc_info = list(all_document_info.values())[0] if all_document_info else {}
    if len(all_document_info) > 1:
        doc_names = list(all_document_info.keys())
        primary_doc_info['title'] = f"合并文档（{', '.join(doc_names)}）"
        primary_doc_info['source_count'] = len(all_document_info)

    ai_processor = AIProcessor(client, model_name)
    polished_paragraphs, new_order, document_title, title_from_first_paragraph, success, generated_chart_titles, chart_title_paragraphs, generated_chapter_titles = ai_processor.process_paragraphs(
        all_paragraphs, 
        merged_order, 
        primary_doc_info,
        user_prompt,
        doc_type
    )

    if not success:
        for _, p in input_paths:
            if p.exists():
                p.unlink()
        raise HTTPException(status_code=500, detail="AI 处理失败，无法生成润色后的文档")

    builder = DocumentBuilder(all_elements, polished_paragraphs, new_order, generated_chart_titles, generated_chapter_titles, document_title, title_from_first_paragraph, chart_title_paragraphs)
    first_filename = input_paths[0][0]
    output_filename = f"processed_{first_filename}"
    output_path = upload_dir / output_filename
    builder.build(str(output_path))

    log_success(f"文档处理完成：{len(files)} 个文件")

    from starlette.responses import Response

    with open(output_path, 'rb') as f:
        file_content = f.read()

    response = Response(
        content=file_content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    doc_type_simple = primary_doc_info.get('type', 'Other')
    type_mapping = {
        '技术方案/设计文档': 'Technical Design',
        '学术论文': 'Academic Paper',
        '测试报告': 'Test Report',
        '调研报告': 'Survey Report',
        '项目文档': 'Project Document',
        '其他类型': 'Other'
    }
    simple_type = type_mapping.get(doc_type_simple, 'Other')

    response.headers["Content-Disposition"] = f'attachment; filename="processed_doc.docx"'
    response.headers["X-Doc-Type"] = simple_type

    # 清理临时文件
    try:
        for _, p in input_paths:
            if p.exists():
                p.unlink()
        if output_path.exists():
            output_path.unlink()
    except Exception as e:
        log_warning(f"清理临时文件失败: {e}")

    return response


@router.get("/config/status")
async def get_config_status():
    """获取配置状态"""
    from src.config import ConfigManager

    config_manager = get_config_manager()
    if config_manager is None:
        config_manager = ConfigManager()

    models = config_manager.get_all_models()
    config_status = {}

    for model_name in models:
        model_config = config_manager.models_config.get(model_name, {})
        config_status[model_name] = {
            "has_config": bool(model_config.get("api_key")),
            "base_url": model_config.get("base_url", ""),
            "model": model_config.get("model", "")
        }

    return {
        "storage_enabled": config_manager.get_storage_status(),
        "current_model": config_manager.get_current_model(),
        "config_status": config_status,
        "storage_path": config_manager.get_storage_path()
    }


@router.post("/config/save")
async def save_model_config(request: ModelConfigRequest):
    """保存模型配置"""
    from src.config import ConfigManager

    log_info(f"收到配置保存请求：{request.model_name}")

    config_manager = get_config_manager()
    if config_manager is None:
        config_manager = ConfigManager()

    try:
        success = config_manager.save_model_config(
            request.model_name,
            request.api_key,
            request.base_url,
            request.model
        )

        if success:
            log_success(f"配置保存成功：{request.model_name}")
            return {
                "message": "配置保存成功",
                "model_name": request.model_name
            }
        else:
            log_error(f"配置保存失败：{request.model_name}")
            raise HTTPException(status_code=500, detail="配置保存失败")

    except Exception as e:
        log_error(f"配置保存异常：{str(e)}")
        raise HTTPException(status_code=500, detail=f"配置保存异常：{str(e)}")


@router.post("/config/test")
async def test_model_config(request: TestConfigRequest):
    """测试模型配置"""
    from openai import OpenAI

    log_info(f"收到配置测试请求：{request.model_name}")

    try:
        client = OpenAI(
            api_key=request.api_key,
            base_url=request.base_url
        )

        # 发送一个简单的测试请求
        response = client.chat.completions.create(
            model=request.model,
            messages=[
                {"role": "user", "content": "请回复'测试通过'"}
            ],
            max_tokens=10
        )

        result = response.choices[0].message.content.strip()
        log_success(f"配置测试成功：{request.model_name} - {result}")

        return {
            "message": "配置测试成功",
            "result": result,
            "model_name": request.model_name
        }

    except Exception as e:
        error_msg = str(e)
        log_error(f"配置测试失败：{request.model_name} - {error_msg}")

        # 提供更友好的错误信息
        if "api_key" in error_msg.lower() or "authentication" in error_msg.lower():
            detail = "API Key 无效或认证失败"
        elif "connection" in error_msg.lower() or "timeout" in error_msg.lower():
            detail = "网络连接问题，请检查网络连接"
        elif "model" in error_msg.lower():
            detail = "模型名称无效"
        else:
            detail = f"配置测试失败：{error_msg}"

        raise HTTPException(status_code=500, detail=detail)


@router.get("/config/path")
async def get_config_path():
    """获取配置文件路径"""
    from src.config import ConfigManager

    config_manager = get_config_manager()
    if config_manager is None:
        config_manager = ConfigManager()

    return {
        "storage_path": config_manager.get_storage_path()
    }


@router.post("/config/path")
async def change_config_path(request: StoragePathRequest):
    """更改配置文件路径"""
    from src.config import ConfigManager

    log_info(f"收到配置路径更改请求：{request.storage_path}")

    config_manager = get_config_manager()
    if config_manager is None:
        config_manager = ConfigManager()

    try:
        success = config_manager.change_storage_path(request.storage_path)

        if success:
            log_success(f"配置路径更改成功：{request.storage_path}")
            return {
                "message": "配置路径更改成功",
                "storage_path": request.storage_path
            }
        else:
            log_error(f"配置路径更改失败：{request.storage_path}")
            raise HTTPException(status_code=500, detail="配置路径更改失败")

    except ValueError as e:
        log_error(f"配置路径更改异常：{str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log_error(f"配置路径更改异常：{str(e)}")
        raise HTTPException(status_code=500, detail=f"配置路径更改异常：{str(e)}")


@router.get("/switch/{model_name}")
async def switch_model(model_name: str):
    """切换模型（运行时切换，并持久化到存储模块）"""
    from src.config import ConfigManager

    log_info(f"收到模型切换请求：{model_name}")

    config_manager = get_config_manager()
    if config_manager is None:
        config_manager = ConfigManager()

    if model_name not in config_manager.get_all_models():
        log_warning(f"模型不存在：{model_name}")
        return {"error": f"模型不存在。可用模型：{config_manager.get_all_models()}"}

    # 切换模型并持久化到存储模块
    success = config_manager.switch_model(model_name, persist=True)

    if not success:
        log_error(f"切换模型失败：{model_name}")
        return {"error": f"切换模型失败：{model_name}"}

    model_config = config_manager.get_current_model_config()
    log_success(f"模型已切换：{model_name} -> {model_config.get('model', 'unknown')}")

    return {
        "message": f"已切换到模型：{model_name}",
        "model_name": model_config.get("model", "unknown"),
        "api_url": model_config.get("base_url", "unknown"),
        "current_model": config_manager.get_current_model()
    }


@router.get("/templates")
async def get_templates():
    """获取可用模板列表"""
    from src.template_parser import WordTemplateParser
    
    templates = WordTemplateParser.list_saved_templates()
    
    return {
        "templates": templates,
        "count": len(templates)
    }


@router.get("/templates/{template_id}")
async def get_template(template_id: str):
    """获取指定模板详情"""
    from src.template_parser import WordTemplateParser
    
    templates = WordTemplateParser.list_saved_templates()
    template_info = next((t for t in templates if t["template_id"] == template_id), None)
    
    if not template_info:
        raise HTTPException(status_code=404, detail=f"模板不存在：{template_id}")
    
    try:
        template = WordTemplateParser.load_template_json(template_info["file_path"])
        return {
            "id": template_id,
            "template": template.to_dict()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模板加载失败：{str(e)}")


@router.post("/templates/parse")
async def parse_template(file: UploadFile = File(...)):
    """
    解析 Word 模板文档，生成模板 JSON
    
    Args:
        file: 上传的模板文件
    """
    from src.template_parser import WordTemplateParser
    
    log_info(f"收到模板解析请求：{file.filename}")
    
    file_content = await file.read()
    if len(file_content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件大小不能超过 50MB")
    
    upload_dir = Path("./uploads")
    upload_dir.mkdir(exist_ok=True)
    
    safe_filename = Path(file.filename).name
    input_path = upload_dir / safe_filename
    with open(input_path, "wb") as f:
        f.write(file_content)
    
    try:
        from src.config import ConfigManager
        from openai import OpenAI
        
        config_manager = get_config_manager()
        if config_manager is None:
            config_manager = ConfigManager()
        
        model_config = config_manager.get_current_model_config()
        ai_client = None
        model_name = ""
        
        if model_config and model_config.get("api_key"):
            try:
                ai_client = OpenAI(
                    api_key=model_config["api_key"],
                    base_url=model_config["base_url"]
                )
                model_name = model_config["model"]
                log_info(f"模板解析将使用 AI 推断章节描述，模型：{model_name}")
            except Exception as e:
                log_error(f"AI 客户端初始化失败：{str(e)}")
        else:
            log_info("未配置 AI，跳过章节描述推断")
        
        parser = WordTemplateParser()
        template_def = parser.parse_template(str(input_path), ai_client=ai_client, model_name=model_name)
        
        templates_dir = WordTemplateParser.get_templates_dir()
        output_path = templates_dir / f"{template_def.template_id}.json"
        parser.save_template_json(str(output_path))
        
        log_success(f"模板解析完成：{template_def.name}")
        
        return {
            "message": "模板解析成功",
            "template": template_def.to_dict(),
            "saved_path": str(output_path)
        }
        
    except Exception as e:
        log_error(f"模板解析失败：{str(e)}")
        raise HTTPException(status_code=500, detail=f"模板解析失败：{str(e)}")


@router.post("/process-with-template-generative")
async def process_document_with_template_generative(
    files: List[UploadFile] = File(...),
    template_id: str = Form(None),
    template_json: str = Form(None)
):
    """
    使用模板处理文档（新策略：AI理解原文→按模板生成新内容）
    
    Args:
        files: 上传的源文档列表
        template_id: 模板 ID
        template_json: 自定义模板 JSON 字符串（可选）
    """
    from src.config import ConfigManager
    from src.parser import DocumentParser
    from src.template_parser import WordTemplateParser
    from src.ai_generative_processor import AIGenerativeTemplateProcessor
    from src.ai_generative_renderer import AIGenerativeRenderer
    from openai import OpenAI
    
    log_info(f"收到AI生成式模板处理请求：{len(files)} 个文件, 模板 ID: {template_id}")
    
    upload_dir = Path("./uploads")
    upload_dir.mkdir(exist_ok=True)
    
    input_paths = []
    for file in files:
        file_content = await file.read()
        if len(file_content) > 50 * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"文件 {file.filename} 大小不能超过 50MB")
        safe_filename = Path(file.filename).name
        input_path = upload_dir / safe_filename
        with open(input_path, "wb") as f:
            f.write(file_content)
        input_paths.append((safe_filename, input_path))
    
    config_manager = get_config_manager()
    if config_manager is None:
        config_manager = ConfigManager()
    
    current_model = config_manager.get_current_model()
    model_config = config_manager.get_current_model_config()
    
    if not model_config or not model_config.get("api_key"):
        for _, p in input_paths:
            if p.exists():
                p.unlink()
        raise HTTPException(status_code=500, detail="API 配置无效")
    
    try:
        client = OpenAI(
            api_key=model_config["api_key"],
            base_url=model_config["base_url"]
        )
        model_name = model_config["model"]
    except Exception as e:
        for _, p in input_paths:
            if p.exists():
                p.unlink()
        raise HTTPException(status_code=500, detail=f"AI 服务初始化失败：{str(e)}")
    
    try:
        if template_json:
            import json as json_module
            template_data = json_module.loads(template_json)
            from src.template import TemplateDefinition
            template = TemplateDefinition.from_dict(template_data)
            log_info(f"使用自定义模板：{template.name}")
        elif template_id:
            templates = WordTemplateParser.list_saved_templates()
            template_info = next((t for t in templates if t["template_id"] == template_id), None)
            
            if not template_info:
                for _, p in input_paths:
                    if p.exists():
                        p.unlink()
                raise HTTPException(status_code=404, detail=f"模板不存在：{template_id}")
            
            template = WordTemplateParser.load_template_json(template_info["file_path"])
            log_info(f"使用模板：{template.name}")
        else:
            for _, p in input_paths:
                if p.exists():
                    p.unlink()
            raise HTTPException(status_code=400, detail="未指定模板")
    except HTTPException:
        raise
    except Exception as e:
        for _, p in input_paths:
            if p.exists():
                p.unlink()
        raise HTTPException(status_code=500, detail=f"模板加载失败：{str(e)}")
    
    all_elements = []
    all_paragraphs = {}
    all_document_info = {}
    original_docs = []
    
    # 统计图表数量
    total_tables = 0
    total_images = 0

    for safe_filename, input_path in input_paths:
        parser = DocumentParser()
        elements, paragraphs, original_doc = parser.parse(str(input_path))
        
        if original_doc:
            original_docs.append(original_doc)
            # 统计该文档的图表数量
            total_tables += len(original_doc.tables)
            for rel in original_doc.part.rels.values():
                if "image" in rel.target_ref:
                    total_images += 1

        if len(input_paths) > 1:
            for key, value in paragraphs.items():
                new_key = safe_filename + "::" + key
                all_paragraphs[new_key] = value
            for elem in elements:
                all_elements.append((elem[0], safe_filename + "::" + elem[1], elem[2]))
        else:
            all_paragraphs.update(paragraphs)
            all_elements.extend(elements)

        document_info = extract_document_info(safe_filename, paragraphs, [elem[1] for elem in elements])
        all_document_info[safe_filename] = document_info
    
    source_content = {
        'elements': all_elements,
        'paragraphs': all_paragraphs
    }
    
    primary_doc_info = list(all_document_info.values())[0] if all_document_info else {}
    if len(all_document_info) > 1:
        doc_names = list(all_document_info.keys())
        primary_doc_info['title'] = f"合并文档（{', '.join(doc_names)}）"
        primary_doc_info['source_count'] = len(all_document_info)
    
    # 添加图表统计信息
    primary_doc_info['table_count'] = total_tables
    primary_doc_info['image_count'] = total_images
    
    log_info(f"源文档统计：{total_tables} 个表格, {total_images} 个图片")
    
    # 使用新的AI生成式处理器
    ai_processor = AIGenerativeTemplateProcessor(client, model_name)
    generated_content = ai_processor.process_with_template(
        source_content=source_content,
        template=template,
        source_docs_info=primary_doc_info
    )
    
    if not generated_content:
        for _, p in input_paths:
            if p.exists():
                p.unlink()
        raise HTTPException(status_code=500, detail="AI 生成失败")
    
    log_info(f"AI 生成内容成功，共 {len(generated_content['structure'])} 个元素")
    
    try:
        # 使用新的渲染器
        renderer = AIGenerativeRenderer()
        
        first_filename = input_paths[0][0]
        output_filename = f"generative_{first_filename}"
        output_path = upload_dir / output_filename
        
        renderer.render(generated_content, str(output_path))
        
        log_success(f"AI生成式模板处理完成：{len(files)} 个文件")
        
        from starlette.responses import Response
        
        with open(output_path, 'rb') as f:
            file_content = f.read()
        
        response = Response(
            content=file_content,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        
        # 使用 URL 编码处理中文文件名
        encoded_filename = quote(output_filename)
        response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_filename}"
        response.headers["X-Template-Name"] = quote(template.name)
        response.headers["X-Content-Elements"] = str(len(generated_content['structure']))
        
        return response
        
    except Exception as e:
        for _, p in input_paths:
            if p.exists():
                p.unlink()
        raise HTTPException(status_code=500, detail=f"文档渲染失败：{str(e)}")
