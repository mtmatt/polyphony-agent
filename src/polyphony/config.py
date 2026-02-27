import os
import tomllib
from typing import Optional
from pydantic import BaseModel, Field

class Config(BaseModel):
    provider: str = Field(default="gemini")
    model: Optional[str] = None
    base_url: Optional[str] = Field(default=None, alias="base_url")
    api_key: Optional[str] = Field(default=None, alias="api_key")
    auto_commit: bool = Field(default=False, alias="auto_commit")

def load_config(config_path: str = "polyphony.toml") -> Config:
    """
    Loads configuration from a TOML file.
    Returns a default Config if the file doesn't exist.
    """
    if not os.path.exists(config_path):
        return Config()

    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
            # Support nested [polyphony] section or flat structure
            config_data = data.get("polyphony", data)
            return Config(**config_data)
    except Exception as e:
        print(f"Warning: Error loading config file {config_path}: {e}")
        return Config()
