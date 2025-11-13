from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv


def _project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return current.parents[2]


def _substitute_env_vars(value: Any) -> Any:
    """Recursively substitute environment variables in config values.
    
    Syntax: ${VAR_NAME:default_value} or ${VAR_NAME}
    """
    if isinstance(value, str):
        pattern = r'\$\{([^}:]+)(?::([^}]*))?\}'
        def replacer(match: re.Match) -> str:
            var_name = match.group(1)
            default = match.group(2) or ""
            return os.getenv(var_name, default)
        return re.sub(pattern, replacer, value)
    elif isinstance(value, dict):
        return {k: _substitute_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_substitute_env_vars(item) for item in value]
    return value


@lru_cache(maxsize=1)
def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load and return the pipeline configuration."""
    load_dotenv()
    
    path = config_path or (_project_root() / "config" / "recommendation" / "pipeline.yaml")
    path = path.resolve()
    
    if not path.exists():
        raise FileNotFoundError(f"Pipeline config not found: {path}")
    
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    
    return _substitute_env_vars(config)


def get_case_name(config: Optional[Dict[str, Any]] = None) -> str:
    """Get the case name from config."""
    cfg = config or load_config()
    return str(cfg["case_name"])


def get_neo4j_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Get Neo4j connection configuration."""
    cfg = config or load_config()
    case_name = get_case_name(cfg)
    neo4j = cfg["neo4j"]
    
    return {
        "uri": neo4j["uri"],
        "username": neo4j["username"],
        "password": neo4j["password"],
        "database": case_name,
    }


def get_graph_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Get graph building configuration with resolved paths."""
    cfg = config or load_config()
    case_name = get_case_name(cfg)
    graph = cfg["graph"].copy()
    
    graph["data_dir"] = (_project_root() / "data" / "processed" / "rvt" / case_name).resolve()
    graph["case_name"] = case_name
    return graph


def get_suggestions_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Get suggestions generation configuration with resolved paths."""
    cfg = config or load_config()
    case_name = get_case_name(cfg)
    suggestions = cfg["suggestions"].copy()
    
    suggestions["case_name"] = case_name
    output_filename = suggestions.get("output_filename", "suggestions.json")
    suggestions["issues_path"] = (
        _project_root() / "data" / "processed" / "acc_result" / case_name / "issues" / "topics.json"
    ).resolve()
    suggestions["output_path"] = (
        _project_root() / "data" / "output" / case_name / output_filename
    ).resolve()
    
    return suggestions

