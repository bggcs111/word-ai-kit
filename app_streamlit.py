"""
WordAiKit - Streamlit WebUI
自然语言润色模式：侧边栏任务管理 + 主聊天区
"""
import os
import sys
import json
import time
import threading
import tempfile
import atexit
import shutil
from pathlib import Path

import streamlit as st

# 将项目根目录加入路径，以便导入 src 模块
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

from src.config import ConfigManager
from src.parser import DocumentParser, DocumentParseStopped
from src.natural_language_processor import NaturalLanguageProcessor
from src.ai_generative_renderer import AIGenerativeRenderer
from src.logger import log_info, log_error
from openai import OpenAI

# Streamlit 内部控制异常：st.rerun() 抛 RerunException，右上角 Stop 抛 StopException。
# 两者都继承自 BaseException，需区分处理，避免把正常 rerun 误当成"停止"。
try:
    from streamlit.runtime.scriptrunner_utils.exceptions import StopException, RerunException
except ImportError:
    try:
        from streamlit.runtime.scriptrunner.exceptions import StopException, RerunException
    except ImportError:
        StopException = RerunException = BaseException

# ========== 生成文档本地留存（会话级） ==========
# 生成的 docx 文件存放在独立会话目录中，运行期间一直保存；
# 服务退出时整体删除（通过 atexit 清理）。最多保留最近 10 轮。
MAX_KEPT_GENERATED = 10  # 最多本地留存的最近生成轮数
SESSION_DIR = Path(tempfile.gettempdir()) / f"wordaikit_session_{os.getpid()}"


def _ensure_session_dir() -> Path:
    """确保会话目录存在并返回路径"""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return SESSION_DIR


def _cleanup_session_dir():
    """服务退出时删除会话目录（本地留存的生成文档）"""
    if SESSION_DIR.exists():
        try:
            shutil.rmtree(SESSION_DIR, ignore_errors=True)
            log_info(f"已清理会话生成目录：{SESSION_DIR}")
        except Exception as e:
            log_error(f"清理会话目录失败：{e}")


atexit.register(_cleanup_session_dir)


def _prune_generated_files():
    """对话历史中最多保留最近 MAX_KEPT_GENERATED 轮生成文档，删除更早的本地文件"""
    gen_records = [
        m for m in st.session_state.chat_messages
        if m.get("role") == "assistant" and m.get("download") and m.get("download", {}).get("path")
    ]
    # 按时间戳排序，旧的在前
    gen_records.sort(key=lambda m: m.get("ts", 0))
    # 超过上限的旧记录删除其本地文件
    while len(gen_records) > MAX_KEPT_GENERATED:
        oldest = gen_records.pop(0)
        path = oldest["download"].get("path")
        if path and os.path.exists(path):
            try:
                os.unlink(path)
            except Exception as e:
                log_error(f"删除旧生成文件失败：{path}，{e}")
        # 移除该消息的下载条目（保留文字记录）
        try:
            st.session_state.chat_messages.remove(oldest)
        except ValueError:
            pass

