"""
配置管理模块
负责加载和管理 API 配置信息
配置通过 Web UI 保存到 .wordaikit_config.json
"""
from typing import Dict


# 硬编码的模型配置（默认配置）
MODEL_CONFIGS = {
    "deepseek": {
        "api_key": "",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat"
    },
    "aliyun": {
        "api_key": "",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3.5-plus"
    },
    "kimi": {
        "api_key": "",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "kimi-k2.5"
    },
    "ollama": {
        "api_key": "ollama",
        "base_url": "http://localhost:11434/v1",
        "model": "qwen2.5:7b"
    },
    "lmstudio": {
        "api_key": "lmstudio",
        "base_url": "http://localhost:1234/v1",
        "model": "local-model"
    }
}


class ConfigManager:
    """配置管理器（单例模式）"""

    _instance = None
    _initialized = False

    def __new__(cls, storage_path: str = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, storage_path: str = None):
        """初始化配置管理器"""
        if ConfigManager._initialized:
            return

        self.api_keys = {}
        self.storage = None

        # 使用存储模块加载配置
        try:
            from src.storage import ConfigStorage
            self.storage = ConfigStorage(storage_path)
            self._load_from_storage()
        except Exception:
            pass

        # 设置默认模型
        self.current_model = "deepseek"
        if self.storage and self.storage.get_current_model():
            self.current_model = self.storage.get_current_model()

        self._build_models_config()
        ConfigManager._initialized = True

    def _load_from_storage(self):
        """从存储模块加载配置"""
        if not self.storage:
            return

        for model_name in MODEL_CONFIGS.keys():
            config = self.storage.get_model_config(model_name)
            if config and config.get('api_key'):
                self.api_keys[model_name] = config['api_key']
                # 更新默认配置中的 URL 和 model
                MODEL_CONFIGS[model_name]['base_url'] = config.get('base_url', MODEL_CONFIGS[model_name]['base_url'])
                MODEL_CONFIGS[model_name]['model'] = config.get('model', MODEL_CONFIGS[model_name]['model'])

    def _build_models_config(self):
        """构建模型配置（将 API Key 注入到硬编码的配置中）"""
        self.models_config = {}

        for model_name, base_config in MODEL_CONFIGS.items():
            self.models_config[model_name] = {
                "api_key": self.api_keys.get(model_name, ""),
                "base_url": base_config["base_url"],
                "model": base_config["model"]
            }

    def get_current_model(self) -> str:
        """获取当前模型名称"""
        return self.current_model

    def get_current_model_config(self) -> Dict[str, str]:
        """获取当前模型的配置"""
        return self.models_config.get(self.current_model, {})

    def get_all_models(self) -> list:
        """获取所有可用模型列表"""
        return list(self.models_config.keys())

    def save_model_config(self, model_name: str, api_key: str, base_url: str, model: str) -> bool:
        """
        保存模型配置到存储模块

        Args:
            model_name: 模型名称
            api_key: API Key
            base_url: API 基础 URL
            model: 模型标识

        Returns:
            bool: 保存是否成功
        """
        if not self.storage:
            return False

        success = self.storage.save_model_config(model_name, api_key, base_url, model)
        if success:
            # 更新内存中的配置
            self.api_keys[model_name] = api_key
            MODEL_CONFIGS[model_name]['base_url'] = base_url
            MODEL_CONFIGS[model_name]['model'] = model
            self._build_models_config()
        return success

    def switch_model(self, model_name: str, persist: bool = False) -> bool:
        """
        切换当前模型

        Args:
            model_name: 要切换的模型名称
            persist: 是否将切换结果保存到存储模块

        Returns:
            bool: 切换是否成功
        """
        if model_name not in self.models_config:
            return False
        self.current_model = model_name

        # 如果启用存储模块且需要持久化，保存当前模型选择
        if persist and self.storage:
            self.storage.set_current_model(model_name)

        model_info = self.models_config.get(model_name, {})
        return True

    def get_storage_status(self) -> bool:
        """获取存储模块是否启用"""
        return self.storage is not None

    def get_storage_path(self) -> str:
        """获取配置文件路径"""
        if not self.storage:
            return ""
        return self.storage.get_storage_path()

    def change_storage_path(self, new_path: str) -> bool:
        """
        更改配置文件路径

        Args:
            new_path: 新的配置文件路径

        Returns:
            bool: 是否成功
        """
        if not self.storage:
            return False

        try:
            success = self.storage.change_storage_path(new_path)
            if success:
                return True
            else:
                return False
        except (ValueError, Exception):
            return False
