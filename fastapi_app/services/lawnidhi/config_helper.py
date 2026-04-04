"""
Lawnidhi Config Helper
Utility to read counsel and litigation settings from LawNidhi/data/config.ini.
"""
import configparser
from pathlib import Path
from workflow_engine.utils import get_project_root

def get_primary_counsel() -> str:
    """
    Reads the primary counsel name from LawNidhi/data/config.ini.
    Defaults to 'Hemlata Singh' if not found.
    """
    root = get_project_root()
    config_path = root / "LawNidhi" / "data" / "config.ini"
    
    if not config_path.exists():
        return "Hemlata Singh"
        
    try:
        config = configparser.ConfigParser()
        config.read(config_path)
        return config.get("counsel", "name", fallback="Hemlata Singh")
    except Exception:
        return "Hemlata Singh"

def get_counsel_details() -> dict:
    """
    Returns full counsel details dictionary.
    """
    root = get_project_root()
    config_path = root / "LawNidhi" / "data" / "config.ini"
    
    details = {
        "name": "Hemlata Singh",
        "aliases": ["H. SINGH", "MS. HEMLATA SINGH", "HEMLATA SINGH"],
        "email": "navin.rathore@gmail.com"
    }
    
    if not config_path.exists():
        return details
        
    try:
        config = configparser.ConfigParser()
        config.read(config_path)
        if config.has_section("counsel"):
            details["name"] = config.get("counsel", "name", fallback=details["name"])
            aliases_str = config.get("counsel", "aliases", fallback="")
            if aliases_str:
                details["aliases"] = [a.strip() for a in aliases_str.split(",")]
            details["email"] = config.get("counsel", "email", fallback=details["email"])
    except Exception:
        pass
        
    return details
