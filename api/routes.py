"""
API 路由模块
提供自然语言润色接口与模型配置接口。
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
    提取文档信息，用于 AI 处理时的上下文
    """
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


@router.get("/")
async def root():
    """根路由"""
    from src.config import ConfigManager

    config_manager = get_config_manager()
    if config_manager is None:
        config_manager = ConfigManager()

    return {
        "message": "Word 智能处理服务（自然语言润色模式）",
        "current_model": config_manager.get_current_model(),
        "model_name": config_manager.get_current_model_config().get("model", "unknown"),
        "endpoint": "POST /process-natural",
        "mode": "自然语言润色",
        "可用模型": config_manager.get_all_models()
    }


@router.post("/process-natural")
async def process_document_natural(
    files: List[UploadFile] = File(...),
    user_prompt: str = Form("")
):
    """
    自然语言润色处理

    根据用户用自然语言描述的风格、结构等要求，对上传的 Word 文档进行重写，
    保留原文核心内容，并复用原文中的图片、表格、公式。
    """
    from src.config import ConfigManager
    from src.parser import DocumentParser
    from src.natural_language_processor import NaturalLanguageProcessor
    from src.ai_generative_renderer import AIGenerativeRenderer
    from openai import OpenAI

    log_info(f"收到自然语言润色请求：{len(files)} 个文件")

    if not user_prompt or not user_prompt.strip():
        raise HTTPException(status_code=400, detail="请输入润色要求")

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

    for safe_filename, input_path in input_paths:
        parser = DocumentParser()
        elements, paragraphs, _ = parser.parse(str(input_path))

        if len(input_paths) > 1:
            for key, value in paragraphs.items():
                new_key = safe_filename + "::" + key
                all_paragraphs[new_key] = value
            for elem in elements:
                all_elements.append((elem[0], safe_filename + "::" + elem[1], elem[2]))
        else:
            all_paragraphs.update(paragraphs)
            all_elements.extend(elements)

        current_order = [elem[1] for elem in elements]
        document_info = extract_document_info(safe_filename, paragraphs, current_order)
        all_document_info[safe_filename] = document_info

    primary_doc_info = list(all_document_info.values())[0] if all_document_info else {}
    if len(all_document_info) > 1:
        doc_names = list(all_document_info.keys())
        primary_doc_info['title'] = f"合并文档（{', '.join(doc_names)}）"
        primary_doc_info['source_count'] = len(all_document_info)

    source_content = {
        'elements': all_elements,
        'paragraphs': all_paragraphs
    }

    try:
        use_tool_calling = config_manager.get_use_tool_calling()
        processor = NaturalLanguageProcessor(client, model_name, use_tool_calling=use_tool_calling)
        generated_content = processor.process(
            source_content=source_content,
            document_info=primary_doc_info,
            user_prompt=user_prompt.strip()
        )
    except Exception as e:
        log_error(f"自然语言处理异常：{e}")
        generated_content = None

    if not generated_content:
        for _, p in input_paths:
            if p.exists():
                p.unlink()
        raise HTTPException(status_code=500, detail="AI 处理失败，无法生成润色后的文档")

    try:
        renderer = AIGenerativeRenderer()
        first_filename = input_paths[0][0]
        output_filename = f"nl_{first_filename}"
        output_path = upload_dir / output_filename
        renderer.render(generated_content, str(output_path))
    except Exception as e:
        log_error(f"文档渲染失败：{e}")
        for _, p in input_paths:
            if p.exists():
                p.unlink()
        raise HTTPException(status_code=500, detail=f"文档渲染失败：{str(e)}")

    log_success(f"自然语言润色完成：{len(files)} 个文件")

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

    encoded_filename = quote(output_filename)
    response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_filename}"
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
    """切换当前模型"""
    from src.config import ConfigManager

    log_info(f"收到模型切换请求：{model_name}")

    config_manager = get_config_manager()
    if config_manager is None:
        config_manager = ConfigManager()

    if model_name not in config_manager.get_all_models():
        log_warning(f"模型不存在：{model_name}")
        return {"error": f"模型不存在。可用模型：{config_manager.get_all_models()}"}

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
