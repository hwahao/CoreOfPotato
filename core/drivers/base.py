from abc import ABC, abstractmethod
from playwright.async_api import Page
import asyncio
import random

class BaseDriver(ABC):
    def __init__(self, page: Page):
        self.page = page

    async def execute(self, prompt: str, **kwargs) -> str:
        """Execute the prompt by sending it and waiting for response."""
        await self.send_prompt(prompt, **kwargs)
        if kwargs.get('streaming', False):
            return await self.wait_for_response_streaming(**kwargs)
        return await self.wait_for_response(**kwargs)

    @abstractmethod
    async def send_prompt(self, prompt: str, **kwargs):
        """Send the prompt to the AI."""
        pass

    @abstractmethod
    async def wait_for_response(self, **kwargs) -> str:
        """Wait for the full response and return it."""
        pass

    @abstractmethod
    async def wait_for_response_streaming(self, **kwargs):
        """Wait for the response and yield chunks."""
        pass

    async def dismiss_cookie_consent(self):
        """Dismiss standard cookie consent popups if they appear."""
        selectors = [
            "#onetrust-accept-btn-handler",
            "#cookie-accept",
            ".cookie-accept",
            "button:has-text('Accept')",
            "button:has-text('Accept All')"
        ]
        for sel in selectors:
            try:
                btn = self.page.locator(sel)
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click(timeout=1000)
                    await asyncio.sleep(0.5)
            except Exception:
                pass

    async def type_human_like(self, selector: str, text: str):
        """Implement human-like typing using page.type with random delays, 
        and for >500 chars, paste + type tail."""
        
        # Focus the element
        locator = self.page.locator(selector).first
        await locator.focus()
        await asyncio.sleep(0.1)

        if len(text) > 500:
            # Type first sentence
            period_idx = text.find('.')
            if period_idx != -1 and period_idx < len(text) - 1:
                first_part = text[:period_idx + 1]
                rest = text[period_idx + 1:]
            else:
                split_len = min(15, len(text))
                first_part = text[:split_len]
                rest = text[split_len:]

            # Paste the rest
            await locator.fill(rest)
            await asyncio.sleep(0.2)

            # Move cursor to the beginning
            await self.page.keyboard.press('Control+A')
            await asyncio.sleep(0.1)
            await self.page.keyboard.press('ArrowLeft')
            await asyncio.sleep(0.1)

            # Type the first part
            for char in first_part:
                await self.page.keyboard.insert_text(char)
                await asyncio.sleep(random.uniform(0.04, 0.09))
        else:
            # Type normally with press_sequentially
            await locator.press_sequentially(text, delay=random.randint(30, 80))
