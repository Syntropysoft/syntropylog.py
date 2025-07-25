"""
Configuration Management for SyntropyLog

This module provides configuration management functionality with schema validation,
environment variable support, and hot-reload capabilities. It uses Pydantic for
type safety and validation.
"""

import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from pydantic import BaseModel, Field, validator


class LoggerConfig(BaseModel):
    """
    Configuration for the logger system.
    
    This class defines the configuration schema for the logger component,
    including log levels, transports, and formatters.
    
    Attributes:
        level: Minimum log level to process
        transports: List of transport names to use
        formatters: Configuration for log formatters
        enable_context: Whether to include context in log entries
        enable_correlation: Whether to include correlation IDs
    """
    level: str = Field(default="info", description="Minimum log level")
    transports: List[str] = Field(default=["console"], description="Transport names")
    formatters: Dict[str, Any] = Field(default_factory=dict, description="Formatter config")
    enable_context: bool = Field(default=True, description="Include context in logs")
    enable_correlation: bool = Field(default=True, description="Include correlation IDs")
    
    @validator('level')
    def validate_level(cls, v):
        """Validate log level."""
        valid_levels = ['debug', 'info', 'warn', 'error']
        if v.lower() not in valid_levels:
            raise ValueError(f'Log level must be one of: {valid_levels}')
        return v.lower()


class HttpConfig(BaseModel):
    """
    Configuration for HTTP instrumentation.
    
    This class defines the configuration schema for HTTP client instrumentation,
    including correlation headers and request/response logging.
    
    Attributes:
        enabled: Whether HTTP instrumentation is enabled
        correlation_headers: Headers to include for correlation
        log_requests: Whether to log HTTP requests
        log_responses: Whether to log HTTP responses
        mask_sensitive_data: Whether to mask sensitive data in logs
    """
    enabled: bool = Field(default=True, description="Enable HTTP instrumentation")
    correlation_headers: List[str] = Field(
        default=["X-Correlation-ID", "X-Request-ID"],
        description="Headers for correlation"
    )
    log_requests: bool = Field(default=True, description="Log HTTP requests")
    log_responses: bool = Field(default=True, description="Log HTTP responses")
    mask_sensitive_data: bool = Field(default=True, description="Mask sensitive data")


class RedisConfig(BaseModel):
    """
    Configuration for Redis integration.
    
    This class defines the configuration schema for Redis client integration,
    including connection settings and context storage configuration.
    
    Attributes:
        enabled: Whether Redis integration is enabled
        url: Redis connection URL
        host: Redis host address
        port: Redis port number
        db: Redis database number
        password: Redis password
        context_ttl: TTL for context data in seconds
        enable_clustering: Whether to enable Redis clustering
    """
    enabled: bool = Field(default=True, description="Enable Redis integration")
    url: Optional[str] = Field(default=None, description="Redis connection URL")
    host: str = Field(default="localhost", description="Redis host")
    port: int = Field(default=6379, description="Redis port")
    db: int = Field(default=0, description="Redis database")
    password: Optional[str] = Field(default=None, description="Redis password")
    context_ttl: int = Field(default=3600, description="Context TTL in seconds")
    enable_clustering: bool = Field(default=False, description="Enable Redis clustering")


class BrokerConfig(BaseModel):
    """
    Configuration for message brokers.
    
    This class defines the configuration schema for message broker integration,
    including Kafka, RabbitMQ, and NATS settings.
    
    Attributes:
        enabled: Whether broker integration is enabled
        type: Type of broker (kafka, rabbitmq, nats)
        connection: Broker connection configuration
        topics: Topic configuration for correlation
        enable_correlation: Whether to enable message correlation
    """
    enabled: bool = Field(default=False, description="Enable broker integration")
    type: str = Field(default="kafka", description="Broker type")
    connection: Dict[str, Any] = Field(default_factory=dict, description="Connection config")
    topics: Dict[str, str] = Field(default_factory=dict, description="Topic mapping")
    enable_correlation: bool = Field(default=True, description="Enable message correlation")
    
    @validator('type')
    def validate_type(cls, v):
        """Validate broker type."""
        valid_types = ['kafka', 'rabbitmq', 'nats']
        if v.lower() not in valid_types:
            raise ValueError(f'Broker type must be one of: {valid_types}')
        return v.lower()


