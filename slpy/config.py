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
    transports: List[Any] = field(default_factory=list)


@dataclass
class OutboundConfig:
    # Default outbound: conceptual field → HTTP header name
    propagation: Dict[str, str] = field(default_factory=dict)
    # Per-target: target name → {conceptual field → target key}
    targets: Dict[str, Dict[str, str]] = field(default_factory=dict)


@dataclass
class ContextConfig:
    # Per-source inbound: source name → {conceptual field → header name}
    inbound: Dict[str, Dict[str, str]] = field(default_factory=dict)
    # Outbound mapping — propagation + per-target
    outbound: OutboundConfig = field(default_factory=OutboundConfig)
    # Custom headers to extract from inbound requests and propagate as-is
    custom_headers: List[str] = field(default_factory=list)


@dataclass
class ObservabilityConfig:
    transports: List[Any] = field(default_factory=list)
    enabled: bool = True


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
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)


class ConfigManager:
    def __init__(self, raw: Dict[str, Any]):
        logger_raw  = raw.get("logger", {})
        context_raw = raw.get("context", {})
        masking_raw = raw.get("masking", {})
        obs_raw     = raw.get("observability", {})

        level = os.getenv("SLPY_LOG_LEVEL", logger_raw.get("level", "info"))

        outbound_raw = context_raw.get("outbound", {})

        self._config = Config(
            logger=LoggerConfig(
                level=level,
                transports=logger_raw.get("transports", []),
            ),
            context=ContextConfig(
                inbound=context_raw.get("inbound", {}),
                outbound=OutboundConfig(
                    propagation=outbound_raw.get("propagation", {}),
                    targets=outbound_raw.get("targets", {}),
                ),
                custom_headers=context_raw.get("custom_headers", []),
            ),
            masking=MaskingConfig(
                enable_default_rules=masking_raw.get("enable_default_rules", True),
                rules=masking_raw.get("rules", []),
                max_depth=masking_raw.get("max_depth", 10),
            ),
            observability=ObservabilityConfig(
                transports=obs_raw.get("transports", []),
                enabled=obs_raw.get("enabled", True),
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

    @property
    def observability(self) -> ObservabilityConfig:
        return self._config.observability
