"""
Data Masking Engine for SyntropyLog

This module provides ultra-fast data masking using JSON flattening strategy.
Instead of processing nested objects recursively, we flatten them to a linear
structure for extreme processing speed.
"""

import re
import json
from typing import Dict, Any, List, Set, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum


class MaskingStrategy(Enum):
    """Masking strategies for different data types."""
    CREDIT_CARD = "credit_card"
    SSN = "ssn"
    EMAIL = "email"
    PHONE = "phone"
    PASSWORD = "password"
    TOKEN = "token"
    CUSTOM = "custom"


@dataclass
class MaskingRule:
    """
    Masking rule configuration.
    
    Attributes:
        pattern: Regex pattern to match field names
        strategy: Masking strategy to apply
        custom_mask: Custom masking function (for CUSTOM strategy)
        preserve_length: Whether to preserve original length
        mask_char: Character to use for masking
    """
    pattern: str
    strategy: MaskingStrategy
    custom_mask: Optional[Callable[[str], str]] = None
    preserve_length: bool = True
    mask_char: str = "*"
    
    def __post_init__(self):
        """Compile regex pattern for performance."""
        self._compiled_pattern = re.compile(self.pattern, re.IGNORECASE)


class DataMaskingEngine:
    """
    Ultra-fast data masking engine using JSON flattening.
    
    This engine flattens complex nested objects into linear key-value pairs,
    applies masking rules, and then reconstructs the original structure.
    This approach provides extreme processing speed for any object depth.
    """
    
    def __init__(self):
        """Initialize the masking engine."""
        self._rules: List[MaskingRule] = []
        self._default_rules: List[MaskingRule] = []
        self._initialized = False
        
        # Pre-compiled patterns for common data types
        self._common_patterns = {
            "credit_card": re.compile(r"(?:credit|card|cc|payment).*?(?:number|num|id)", re.IGNORECASE),
            "ssn": re.compile(r"(?:ssn|social|security).*?(?:number|num)", re.IGNORECASE),
            "email": re.compile(r"(?:email|mail|e-mail)", re.IGNORECASE),
            "phone": re.compile(r"(?:phone|tel|mobile|cell).*?(?:number|num)", re.IGNORECASE),
            "password": re.compile(r"(?:password|pass|pwd|secret)", re.IGNORECASE),
            "token": re.compile(r"(?:token|key|auth|jwt|bearer)", re.IGNORECASE),
        }
    
    async def init(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize the masking engine with configuration.
        
        Args:
            config: Configuration dictionary for masking rules
        """
        config = config or {}
        
        # Add default rules
        self._add_default_rules()
        
        # Add custom rules from config
        custom_rules = config.get('rules', [])
        for rule_config in custom_rules:
            self.add_rule(
                pattern=rule_config['pattern'],
                strategy=MaskingStrategy(rule_config['strategy']),
                preserve_length=rule_config.get('preserve_length', True),
                mask_char=rule_config.get('mask_char', '*'),
                custom_mask=rule_config.get('custom_mask')
            )
        
        self._initialized = True
    
    def _add_default_rules(self) -> None:
        """Add default masking rules for common data types."""
        default_rules = [
            MaskingRule(r"(?:credit|card|cc|payment).*?(?:number|num|id)", MaskingStrategy.CREDIT_CARD),
            MaskingRule(r"(?:ssn|social|security).*?(?:number|num)", MaskingStrategy.SSN),
            MaskingRule(r"(?:email|mail|e-mail)", MaskingStrategy.EMAIL),
            MaskingRule(r"(?:phone|tel|mobile|cell).*?(?:number|num)", MaskingStrategy.PHONE),
            MaskingRule(r"(?:password|pass|pwd|secret)", MaskingStrategy.PASSWORD),
            MaskingRule(r"(?:token|key|auth|jwt|bearer)", MaskingStrategy.TOKEN),
        ]
        
        self._default_rules.extend(default_rules)
        self._rules.extend(default_rules)
    
    def add_rule(self, 
                 pattern: str, 
                 strategy: MaskingStrategy,
                 preserve_length: bool = True,
                 mask_char: str = "*",
                 custom_mask: Optional[Callable[[str], str]] = None) -> None:
        """
        Add a custom masking rule.
        
        Args:
            pattern: Regex pattern to match field names
            strategy: Masking strategy to apply
            preserve_length: Whether to preserve original length
            mask_char: Character to use for masking
            custom_mask: Custom masking function
        """
        rule = MaskingRule(
            pattern=pattern,
            strategy=strategy,
            custom_mask=custom_mask,
            preserve_length=preserve_length,
            mask_char=mask_char
        )
        self._rules.append(rule)
    
    def mask_data(self, data: Any) -> Any:
        """
        Mask sensitive data in any structure.
        
        Args:
            data: Data to mask (dict, list, or primitive)
            
        Returns:
            Masked data with same structure
        """
        if not self._initialized:
            return data
        
        try:
            # Flatten the data for extreme speed
            flattened = self._flatten(data)
            
            # Apply masking rules
            masked_flat = self._apply_masking_rules(flattened)
            
            # Reconstruct original structure
            return self._unflatten(masked_flat)
            
        except Exception:
            # Silent observer - return original data if masking fails
            return data
    
    def _flatten(self, obj: Any, prefix: str = "") -> Dict[str, Any]:
        """
        Flatten nested object into linear key-value pairs.
        
        Args:
            obj: Object to flatten
            prefix: Current key prefix
            
        Returns:
            Flattened dictionary
        """
        flattened = {}
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_key = f"{prefix}.{key}" if prefix else key
                flattened.update(self._flatten(value, new_key))
        
        elif isinstance(obj, list):
            for i, value in enumerate(obj):
                new_key = f"{prefix}.{i}" if prefix else str(i)
                flattened.update(self._flatten(value, new_key))
        
        else:
            # Primitive value
            flattened[prefix] = obj
        
        return flattened
    
    def _unflatten(self, flattened: Dict[str, Any]) -> Any:
        """
        Reconstruct original structure from flattened data.
        
        Args:
            flattened: Flattened dictionary
            
        Returns:
            Reconstructed object
        """
        result = {}
        
        for key, value in flattened.items():
            keys = key.split('.')
            current = result
            
            # Navigate to the correct level
            for k in keys[:-1]:
                if k.isdigit():
                    k = int(k)
                    if k not in current:
                        current[k] = {}
                else:
                    if k not in current:
                        current[k] = {}
                current = current[k]
            
            # Set the value
            last_key = keys[-1]
            if last_key.isdigit():
                last_key = int(last_key)
            
            current[last_key] = value
        
        return result
    
    def _apply_masking_rules(self, flattened: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply masking rules to flattened data.
        
        Args:
            flattened: Flattened data dictionary
            
        Returns:
            Masked flattened data
        """
        masked = flattened.copy()
        
        for key, value in flattened.items():
            if not isinstance(value, str):
                continue
            
            # Check each rule
            for rule in self._rules:
                if rule._compiled_pattern.search(key):
                    masked[key] = self._apply_strategy(value, rule)
                    break  # First matching rule wins
        
        return masked
    
    def _apply_strategy(self, value: str, rule: MaskingRule) -> str:
        """
        Apply specific masking strategy to a value.
        
        Args:
            value: Value to mask
            rule: Masking rule to apply
            
        Returns:
            Masked value
        """
        if rule.strategy == MaskingStrategy.CUSTOM and rule.custom_mask:
            return rule.custom_mask(value)
        
        elif rule.strategy == MaskingStrategy.CREDIT_CARD:
            return self._mask_credit_card(value, rule)
        
        elif rule.strategy == MaskingStrategy.SSN:
            return self._mask_ssn(value, rule)
        
        elif rule.strategy == MaskingStrategy.EMAIL:
            return self._mask_email(value, rule)
        
        elif rule.strategy == MaskingStrategy.PHONE:
            return self._mask_phone(value, rule)
        
        elif rule.strategy == MaskingStrategy.PASSWORD:
            return self._mask_password(value, rule)
        
        elif rule.strategy == MaskingStrategy.TOKEN:
            return self._mask_token(value, rule)
        
        else:
            # Default masking
            return self._mask_default(value, rule)
    
    def _mask_credit_card(self, value: str, rule: MaskingRule) -> str:
        """Mask credit card number."""
        # Remove non-digits
        digits = re.sub(r'\D', '', value)
        
        if len(digits) >= 4:
            if rule.preserve_length:
                return rule.mask_char * (len(digits) - 4) + digits[-4:]
            else:
                return "****-****-****-" + digits[-4:]
        
        return rule.mask_char * len(value)
    
    def _mask_ssn(self, value: str, rule: MaskingRule) -> str:
        """Mask social security number."""
        # Remove non-digits
        digits = re.sub(r'\D', '', value)
        
        if len(digits) >= 4:
            if rule.preserve_length:
                return rule.mask_char * (len(digits) - 4) + digits[-4:]
            else:
                return "***-**-" + digits[-4:]
        
        return rule.mask_char * len(value)
    
    def _mask_email(self, value: str, rule: MaskingRule) -> str:
        """Mask email address."""
        if '@' in value:
            username, domain = value.split('@', 1)
            if len(username) > 2:
                masked_username = username[0] + rule.mask_char * (len(username) - 2) + username[-1]
            else:
                masked_username = rule.mask_char * len(username)
            return f"{masked_username}@{domain}"
        
        return rule.mask_char * len(value)
    
    def _mask_phone(self, value: str, rule: MaskingRule) -> str:
        """Mask phone number."""
        # Remove non-digits
        digits = re.sub(r'\D', '', value)
        
        if len(digits) >= 4:
            if rule.preserve_length:
                return rule.mask_char * (len(digits) - 4) + digits[-4:]
            else:
                return "***-***-" + digits[-4:]
        
        return rule.mask_char * len(value)
    
    def _mask_password(self, value: str, rule: MaskingRule) -> str:
        """Mask password."""
        return rule.mask_char * len(value)
    
    def _mask_token(self, value: str, rule: MaskingRule) -> str:
        """Mask token."""
        if len(value) > 8:
            return value[:4] + rule.mask_char * (len(value) - 8) + value[-4:]
        
        return rule.mask_char * len(value)
    
    def _mask_default(self, value: str, rule: MaskingRule) -> str:
        """Default masking strategy."""
        if rule.preserve_length:
            return rule.mask_char * len(value)
        else:
            return rule.mask_char * min(len(value), 8)
    
    def get_masking_stats(self) -> Dict[str, Any]:
        """
        Get masking engine statistics.
        
        Returns:
            Dictionary with masking statistics
        """
        return {
            "initialized": self._initialized,
            "total_rules": len(self._rules),
            "default_rules": len(self._default_rules),
            "custom_rules": len(self._rules) - len(self._default_rules),
            "strategies": [rule.strategy.value for rule in self._rules]
        }
    
    @property
    def is_initialized(self) -> bool:
        """Check if the masking engine is initialized."""
        return self._initialized
    
    async def shutdown(self) -> None:
        """Shutdown the masking engine."""
        self._rules.clear()
        self._default_rules.clear()
        self._initialized = False