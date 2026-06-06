"""
Core of Potato v1.0.0 — Test Fixtures
"""
import asyncio
import os
import sys
import time
import json
import pytest
from dataclasses import dataclass
from typing import Optional

# Add project root and core/ to Python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "core"))

@dataclass
class MockWorkerSlot:
    id: str
    platform: str
    status: str
    current_url: str
    job_id: Optional[str]

class MockBrowserManager:
    """Mock BrowserManager that simulates Playwright browser workers for tests."""
    def __init__(self, config):
        self.config = config
        self.show_browser_window = True
        self.workers = {}
        for platform, count in config.get("workers", {}).items():
            self.workers[platform] = []
            for i in range(count):
                self.workers[platform].append(MockWorkerSlot(
                    id=f"{platform}-{i+1}",
                    platform=platform,
                    status="idle",
                    current_url="",
                    job_id=None
                ))
        self.queue_count = 0
        self.active_count = 0
        self._is_running = True

    async def start(self):
        self._is_running = True

    async def stop(self):
        self._is_running = False

    async def toggle_visibility(self):
        self.show_browser_window = not self.show_browser_window
        return self.show_browser_window

    async def get_slots_info(self):
        result = []
        for platform, slots in self.workers.items():
            for slot in slots:
                result.append({
                    "id": slot.id,
                    "driver": slot.platform,
                    "status": slot.status,
                    "currentJob": slot.job_id,
                    "url": slot.current_url
                })
        return result

    async def submit_job(self, job: dict) -> dict:
        if not self._is_running:
            raise RuntimeError("BrowserManager is not running")
        platform = job["model"]
        job_id = job["jobId"]
        slot = None
        for s in self.workers.get(platform, []):
            if s.status == "idle":
                slot = s
                break
        if slot:
            slot.status = "busy"
            slot.job_id = job_id
            
        try:
            await asyncio.sleep(0.05)
            if job["prompt"] == "FAIL_TEST":
                return {"status": "error", "error": "Simulated failure", "jobId": job_id}
            return {
                "status": "done",
                "answer": "Mock response from Core of Potato test bridge.",
                "conversation_url": f"https://{platform}.com/c/test-conv-123",
                "jobId": job_id
            }
        finally:
            if slot:
                slot.status = "idle"
                slot.job_id = None

    async def submit_job_streaming(self, job: dict):
        if not self._is_running:
            raise RuntimeError("BrowserManager is not running")
        platform = job["model"]
        
        yield {"text": "Mock", "done": False}
        await asyncio.sleep(0.01)
        yield {"text": "Mock response", "done": False}
        await asyncio.sleep(0.01)
        yield {
            "text": "Mock response from Core of Potato test bridge.",
            "done": True,
            "status": "done",
            "conversation_url": f"https://{platform}.com/c/test-conv-123"
        }

@pytest.fixture
def temp_data_dir(tmp_path):
    """Create a temporary data directory with required files."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    logs_dir = data_dir / "logs"
    logs_dir.mkdir()
    
    # Minimal caller_map
    caller_map = {"OC": "OpenClaw", "CD": "OpenCode"}
    (data_dir / "caller_map.json").write_text(json.dumps(caller_map))
    return str(data_dir)

@pytest.fixture
async def client(aiohttp_client, temp_data_dir):
    """Create a test client with a mocked browser manager."""
    from core.server import CNAdapterServer
    from core.storage import Storage

    server = CNAdapterServer()
    server.config = {
        "port": 2809,
        "host": "127.0.0.1",
        "log_level": "INFO",
        "job_accept_timeout": 5,
        "job_result_timeout": 10,
        "url_default_mode": "usage_based",
        "url_default_max_uses": 10,
        "url_default_ttl_minutes": 30,
        "log_retention_days": 3,
        "default_urls": {
            "grok": "https://grok.com",
            "gemini": "https://gemini.google.com/app",
            "chatgpt": "https://chatgpt.com"
        },
        "workers": {
            "grok": 3,
            "gemini": 1,
            "chatgpt": 2
        },
        "security": {
            "admin_token": "test-secret-token",
            "cors_origins": ["*"],
            "require_auth": False
        }
    }
    server.storage = Storage(temp_data_dir)
    server.browser = MockBrowserManager(server.config)
    server.job_results = {}
    server.image_store = {}
    server._start_time = time.time()
    server._jobs_today = 0
    server._midnight_task = None

    app = server.create_app()
    app["_server"] = server
    return await aiohttp_client(app)