class SerializationConfig(BaseModel):
    """
    Configuration for serialization pipeline.
    
    This class defines the configuration schema for the serialization pipeline,
    including custom serializers and pipeline steps.
    
    Attributes:
        enabled: Whether serialization is enabled
        serializers: Custom serializer configuration
        pipeline_steps: Pipeline step configuration
        timeout: Serialization timeout in seconds
        enable_caching: Whether to enable serializer caching
    """
    enabled: bool = Field(default=True, description="Enable serialization")
    serializers: Dict[str, str] = Field(default_factory=dict, description="Custom serializers")
    pipeline_steps: List[str] = Field(default_factory=list, description="Pipeline steps")
    timeout: int = Field(default=5000, description="Serialization timeout (ms)")
    enable_caching: bool = Field(default=True, description="Enable serializer caching")


class ContextConfig(BaseModel):
    """
    Configuration for context management.
    
    This class defines the configuration schema for context management,
    including correlation ID generation and context storage.
    
    Attributes:
        enabled: Whether context management is enabled
        correlation_id_header: HTTP header for correlation ID
        enable_auto_correlation: Whether to auto-generate correlation IDs
        context_storage: Context storage configuration
        max_context_depth: Maximum context nesting depth
    """
    enabled: bool = Field(default=True, description="Enable context management")
    correlation_id_header: str = Field(default="X-Correlation-ID", description="Correlation header")
    enable_auto_correlation: bool = Field(default=True, description="Auto-generate correlation IDs")
    context_storage: Dict[str, Any] = Field(default_factory=dict, description="Storage config")
    max_context_depth: int = Field(default=10, description="Max context nesting depth")


class Config(BaseModel):
    """
    Main configuration class for SyntropyLog.
    
    This class defines the complete configuration schema for the SyntropyLog
    framework, including all component configurations.
    
    Attributes:
        logger: Logger configuration
        http: HTTP instrumentation configuration
        redis: Redis integration configuration
        brokers: Message broker configuration
        serialization: Serialization pipeline configuration
        context: Context management configuration
        environment: Environment-specific settings
        debug: Debug mode configuration
    """
    logger: LoggerConfig = Field(default_factory=LoggerConfig, description="Logger configuration")
    http: HttpConfig = Field(default_factory=HttpConfig, description="HTTP configuration")
    redis: RedisConfig = Field(default_factory=RedisConfig, description="Redis configuration")
    brokers: BrokerConfig = Field(default_factory=BrokerConfig, description="Broker configuration")
    serialization: SerializationConfig = Field(default_factory=SerializationConfig, description="Serialization configuration")
    context: ContextConfig = Field(default_factory=ContextConfig, description="Context configuration")
    environment: str = Field(default="development", description="Environment name")
    debug: bool = Field(default=False, description="Debug mode")


