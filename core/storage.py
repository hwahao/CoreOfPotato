from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone, timedelta

from core.config import ROOT_DIR, load_config
from core.utils import setup_logger, now_iso, today_str

logger = setup_logger("Storage")

class Storage:
    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = os.path.join(ROOT_DIR, "data")
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

        self.jobs_file = os.path.join(data_dir, "jobs.json")
        self.logs_dir = os.path.join(data_dir, "logs")
        self.counter_file = os.path.join(self.logs_dir, "_counter.json")
        self.caller_map_file = os.path.join(data_dir, "caller_map.json")

        os.makedirs(self.logs_dir, exist_ok=True)

        self._lock = threading.RLock()
        self.jobs = self._load(self.jobs_file)
        self._init_context()

    # ─────────────────────── FILE I/O ────────────────────────

    def _load(self, path: str, default=None) -> list | dict:
        if default is None:
            default = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading {path}: {e}")
        return default

    def _save(self, path: str, data: list | dict):
        with self._lock:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Error saving {path}: {e}")

    # ─────────────────── JOBS (job_id → URL) ─────────────────

    def _get_job(self, key: str) -> dict | None:
        """Look up a job by its NaModu key (caller+module, e.g. 'OCvien')."""
        return next((j for j in self.jobs if j.get("key") == key), None)

    def get_url_by_key(self, key: str) -> str | None:
        """Get saved conversation URL for a NaModu key, handling expiry."""
        job = self._get_job(key)
        if not job or not job.get("url"):
            return None

        base_key = key.split("_")[0] if "_" in key else key
        base_job = self._get_job(base_key) if base_key != key else None
        cfg = load_config()

        mode = job.get("url_mode")
        if not mode and base_job:
            mode = base_job.get("url_mode")
        if not mode:
            mode = cfg.get("url_default_mode", "usage_based")

        if mode == "fixed":
            return job["url"]

        if mode == "time_based":
            ttl = job.get("url_ttl_minutes")
            if ttl is None and base_job:
                ttl = base_job.get("url_ttl_minutes")
            if ttl is None:
                ttl = cfg.get("url_default_ttl_minutes", 30)

            last_used = job.get("url_last_used", "")
            if last_used:
                try:
                    last = datetime.fromisoformat(last_used)
                    elapsed = (datetime.now(timezone.utc) - last).total_seconds() / 60
                    if elapsed >= ttl:
                        logger.info(
                            f"URL for '{key}' expired (time_based, {elapsed:.0f}m >= {ttl}m)"
                        )
                        self.delete_url_by_key(key)
                        return None
                except ValueError:
                    pass
            return job["url"]

        if mode == "usage_based":
            max_u = job.get("url_max_uses")
            if max_u is None and base_job:
                max_u = base_job.get("url_max_uses")
            if max_u is None:
                max_u = cfg.get("url_default_max_uses", 10)

            used = job.get("url_use_count", 0)
            if used >= max_u:
                logger.info(f"URL for '{key}' expired (usage_based, {used}/{max_u})")
                self.delete_url_by_key(key)
                return None
            return job["url"]

        return job["url"]

    def save_url(self, key: str, url: str):
        """Save conversation URL for a NaModu key. Called after job completes."""
        now = now_iso()
        new_jobs = []
        found = False
        with self._lock:
            for job in self.jobs:
                if job.get("key") == key:
                    new_job = {
                        **job,
                        "url": url,
                        "url_last_used": now,
                        "url_use_count": job.get("url_use_count", 0) + 1
                    }
                    new_jobs.append(new_job)
                    found = True
                else:
                    new_jobs.append(job)

            if not found:
                base_key = key.split("_")[0] if "_" in key else key
                base_job = self._get_job(base_key) if base_key != key else None
                cfg = load_config()

                if base_job:
                    mode = base_job.get("url_mode", cfg.get("url_default_mode", "usage_based"))
                    ttl = base_job.get("url_ttl_minutes", cfg.get("url_default_ttl_minutes", 30))
                    max_uses = base_job.get("url_max_uses", cfg.get("url_default_max_uses", 10))
                else:
                    mode = cfg.get("url_default_mode", "usage_based")
                    ttl = cfg.get("url_default_ttl_minutes", 30)
                    max_uses = cfg.get("url_default_max_uses", 10)

                new_job = {
                    "key": key,
                    "url": url,
                    "url_mode": mode,
                    "url_ttl_minutes": ttl,
                    "url_max_uses": max_uses,
                    "url_created": now,
                    "url_last_used": now,
                    "url_use_count": 1,
                }
                new_jobs.append(new_job)
                logger.info(f"Job created: '{key}'")
            self.jobs = new_jobs
            self._save(self.jobs_file, self.jobs)

    def set_url_config(
        self, key: str, mode: str, ttl_minutes: int = None, max_uses: int = None
    ):
        """Configure URL management mode for a NaModu key."""
        now = now_iso()
        new_jobs = []
        found = False

        with self._lock:
            for job in self.jobs:
                if job.get("key") == key:
                    new_job = {
                        **job,
                        "url_mode": mode
                    }
                    if ttl_minutes is not None:
                        new_job["url_ttl_minutes"] = ttl_minutes
                    if max_uses is not None:
                        new_job["url_max_uses"] = max_uses
                    new_jobs.append(new_job)
                    found = True
                elif "_" not in key and job.get("key", "").startswith(key + "_"):
                    new_job = {
                        **job,
                        "url_mode": mode
                    }
                    if ttl_minutes is not None:
                        new_job["url_ttl_minutes"] = ttl_minutes
                    if max_uses is not None:
                        new_job["url_max_uses"] = max_uses
                    new_jobs.append(new_job)
                else:
                    new_jobs.append(job)

            if not found:
                new_job = {
                    "key": key,
                    "url": "",
                    "url_mode": mode,
                    "url_created": now,
                    "url_last_used": now,
                    "url_use_count": 0,
                }
                if ttl_minutes is not None:
                    new_job["url_ttl_minutes"] = ttl_minutes
                if max_uses is not None:
                    new_job["url_max_uses"] = max_uses
                new_jobs.append(new_job)

            self.jobs = new_jobs
            self._save(self.jobs_file, self.jobs)
        logger.info(f"URL config for '{key}': mode={mode}")

    def delete_url_by_key(self, key: str):
        """Clear saved URL for a job based on the key pattern."""
        now = now_iso()
        new_jobs = []
        key_upper = key.strip().upper()

        with self._lock:
            if key_upper == "ALL":
                for job in self.jobs:
                    new_job = {
                        **job,
                        "url": "",
                        "url_use_count": 0,
                        "url_last_used": now
                    }
                    new_jobs.append(new_job)
                self.jobs = new_jobs
                self._save(self.jobs_file, self.jobs)
                logger.info("All saved conversation URLs cleared via delete pattern")
                return

            if len(key.strip()) == 2:
                prefix = key.strip().upper()
                for job in self.jobs:
                    job_key = job.get("key", "").upper()
                    if job_key.startswith(prefix):
                        new_job = {
                            **job,
                            "url": "",
                            "url_use_count": 0,
                            "url_last_used": now
                        }
                        new_jobs.append(new_job)
                    else:
                        new_jobs.append(job)
                self.jobs = new_jobs
                self._save(self.jobs_file, self.jobs)
                logger.info(f"All URLs for Caller '{prefix}' cleared")
                return

            prefix = key.strip().upper()
            for job in self.jobs:
                job_key = job.get("key", "").upper()
                if job_key == prefix or job_key.startswith(prefix + "_"):
                    new_job = {
                        **job,
                        "url": "",
                        "url_use_count": 0,
                        "url_last_used": now
                    }
                    new_jobs.append(new_job)
                else:
                    new_jobs.append(job)
            self.jobs = new_jobs
            self._save(self.jobs_file, self.jobs)
        logger.info(f"URLs deleted for key/prefix '{prefix}'")

    def get_all_job_configs(self) -> list:
        with self._lock:
            return list(self.jobs)

    # ─────────────────── LOGGING ─────────────────────────────

    def _init_context(self):
        # Load or create daily counter
        day = today_str().replace("-", "")
        if os.path.exists(self.counter_file):
            try:
                with open(self.counter_file) as f:
                    counter_data = json.load(f)
                if counter_data.get("date") != day:
                    counter_data = {"date": day, "request_count": 0, "per_job": {}}
            except Exception:
                counter_data = {"date": day, "request_count": 0, "per_job": {}}
        else:
            counter_data = {"date": day, "request_count": 0, "per_job": {}}
        self._counter_data = counter_data

    def _save_counter(self):
        self._save(self.counter_file, self._counter_data)

    def get_next_job_number(self, key: str) -> int:
        """Get next sequential number for a NaModu key (e.g. 'OCvien')."""
        with self._lock:
            day = today_str().replace("-", "")
            if self._counter_data.get("date") != day:
                self._counter_data = {"date": day, "request_count": 0, "per_job": {}}
            per_job = self._counter_data.setdefault("per_job", {})
            key_lower = key.lower()
            count = per_job.get(key_lower, 0) + 1
            per_job[key_lower] = count
            self._save_counter()
            return count

    def next_request_id(self) -> str:
        """Get next global request ID: req_NNNNNNNN."""
        with self._lock:
            day = today_str().replace("-", "")
            if self._counter_data.get("date") != day:
                self._counter_data = {"date": day, "request_count": 0, "per_job": {}}
            self._counter_data["request_count"] += 1
            self._save_counter()
            return f"req_{self._counter_data['request_count']:08d}"

    def next_step_label(self, key: str) -> str:
        """Get next per-module step label: e.g. vien#01."""
        with self._lock:
            day = today_str().replace("-", "")
            if self._counter_data.get("date") != day:
                self._counter_data = {"date": day, "request_count": 0, "per_job": {}}
            per_job = self._counter_data.setdefault("per_job", {})
            
            key_lower = key.lower()
            count = per_job.get(key_lower, 0) + 1
            per_job[key_lower] = count
            self._save_counter()
            
            if len(key) >= 6:
                abbr = key[2:6].replace("-", "").replace("_", "").lower()
            else:
                abbr = key.replace("-", "").replace("_", "").lower()
                
            return f"{abbr}#{count:02d}"

    def write_log(self, request_id: str, log_entry: dict):
        """Write a complete log entry for one user request."""
        day = today_str()
        log_file = os.path.join(self.logs_dir, f"{day}.json")
        with self._lock:
            logs = self._load(log_file)
            logs.append(log_entry)
            self._save(log_file, logs)
        logger.info(f"Log written: {request_id}")

    def get_logs_for_date(self, date_str: str) -> list:
        log_file = os.path.join(self.logs_dir, f"{date_str}.json")
        return self._load(log_file)

    def clear_logs(self):
        """Delete all log files. Called from Hub UI."""
        with self._lock:
            for f in os.listdir(self.logs_dir):
                if f.endswith(".json") and f != "_counter.json":
                    try:
                        os.remove(os.path.join(self.logs_dir, f))
                    except Exception:
                        pass
        logger.info("All logs cleared")

    def cleanup_old_logs(self):
        """Remove log files older than retention period."""
        cfg = load_config()
        max_days = cfg.get("log_retention_days", 3)
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
        with self._lock:
            for f in os.listdir(self.logs_dir):
                if f.endswith(".json") and f != "_counter.json":
                    try:
                        file_date = datetime.strptime(f.replace(".json", ""), "%Y-%m-%d")
                        if file_date.replace(tzinfo=timezone.utc) < cutoff:
                            os.remove(os.path.join(self.logs_dir, f))
                            logger.info(f"Removed old log: {f}")
                    except (ValueError, OSError):
                        continue

    def clear_all_urls(self):
        """Clear saved URLs for all jobs."""
        now = now_iso()
        new_jobs = []
        with self._lock:
            for job in self.jobs:
                new_job = {
                    **job,
                    "url": "",
                    "url_use_count": 0,
                    "url_last_used": now
                }
                new_jobs.append(new_job)
            self.jobs = new_jobs
            self._save(self.jobs_file, self.jobs)
            logger.info("All saved conversation URLs cleared")

    # ─────────────────── CALLER MAP ─────────────────────────

    def get_caller_map(self) -> dict:
        if os.path.exists(self.caller_map_file):
            return self._load(self.caller_map_file, default={})
        cfg = load_config()
        return cfg.get(
            "caller_map", {"OC": "OpenClaw", "CD": "OpenCode"}
        )

    def save_caller_map(self, data: dict):
        self._save(self.caller_map_file, data)
        # Also invalidate the in-memory cache in utils
        import core.utils as utils
        utils._caller_map.invalidate()

