"""
CoreNexus v1.0.0 — Config loader
"""

import json
import logging
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

def load_config() -> dict:
    cfg_path = os.path.join(ROOT_DIR, "config.json")
    defaults = {
        "port": 2809,
        "host": "127.0.0.1",
        "log_level": "INFO",
        "job_accept_timeout": 10,
        "job_result_timeout": 180,
        "url_default_mode": "usage_based",
        "url_default_max_uses": 10,
        "url_default_ttl_minutes": 30,
        "log_retention_days": 3,
        "default_urls": {
            "grok": "https://grok.com",
            "gemini": "https://gemini.google.com",
            "chatgpt": "https://chatgpt.com",
        },
        "workers": {
            "grok": 3,
            "gemini": 1,
            "chatgpt": 2,
        },
        "caller_map": {
            "OC": "OpenClaw",
            "CD": "OpenCode",
        },
        "browser": {
            "executable_path": None,
            "show_browser_window": True,
            "user_data_dir": None,
            "viewport": {"width": 1280, "height": 800}
        },
        "security": {
            "admin_token": "admin-token-change-me",
            "cors_origins": ["*"],
            "require_auth": False
        }
    }
    
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    if "default_urls" in loaded and isinstance(loaded["default_urls"], dict):
                        defaults["default_urls"].update(loaded.pop("default_urls"))
                    if "workers" in loaded and isinstance(loaded["workers"], dict):
                        defaults["workers"].update(loaded.pop("workers"))
                    if "caller_map" in loaded and isinstance(loaded["caller_map"], dict):
                        defaults["caller_map"].update(loaded.pop("caller_map"))
                    if "browser" in loaded and isinstance(loaded["browser"], dict):
                        defaults["browser"].update(loaded.pop("browser"))
                    if "security" in loaded and isinstance(loaded["security"], dict):
                        defaults["security"].update(loaded.pop("security"))
                    defaults.update(loaded)
        except Exception as e:
            logging.getLogger("config").warning(f"Failed to parse config.json: {e}")
            
    # Validation
    try:
        defaults["port"] = int(defaults["port"])
    except (ValueError, TypeError):
        logging.getLogger("config").warning("Invalid port in config, using default 2809")
        defaults["port"] = 2809
        
    return defaults
