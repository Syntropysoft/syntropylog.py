"""
Configuration for slpy.

Declarative config — declare once at init(), framework handles the rest.
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LoggerConfig:
    level: str = "info"
    transports: List[Any] = field(default_factory=list)  # Transport instances


@dataclass
class ContextConfig:
    correlation_id_header: str = "X-Correlation-ID"
    enable_auto_correlation: bool = True


@dataclass
class MaskingConfig:
    enable_default_rules: bool = True
    rules: List[Dict[str, Any]] = field(default_factory=list)
    max_depth: int = 10


@dataclass
class Config:
    logger: LoggerConfig = field(default_factory=LoggerConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    masking: MaskingConfig = field(default_factory=MaskingConfig)


class ConfigManager:
    def __init__(self, raw: Dict[str, Any]):
        logger_raw = raw.get("logger", {})
        context_raw = raw.get("context", {})
        masking_raw = raw.get("masking", {})

        # Env override for log level
        level = os.getenv("SLPY_LOG_LEVEL", logger_raw.get("level", "info"))

        self._config = Config(
            logger=LoggerConfig(
                level=level,
                transports=logger_raw.get("transports", []),
            ),
            context=ContextConfig(
                correlation_id_header=context_raw.get(
                    "correlation_id_header", "X-Correlation-ID"
                ),
                enable_auto_correlation=context_raw.get(
                    "enable_auto_correlation", True
                ),
            ),
            masking=MaskingConfig(
                enable_default_rules=masking_raw.get("enable_default_rules", True),
                rules=masking_raw.get("rules", []),
                max_depth=masking_raw.get("max_depth", 10),
            ),
        )

    def validate(self) -> None:
        valid_levels = {"debug", "info", "warn", "error", "audit", "silent"}
        if self._config.logger.level not in valid_levels:
            raise ValueError(
                f"Invalid log level '{self._config.logger.level}'. "
                f"Valid levels: {valid_levels}"
            )

    @property
    def logger(self) -> LoggerConfig:
        return self._config.logger

    @property
    def context(self) -> ContextConfig:
        return self._config.context

    @property
    def masking(self) -> MaskingConfig:
        return self._config.masking
