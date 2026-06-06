import asyncio
import json
import os
import signal
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

from aiohttp import web

try:
    signal.signal(signal.SIGPIPE, signal.SIG_IGN)
except AttributeError:
    pass

from core.browser_mgr import BrowserManager
from core.config import ROOT_DIR, SCRIPT_DIR, load_config
from core.storage import Storage
from core.utils import (
    kill_process_on_port,
    now_iso,
    setup_logger,
    today_str,
    validate_user,
)
from core.routes import setup_routes

LOG_FILE = os.path.join(SCRIPT_DIR, "adapter.log")
logger = setup_logger("CNAdapter", LOG_FILE)

# Model → platform + mode mapping
MODEL_MAP = {
    "gemini": "gemini",
    "chatgpt": "chatgpt",
    "gpt": "chatgpt",
    "grok": "grok",
}

def resolve_model(raw: str) -> str:
    raw_lower = raw.strip().lower()
    if raw_lower not in MODEL_MAP:
        raise ValueError(f"Unknown model: {raw}")
    return MODEL_MAP[raw_lower]

def get_default_url(model: str, platform: str) -> str:
    cfg = load_config()
    urls = cfg.get("default_urls", {})
    return urls.get(platform, urls.get(model, "https://grok.com"))

class CNAdapterServer:
    def __init__(self):
        self.config = load_config()
        self.storage = Storage(os.path.join(ROOT_DIR, "data"))
        self.browser = BrowserManager(self.config, self.storage)
        self.job_results: dict = {}
        self.image_store: dict = {}
        self._start_time = time.time()
        self._jobs_today = 0
        self._midnight_task = None
        self._max_results = 500
        self._max_images = 200
        self._result_ttl = 3600

    def _build_log_entry(
        self, hub_job_id, user, nav_key, parsed, model_raw, platform, 
        prompt, system_msg, text, elapsed_ms, status
    ):
        request_id = self.storage.next_request_id()
        return {
            "request_id": request_id,
            "instance": self.storage._counter_data["request_count"],
            "job_id": hub_job_id,
            "user": user,
            "nav_key": nav_key,
            "caller": parsed["caller"],
            "modu": parsed["modu"],
            "date": today_str(),
            "created": now_iso(),
            "model": model_raw,
            "platform": platform,
            "total_time_ms": elapsed_ms,
            "status": "completed" if status == "done" else "error",
            "steps": [
                {
                    "step": 1,
                    "label": self.storage.next_step_label(parsed["modu"]),
                    "module": parsed["modu"],
                    "type": "chat",
                    "prompt_sent": prompt,
                    "system_prompt": system_msg or "",
                    "output": text[:5000],
                    "response_time_ms": elapsed_ms,
                    "model": platform,
                    "status": "success" if status == "done" else "error",
                }
            ],
        }

    async def api_chat_completions(self, request: web.Request) -> web.Response:
        start_time = time.time()
        body = await request.json()
        logger.info(f"Incoming request keys: {list(body.keys())}, model: {body.get('model')}, user: {body.get('user')}")
        
        messages = body.get("messages", [])
        model_raw = body.get("model", "Grok-Fast")

        if not model_raw or model_raw.lower() not in MODEL_MAP:
            return web.json_response({"error": f"Model '{model_raw}' is not supported"}, status=400)
        
        user = body.get("user", "").strip()
        if not user:
            auth_header = request.headers.get("Authorization", "").strip()
            if auth_header.lower().startswith("bearer "):
                user = auth_header[7:].strip()
                
        if not user:
            user = request.headers.get("x-user", "").strip()
        if not user:
            user = request.headers.get("user", "").strip()

        if not messages:
            return web.json_response({"error": "messages list is required"}, status=400)

        parsed, err_msg = validate_user(user)
        if err_msg:
            logger.warning(f"Request Rejected: {err_msg} | user='{user}' | model='{model_raw}'")
            return web.json_response({"error": {"message": err_msg}}, status=400)

        platform = resolve_model(model_raw)
        default_url = get_default_url(model_raw, platform)

        nav_key_without_model = f"{parsed['caller']}{parsed['modu']}"
        nav_key = f"{nav_key_without_model}_{platform}"
        saved_url = self.storage.get_url_by_key(nav_key)

        system_msg = next((m.get("content") for m in messages if m.get("role") == "system"), None)
        last_msg = next((m for m in reversed(messages) if m.get("role") == "user"), None)
        if not last_msg:
            return web.json_response({"error": "No user message found"}, status=400)

        last_content = last_msg.get("content", "")
        files = []
        last_text = ""
        if isinstance(last_content, list):
            for part in last_content:
                if part.get("type") == "text":
                    last_text += part.get("text", "")
                elif part.get("type") == "image_url":
                    img_url = part.get("image_url", {}).get("url", "")
                    if img_url:
                        files.append(img_url)
        else:
            last_text = str(last_content)

        if files:
            new_files = []
            for f in files:
                if isinstance(f, str) and f.startswith("data:") and len(f) > 1000:
                    img_id = uuid.uuid4().hex[:12]
                    self.image_store[img_id] = f
                    new_files.append(f"http://localhost:{self.config['port']}/api/image/{img_id}")
                else:
                    new_files.append(f)
            files = new_files

        prompt_parts = []
        if system_msg:
            prompt_parts.append(f"[System Instructions:] {system_msg}")
        prompt_parts.append(last_text)
        prompt = "\n\n".join(prompt_parts)

        num = self.storage.get_next_job_number(nav_key_without_model)
        job_id = f"{nav_key_without_model}{parsed['mmdd']}{num:05d}"
        job_payload = {
            "type": "chat",
            "jobId": job_id,
            "navKey": nav_key,
            "url": saved_url or default_url,
            "prompt": prompt,
            "files": files,
            "model": platform,
            "_raw_user": user,
        }

        stream = body.get("stream", False)

        if not stream:
            # Synchronous processing
            try:
                result = await self.browser.submit_job(job_payload)
            except Exception as e:
                return web.json_response({"error": str(e)}, status=500)

            answer = result.get("answer", "") or result.get("text", "")
            status = result.get("status", "done")
            conversation_url = result.get("conversation_url", "")
            elapsed_ms = int((time.time() - start_time) * 1000)

            if status == "done" and conversation_url:
                self.storage.save_url(nav_key, conversation_url)
                
            self.job_results[job_id] = {**result, "_ts": time.time()}
            self._jobs_today += 1

            if status == "error":
                return web.json_response({"error": result.get("error", "Unknown error")}, status=500)

            log_entry = self._build_log_entry(
                job_id, user, nav_key, parsed, model_raw, platform,
                prompt, system_msg, answer, elapsed_ms, status
            )
            self.storage.write_log(log_entry["request_id"], log_entry)

            response_data = {
                "id": f"chatcmpl-{job_id}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model_raw,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": answer},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": len(prompt) // 4,
                    "completion_tokens": len(answer) // 4,
                    "total_tokens": (len(prompt) + len(answer)) // 4,
                },
            }
            return web.json_response(response_data)

        else:
            response = web.StreamResponse()
            response.headers["Content-Type"] = "text/event-stream"
            response.headers["Cache-Control"] = "no-cache"
            response.headers["Connection"] = "keep-alive"
            await response.prepare(request)

            last_sent_len = 0
            full_text = ""
            final_status = "done"
            conversation_url = ""

            try:
                async for chunk in self.browser.submit_job_streaming(job_payload):
                    text = chunk.get("text", "")
                    done = chunk.get("done", False)
                    error = chunk.get("error")
                    status = chunk.get("status", "chunk")
                    conversation_url = chunk.get("conversation_url", conversation_url)

                    if error:
                        error_data = json.dumps({"error": {"message": error}})
                        await response.write(f"data: {error_data}\n\n".encode())
                        final_status = "error"
                        break

                    full_text = text
                    if len(text) > last_sent_len:
                        new_tokens = text[last_sent_len:]
                        if new_tokens:
                            if 0xD800 <= ord(new_tokens[-1]) <= 0xDBFF:
                                new_tokens = new_tokens[:-1]
                                last_sent_len = len(text) - 1
                            else:
                                last_sent_len = len(text)

                        if new_tokens:
                            chunk_data = {
                                "id": f"chatcmpl-{job_id}",
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": model_raw,
                                "choices": [{
                                    "index": 0,
                                    "delta": {"content": new_tokens},
                                    "finish_reason": None
                                }]
                            }
                            await response.write(f"data: {json.dumps(chunk_data)}\n\n".encode("utf-8", "ignore"))

                    if done:
                        final_status = "done" if status == "done" else "error"
                        break

            except Exception as e:
                logger.error(f"Error in streaming: {e}")
                final_status = "error"

            elapsed_ms = int((time.time() - start_time) * 1000)

            if final_status == "done" and conversation_url:
                self.storage.save_url(nav_key, conversation_url)

            self.job_results[job_id] = {"status": final_status, "answer": full_text, "conversation_url": conversation_url, "_ts": time.time()}
            self._jobs_today += 1

            log_entry = self._build_log_entry(
                job_id, user, nav_key, parsed, model_raw, platform,
                prompt, system_msg, full_text, elapsed_ms, final_status
            )
            self.storage.write_log(log_entry["request_id"], log_entry)

            final_chunk_data = {
                "id": f"chatcmpl-{job_id}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model_raw,
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }]
            }
            await response.write(f"data: {json.dumps(final_chunk_data)}\n\n".encode())
            await response.write(b"data: [DONE]\n\n")

            return response

    async def _prune_caches(self):
        while True:
            await asyncio.sleep(600)
            now = time.time()
            try:
                expired = [k for k, v in self.job_results.items() if now - v.get("_ts", 0) > self._result_ttl]
                for k in expired:
                    self.job_results.pop(k, None)
                while len(self.job_results) > self._max_results:
                    oldest = next(iter(self.job_results))
                    self.job_results.pop(oldest, None)
                while len(self.image_store) > self._max_images:
                    oldest = next(iter(self.image_store))
                    self.image_store.pop(oldest, None)
            except Exception as e:
                logger.error(f"Error during cache pruning: {e}")

    async def _midnight_cleanup(self):
        while True:
            now_dt = datetime.now(timezone.utc)
            next_midnight = now_dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            wait_sec = (next_midnight - now_dt).total_seconds()
            await asyncio.sleep(wait_sec)
            self.storage.cleanup_old_logs()
            logger.info("Midnight log cleanup completed")

    def create_app(self):
        # Reduce client_max_size to 10MB
        app = web.Application(client_max_size=10 * 1024 * 1024)

        @web.middleware
        async def cors_mw(request, handler):
            allowlist = self.config.get("cors_allowlist", ["*"])
            origin = request.headers.get("Origin")

            def set_cors_headers(headers):
                if "*" in allowlist or origin in allowlist:
                    headers["Access-Control-Allow-Origin"] = origin if origin else "*"
                headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
                headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Admin-Token, X-User, User"

            if request.method == "OPTIONS":
                resp = web.Response(status=200)
                set_cors_headers(resp.headers)
                return resp
            
            try:
                resp = await handler(request)
            except web.HTTPException as ex:
                set_cors_headers(ex.headers)
                raise ex
            
            set_cors_headers(resp.headers)
            return resp

        app.middlewares.append(cors_mw)

        # OpenAI-compatible API
        app.router.add_post("/v1/chat/completions", self.api_chat_completions)

        # Setup admin routes
        setup_routes(app, self)

        # Serve static files for /hub
        hub_path = os.path.join(ROOT_DIR, "hub")
        if os.path.exists(hub_path):
            async def redirect_hub(request):
                return web.HTTPFound("/hub/index.html")
            app.router.add_get("/hub", redirect_hub)
            app.router.add_get("/hub/", redirect_hub)
            app.router.add_static("/hub", hub_path)

        return app

    async def start(self):
        port = self.config.get("port", 2809)
        host = self.config.get("host", "0.0.0.0")

        logger.info("Starting Core of Potato 1.0.0 Server")

        await self.browser.start()

        self.storage.cleanup_old_logs()
        self._midnight_task = asyncio.create_task(self._midnight_cleanup())
        asyncio.create_task(self._prune_caches())

        if os.environ.get("CN_RESTARTED") != "1":
            kill_process_on_port(port)
        await asyncio.sleep(0.5)

        app = self.create_app()

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()

        logger.info("=" * 50)
        logger.info("  Core of Potato v1.0.0 — Running")
        logger.info(f"  PID       : {os.getpid()}")
        logger.info(f"  REST API  : http://{host}:{port}/api/")
        logger.info(f"  OpenAI    : http://{host}:{port}/v1/chat/completions")
        logger.info("=" * 50)

        url_host = "127.0.0.1" if host == "0.0.0.0" else host
        hub_url = f"http://{url_host}:{port}/hub"
        
        try:
            await self.browser.open_hub_page(hub_url)
        except Exception as e:
            logger.error(f"Failed to open Hub page in Playwright context: {e}")

        while True:
            await asyncio.sleep(3600)

def main():
    logger.info(f"Core of Potato v1.0.0 starting — {now_iso()}")
    server = CNAdapterServer()
    try:
        asyncio.run(server.start())
        return 0
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
        return 0
    except Exception as e:
        logger.error(f"Fatal: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())
