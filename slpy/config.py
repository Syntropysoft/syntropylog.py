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
    # Called when a transport raises: on_log_failure(exc, transport). Never raises.
    on_log_failure: Optional[Any] = None


@dataclass
class ContextConfig:
    # Per-source inbound: source name → {conceptual field → header name}
    inbound: Dict[str, Dict[str, str]] = field(default_factory=dict)
    # Per-target outbound: target name → {conceptual field → wire name}
    # Use 'http' for the default HTTP target (used by get_propagation_headers() with no arg)
    outbound: Dict[str, Dict[str, str]] = field(default_factory=dict)
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
    # Called when masking fails (never receives the raw payload). Never raises.
    on_masking_error: Optional[Any] = None


@dataclass
class Config:
    logger: LoggerConfig = field(default_factory=LoggerConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    masking: MaskingConfig = field(default_factory=MaskingConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    # Per-level whitelist of context fields: {'default': [...], 'info': [...], 'error': ['*']}
    logging_matrix: Dict[str, List[str]] = field(default_factory=dict)
    # Named retention policies: {'SOX_AUDIT_TRAIL': {'years': 7, 'class': 'SOX'}}
    # Exactly one unit per policy — days | months | years. Prefer the calendar
    # unit: 2555 days is 7 x 365 and ends two days before seven actual years.
    retention_policies: Dict[str, Any] = field(default_factory=dict)


class ConfigManager:
    def __init__(self, raw: Dict[str, Any]):
        logger_raw  = raw.get("logger", {})
        context_raw = raw.get("context", {})
        masking_raw = raw.get("masking", {})
        obs_raw     = raw.get("observability", {})

        level = os.getenv("SLPY_LOG_LEVEL", logger_raw.get("level", "info"))

        self._config = Config(
            logger=LoggerConfig(
                level=level,
                transports=logger_raw.get("transports", []),
                on_log_failure=logger_raw.get("on_log_failure"),
            ),
            context=ContextConfig(
                inbound=context_raw.get("inbound", {}),
                outbound=context_raw.get("outbound", {}),
                custom_headers=context_raw.get("custom_headers", []),
            ),
            masking=MaskingConfig(
                enable_default_rules=masking_raw.get("enable_default_rules", True),
                rules=masking_raw.get("rules", []),
                max_depth=masking_raw.get("max_depth", 10),
                on_masking_error=masking_raw.get("on_masking_error"),
            ),
            observability=ObservabilityConfig(
                transports=obs_raw.get("transports", []),
                enabled=obs_raw.get("enabled", True),
            ),
            logging_matrix=raw.get("logging_matrix", {}),
            retention_policies=raw.get("retention_policies", {}),
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

    @property
    def logging_matrix(self) -> Dict[str, List[str]]:
        return self._config.logging_matrix

    @property
    def retention_policies(self) -> Dict[str, Any]:
        return self._config.retention_policies
