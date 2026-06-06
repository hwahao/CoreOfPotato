import asyncio
import os
from dataclasses import dataclass
from typing import Optional, Dict, List
from playwright.async_api import async_playwright, Page
from core.drivers import get_driver
from core.utils import setup_logger

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adapter.log")
logger = setup_logger("CNBrowser", LOG_FILE)

@dataclass
class WorkerSlot:
    id: str
    platform: str
    page: Optional[Page]
    status: str  # "idle" | "busy" | "offline"
    current_url: str
    job_id: Optional[str]
    nav_key: Optional[str] = None

class BrowserManager:
    def __init__(self, config: dict, storage=None):
        self.config = config
        self.storage = storage
        self.playwright = None
        self.browser = None
        self.context = None
        self.workers: Dict[str, List[WorkerSlot]] = {}
        
        browser_cfg = config.get("browser", {})
        self.show_browser_window = browser_cfg.get("show_browser_window", True)
        self.user_data_dir = browser_cfg.get("user_data_dir")
        if self.user_data_dir:
            from core.config import ROOT_DIR
            self.user_data_dir = os.path.abspath(os.path.join(ROOT_DIR, self.user_data_dir))
        else:
            from core.config import ROOT_DIR
            self.user_data_dir = os.path.abspath(os.path.join(ROOT_DIR, "data", "browser_profiles"))
            
        self.executable_path = browser_cfg.get("executable_path") or None
        self.viewport = browser_cfg.get("viewport", {"width": 1280, "height": 800})
        self._is_running = False
        self._queue_count_val = 0
        self.hub_page = None
        self.workers: Dict[str, List[WorkerSlot]] = {}

    @property
    def queue_count(self) -> int:
        return self._queue_count_val

    @property
    def active_count(self) -> int:
        count = 0
        for slots in self.workers.values():
            for slot in slots:
                if slot.status == "busy":
                    count += 1
        return count

    async def start(self):
        """Initialize the browser manager and start the workers."""
        logger.info(f"Starting BrowserManager (show_browser_window={self.show_browser_window})")
        self.playwright = await async_playwright().start()
        await self._launch_browser()
        self._is_running = True

    async def _launch_browser(self):
        """Launch standard Chromium browser with persistent context and setup worker pages."""
        os.makedirs(self.user_data_dir, exist_ok=True)
        
        launch_args = [
            "--disable-blink-features=AutomationControlled",
        ]
        
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            headless=not self.show_browser_window,
            executable_path=self.executable_path,
            viewport=self.viewport,
            args=launch_args,
            ignore_default_args=["--enable-automation"]
        )
        
        # We leave the default blank page open to prevent the context from auto-closing.
        # open_hub_page will reuse it.


    async def stop(self):
        """Stop the browser context and Playwright."""
        self._is_running = False
        if self.context:
            await self.context.close()
            self.context = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
            
        for platform, slots in self.workers.items():
            for slot in slots:
                slot.page = None
                slot.status = "offline"

    async def toggle_visibility(self) -> bool:
        """Toggle headed/headless. Returns new show_browser_window state."""
        self.show_browser_window = not self.show_browser_window
        logger.info(f"Toggling show browser window mode to: {self.show_browser_window}")
        
        hub_url = self.hub_page.url if self.hub_page else None
        
        if self.context:
            await self.context.close()
            self.context = None
            
        await self._launch_browser()
        
        if hub_url:
            await self.open_hub_page(hub_url)
            
        await self.apply_worker_config(self.config.get("workers", {}))
        
        return self.show_browser_window

    async def open_hub_page(self, url: str):
        """Open the Hub page directly in the Playwright context."""
        if not self.context:
            return
        logger.info(f"Opening Hub page at {url}")
        
        # Reuse the default blank page if it exists
        pages = self.context.pages
        if len(pages) > 0 and pages[0].url == "about:blank":
            self.hub_page = pages[0]
        else:
            self.hub_page = await self.context.new_page()
            
        await self.hub_page.goto(url)

    async def apply_worker_config(self, workers_config: dict):
        """Dynamically add or remove worker slots based on new configuration."""
        self.config["workers"] = workers_config
        
        # We need to synchronize self.workers with the new config
        for platform, target_count in workers_config.items():
            current_slots = self.workers.get(platform, [])
            
            # Add new slots if needed
            while len(current_slots) < target_count:
                new_idx = len(current_slots) + 1
                slot_id = f"{platform}-{new_idx}"
                slot = WorkerSlot(
                    id=slot_id,
                    platform=platform,
                    page=None,
                    status="offline",
                    current_url="",
                    job_id=None
                )
                
                if self.context:
                    logger.info(f"Dynamically creating worker slot page: {slot.id}")
                    slot.page = await self.context.new_page()
                    slot.status = "idle"
                    default_url = self.config.get("default_urls", {}).get(platform, f"https://{platform}.com")
                    slot.current_url = default_url
                    try:
                        await slot.page.goto(default_url, timeout=30000)
                    except Exception as e:
                        logger.warning(f"Initial navigation failed for slot {slot.id}: {e}")
                
                current_slots.append(slot)
            
            # Remove excess slots if needed
            while len(current_slots) > target_count:
                slot_to_remove = current_slots.pop()
                logger.info(f"Dynamically removing worker slot: {slot_to_remove.id}")
                if slot_to_remove.page:
                    try:
                        await slot_to_remove.page.close()
                    except Exception:
                        pass
                        
            self.workers[platform] = current_slots

    async def get_slots_info(self) -> list[dict]:
        """Return worker slot status information."""
        result = []
        for platform, slots in self.workers.items():
            for slot in slots:
                result.append({
                    "id": slot.id,
                    "driver": slot.platform,
                    "status": slot.status,
                    "currentJob": slot.job_id,
                    "url": slot.page.url if slot.page else ""
                })
        return result

    async def _acquire_slot(self, platform: str, job_id: str, nav_key: str) -> WorkerSlot:
        """Wait for and acquire an idle worker slot, ensuring sequential processing for same nav_key."""
        self._queue_count_val += 1
        try:
            while True:
                if not self._is_running:
                    raise RuntimeError("BrowserManager is not running")
                slots = self.workers.get(platform, [])
                
                # Check if another slot is busy with the same nav_key
                same_nav_key_busy = False
                if nav_key:
                    for slot in slots:
                        if slot.status == "busy" and slot.nav_key == nav_key:
                            same_nav_key_busy = True
                            break
                            
                if not same_nav_key_busy:
                    for slot in slots:
                        if slot.status == "idle":
                            slot.status = "busy"
                            slot.job_id = job_id
                            slot.nav_key = nav_key
                            return slot
                await asyncio.sleep(0.5)
        finally:
            self._queue_count_val -= 1

    async def submit_job(self, job: dict) -> dict:
        """Submit job, wait for result, and return response dict."""
        platform = job["model"]
        job_id = job["jobId"]
        nav_key = job.get("navKey", "")
        
        slot = await self._acquire_slot(platform, job_id, nav_key)
        try:
            logger.info(f"Slot {slot.id} acquired for job {job_id}")
            
            target_url = job.get("url")
            # Resolve the latest URL from storage in case it was updated by a queued job
            if self.storage and nav_key:
                stored_url = self.storage.get_url_by_key(nav_key)
                if stored_url:
                    target_url = stored_url
                    
            if target_url and slot.page.url != target_url:
                try:
                    await slot.page.goto(target_url, timeout=30000)
                except Exception as e:
                    logger.warning(f"Failed to navigate slot {slot.id} to {target_url}: {e}")
            
            driver_class = get_driver(platform)
            if not driver_class:
                raise ValueError(f"No driver found for platform {platform}")
                
            driver = driver_class(slot.page)
            await driver.send_prompt(job["prompt"])
            
            timeout = self.config.get("job_result_timeout", 180)
            answer = await asyncio.wait_for(driver.wait_for_response(), timeout=timeout)
            
            slot.current_url = slot.page.url
            return {
                "status": "done",
                "answer": answer,
                "conversation_url": slot.page.url,
                "jobId": job_id
            }
        except Exception as e:
            logger.error(f"Error executing job {job_id} on slot {slot.id}: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "jobId": job_id
            }
        finally:
            slot.status = "idle"
            slot.job_id = None
            slot.nav_key = None

    async def submit_job_streaming(self, job: dict):
        """Submit job, stream response chunks as async generator."""
        platform = job["model"]
        job_id = job["jobId"]
        nav_key = job.get("navKey", "")
        
        slot = await self._acquire_slot(platform, job_id, nav_key)
        try:
            logger.info(f"Slot {slot.id} acquired for streaming job {job_id}")
            
            target_url = job.get("url")
            # Resolve the latest URL from storage in case it was updated by a queued job
            if self.storage and nav_key:
                stored_url = self.storage.get_url_by_key(nav_key)
                if stored_url:
                    target_url = stored_url
                    
            if target_url and slot.page.url != target_url:
                try:
                    await slot.page.goto(target_url, timeout=30000)
                except Exception as e:
                    logger.warning(f"Failed to navigate slot {slot.id} to {target_url}: {e}")
                    
            driver_class = get_driver(platform)
            if not driver_class:
                raise ValueError(f"No driver found for platform {platform}")
                
            driver = driver_class(slot.page)
            await driver.send_prompt(job["prompt"])
            
            async for chunk in driver.wait_for_response_streaming():
                yield chunk
                
            slot.current_url = slot.page.url
        except Exception as e:
            logger.error(f"Error executing streaming job {job_id} on slot {slot.id}: {e}", exc_info=True)
            yield {
                "status": "error",
                "error": str(e),
                "jobId": job_id
            }
        finally:
            slot.status = "idle"
            slot.job_id = None
            slot.nav_key = None
