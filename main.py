"""
WordAiKit - Word 文档智能处理服务
主程序入口（Streamlit WebUI）
"""
import os
import sys
import webbrowser
import subprocess
import atexit

# 将项目根目录加入路径
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)

from src.cache_manager import clear_cache_on_exit
from src.logger import log_info


def open_browser():
    """延迟打开浏览器"""
    import time
    time.sleep(2)
    webbrowser.open("http://localhost:8501")


if __name__ == "__main__":
    atexit.register(clear_cache_on_exit, keep_recent_uploads=0)

    log_info("WordAiKit Streamlit 服务启动")

    # 延迟打开浏览器
    import threading
    t = threading.Thread(target=open_browser, daemon=True)
    t.start()

    # 启动 Streamlit
    streamlit_path = os.path.join(ROOT_DIR, ".venv", "Scripts", "streamlit.exe")
    if not os.path.exists(streamlit_path):
        streamlit_path = "streamlit"

    app_path = os.path.join(ROOT_DIR, "app_streamlit.py")

    # 写入用户目录的 credentials.toml 跳过首次邮件提示
    user_streamlit_dir = os.path.join(os.path.expanduser("~"), ".streamlit")
    os.makedirs(user_streamlit_dir, exist_ok=True)
    cred_path = os.path.join(user_streamlit_dir, "credentials.toml")
    if not os.path.exists(cred_path):
        with open(cred_path, "w", encoding="utf-8") as f:
            f.write('[general]\nemail = ""\n')

    try:
        subprocess.run(
            [streamlit_path, "run", app_path, "--server.port", "8501", "--server.headless", "true"],
            cwd=ROOT_DIR,
        )
    except KeyboardInterrupt:
        print("\n收到中断信号，程序即将退出...")
