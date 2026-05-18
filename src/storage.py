"""
配置存储模块
负责安全地保存和加载用户配置（API Key 等敏感信息）
使用 base64 编码提供基本保护（生产环境建议使用更强的加密）
配置文件保存在用户指定的路径，不能保存在项目目录中
"""
import json
import base64
from pathlib import Path
from typing import Dict, Any, Optional


class ConfigStorage:
    """配置存储管理器"""
    
    # 默认存储位置（用于存储路径指针）
    DEFAULT_CONFIG_NAME = '.wordaikit_config.json'
    PATH_POINTER_NAME = '.wordaikit_path.json'
    
    def __init__(self, storage_file: str = None):
        """
        初始化配置存储器
        
        Args:
            storage_file: 存储文件路径，如果为None则自动查找或创建
        """
        # 项目根目录路径（用于验证）
        self.project_root = Path(__file__).parent.parent.resolve()
        
        # 获取默认存储目录（用户文档目录）
        import os
        if os.name == 'nt':  # Windows
            self.default_dir = Path(os.environ.get('USERPROFILE', '')) / 'Documents'
        else:  # Linux/Mac
            self.default_dir = Path.home() / 'Documents'
        
        # 备用目录（用户主目录）
        if os.name == 'nt':
            self.fallback_dir = Path(os.environ.get('USERPROFILE', ''))
        else:
            self.fallback_dir = Path.home()
        
        if storage_file:
            # 使用指定的路径
            self.storage_file = Path(storage_file)
        else:
            # 自动查找配置路径
            self.storage_file = self._find_storage_path()
        
        # 验证路径
        try:
            self._validate_storage_path()
        except ValueError as e:
            print(f"存储路径验证失败：{e}")
            self.storage_file = self.fallback_dir / self.DEFAULT_CONFIG_NAME
            print(f"使用备用路径：{self.storage_file}")
        
        self.configs = {}
        self._load_configs()
    
    def _get_default_storage_path(self) -> Path:
        """获取默认存储路径"""
        return self.default_dir / self.DEFAULT_CONFIG_NAME
    
    def _get_path_pointer_path(self) -> Path:
        """获取路径指针文件路径"""
        # 路径指针保存在备用目录（确保可访问）
        return self.fallback_dir / self.PATH_POINTER_NAME
    
    def _find_storage_path(self) -> Path:
        """
        查找配置存储路径
        优先级：
        1. 检查路径指针文件指向的位置
        2. 检查默认位置
        3. 使用默认位置创建新配置
        """
        # 1. 检查路径指针
        pointer_path = self._get_path_pointer_path()
        if pointer_path.exists():
            try:
                with open(pointer_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    saved_path = data.get('storage_path')
                    if saved_path:
                        path = Path(saved_path)
                        if path.exists() or path.parent.exists():
                            print(f"从路径指针加载配置路径：{path}")
                            return path
            except Exception as e:
                print(f"读取路径指针失败：{e}")
        
        # 2. 检查默认位置
        default_path = self._get_default_storage_path()
        if default_path.exists():
            print(f"使用默认配置路径：{default_path}")
            return default_path
        
        # 3. 使用默认位置
        print(f"创建新的配置路径：{default_path}")
        return default_path
    
    def _save_path_pointer(self):
        """保存路径指针"""
        try:
            pointer_path = self._get_path_pointer_path()
            with open(pointer_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'storage_path': str(self.storage_file),
                    'version': '1.0'
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存路径指针失败：{e}")
    
    def _validate_storage_path(self) -> bool:
        """
        验证当前 storage_file 路径是否合法
        
        Returns:
            bool: 路径是否合法
        
        Raises:
            ValueError: 如果路径不合法
        """
        return self._validate_storage_path_for_path(self.storage_file)
    
    def _validate_storage_path_for_path(self, path: Path) -> bool:
        """
        验证指定路径是否合法
        
        Args:
            path: 要验证的路径
            
        Returns:
            bool: 路径是否合法
        
        Raises:
            ValueError: 如果路径不合法
        """
        # 获取父目录的绝对路径（resolve 在文件不存在时会失败，所以先获取父目录）
        try:
            parent_path = path.parent.resolve()
            storage_path = parent_path / path.name
        except Exception:
            # 如果无法解析，使用绝对路径
            storage_path = path.absolute()
        
        # 检查是否在项目目录内
        try:
            storage_path.relative_to(self.project_root)
            # 如果在项目目录内，抛出异常（确保所有路径都转换为字符串）
            raise ValueError(
                f"配置文件不能保存在项目目录中！\n"
                f"项目目录：{str(self.project_root)}\n"
                f"当前路径：{str(storage_path)}\n"
                f"请选择其他目录（如：文档目录、桌面等）"
            )
        except ValueError as e:
            if "配置文件不能保存在项目目录中" in str(e):
                raise
            # 如果不在项目目录内，路径合法
            return True
    
    def _encode_value(self, value: str) -> str:
        """对敏感值进行 base64 编码"""
        return base64.b64encode(value.encode('utf-8')).decode('utf-8')
    
    def _decode_value(self, value: str) -> str:
        """对敏感值进行 base64 解码"""
        try:
            return base64.b64decode(value.encode('utf-8')).decode('utf-8')
        except Exception:
            return value
    
    def _load_configs(self):
        """从文件加载配置"""
        if not self.storage_file.exists():
            self.configs = {}
            return
        
        try:
            with open(self.storage_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.configs = data.get('configs', {})
        except Exception as e:
            print(f"加载配置失败：{e}")
            self.configs = {}
    
    def _save_configs(self):
        """保存配置到文件"""
        try:
            # 验证路径
            self._validate_storage_path()
            
            # 确保目录存在
            self.storage_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'version': '1.0',
                    'configs': self.configs
                }, f, indent=2, ensure_ascii=False)
            
            # 保存路径指针（记住当前配置位置）
            self._save_path_pointer()
            
        except ValueError as e:
            # 确保异常消息是纯字符串
            error_msg = str(e)
            print(f"保存配置失败：{error_msg}")
            raise ValueError(error_msg) from e
        except Exception as e:
            error_msg = str(e)
            print(f"保存配置失败：{error_msg}")
            raise
    
    def save_model_config(self, model_name: str, api_key: str, base_url: str, model: str) -> bool:
        """
        保存模型配置
        
        Args:
            model_name: 模型名称（如 deepseek, aliyun, kimi）
            api_key: API Key
            base_url: API 基础 URL
            model: 模型标识
            
        Returns:
            bool: 保存是否成功
        """
        try:
            self.configs[model_name] = {
                'api_key': self._encode_value(api_key),
                'base_url': base_url,
                'model': model
            }
            self._save_configs()
            return True
        except Exception as e:
            print(f"保存配置失败：{e}")
            return False
    
    def get_model_config(self, model_name: str) -> Optional[Dict[str, str]]:
        """
        获取模型配置
        
        Args:
            model_name: 模型名称
            
        Returns:
            模型配置字典，如果不存在则返回 None
        """
        config = self.configs.get(model_name)
        if not config:
            return None
        
        return {
            'api_key': self._decode_value(config.get('api_key', '')),
            'base_url': config.get('base_url', ''),
            'model': config.get('model', '')
        }
    
    def get_all_models(self) -> list:
        """获取所有已配置的模型列表"""
        return list(self.configs.keys())
    
    def delete_model_config(self, model_name: str) -> bool:
        """
        删除模型配置
        
        Args:
            model_name: 模型名称
            
        Returns:
            bool: 删除是否成功
        """
        if model_name in self.configs:
            del self.configs[model_name]
            self._save_configs()
            return True
        return False
    
    def has_config(self, model_name: str) -> bool:
        """检查模型是否已配置"""
        return model_name in self.configs and bool(self.configs[model_name].get('api_key'))
    
    def get_current_model(self) -> Optional[str]:
        """获取当前默认模型"""
        return self.configs.get('_current_model')
    
    def set_current_model(self, model_name: str) -> bool:
        """设置当前默认模型"""
        if model_name not in self.configs:
            return False
        self.configs['_current_model'] = model_name
        self._save_configs()
        return True
    
    def get_storage_path(self) -> str:
        """获取配置文件路径"""
        return str(self.storage_file)
    
    def change_storage_path(self, new_path: str) -> bool:
        """
        更改配置文件路径
        
        Args:
            new_path: 新的配置文件路径
            
        Returns:
            bool: 是否成功
        
        Raises:
            ValueError: 如果新路径不合法
        """
        new_path = Path(new_path)
        
        # 如果是目录，则使用默认文件名
        if new_path.is_dir():
            new_path = new_path / self.DEFAULT_CONFIG_NAME
        
        # 验证新路径
        old_path = self.storage_file
        self.storage_file = new_path
        try:
            self._validate_storage_path()
            
            # 迁移现有配置
            if old_path.exists():
                self._save_configs()
            
            # 保存路径指针
            self._save_path_pointer()
            
            return True
        except ValueError as e:
            # 恢复旧路径
            self.storage_file = old_path
            # 重新抛出异常，但确保异常消息是纯字符串
            error_msg = str(e)
            raise ValueError(error_msg) from e
