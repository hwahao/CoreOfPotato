import os
import json
import time
from aiohttp import web

from core.utils import now_iso, today_str
from core.config import ROOT_DIR, load_config

def require_admin(handler):
    async def wrapper(self, request):
        sec_cfg = self.config.get("security", {})
        token = sec_cfg.get("admin_token", self.config.get("admin_token", ""))
        
        # If no token is configured, allow access
        if not token:
            return await handler(self, request)
            
        # If token matches, allow access
        if request.headers.get("X-Admin-Token") == token:
            return await handler(self, request)
            
        # Check same-origin requests (e.g. from the served Hub UI)
        origin = request.headers.get("Origin")
        referer = request.headers.get("Referer", "")
        host = request.host
        
        is_same_origin = False
        if origin and (origin == f"http://{host}" or origin == f"https://{host}"):
            is_same_origin = True
        elif referer and (referer.startswith(f"http://{host}/") or referer.startswith(f"https://{host}/")):
            is_same_origin = True
            
        if is_same_origin:
            return await handler(self, request)
            
        return web.json_response({"error": "Unauthorized"}, status=401)
    return wrapper

class APIRoutes:
    def __init__(self, server):
        self.server = server
        self.config = server.config
        self.storage = server.storage
        self.browser = server.browser

    async def api_health(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "ok",
                "version": "1.0.1",
                "uptime_seconds": int(time.time() - self.server._start_time),
                "jobs_today": self.server._jobs_today,
                "adapter": "CoreNexus",
                "port": self.config.get("port", 2809),
                "workers": self.config.get("workers", {}),
                "timestamp": now_iso(),
            }
        )

    @require_admin
    async def api_status(self, request: web.Request) -> web.Response:
        slots = await self.browser.get_slots_info() if hasattr(self.browser, "get_slots_info") else {}
        return web.json_response(
            {
                "status": "ok",
                "version": "1.0.1",
                "port": self.config.get("port", 2809),
                "uptime_seconds": int(time.time() - self.server._start_time),
                "jobs_today": self.server._jobs_today,
                "active_count": self.browser.active_count if hasattr(self.browser, "active_count") else 0,
                "queue_count": self.browser.queue_count if hasattr(self.browser, "queue_count") else 0,
                "workers": self.config.get("workers", {}),
                "default_urls": self.config.get("default_urls", {}),
                "slots": slots,
                "show_browser_window": getattr(self.browser, "show_browser_window", True),
                "timestamp": now_iso(),
            }
        )

    @require_admin
    async def api_url_config(self, request: web.Request) -> web.Response:
        body = await request.json()
        key = body.get("key", "").strip()
        mode = body.get("mode", "").strip()
        if not key or mode not in ("fixed", "time_based", "usage_based"):
            return web.json_response(
                {"error": "key and mode (fixed|time_based|usage_based) required"},
                status=400,
            )
        self.storage.set_url_config(
            key,
            mode,
            ttl_minutes=body.get("ttl_minutes"),
            max_uses=body.get("max_uses"),
        )
        return web.json_response({"status": "ok"})

    @require_admin
    async def api_url_delete(self, request: web.Request) -> web.Response:
        key = request.match_info["key"]
        self.storage.delete_url_by_key(key)
        return web.json_response({"status": "deleted", "key": key})

    @require_admin
    async def api_url_clear_all(self, request: web.Request) -> web.Response:
        self.storage.clear_all_urls()
        return web.json_response({"status": "ok", "message": "All saved URLs cleared"})

    @require_admin
    async def api_url_configs(self, request: web.Request) -> web.Response:
        return web.json_response({"jobs": self.storage.get_all_job_configs()})

    @require_admin
    async def api_log_summary(self, request: web.Request) -> web.Response:
        date_str = request.query.get("date", today_str())
        logs = self.storage.get_logs_for_date(date_str)
        return web.json_response(
            {
                "date": date_str,
                "count": len(logs),
                "logs": logs[-50:],
            }
        )

    @require_admin
    async def api_log_export(self, request: web.Request) -> web.Response:
        date_str = request.query.get("date", today_str())
        caller = request.query.get("caller", "").strip()

        logs = self.storage.get_logs_for_date(date_str)
        if caller and caller.lower() != "all":
            logs = [log for log in logs if log.get("caller", "").lower() == caller.lower()]

        return web.json_response(logs)

    @require_admin
    async def api_log_detail(self, request: web.Request) -> web.Response:
        request_id = request.query.get("id", "")
        if not request_id:
            return web.json_response({"error": "id parameter required"}, status=400)
        date_str = today_str()
        logs = self.storage.get_logs_for_date(date_str)
        entry = next((log for log in logs if log.get("request_id") == request_id), None)
        if not entry:
            return web.json_response({"error": "Not found"}, status=404)
        return web.json_response(entry)

    @require_admin
    async def api_clear_logs(self, request: web.Request) -> web.Response:
        self.storage.clear_logs()
        return web.json_response({"status": "ok", "message": "All logs cleared"})

    @require_admin
    async def api_system_logs(self, request: web.Request) -> web.Response:
        try:
            since = float(request.query.get("since", 0))
        except (ValueError, TypeError):
            since = 0
            
        from core.utils import SYSTEM_LOG_BUFFER
        filtered = [log_entry for log_entry in SYSTEM_LOG_BUFFER if log_entry["timestamp"] > since]
        return web.json_response({"logs": filtered})

    async def api_job_result(self, request: web.Request) -> web.Response:
        job_id = request.match_info["job_id"]
        # If storing job_results locally on server
        if job_id in self.server.job_results:
            return web.json_response(self.server.job_results[job_id])
        return web.json_response({"status": "pending", "jobId": job_id})

    @require_admin
    async def api_slots(self, request: web.Request) -> web.Response:
        slots = await self.browser.get_slots_info() if hasattr(self.browser, "get_slots_info") else {}
        return web.json_response(slots)

    async def api_image(self, request: web.Request) -> web.Response:
        img_id = request.match_info["img_id"]
        data_url = self.server.image_store.get(img_id)
        if not data_url:
            return web.Response(status=404, text="Not found")
        try:
            import base64
            header, b64data = data_url.split(",", 1)
            content_type = header.split(":")[1].split(";")[0]
            return web.Response(
                body=base64.b64decode(b64data), content_type=content_type
            )
        except Exception as e:
            return web.Response(status=500, text=str(e))

    @require_admin
    async def api_default_urls(self, request: web.Request) -> web.Response:
        if request.method == "POST":
            body = await request.json()
            cfg = load_config()
            for platform in ("grok", "gemini", "chatgpt"):
                if platform in body:
                    if "default_urls" not in cfg:
                        cfg["default_urls"] = {}
                    cfg["default_urls"][platform] = body[platform]
            cfg_path = os.path.join(ROOT_DIR, "config.json")
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                existing["default_urls"] = cfg["default_urls"]
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(existing, f, indent=2, ensure_ascii=False)
                self.config["default_urls"] = cfg["default_urls"]
                return web.json_response(
                    {"status": "ok", "default_urls": self.config["default_urls"]}
                )
            except Exception as e:
                return web.json_response({"error": str(e)}, status=500)
        return web.json_response(self.config.get("default_urls", {}))

    @require_admin
    async def api_caller_map(self, request: web.Request) -> web.Response:
        if request.method == "POST":
            body = await request.json()
            self.storage.save_caller_map(body)
            return web.json_response({"status": "ok", "caller_map": body})
        return web.json_response(self.storage.get_caller_map())

    @require_admin
    async def api_browser_toggle_visibility(self, request: web.Request) -> web.Response:
        """New endpoint to toggle browser visibility mode"""
        if hasattr(self.browser, "toggle_visibility"):
            new_visible = await self.browser.toggle_visibility()
            return web.json_response({"status": "ok", "visible": new_visible})
        return web.json_response({"error": "BrowserManager does not support toggle_visibility"}, status=501)

    @require_admin
    async def api_config(self, request: web.Request) -> web.Response:
        body = await request.json()
        if "workers" in body:
            cfg_path = os.path.join(ROOT_DIR, "config.json")
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                existing["workers"] = body["workers"]
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(existing, f, indent=2, ensure_ascii=False)
                
                if hasattr(self.browser, "apply_worker_config"):
                    await self.browser.apply_worker_config(body["workers"])
                return web.json_response({"status": "ok"})
            except Exception as e:
                return web.json_response({"error": str(e)}, status=500)
        return web.json_response({"error": "No workers object in request"}, status=400)

