"""
Configuration loader for Platform Adapter
Loads settings from config.yaml and .env files
"""

import os
import yaml
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Any

# Load environment variables
load_dotenv()


class Config:
    """Configuration manager for Platform Adapter"""
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            # Default to config/config.yaml relative to project root
            base_dir = Path(__file__).parent.parent.parent.parent
            config_path = base_dir / "config" / "config.yaml"
        
        self.config_path = Path(config_path)
        self._config = self._load_config()
        self._load_env_overrides()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)
    
    def _load_env_overrides(self):
        """Override config values with environment variables"""
        # IB Connection
        if os.getenv('IB_HOST'):
            self._config['ib_connection']['host'] = os.getenv('IB_HOST')
        if os.getenv('IB_PORT'):
            self._config['ib_connection']['port'] = int(os.getenv('IB_PORT'))
        if os.getenv('IB_CLIENT_ID'):
            self._config['ib_connection']['client_id'] = int(os.getenv('IB_CLIENT_ID'))
        
        # Credentials (from .env only)
        self._config['ib_connection']['username'] = os.getenv('IB_USERNAME', '')
        self._config['ib_connection']['password'] = os.getenv('IB_PASSWORD', '')
        self._config['ib_connection']['account_id'] = os.getenv('IB_ACCOUNT_ID', '')
        
        # Logging
        if os.getenv('LOG_LEVEL'):
            self._config['logging']['level'] = os.getenv('LOG_LEVEL')
        
        # Environment
        self._config['environment'] = os.getenv('ENVIRONMENT', 'development')
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key (dot notation supported)"""
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        
        return value
    
    def get_all(self) -> Dict[str, Any]:
        """Get all configuration"""
        return self._config.copy()
    
    @property
    def ib_connection(self) -> Dict[str, Any]:
        """Get IB connection configuration"""
        return self._config.get('ib_connection', {})
    
    @property
    def market_data(self) -> Dict[str, Any]:
        """Get market data configuration"""
        return self._config.get('market_data', {})
    
    @property
    def orders(self) -> Dict[str, Any]:
        """Get orders configuration"""
        return self._config.get('orders', {})
    
    @property
    def account(self) -> Dict[str, Any]:
        """Get account configuration"""
        return self._config.get('account', {})
    
    @property
    def logging(self) -> Dict[str, Any]:
        """Get logging configuration"""
        return self._config.get('logging', {})


# Global config instance
_config = None


def load_config(config_path: str = None) -> Config:
    """Load and return global config instance"""
    global _config
    if _config is None:
        _config = Config(config_path)
    return _config


def get_config() -> Config:
    """Get global config instance"""
    global _config
    if _config is None:
        _config = Config()
    return _config