class ConfigManager:
    """
    Manages configuration for the SyntropyLog framework.
    
    This class provides configuration management functionality including
    loading from various sources, validation, and hot-reload capabilities.
    
    The configuration manager follows the "Silent Observer" philosophy -
    configuration errors are logged but don't prevent framework operation.
    
    Attributes:
        _config: Current configuration instance
        _raw_config: Raw configuration dictionary
        _environment: Current environment
        _validators: List of configuration validators
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the configuration manager.
        
        Args:
            config: Raw configuration dictionary
        """
        self._raw_config = config
        self._config: Optional[Config] = None
        self._environment = os.getenv('SYNTROPY_ENV', 'development')
        self._validators: List[callable] = []
        
        # Load and validate configuration
        self._load_config()
    
    def _load_config(self) -> None:
        """
        Load and validate configuration from raw config.
        
        This method processes the raw configuration, applies environment
        overrides, and validates the final configuration.
        """
        try:
            # Apply environment overrides
            config_with_env = self._apply_environment_overrides(self._raw_config)
            
            # Create configuration instance
            self._config = Config(**config_with_env)
            
            # Run custom validators
            self._run_validators()
            
        except Exception as error:
            # Silent observer - use defaults if configuration fails
            print(f"Configuration error: {error}. Using defaults.")
            self._config = Config()
    
    def _apply_environment_overrides(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply environment-specific configuration overrides.
        
        Args:
            config: Base configuration dictionary
            
        Returns:
            Configuration with environment overrides applied
        """
        # Create a copy to avoid modifying the original
        config_copy = config.copy()
        
        # Apply environment-specific overrides
        env_config = config_copy.get('environments', {}).get(self._environment, {})
        
        # Merge environment config with base config
        for key, value in env_config.items():
            if key in config_copy:
                if isinstance(value, dict) and isinstance(config_copy[key], dict):
                    config_copy[key].update(value)
                else:
                    config_copy[key] = value
            else:
                config_copy[key] = value
        
        return config_copy
    
    def _run_validators(self) -> None:
        """
        Run custom configuration validators.
        
        This method executes any registered custom validators to ensure
        the configuration meets application-specific requirements.
        """
        for validator in self._validators:
            try:
                validator(self._config)
            except Exception as error:
                print(f"Configuration validation error: {error}")
    
    def add_validator(self, validator: callable) -> None:
        """
        Add a custom configuration validator.
        
        Args:
            validator: Function that validates configuration
        """
        self._validators.append(validator)
    
    async def validate(self) -> None:
        """
        Validate the current configuration.
        
        This method performs comprehensive validation of the configuration
        and raises exceptions for critical configuration errors.
        """
        if not self._config:
            raise ValueError("Configuration not loaded")
        
        # Validate Redis configuration if enabled
        if self._config.redis.enabled and not self._config.redis.url:
            # Try to construct URL from components
            if not all([self._config.redis.host, self._config.redis.port]):
                raise ValueError("Redis enabled but no connection details provided")
    
    def get_logger_config(self) -> LoggerConfig:
        """
        Get logger configuration.
        
        Returns:
            Logger configuration instance
        """
        return self._config.logger if self._config else LoggerConfig()
    
    def get_http_config(self) -> HttpConfig:
        """
        Get HTTP configuration.
        
        Returns:
            HTTP configuration instance
        """
        return self._config.http if self._config else HttpConfig()
    
    def get_redis_config(self) -> RedisConfig:
        """
        Get Redis configuration.
        
        Returns:
            Redis configuration instance
        """
        return self._config.redis if self._config else RedisConfig()
    
    def get_broker_config(self) -> BrokerConfig:
        """
        Get broker configuration.
        
        Returns:
            Broker configuration instance
        """
        return self._config.brokers if self._config else BrokerConfig()
    
    def get_serialization_config(self) -> SerializationConfig:
        """
        Get serialization configuration.
        
        Returns:
            Serialization configuration instance
        """
        return self._config.serialization if self._config else SerializationConfig()
    
    def get_context_config(self) -> ContextConfig:
        """
        Get context configuration.
        
        Returns:
            Context configuration instance
        """
        return self._config.context if self._config else ContextConfig()
    
    def get_environment(self) -> str:
        """
        Get current environment.
        
        Returns:
            Current environment name
        """
        return self._environment
    
    def is_debug(self) -> bool:
        """
        Check if debug mode is enabled.
        
        Returns:
            True if debug mode is enabled
        """
        return self._config.debug if self._config else False
    
    def reload(self, new_config: Dict[str, Any]) -> None:
        """
        Reload configuration with new settings.
        
        This method allows hot-reloading of configuration without
        restarting the framework.
        
        Args:
            new_config: New configuration dictionary
        """
        self._raw_config = new_config
        self._load_config()
    
    def get_all(self) -> Config:
        """
        Get the complete configuration.
        
        Returns:
            Complete configuration instance
        """
        return self._config
    
    @property
    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return self._config is not None 