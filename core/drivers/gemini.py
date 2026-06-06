from .base import BaseDriver
import asyncio
import random

class GeminiDriver(BaseDriver):
    async def send_prompt(self, prompt: str, **kwargs):
        await self.dismiss_cookie_consent()
        editor_selector = 'div.ql-editor, div[contenteditable="true"][role="textbox"], textarea'
        
        await self.page.wait_for_selector(editor_selector, state='visible', timeout=15000)
        
        await self.type_human_like(editor_selector, prompt)
        
        # Wait a bit before sending (hesitation)
        await asyncio.sleep(random.uniform(0.5, 1.2))
        
        btn_selector = 'button[aria-label*="Send"], button[aria-label*="Gửi"], button.send-button-container, button[class*="send-button"]'
        
        send_btn = self.page.locator(btn_selector).first
        if await send_btn.is_visible() and await send_btn.is_enabled():
            await send_btn.click()
        else:
            await self.page.keyboard.press('Enter')

    async def wait_for_response(self, **kwargs) -> str:
        response_selector = 'message-content, .model-response, .message-content'
        
        # Wait for at least one response to appear
        await self.page.wait_for_selector(response_selector, state='attached')
        
        last_text = ""
        stable_count = 0
        
        while True:
            elements = await self.page.locator(response_selector).all()
            if not elements:
                await asyncio.sleep(0.25)
                continue
                
            last_element = elements[-1]
            current_text = await last_element.inner_text()
            
            if current_text == last_text and len(current_text) > 0:
                stable_count += 1
                if stable_count >= 8: # 8 * 0.25s = 2s stable
                    return current_text
            else:
                stable_count = 0
                last_text = current_text
                
            await asyncio.sleep(0.25)

    async def wait_for_response_streaming(self, **kwargs):
        response_selector = 'message-content, .model-response, .message-content'
        await self.page.wait_for_selector(response_selector, state='attached')
        last_text = ""
        stable_count = 0
        
        while True:
            elements = await self.page.locator(response_selector).all()
            if not elements:
                await asyncio.sleep(0.25)
                continue
                
            last_element = elements[-1]
            current_text = await last_element.inner_text()
            
            if current_text != last_text and len(current_text) > 0:
                yield {"text": current_text, "done": False}
                stable_count = 0
                last_text = current_text
            elif len(current_text) > 0:
                stable_count += 1
                if stable_count >= 8: # 2 seconds stable
                    yield {"text": current_text, "done": True, "status": "done", "conversation_url": self.page.url}
                    break
            
            await asyncio.sleep(0.25)
