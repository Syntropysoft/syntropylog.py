"""
Configuration Management for SyntropyLog

This module provides configuration management functionality with schema validation,
environment variable support, and hot-reload capabilities.
"""

import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field


@dataclass
class LoggerConfig:
    """Configuration for the logger system."""
    level: str = "info"
    transports: List[str] = field(default_factory=lambda: ["console"])
    formatters: Dict[str, Any] = field(default_factory=dict)
    enable_context: bool = True
    enable_correlation: bool = True


@dataclass
class HttpConfig:
    """Configuration for HTTP instrumentation."""
    enabled: bool = True
    correlation_headers: List[str] = field(default_factory=lambda: ["X-Correlation-ID", "X-Request-ID"])
    log_requests: bool = True
    log_responses: bool = True
    mask_sensitive_data: bool = True


@dataclass
class RedisConfig:
    """Configuration for Redis integration."""
    enabled: bool = True
    url: Optional[str] = None
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    context_ttl: int = 3600
    enable_clustering: bool = False


@dataclass
class BrokerConfig:
    """Configuration for message brokers."""
    enabled: bool = False
    type: str = "kafka"
    connection: Dict[str, Any] = field(default_factory=dict)
    topics: Dict[str, str] = field(default_factory=dict)
    enable_correlation: bool = True


@dataclass
class SerializationConfig:
    """Configuration for serialization pipeline."""
    enabled: bool = True
    serializers: Dict[str, str] = field(default_factory=dict)
    pipeline_steps: List[str] = field(default_factory=list)
    timeout: int = 5000
    enable_caching: bool = True


@dataclass
class ContextConfig:
    """Configuration for context management."""
    enabled: bool = True
    correlation_id_header: str = "X-Correlation-ID"
    enable_auto_correlation: bool = True
    context_storage: Dict[str, Any] = field(default_factory=dict)
    max_context_depth: int = 10


@dataclass
class MaskingConfig:
    """Configuration for data masking."""
    enabled: bool = True
    rules: List[Dict[str, Any]] = field(default_factory=list)
    max_object_depth: int = 3
    max_field_length: int = 1000


@dataclass
class Config:
    """Main configuration class for SyntropyLog."""
    logger: LoggerConfig = field(default_factory=LoggerConfig)
    http: HttpConfig = field(default_factory=HttpConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    brokers: BrokerConfig = field(default_factory=BrokerConfig)
    serialization: SerializationConfig = field(default_factory=SerializationConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    masking: MaskingConfig = field(default_factory=MaskingConfig)
    environment: str = "development"
    debug: bool = False


class ConfigManager:
    """
    Configuration manager for SyntropyLog.
    
    This class manages configuration loading, validation, and hot-reload
    capabilities for the SyntropyLog framework.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the configuration manager.
        
        Args:
            config: Configuration dictionary
        """
        self._config = config
        self._validators: List[callable] = []
        self._is_valid = False
        
        # Load and process configuration
        self._load_config()
    
    def _load_config(self) -> None:
        """Load and process configuration."""
        # Apply environment overrides
        self._config = self._apply_environment_overrides(self._config)
        
        # Create config object
        self._config_obj = self._create_config_object()
        
        # Run validators
        self._run_validators()
        
        self._is_valid = True
    
    def _create_config_object(self) -> Config:
        """Create Config object from dictionary."""
        return Config(
            logger=LoggerConfig(**self._config.get('logger', {})),
            http=HttpConfig(**self._config.get('http', {})),
            redis=RedisConfig(**self._config.get('redis', {})),
            brokers=BrokerConfig(**self._config.get('brokers', {})),
            serialization=SerializationConfig(**self._config.get('serialization', {})),
            context=ContextConfig(**self._config.get('context', {})),
            masking=MaskingConfig(**self._config.get('masking', {})),
            environment=self._config.get('environment', 'development'),
            debug=self._config.get('debug', False)
        )
    
    def _apply_environment_overrides(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply environment variable overrides to configuration.
        
        Args:
            config: Base configuration dictionary
            
        Returns:
            Configuration with environment overrides applied
        """
        # Environment-specific overrides
        env = os.getenv('SYNTROPY_ENV', 'development')
        
        # Apply environment-specific config
        env_config = config.get('environments', {}).get(env, {})
        config.update(env_config)
        
        # Apply individual environment variables
        if os.getenv('SYNTROPY_LOG_LEVEL'):
            config.setdefault('logger', {})['level'] = os.getenv('SYNTROPY_LOG_LEVEL')
        
        if os.getenv('SYNTROPY_REDIS_URL'):
            config.setdefault('redis', {})['url'] = os.getenv('SYNTROPY_REDIS_URL')
        
        if os.getenv('SYNTROPY_DEBUG'):
            config['debug'] = os.getenv('SYNTROPY_DEBUG').lower() in ('true', '1', 'yes')
        
        return config
    
    def _run_validators(self) -> None:
        """Run all registered validators."""
        for validator in self._validators:
            validator(self._config_obj)
    
    def add_validator(self, validator: callable) -> None:
        """
        Add a configuration validator.
        
        Args:
            validator: Validation function
        """
        self._validators.append(validator)
    
    async def validate(self) -> None:
        """
        Validate the current configuration.
        
        Raises:
            ValueError: If configuration is invalid
        """
        if not self._is_valid:
            raise ValueError("Configuration is not valid")
        
        # Run validators
        self._run_validators()
    
    def get_logger_config(self) -> LoggerConfig:
        """Get logger configuration."""
        return self._config_obj.logger
    
    def get_http_config(self) -> HttpConfig:
        """Get HTTP configuration."""
        return self._config_obj.http
    
    def get_redis_config(self) -> RedisConfig:
        """Get Redis configuration."""
        return self._config_obj.redis
    
    def get_broker_config(self) -> BrokerConfig:
        """Get broker configuration."""
        return self._config_obj.brokers
    
    def get_serialization_config(self) -> SerializationConfig:
        """Get serialization configuration."""
        return self._config_obj.serialization
    
    def get_context_config(self) -> ContextConfig:
        """Get context configuration."""
        return self._config_obj.context
    
    def get_masking_config(self) -> MaskingConfig:
        """Get masking configuration."""
        return self._config_obj.masking
    
    def get_environment(self) -> str:
        """Get current environment."""
        return self._config_obj.environment
    
    def is_debug(self) -> bool:
        """Check if debug mode is enabled."""
        return self._config_obj.debug
    
    def reload(self, new_config: Dict[str, Any]) -> None:
        """
        Reload configuration with new settings.
        
        Args:
            new_config: New configuration dictionary
        """
        self._config = new_config
        self._load_config()
    
    def get_all(self) -> Config:
        """Get complete configuration object."""
        return self._config_obj
    
    @property
    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return self._is_valid 