# ========== 页面配置 ==========
st.set_page_config(
    page_title="WordAiKit - 自然语言润色",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ========== 自定义样式 ==========
st.markdown("""
<style>
/* 主按钮 - 深灰色 */
.stButton > button[kind="primary"],
.stButton > button[data-testid="baseButton-primary"] {
    background-color: #2c3e50 !important;
    color: #ffffff !important;
    border: none !important;
}

.stButton > button[kind="primary"]:hover,
.stButton > button[data-testid="baseButton-primary"]:hover {
    background-color: #34495e !important;
    color: #ffffff !important;
}

/* 普通按钮 - 深灰色边框 */
.stButton > button:not([data-testid="baseButton-primary"]) {
    background-color: transparent !important;
    color: #2c3e50 !important;
    border: 1px solid #2c3e50 !important;
}

.stButton > button:not([data-testid="baseButton-primary"]):hover {
    background-color: #2c3e50 !important;
    color: #ffffff !important;
    border: 1px solid #2c3e50 !important;
}

/* 下载按钮 - 深灰色 */
.stDownloadButton > button {
    background-color: #2c3e50 !important;
    color: #ffffff !important;
    border: none !important;
}

.stDownloadButton > button:hover {
    background-color: #34495e !important;
    color: #ffffff !important;
}

/* 成功/错误消息 - 使用柔和颜色 */
.stSuccess {
    background-color: #e8f5e9 !important;
    color: #2e7d32 !important;
    border-left: 4px solid #4caf50 !important;
}

.stError {
    background-color: #ffebee !important;
    color: #c62828 !important;
    border-left: 4px solid #ef5350 !important;
}

.stWarning {
    background-color: #fff3e0 !important;
    color: #e65100 !important;
    border-left: 4px solid #ff9800 !important;
}
</style>
""", unsafe_allow_html=True)

# ========== 常量 ==========
TASKS_FILE = ROOT_DIR / ".tasks.json"
QUICK_PROMPTS = [
    "请用学术风格重写，逻辑严密，保留所有图表公式。",
    "请用通俗易懂的科普风格重写，保留所有图表公式。",
    "请重新组织文章结构，增加小标题，使层次更清晰，保留所有图表公式。",
    "请对原文进行精简，去除冗余表达，保留核心内容和所有图表公式。",
]


# ========== 任务持久化 ==========
def load_tasks():
    if TASKS_FILE.exists():
        try:
            return json.loads(TASKS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return [{"id": "task_1", "name": "新任务", "prompt": ""}]


def save_tasks(tasks):
    TASKS_FILE.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")


def get_current_task(tasks, task_id):
    for t in tasks:
        if t["id"] == task_id:
            return t
    return tasks[0] if tasks else None


# ========== 初始化 session_state ==========
if "tasks" not in st.session_state:
    st.session_state.tasks = load_tasks()
if "current_task_id" not in st.session_state:
    st.session_state.current_task_id = st.session_state.tasks[0]["id"]
# 按任务归档历史：task_histories[tid] -> 该任务的聊天消息列表
if "task_histories" not in st.session_state:
    st.session_state.task_histories = {}
# 当前任务历史就是当前选中的任务
_cur_tid = st.session_state.current_task_id
st.session_state.task_histories.setdefault(_cur_tid, [])
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = st.session_state.task_histories[_cur_tid]
if "config_manager" not in st.session_state:
    st.session_state.config_manager = ConfigManager()

# 处理状态：后台线程运行解析+AI生成，主脚本轮询等待，便于右上角 Stop 中断
if "_processing_active" not in st.session_state:
    st.session_state["_processing_active"] = False
if "_processing_thread" not in st.session_state:
    st.session_state["_processing_thread"] = None
if "_processing_stop" not in st.session_state:
    st.session_state["_processing_stop"] = None
if "_processing_holder" not in st.session_state:
    st.session_state["_processing_holder"] = None


# ========== 文档处理逻辑 ==========
def process_documents(uploaded_files, user_prompt, stop_event=None, config_manager=None):
    """处理文档并返回 (成功, 结果数据或错误信息)。

    stop_event: 可选 threading.Event，用户点击停止时置位，解析阶段会尽快中止。
    config_manager: 可选，传入后不在子线程中访问 st.session_state。
    """
    config_manager = config_manager or st.session_state.config_manager
    MAX_TEXT_CHARS = config_manager.get_max_text_chars()  # 单次处理正文最长文本限制（可配置）
    try:
        all_elements = []
        all_paragraphs = {}
        all_doc_info = {}

        for uploaded_file in uploaded_files:
            if stop_event is not None and stop_event.is_set():
                return False, "处理已停止"
            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_path = tmp.name

            try:
                parser = DocumentParser()
                elements, paragraphs, _ = parser.parse(tmp_path, stop_event=stop_event)

                # 单文件正文超过上限则提示分开处理
                total_chars = 0
                for p in paragraphs.values():
                    total_chars += len(str(p[0] if isinstance(p, tuple) and p else p))
                if total_chars > MAX_TEXT_CHARS:
                    return False, (
                        f"文档《{uploaded_file.name}》正文约 {total_chars} 字，"
                        f"超过单次处理上限（{MAX_TEXT_CHARS} 字）。请将文档拆分为多份后分开处理。"
                    )

                safe_filename = uploaded_file.name
                if len(uploaded_files) > 1:
                    for key, value in paragraphs.items():
                        all_paragraphs[safe_filename + "::" + key] = value
                    for elem in elements:
                        all_elements.append((elem[0], safe_filename + "::" + elem[1], elem[2]))
                else:
                    all_paragraphs.update(paragraphs)
                    all_elements.extend(elements)

                from api.routes import extract_document_info
                current_order = [elem[1] for elem in elements]
                doc_info = extract_document_info(safe_filename, paragraphs, current_order)
                all_doc_info[safe_filename] = doc_info
            finally:
                os.unlink(tmp_path)

        primary_doc_info = list(all_doc_info.values())[0] if all_doc_info else {}
        if len(all_doc_info) > 1:
            doc_names = list(all_doc_info.keys())
            primary_doc_info["title"] = f"合并文档（{', '.join(doc_names)}）"

        source_content = {
            "elements": all_elements,
            "paragraphs": all_paragraphs,
        }

        # 多份文档合并后，累计正文总长同样受单次处理上限约束
        total_chars = 0
        for p in all_paragraphs.values():
            total_chars += len(str(p[0] if isinstance(p, tuple) and p else p))
        if total_chars > MAX_TEXT_CHARS:
            return False, (
                f"本次文档正文合计约 {total_chars} 字，超过单次处理上限（{MAX_TEXT_CHARS} 字）。"
                f"请将文档拆分后再分开处理。"
            )

        model_config = config_manager.get_current_model_config()

        if not model_config or not model_config.get("api_key"):
            return False, "API 配置无效，请在侧边栏配置 API Key"

        client = OpenAI(
            api_key=model_config["api_key"],
            base_url=model_config["base_url"],
        )
        model_name = model_config["model"]
        use_tool_calling = config_manager.get_use_tool_calling()

        processor = NaturalLanguageProcessor(client, model_name, use_tool_calling=use_tool_calling)
        if stop_event is not None and stop_event.is_set():
            return False, "处理已停止"
        generated_content = processor.process(
            source_content=source_content,
            document_info=primary_doc_info,
            user_prompt=user_prompt.strip(),
        )

        if not generated_content:
            return False, "AI 处理失败，无法生成润色后的文档"

        renderer = AIGenerativeRenderer()
        if stop_event is not None and stop_event.is_set():
            return False, "处理已停止"
        # 生成文档写入会话目录，运行期间一直保存，服务退出时整体删除
        sess_dir = _ensure_session_dir()
        ts_str = time.strftime("%Y%m%d_%H%M%S")
        output_filename = f"nl_{ts_str}_{uploaded_files[0].name}"
        output_path = sess_dir / output_filename
        renderer.render(generated_content, str(output_path))

        with open(output_path, "rb") as f:
            file_data = f.read()

        return True, {
            "data": file_data,
            "path": str(output_path),
            "filename": output_filename,
            "element_count": len(generated_content.get("structure", [])),
        }

    except DocumentParseStopped:
        return False, "处理已停止"
    except Exception as e:
        log_error(f"处理异常：{e}")
        return False, str(e)


def _run_processing_thread(uploaded_files, user_prompt, stop_event, holder, config_manager):
    """后台线程执行文档处理，结果写入 holder["result"]，避免在子线程修改 st.session_state。"""
    try:
        success, result = process_documents(
            uploaded_files, user_prompt, stop_event=stop_event, config_manager=config_manager
        )
        holder["result"] = (success, result)
    except Exception as e:
        log_error(f"后台处理线程异常：{e}")
        holder["result"] = (False, str(e))


# ========== 侧边栏 ==========
def render_sidebar():
    st.sidebar.title(" WordAiKit")

    st.sidebar.markdown("### 任务列表")

    # === 在 widget 渲染前，处理 session_state 同步（避免 widget 实例化后修改其 key）===
    # 新建任务后清空名称输入框
    if st.session_state.get("_clear_new_task_input"):
        st.session_state["new_task_name_input"] = ""
        st.session_state["_clear_new_task_input"] = False

    # 切换任务 / 保存重命名后，同步重命名输入框
    if st.session_state.get("_sync_rename_input"):
        cur = get_current_task(st.session_state.tasks, st.session_state.current_task_id)
        st.session_state["task_name_input"] = cur["name"] if cur else ""
        st.session_state["_sync_rename_input"] = False

    # 重置重命名输入框
    if st.session_state.get("_reset_rename_input"):
        cur = get_current_task(st.session_state.tasks, st.session_state.current_task_id)
        st.session_state["task_name_input"] = cur["name"] if cur else ""
        st.session_state["_reset_rename_input"] = False

    # 新建任务（先命名再创建）
    with st.sidebar.expander("➕ 新建任务", expanded=False):
        new_task_name = st.text_input(
            "任务名称",
            value="",
            placeholder="请输入任务名称",
            key="new_task_name_input",
            label_visibility="collapsed",
        )
        if st.button("确定新建", use_container_width=True, key="btn_create_task"):
            name = new_task_name.strip() or f"新任务 {len(st.session_state.tasks) + 1}"
            new_id = f"task_{int(time.time() * 1000)}"
            st.session_state.tasks.insert(0, {"id": new_id, "name": name, "prompt": ""})
            st.session_state.current_task_id = new_id
            st.session_state.task_histories[new_id] = []
            st.session_state.chat_messages = st.session_state.task_histories[new_id]
            save_tasks(st.session_state.tasks)
            # 设置标志，rerun 后在 widget 渲染前清空输入框
            st.session_state["_clear_new_task_input"] = True
            st.session_state["_sync_rename_input"] = True
            st.rerun()

    # 任务选择下拉框
    task_ids = [t["id"] for t in st.session_state.tasks]
    current_idx = task_ids.index(st.session_state.current_task_id) if st.session_state.current_task_id in task_ids else 0

    def task_label(tid):
        for t in st.session_state.tasks:
            if t["id"] == tid:
                return t["name"]
        return tid

    selected = st.sidebar.selectbox(
        "选择任务",
        options=task_ids,
        index=current_idx,
        format_func=task_label,
        label_visibility="collapsed",
        key="task_selector",
    )
    if selected != st.session_state.current_task_id:
        # 将当前聊天历史归档到旧任务，再载入新任务的历史
        old_tid = st.session_state.current_task_id
        st.session_state.task_histories[old_tid] = st.session_state.chat_messages
        st.session_state.current_task_id = selected
        st.session_state.task_histories.setdefault(selected, [])
        st.session_state.chat_messages = st.session_state.task_histories[selected]
        st.session_state["_sync_rename_input"] = True
        # 切换任务时复用该任务保存的提示词（若存在），省去重复输入
        st.session_state["_apply_task_prompt"] = True
        st.rerun()

    # 删除任务：小按钮 + 二次确认，避免误删
    if len(st.session_state.tasks) > 1:
        st.sidebar.markdown("---")
        del_cols = st.sidebar.columns([1, 3])
        with del_cols[0]:
            if st.button("🗑️", key="btn_del_task_small", help="删除当前任务", use_container_width=True):
                st.session_state["_confirm_delete_task"] = True
                st.rerun()

        if st.session_state.get("_confirm_delete_task"):
            st.sidebar.warning("确认删除当前任务？此操作不可撤销。")
            conf_cols = st.sidebar.columns(2)
            with conf_cols[0]:
                if st.button("确认删除", key="btn_del_confirm", use_container_width=True):
                    del_tid = st.session_state.current_task_id
                    st.session_state.tasks = [t for t in st.session_state.tasks if t["id"] != del_tid]
                    st.session_state.current_task_id = st.session_state.tasks[0]["id"]
                    # 清除被删任务的归档历史，并载入新当前任务的历史
                    st.session_state.task_histories.pop(del_tid, None)
                    st.session_state.task_histories.setdefault(st.session_state.current_task_id, [])
                    st.session_state.chat_messages = st.session_state.task_histories[st.session_state.current_task_id]
                    save_tasks(st.session_state.tasks)
                    st.session_state["_confirm_delete_task"] = False
                    st.session_state["_sync_rename_input"] = True
                    st.rerun()
            with conf_cols[1]:
                if st.button("取消", key="btn_del_cancel", use_container_width=True):
                    st.session_state["_confirm_delete_task"] = False
                    st.rerun()

    st.sidebar.divider()

    # 重命名任务（使用保存按钮，避免每次 rerun 自动覆盖）
    current_task = get_current_task(st.session_state.tasks, st.session_state.current_task_id)
    current_name = current_task["name"] if current_task else "新任务"

    rename_input = st.sidebar.text_input(
        "任务名称",
        key="task_name_input",
    )

    col_rename, col_reset = st.sidebar.columns(2)
    with col_rename:
        if st.button("保存重命名", use_container_width=True, key="btn_save_rename"):
            new_name = rename_input.strip()
            if new_name and current_task and new_name != current_task["name"]:
                current_task["name"] = new_name
                save_tasks(st.session_state.tasks)
                st.sidebar.success("已重命名")
                st.session_state["_sync_rename_input"] = True
                st.rerun()
    with col_reset:
        if st.button("重置", use_container_width=True, key="btn_reset_name"):
            st.session_state["_reset_rename_input"] = True
            st.rerun()

    st.sidebar.divider()

    # 模型选择
    st.sidebar.markdown("### ⚙️ 模型配置")
    config_manager = st.session_state.config_manager
    current_model = config_manager.get_current_model()
    all_models = config_manager.get_all_models()

    selected_model = st.sidebar.selectbox(
        "选择模型",
        options=all_models,
        index=all_models.index(current_model) if current_model in all_models else 0,
    )
    if selected_model != current_model:
        config_manager.switch_model(selected_model, persist=True)
        st.rerun()

    # API 详细配置
    with st.sidebar.expander("API 详细配置", expanded=False):
        model_cfg = config_manager.get_current_model_config()
        api_key = st.text_input("API Key", value=model_cfg.get("api_key", ""), type="password", key="cfg_api_key")
        base_url = st.text_input("Base URL", value=model_cfg.get("base_url", ""), key="cfg_base_url")
        model_name_input = st.text_input("模型名称", value=model_cfg.get("model", ""), key="cfg_model_name")

        if st.button("保存配置", use_container_width=True, key="btn_save_cfg"):
            config_manager.save_model_config(selected_model, api_key, base_url, model_name_input)
            st.sidebar.success("配置已保存")

        if st.button("测试配置", use_container_width=True, key="btn_test_cfg"):
            with st.spinner("正在测试..."):
                try:
                    client = OpenAI(api_key=api_key, base_url=base_url)
                    resp = client.chat.completions.create(
                        model=model_name_input,
                        messages=[{"role": "user", "content": "请回复'测试通过'"}],
                        max_tokens=10,
                    )
                    st.sidebar.success(f"测试成功：{resp.choices[0].message.content}")
                except Exception as e:
                    st.sidebar.error(f"测试失败：{e}")

    # 处理模式
    st.sidebar.divider()
    st.sidebar.markdown("### 🔧 处理模式")
    use_tool = st.sidebar.toggle(
        "工具调用模式",
        value=config_manager.get_use_tool_calling(),
        help="启用后 AI 可主动查询图表上下文，更准确地放置图表",
        key="toggle_tool_calling",
    )
    if use_tool != config_manager.get_use_tool_calling():
        config_manager.set_use_tool_calling(use_tool)

    # 单次处理正文最长文本限制
    max_chars = st.sidebar.number_input(
        "单次处理上限（字）",
        min_value=1000,
        max_value=500000,
        value=int(config_manager.get_max_text_chars()),
        step=5000,
        help="单次处理的文档正文最长字数，超过后提示拆分文档分别处理",
        key="max_text_chars_input",
    )
    if max_chars != config_manager.get_max_text_chars():
        config_manager.set_max_text_chars(max_chars)

    # 存储路径
    with st.sidebar.expander("存储路径", expanded=False):
        storage_path = st.text_input("配置文件路径", value=config_manager.get_storage_path(), key="cfg_storage_path")
        if st.button("保存路径", use_container_width=True, key="btn_save_path"):
            config_manager.change_storage_path(storage_path)
            st.sidebar.success("路径已更新")

    # 仓库链接
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "<div style='text-align:center; color:#888; font-size:0.8rem'>"
        "<a href='https://github.com/bggcs111/word-ai-kit.git' target='_blank'>"
        "🔗 WordAiKit 仓库</a></div>",
        unsafe_allow_html=True,
    )


# ========== 主聊天区 ==========
def render_main():
    current_task = get_current_task(st.session_state.tasks, st.session_state.current_task_id)

    # 顶部状态栏
    col1, col2 = st.columns([4, 1])
    with col1:
        st.markdown(f"### {current_task['name'] if current_task else '新任务'}")
    with col2:
        st.markdown("🟢 服务正常")

    # 渲染聊天历史
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("files"):
                for f in msg["files"]:
                    st.caption(f"📄 {f}")
            if msg.get("download"):
                st.download_button(
                    label="⬇️ 下载处理后的文档",
                    data=msg["download"]["data"],
                    file_name=msg["download"]["filename"],
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                    key=f"dl_{msg.get('ts', 0)}",
                )

    # === 处理状态：如果正在后台处理，只显示 spinner，不渲染输入区 ===
    if st.session_state["_processing_active"]:
        thread = st.session_state["_processing_thread"]
        stop_evt = st.session_state["_processing_stop"]
        holder = st.session_state["_processing_holder"]
        with st.chat_message("assistant"):
            spinner_ph = st.empty()
            with spinner_ph:
                st.spinner("正在处理文档（解析 + AI 生成）...")
            try:
                while thread is not None and thread.is_alive():
                    time.sleep(0.3)
                    # 定期提供 Streamlit 检查点，使右上角 Stop 可被响应
                    with spinner_ph:
                        st.spinner("正在处理文档（解析 + AI 生成）...")
            except StopException:
                if stop_evt is not None:
                    stop_evt.set()
                raise

        # 线程已结束，取出处理结果并归档到聊天历史
        st.session_state["_processing_active"] = False
        st.session_state["_processing_thread"] = None
        st.session_state["_processing_stop"] = None
        st.session_state["_processing_holder"] = None
        success, result = holder.get("result", (False, "处理未完成"))
        if success:
            st.session_state.chat_messages.append({
                "role": "assistant",
                "content": f"文档已处理完成，共生成 {result['element_count']} 个元素。",
                "download": {
                    "data": result["data"],
                    "path": result.get("path"),
                    "filename": result["filename"],
                },
                "ts": int(time.time() * 1000),
            })
            _prune_generated_files()
        else:
            st.session_state.chat_messages.append({
                "role": "assistant",
                "content": f"❌ 处理失败：{result}",
                "ts": int(time.time() * 1000),
            })
        st.rerun()
        return  # st.rerun() 已结束脚本，此行不会执行，仅作语义提示

    # === 未在处理时：显示欢迎页和输入区 ===
    # 欢迎页 / 快捷按钮
    if not st.session_state.chat_messages:
        st.markdown("---")
        st.markdown("### 🚀 快捷开始")
        st.markdown("上传 Word 文档，用自然语言描述你想要的风格、结构或内容要求。")
        st.markdown("系统会保留原文核心内容与图片、表格、公式，重新生成连贯文章。")
        cols = st.columns(2)
        for i, prompt in enumerate(QUICK_PROMPTS):
            with cols[i % 2]:
                if st.button(prompt, key=f"quick_{i}", use_container_width=True):
                    st.session_state["pending_prompt"] = prompt
                    st.rerun()

    # 输入区
    st.markdown("---")

    uploaded_files = st.file_uploader(
        "上传 Word 文档（.docx）",
        type=["docx"],
        accept_multiple_files=True,
        key="file_uploader",
    )

    # 提示词输入：优先使用 pending_prompt（来自快捷按钮），否则用任务保存的提示词
    pending = st.session_state.pop("pending_prompt", None)
    if pending:
        st.session_state["last_prompt"] = pending
        st.session_state["prompt_input"] = pending  # 同步到输入框缓存，确保点击快捷词立即生效

    # 切换任务后，将该任务保存的提示词应用到输入框，实现同一任务复用、省去重复输入
    if st.session_state.pop("_apply_task_prompt", False):
        task_prompt = (current_task.get("prompt") if current_task else "") or ""
        st.session_state["last_prompt"] = task_prompt
        st.session_state["prompt_input"] = task_prompt

    default_val = st.session_state.get("last_prompt") or (current_task.get("prompt") if current_task else "")

    # 使用 text_area 替代 chat_input，更稳定
    user_prompt = st.text_area(
        "润色要求",
        value=default_val,
        placeholder="输入你的要求，例如：请用正式的技术文档风格重写，分三个章节...",
        height=100,
        key="prompt_input",
        label_visibility="collapsed",
    )

    # 保存当前输入到 session_state
    if user_prompt:
        st.session_state["last_prompt"] = user_prompt

    prompt_to_use = user_prompt

    # 处理按钮
    col_send, col_clear = st.columns([5, 1])
    with col_send:
        send_clicked = st.button("🚀 开始处理", use_container_width=True, type="primary", key="btn_send")
    with col_clear:
        clear_clicked = st.button("🗑️ 清空", use_container_width=True, key="btn_clear")

    if clear_clicked:
        # 清空当前任务的历史（同步到归档，保持同一列表引用）
        st.session_state.task_histories[st.session_state.current_task_id] = []
        st.session_state.chat_messages = st.session_state.task_histories[st.session_state.current_task_id]
        st.rerun()

    if send_clicked:
        if not uploaded_files:
            st.warning("请先上传至少一个 .docx 文件")
            st.stop()
        if not prompt_to_use:
            st.warning("请输入润色要求或使用快捷按钮")
            st.stop()

        # 保存提示词到当前任务
        if current_task:
            current_task["prompt"] = prompt_to_use
            save_tasks(st.session_state.tasks)

        # 添加用户消息
        file_names = [f.name for f in uploaded_files]
        st.session_state.chat_messages.append({
            "role": "user",
            "content": prompt_to_use,
            "files": file_names,
            "ts": int(time.time() * 1000),
        })

        # 启动后台线程处理文档，主脚本轮询等待，使右上角 Stop 能中断等待并取消处理
        stop_evt = threading.Event()
        holder = {}
        config_manager = st.session_state.config_manager
        st.session_state["_processing_stop"] = stop_evt
        st.session_state["_processing_holder"] = holder
        st.session_state["_processing_active"] = True
        thread = threading.Thread(
            target=_run_processing_thread,
            args=(uploaded_files, prompt_to_use, stop_evt, holder, config_manager),
            daemon=True,
        )
        st.session_state["_processing_thread"] = thread
        thread.start()
        st.rerun()


# ========== 主入口 ==========
def main():
    render_sidebar()
    render_main()


if __name__ == "__main__":
    main()
