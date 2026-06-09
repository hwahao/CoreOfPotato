"""
CoreNexus v1.0.0 — Utility helpers
NOTE: logging uses stderr so stdout stays clean for Native Messaging protocol.
"""
from __future__ import annotations

import logging
import os
import platform
import socket
import subprocess
import sys
import signal
from datetime import datetime, timezone

import time

SYSTEM_LOG_BUFFER = []

class MemoryLogHandler(logging.Handler):
    def __init__(self, buffer_list: list, max_size: int = 500):
        super().__init__()
        self.buffer_list = buffer_list
        self.max_size = max_size

    def emit(self, record):
        try:
            msg = self.format(record)
            level = record.levelname.lower()
            if level == "warning":
                level = "warn"
            elif level == "error":
                level = "error"
            else:
                level = "info"
            self.buffer_list.append({
                "timestamp": time.time(),
                "message": msg,
                "level": level
            })
            while len(self.buffer_list) > self.max_size:
                self.buffer_list.pop(0)
        except Exception:
            self.handleError(record)

# ───────────────────────── LOGGING ──────────────────────────


def setup_logger(name: str, log_file: str = None, level=logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        # Check if MemoryLogHandler is already attached
        has_memory_handler = any(isinstance(h, MemoryLogHandler) for h in logger.handlers)
        if not has_memory_handler:
            mh = MemoryLogHandler(SYSTEM_LOG_BUFFER)
            mh.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s %(message)s", datefmt="%H:%M:%S"))
            logger.addHandler(mh)
        return logger
    logger.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s %(message)s", datefmt="%H:%M:%S"
    )
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    
    mh = MemoryLogHandler(SYSTEM_LOG_BUFFER)
    mh.setFormatter(fmt)
    logger.addHandler(mh)
    
    if log_file:
        fh = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def kill_process_on_port(port: int):
    """Kill process using the given port. Cross-platform."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return  # Port is free
    except Exception as e:
        logging.getLogger("utils").warning(f"Error checking port: {e}")

    system = platform.system()
    try:
        if system in ("Linux", "Darwin"):
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True, text=True, timeout=5
            )
            for pid in result.stdout.strip().split("\n"):
                if pid:
                    try:
                        os.kill(int(pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    except Exception as e:
                        logging.getLogger("utils").warning(f"Failed to kill {pid}: {e}")
    except Exception as e:
        logging.getLogger("utils").warning(f"Error executing kill process: {e}")


# ─────────────────── CALLER / USER-ID PARSING ───────────────

# user field format: NaModu (6 characters)
# Examples: OCvien, CDenen, MaTest
# Na = 2-char caller prefix (OC, CD, Ma, ...)
# Modu = 4-char module name (vien, enen, Test, ...)

class CallerMapCache:
    def __init__(self):
        self._cache = None
        
    def get(self):
        if self._cache is None:
            from core.config import ROOT_DIR
            import json
            path = os.path.join(ROOT_DIR, "data", "caller_map.json")
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        self._cache = json.load(f)
                except Exception as e:
                    logging.getLogger("utils").warning(f"Error loading caller map: {e}")
            if self._cache is None:
                from core.config import load_config
                cfg = load_config()
                self._cache = cfg.get(
                    "caller_map", {"OC": "OpenClaw", "CD": "OpenCode"}
                )
        return self._cache

    def invalidate(self):
        self._cache = None

_caller_map = CallerMapCache()

def _get_caller_map() -> dict:
    return _caller_map.get()


def validate_user(user: str) -> tuple[dict | None, str | None]:
    """Validate user string based on 6-character format NaModu and caller mapping.
    Returns (parsed_dict, error_message).
    """
    user_str = str(user or "").strip()

    # 1. Check if user is missing or empty
    if not user_str:
        return None, "What's your name, dude?"

    # 2. Check if user has correct format (exactly 6 alphanumeric characters)
    if len(user_str) != 6 or not user_str.isalnum():
        return None, "Your name seems a bit off, doesn't it?"

    # 3. Check if caller prefix is recognized
    caller = user_str[0:2]
    modu = user_str[2:6]

    caller_map = _get_caller_map()
    if caller not in caller_map:
        return None, "Yo, what faction are you in?"

    day = today_str().replace("-", "")[4:]  # MMDD

    parsed = {
        "raw": user_str,
        "caller": caller,
        "caller_name": caller_map[caller],
        "modu": modu,
        "mmdd": day,
    }
    return parsed, None


def parse_user_or_default(user: str) -> dict:
    """Parse user ID or raise ValueError."""
    parsed, err = validate_user(user)
    if err:
        raise ValueError(err)
    return parsed
