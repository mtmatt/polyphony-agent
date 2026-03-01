import os
import tomllib
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

class AgentConfig(BaseModel):
    provider: str = Field(default="gemini")
    model: Optional[str] = None
    flash_model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None

class MCPServerConfig(BaseModel):
    command: str
    args: List[str] = Field(default_factory=list)
    env: Optional[Dict[str, str]] = None

class Config(BaseModel):
    # Support both flat and nested structure
    planner: AgentConfig = Field(default_factory=lambda: AgentConfig(provider="gemini", model="gemini-3-flash-preview"))
    executor: AgentConfig = Field(default_factory=lambda: AgentConfig(provider="gemini", model="gemini-2.0-flash-exp", flash_model="gemini-3-flash-preview"))
    mcp_servers: List[MCPServerConfig] = Field(default_factory=list)
    auto_commit: bool = Field(default=False)
    budget_limit: float = Field(default=0.0)

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
            # Support nested [polyphony] section
            root_data = data.get("polyphony", data)
            
            # If the user has a flat structure, we map it to planner/executor defaults
            if "provider" in root_data and "planner" not in root_data:
                flat_agent = {
                    "provider": root_data.get("provider"),
                    "model": root_data.get("model"),
                    "base_url": root_data.get("base_url"),
                    "api_key": root_data.get("api_key")
                }
                root_data["planner"] = flat_agent
                root_data["executor"] = flat_agent
            
            return Config(**root_data)
    except Exception as e:
        print(f"Warning: Error loading config file {config_path}: {e}")
        return Config()
