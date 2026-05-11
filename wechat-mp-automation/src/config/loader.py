"""
配置加载器
"""

import os
from pathlib import Path
from typing import Any

import yaml
from loguru import logger
from pydantic import BaseModel, Field

from src.config.validator import ConfigValidator


class AppConfig(BaseModel):
    """应用配置"""
    name: str = "wechat-mp-automation"
    version: str = "1.0.0"
    env: str = "development"


class DatabaseConfig(BaseModel):
    """数据库配置"""
    type: str = "sqlite"
    path: str = "./data/content.db"
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None


class LLMConfig(BaseModel):
    """LLM 配置"""
    provider: str = "openai"
    api_key: str = ""
    model: str = "gpt-4o"
    base_url: str = "https://api.openai.com/v1"
    timeout: int = 120
    retry: int = 3
    max_tokens: int = 4096


class ImageGenConfig(BaseModel):
    """图像生成配置"""
    default_provider: str = "dalle"
    providers: dict = Field(default_factory=dict)


class StorageConfig(BaseModel):
    """存储配置"""
    type: str = "local"
    path: str = "./output"


class LoggingConfig(BaseModel):
    """日志配置"""
    level: str = "INFO"
    file: str = "./logs/app.log"
    max_size: str = "100MB"
    backup_count: int = 5
    format: str = "text"
    rotation: str = "daily"


class MonitoringConfig(BaseModel):
    """监控配置"""
    enabled: bool = True
    metrics_port: int = 9090
    health_check_port: int = 8080


class AlertsConfig(BaseModel):
    """告警配置"""
    enabled: bool = False
    channels: list = Field(default_factory=list)


class Config(BaseModel):
    """主配置"""
    app: AppConfig = Field(default_factory=AppConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    image_gen: ImageGenConfig = Field(default_factory=ImageGenConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    alerts: AlertsConfig = Field(default_factory=AlertsConfig)
    # Phase 1 扩展字段（config.yaml 中有但 Config 类未定义）
    rewrite: dict = Field(default_factory=dict)
    format: dict = Field(default_factory=dict)
    accounts: list = Field(default_factory=list)

    def to_dict(self) -> dict:
        """导出为普通 dict，兼容 config.get() 调用方式"""
        return self.model_dump()

    def get(self, key: str, default=None):
        """兼容 config.get('key') 调用方式（用于 dict 风格配置访问）"""
        d = self.to_dict()
        val = d.get(key, default)
        # llm/account 等字段是 Pydantic 模型，转回 dict 保持接口兼容
        if key in ("llm", "accounts", "rewrite", "format", "database", "storage", "logging"):
            if hasattr(val, "model_dump"):
                return val.model_dump()
        return val


class ConfigLoader:
    """配置加载器"""
    
    _config: Config | None = None
    _config_dir: Path | None = None
    
    @classmethod
    def load(cls, config_path: str = "config/config.yaml") -> Config:
        """加载配置"""
        if cls._config is not None:
            return cls._config
        
        config_file = Path(config_path)
        if not config_file.exists():
            logger.warning(f"Config file not found: {config_path}, using defaults")
            cls._config = Config()
            return cls._config
        
        cls._config_dir = config_file.parent.absolute()
        
        with open(config_file, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)
        
        # 处理环境变量
        raw_config = cls._resolve_env_vars(raw_config)
        
        # 验证配置
        ConfigValidator.validate(raw_config)
        
        cls._config = Config(**raw_config)
        logger.info(f"Config loaded from {config_path}")
        
        return cls._config
    
    @classmethod
    def _resolve_env_vars(cls, obj: Any) -> Any:
        """递归解析环境变量"""
        if isinstance(obj, dict):
            return {k: cls._resolve_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [cls._resolve_env_vars(item) for item in obj]
        elif isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            env_var = obj[2:-1]
            return os.environ.get(env_var, "")
        return obj
    
    @classmethod
    def get_config_dir(cls) -> Path | None:
        """获取配置目录"""
        return cls._config_dir
    
    @classmethod
    def reload(cls, config_path: str = "config/config.yaml") -> Config:
        """重新加载配置"""
        cls._config = None
        return cls.load(config_path)
