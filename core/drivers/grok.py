from .base import BaseDriver
import asyncio
import random

class GrokDriver(BaseDriver):
    async def send_prompt(self, prompt: str, **kwargs):
        await self.dismiss_cookie_consent()
        editor_selector = 'textarea, div[contenteditable="true"], #prompt-textarea, [role="textbox"][contenteditable="true"]'
        editor_selector = f"{editor_selector} >> visible=true"
        
        await self.page.wait_for_selector(editor_selector, state='visible', timeout=15000)
        
        # Save the current number of responses before sending to avoid grabbing an old response
        self._initial_responses_count = await self.page.locator('.message-bubble').count()
        
        await self.type_human_like(editor_selector, prompt)
        
        # Wait a bit before sending (hesitation)
        await asyncio.sleep(random.uniform(0.5, 1.2))
        
        btn_selector = 'form button[type="submit"], button[aria-label*="end"], button[aria-label*="ubmit"], button[data-testid*="send"], button svg.lucide-arrow-right'
        
        send_btn = self.page.locator(btn_selector).first
        if await send_btn.is_visible() and await send_btn.is_enabled():
            await send_btn.click()
        else:
            await self.page.keyboard.press('Enter')

    async def wait_for_response(self, **kwargs) -> str:
        # Check either #last-reply-container .message-bubble or .message-bubble
        
        last_text = ""
        stable_count = 0
        
        while True:
            current_text = ""
            
            # Use same logic as content.js
            last_reply_container = self.page.locator("#last-reply-container")
            if await last_reply_container.count() > 0:
                bubbles = await last_reply_container.locator('.message-bubble').all()
            else:
                # Find all bubbles and filter (simplification: just take the last one if count > initial)
                all_bubbles = await self.page.locator('.message-bubble').all()
                if len(all_bubbles) > self._initial_responses_count:
                    bubbles = all_bubbles
                else:
                    bubbles = []
                    
            if bubbles:
                last_bubble = bubbles[-1]
                inner = last_bubble.locator('.response-content-markdown').first
                if await inner.count() > 0:
                    current_text = await inner.inner_text()
                else:
                    current_text = await last_bubble.inner_text()
            
            if current_text == last_text and len(current_text) > 0:
                stable_count += 1
                if stable_count >= 8: # 8 * 0.25s = 2s stable
                    return current_text
            else:
                stable_count = 0
                last_text = current_text
                
            await asyncio.sleep(0.25)

    async def wait_for_response_streaming(self, **kwargs):
        last_text = ""
        stable_count = 0
        
        while True:
            current_text = ""
            
            last_reply_container = self.page.locator("#last-reply-container")
            if await last_reply_container.count() > 0:
                bubbles = await last_reply_container.locator('.message-bubble').all()
            else:
                all_bubbles = await self.page.locator('.message-bubble').all()
                if len(all_bubbles) > self._initial_responses_count:
                    bubbles = all_bubbles
                else:
                    bubbles = []
                    
            if bubbles:
                last_bubble = bubbles[-1]
                inner = last_bubble.locator('.response-content-markdown').first
                if await inner.count() > 0:
                    current_text = await inner.inner_text()
                else:
                    current_text = await last_bubble.inner_text()
            
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
