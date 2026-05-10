"""
配置验证器
"""

from typing import Any

from loguru import logger


class ConfigValidator:
    """配置验证器"""
    
    @classmethod
    def validate(cls, config: dict) -> bool:
        """验证配置"""
        errors = []
        
        # 验证 LLM 配置
        if "llm" in config:
            llm_errors = cls._validate_llm(config["llm"])
            errors.extend(llm_errors)
        
        # 验证数据库配置
        if "database" in config:
            db_errors = cls._validate_database(config["database"])
            errors.extend(db_errors)
        
        # 验证存储配置
        if "storage" in config:
            storage_errors = cls._validate_storage(config["storage"])
            errors.extend(storage_errors)
        
        if errors:
            for error in errors:
                logger.error(f"Config validation error: {error}")
            raise ValueError(f"Config validation failed with {len(errors)} error(s)")
        
        logger.info("Config validation passed")
        return True
    
    @classmethod
    def _validate_llm(cls, llm_config: dict) -> list[str]:
        """验证 LLM 配置"""
        errors = []
        
        valid_providers = ["openai", "anthropic", "qwen", "deepseek"]
        if llm_config.get("provider") not in valid_providers:
            errors.append(f"Invalid LLM provider: {llm_config.get('provider')}")
        
        if not llm_config.get("api_key"):
            errors.append("LLM api_key is required")
        
        if not llm_config.get("model"):
            errors.append("LLM model is required")
        
        return errors
    
    @classmethod
    def _validate_database(cls, db_config: dict) -> list[str]:
        """验证数据库配置"""
        errors = []
        
        valid_types = ["sqlite", "mysql", "postgres"]
        if db_config.get("type") not in valid_types:
            errors.append(f"Invalid database type: {db_config.get('type')}")
        
        if db_config.get("type") == "sqlite":
            if not db_config.get("path"):
                errors.append("SQLite path is required")
        
        return errors
    
    @classmethod
    def _validate_storage(cls, storage_config: dict) -> list[str]:
        """验证存储配置"""
        errors = []
        
        valid_types = ["local", "oss", "s3"]
        if storage_config.get("type") not in valid_types:
            errors.append(f"Invalid storage type: {storage_config.get('type')}")
        
        if storage_config.get("type") == "local":
            if not storage_config.get("path"):
                errors.append("Local storage path is required")
        
        return errors
