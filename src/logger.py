"""
日志模块
负责将运行日志保存到项目目录
"""
import logging
import os
from pathlib import Path
from datetime import datetime


def setup_logger(log_dir: str = "./logs", log_file: str = "wordaikit.log") -> logging.Logger:
    """
    设置日志记录器
    
    Args:
        log_dir: 日志目录
        log_file: 日志文件名
        
    Returns:
        logging.Logger: 配置好的日志记录器
    """
    # 创建日志目录
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # 完整的日志文件路径
    full_log_path = log_path / log_file
    
    # 创建 logger
    logger = logging.getLogger("WordAiKit")
    logger.setLevel(logging.INFO)
    
    # 避免重复添加 handler
    if not logger.handlers:
        # 创建 FileHandler（追加模式）
        file_handler = logging.FileHandler(full_log_path, encoding='utf-8', mode='a')
        file_handler.setLevel(logging.INFO)
        
        # 创建格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        # 添加 handler
        logger.addHandler(file_handler)
    
    return logger


# 创建全局 logger 实例
logger = setup_logger()


def log_info(message: str):
    """记录 INFO 级别日志"""
    logger.info(message)
    print(f"[INFO] {message}")


def log_error(message: str):
    """记录 ERROR 级别日志"""
    logger.error(message)
    print(f"[ERROR] {message}")


def log_warning(message: str):
    """记录 WARNING 级别日志"""
    logger.warning(message)
    print(f"[WARNING] {message}")


def log_debug(message: str):
    """记录 DEBUG 级别日志"""
    logger.debug(message)
    print(f"[DEBUG] {message}")


def log_success(message: str):
    """记录成功日志（使用 INFO 级别）"""
    logger.info(f"✅ SUCCESS: {message}")
    print(f"[SUCCESS] {message}")