def setup_routes(app: web.Application, server):
    routes = APIRoutes(server)
    
    # Health + Status
    app.router.add_get("/api/health", routes.api_health)
    app.router.add_get("/api/status", routes.api_status)

    # URL Management
    app.router.add_post("/api/url/config", routes.api_url_config)
    app.router.add_get("/api/url/configs", routes.api_url_configs)
    app.router.add_delete("/api/url/{key}", routes.api_url_delete)
    app.router.add_post("/api/url/clear_all", routes.api_url_clear_all)

    # Logs
    app.router.add_get("/api/logs", routes.api_log_summary)
    app.router.add_get("/api/logs/system", routes.api_system_logs)
    app.router.add_get("/api/logs/export", routes.api_log_export)
    app.router.add_get("/api/logs/detail", routes.api_log_detail)
    app.router.add_post("/api/logs/clear", routes.api_clear_logs)

    # Job results + slots
    app.router.add_get("/api/jobs/{job_id}", routes.api_job_result)
    app.router.add_get("/api/slots", routes.api_slots)

    # Images
    app.router.add_get("/api/image/{img_id}", routes.api_image)

    # Default URLs
    app.router.add_get("/api/default-urls", routes.api_default_urls)
    app.router.add_post("/api/default-urls", routes.api_default_urls)

    # Caller Map
    app.router.add_get("/api/caller-map", routes.api_caller_map)
    app.router.add_post("/api/caller-map", routes.api_caller_map)

    # Browser management
    app.router.add_post("/api/browser/toggle-visibility", routes.api_browser_toggle_visibility)
    
    # Config management
    app.router.add_post("/api/config", routes.api_config)
