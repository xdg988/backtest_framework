"""
Configuration management module.
"""

import os
import yaml
from typing import Dict, Any


class Config:
    """Configuration manager for the backtest framework."""

    def __init__(self, config_file: str = None):
        if config_file is None:
            config_file = os.path.join(os.path.dirname(__file__), 'config', 'default.yaml')
        self.config_file = config_file
        self._config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        with open(self.config_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def get(self, key: str, default=None) -> Any:
        """Get configuration value by dot-separated key."""
        keys = key.split('.')
        value = self._config
        try:
            for k in keys:
                value = value[k]
            return value
        except KeyError:
            return default

    def set(self, key: str, value: Any):
        """Set configuration value."""
        keys = key.split('.')
        config = self._config
        for k in keys[:-1]:
            config = config.setdefault(k, {})
        config[keys[-1]] = value

    def save(self, file_path: str = None):
        """Save current configuration to file."""
        if file_path is None:
            file_path = self.config_file
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(self._config, f, default_flow_style=False)


# Global config instance
config = Config()