"""
WordAiKit - Word 文档智能处理服务
主程序入口
"""
import webbrowser
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from api.routes import router
from src.config import ConfigManager
from src.logger import log_info, log_error, log_success
from src.cache_manager import clear_cache_on_exit
import uvicorn
import atexit

# 初始化配置管理器
config_manager = ConfigManager()
# 将 ConfigManager 实例传递给 routes 模块
from api import routes
routes.set_config_manager(config_manager)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    log_info("Word 智能处理服务启动")

    # 延迟打开浏览器，确保服务已启动
    import asyncio
    asyncio.create_task(open_browser())

    yield
    # 关闭时执行（清理缓存资源）
    clear_cache_on_exit(keep_recent_uploads=0)
    log_info("Word 智能处理服务关闭")


# 创建 FastAPI 应用（不挂载根路径，避免与 API 路由冲突）
app = FastAPI(
    title="WordAiKit",
    description="Word 文档智能处理服务（支持文字润色、保留图片/表格/公式）",
    version="V0.1",
    lifespan=lifespan
)

# 注册 API 路由（添加 /api 前缀以避免与静态文件冲突）
app.include_router(router, prefix="/api")

# 挂载静态文件目录（提供前端界面，在 API 路由之后）
import os
static_path = os.path.join(os.path.dirname(__file__), "static")

# 根路由返回 index.html
@app.get("/")
async def serve_index():
    """返回前端主页"""
    index_path = os.path.join(static_path, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "WordAiKit API Service", "docs": "/docs"}

if os.path.exists(static_path):
    # 挂载静态文件到 /static 路径
    app.mount("/static", StaticFiles(directory=static_path), name="static")


async def open_browser():
    """延迟打开浏览器"""
    import asyncio
    await asyncio.sleep(1.5)  # 等待服务完全启动
    webbrowser.open("http://localhost:8000")


if __name__ == "__main__":
    atexit.register(clear_cache_on_exit, keep_recent_uploads=0)
    
    try:
        uvicorn.run(app, host="0.0.0.0", port=8000)
    except KeyboardInterrupt:
        print("\n👋 收到中断信号，程序即将退出...")
        # 缓存清理会在 atexit 中自动执行
