"""
Core of Potato v1.0.0 — BrowserManager Unit Tests
"""
import asyncio
import pytest
from core.browser_mgr import BrowserManager

def test_browser_mgr_initialization():
    """Verify that BrowserManager parses the configuration correctly and initializes worker slots."""
    config = {
        "browser": {
            "show_browser_window": True,
            "user_data_dir": "./custom_profiles_dir",
            "executable_path": "/usr/bin/chrome",
            "viewport": {"width": 1024, "height": 768}
        },
        "workers": {
            "grok": 2,
            "gemini": 3
        },
        "default_urls": {
            "grok": "https://grok.com",
            "gemini": "https://gemini.google.com"
        }
    }
    
    mgr = BrowserManager(config)
    
    assert mgr.show_browser_window is True
    assert mgr.executable_path == "/usr/bin/chrome"
    assert mgr.viewport == {"width": 1024, "height": 768}
    
    # Check worker slots are initially empty (deferred loading)
    assert mgr.workers == {}
@pytest.mark.asyncio

async def test_browser_mgr_apply_config():
    """Verify that BrowserManager dynamically adds workers."""
    config = {
        "browser": {"show_browser_window": True},
        "default_urls": {}
    }
    mgr = BrowserManager(config)
    
    await mgr.apply_worker_config({"grok": 2, "gemini": 3})
    
    assert "grok" in mgr.workers
    assert "gemini" in mgr.workers
    assert len(mgr.workers["grok"]) == 2
    assert len(mgr.workers["gemini"]) == 3
    
    slot = mgr.workers["grok"][0]
    assert slot.id == "grok-1"
    assert slot.platform == "grok"
    assert slot.status == "offline"
    assert slot.job_id is None

@pytest.mark.asyncio
async def test_browser_mgr_sequential_queueing():
    """Verify that multiple jobs with the same nav_key are executed sequentially,
    while different nav_keys can be executed in parallel.
    """
    config = {
        "browser": {"show_browser_window": True},
        "default_urls": {}
    }
    mgr = BrowserManager(config)
    mgr._is_running = True  # Bypass is_running check
    
    # Setup two mock worker slots for grok
    from core.browser_mgr import WorkerSlot
    mgr.workers["grok"] = [
        WorkerSlot(id="grok-1", platform="grok", page=None, status="idle", current_url="", job_id=None, nav_key=None),
        WorkerSlot(id="grok-2", platform="grok", page=None, status="idle", current_url="", job_id=None, nav_key=None),
    ]
    
    # 1. First job for OCtest_grok acquires slot
    slot1 = await mgr._acquire_slot(platform="grok", job_id="job1", nav_key="OCtest_grok")
    assert slot1.id == "grok-1"
    assert slot1.status == "busy"
    assert slot1.nav_key == "OCtest_grok"
    
    # 2. Second job with same nav_key (OCtest_grok) should NOT acquire slot, even though grok-2 is idle.
    # We test this by using asyncio.wait_for with a short timeout.
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            mgr._acquire_slot(platform="grok", job_id="job2", nav_key="OCtest_grok"),
            timeout=0.2
        )
        
    # 3. A job with a different nav_key (e.g., OCdemo_grok) SHOULD be able to acquire the idle grok-2 immediately.
    slot2 = await mgr._acquire_slot(platform="grok", job_id="job3", nav_key="OCdemo_grok")
    assert slot2.id == "grok-2"
    assert slot2.status == "busy"
    assert slot2.nav_key == "OCdemo_grok"
    
    # 4. Once the first job finishes and slot1 is freed, a new job with OCtest_grok can acquire a slot.
    slot1.status = "idle"
    slot1.job_id = None
    slot1.nav_key = None
    
    slot4 = await mgr._acquire_slot(platform="grok", job_id="job4", nav_key="OCtest_grok")
    assert slot4.id == "grok-1"
    assert slot4.status == "busy"
    assert slot4.nav_key == "OCtest_grok"
