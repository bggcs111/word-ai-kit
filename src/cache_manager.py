"""
缓存管理模块
负责管理程序运行过程中产生的临时文件和缓存
"""
import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional
from src.logger import log_info, log_warning, log_error


class CacheManager:
    """缓存管理器"""
    
    # 需要清理的目录和文件模式
    CACHE_PATTERNS = {
        'uploads': './uploads',           # 上传的文件
        'logs': './logs/*.log.old',       # 旧日志文件
        'temp': tempfile.gettempdir(),    # 系统临时目录中的相关文件
    }
    
    def __init__(self):
        """初始化缓存管理器"""
        self.project_root = Path(__file__).parent.parent
        
    def get_uploads_dir(self) -> Path:
        """获取上传目录"""
        return self.project_root / "uploads"
    
    def get_logs_dir(self) -> Path:
        """获取日志目录"""
        return self.project_root / "logs"
    
    def list_cache_files(self) -> dict:
        """
        列出所有缓存文件
        
        Returns:
            dict: 包含各类缓存文件信息的字典
        """
        cache_info = {
            'uploads': [],
            'logs': [],
            'temp': [],
            'total_size': 0
        }
        
        # 检查上传目录
        uploads_dir = self.get_uploads_dir()
        if uploads_dir.exists():
            for file_path in uploads_dir.iterdir():
                if file_path.is_file():
                    file_size = file_path.stat().st_size
                    cache_info['uploads'].append({
                        'path': str(file_path),
                        'size': file_size,
                        'name': file_path.name
                    })
                    cache_info['total_size'] += file_size
        
        # 检查日志目录中的旧日志
        logs_dir = self.get_logs_dir()
        if logs_dir.exists():
            for file_path in logs_dir.glob('*.log.old'):
                if file_path.is_file():
                    file_size = file_path.stat().st_size
                    cache_info['logs'].append({
                        'path': str(file_path),
                        'size': file_size,
                        'name': file_path.name
                    })
                    cache_info['total_size'] += file_size
        
        return cache_info
    
    def clear_uploads(self, keep_recent: int = 0) -> int:
        """
        清理上传目录
        
        Args:
            keep_recent: 保留最近几个文件（0表示全部删除）
            
        Returns:
            int: 清理的文件数量
        """
        uploads_dir = self.get_uploads_dir()
        if not uploads_dir.exists():
            return 0
        
        files = sorted(
            [f for f in uploads_dir.iterdir() if f.is_file()],
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        
        count = 0
        for file_path in files[keep_recent:]:
            try:
                file_path.unlink()
                log_info(f"已删除上传文件：{file_path.name}")
                count += 1
            except Exception as e:
                log_error(f"删除文件失败 {file_path}: {e}")
        
        return count
    
    def clear_old_logs(self, days: int = 7) -> int:
        """
        清理旧日志文件
        
        Args:
            days: 清理多少天前的日志（默认7天）
            
        Returns:
            int: 清理的文件数量
        """
        import time
        
        logs_dir = self.get_logs_dir()
        if not logs_dir.exists():
            return 0
        
        current_time = time.time()
        cutoff_time = current_time - (days * 24 * 60 * 60)
        
        count = 0
        for file_path in logs_dir.glob('*.log.old'):
            if file_path.is_file():
                try:
                    file_mtime = file_path.stat().st_mtime
                    if file_mtime < cutoff_time:
                        file_path.unlink()
                        log_info(f"已删除旧日志：{file_path.name}")
                        count += 1
                except Exception as e:
                    log_error(f"删除日志失败 {file_path}: {e}")
        
        return count
    
    def clear_temp_files(self) -> int:
        """
        清理系统临时目录中的相关临时文件
        
        Returns:
            int: 清理的文件数量
        """
        temp_dir = Path(tempfile.gettempdir())
        count = 0
        
        # 清理以 wordaikit 或 tmp 开头的临时文件
        patterns = ['wordaikit*', 'tmp*', '*.tmp']
        
        for pattern in patterns:
            for file_path in temp_dir.glob(pattern):
                if file_path.is_file():
                    try:
                        file_path.unlink()
                        log_info(f"已删除临时文件：{file_path.name}")
                        count += 1
                    except Exception:
                        # 忽略删除失败的文件（可能正在使用）
                        pass
        
        return count
    
    def clear_all_cache(self, keep_recent_uploads: int = 0) -> dict:
        """
        清理所有缓存
        
        Args:
            keep_recent_uploads: 保留最近几个上传文件
            
        Returns:
            dict: 清理结果统计
        """
        log_info("开始清理缓存...")
        
        result = {
            'uploads_cleared': 0,
            'logs_cleared': 0,
            'temp_cleared': 0,
            'total_cleared': 0
        }
        
        # 清理上传文件
        result['uploads_cleared'] = self.clear_uploads(keep_recent=keep_recent_uploads)
        
        # 清理旧日志
        result['logs_cleared'] = self.clear_old_logs()
        
        # 清理临时文件
        result['temp_cleared'] = self.clear_temp_files()
        
        result['total_cleared'] = (
            result['uploads_cleared'] + 
            result['logs_cleared'] + 
            result['temp_cleared']
        )
        
        log_info(f"缓存清理完成：共清理 {result['total_cleared']} 个文件")
        return result
    
    def get_cache_summary(self) -> str:
        """
        获取缓存摘要信息
        
        Returns:
            str: 格式化的缓存信息字符串
        """
        cache_info = self.list_cache_files()
        
        # 格式化文件大小
        def format_size(size_bytes):
            if size_bytes < 1024:
                return f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                return f"{size_bytes / 1024:.2f} KB"
            else:
                return f"{size_bytes / (1024 * 1024):.2f} MB"
        
        summary = []
        summary.append("=" * 50)
        summary.append("缓存文件统计")
        summary.append("=" * 50)
        
        summary.append(f"\n📁 上传文件 ({len(cache_info['uploads'])} 个):")
        for file_info in cache_info['uploads'][:5]:  # 只显示前5个
            summary.append(f"  - {file_info['name']} ({format_size(file_info['size'])})")
        if len(cache_info['uploads']) > 5:
            summary.append(f"  ... 还有 {len(cache_info['uploads']) - 5} 个文件")
        
        summary.append(f"\n📝 旧日志文件 ({len(cache_info['logs'])} 个)")
        
        summary.append(f"\n💾 总占用空间: {format_size(cache_info['total_size'])}")
        summary.append("=" * 50)
        
        return "\n".join(summary)


# 全局缓存管理器实例
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器实例（单例模式）"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


def clear_cache_on_exit(keep_recent_uploads: int = 0):
    """
    程序退出时清理缓存的便捷函数
    
    Args:
        keep_recent_uploads: 保留最近几个上传文件（默认0，全部删除）
    """
    manager = get_cache_manager()
    result = manager.clear_all_cache(keep_recent_uploads=keep_recent_uploads)
