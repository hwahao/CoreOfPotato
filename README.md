# Core of Potato

**Core of Potato v1.0.1** is an open-source, lightweight API gateway and browser automation framework designed to run local web-based AI models in parallel browser slots. It bridges the gap between structured API requests (e.g., OpenAI-compatible clients, LangChain, or simple HTTP requests) and free browser-based AI platforms (Grok, Gemini, ChatGPT) using advanced session multiplexing.

---

## 🚀 Features

- **OpenAI-Compatible Endpoint**: Seamless integration with tools like OpenAI's official SDKs, LangChain, and other API wrappers at `/v1/chat/completions`.
- **Dynamic Headless Toggle**: Toggle between headed (visible tabs) and headless (completely silent background processes) on the fly via the Control Panel or REST API. *(Note: Running in headless mode is currently only reliably supported on Gemini. Grok and ChatGPT employ strict anti-bot protections that often block headless execution.)*
- **Session Continuity (NaModu Keys)**: Isolated browser tabs mapped to custom 6-character keys (`NaModu` format, e.g., `OCtest`), preserving cookie sessions, conversations, and custom settings.
- **Human-like Automation**: Features human-like typing delays (30-120ms) and intelligent copy-pasting for larger prompts (>500 chars) to prevent bot detection.
- **Unified Control Panel (Hub)**: Beautiful dark-themed dashboard served locally at `/hub` to monitor worker slot statuses (Idle, Busy, Offline), adjust active worker configurations, and inspect real-time system logs.

---

## 📐 Architecture

```
┌───────────────────────────────────────────────────────┐
│  Clients (OpenAI Python SDK, LangChain, cURL, etc.)  │
└──────────────┬────────────────────────────────────────┘
               │ HTTP (port 2809)
               ▼
┌───────────────────────────────────────────────────────┐
│  Core of Potato Server (aiohttp)                      │
│  ├─ /v1/chat/completions (OpenAI Compatible API)      │
│  ├─ /api/* (Management, Logs, Slots, Visibility)      │
│  └─ /hub   (Static Control Panel UI)                  │
│                                                       │
│  BrowserManager (core/browser_mgr.py)                 │
│  ├─ Launches persistent Chromium contexts             │
│  ├─ Maintains separate page slots per platform        │
│  └─ Handles headed/headless toggling                  │
└──────────────┬────────────────────────────────────────┘
               │ Playwright CDP
               ▼
┌───────────────────────────────────────────────────────┐
│  Stealth Browser (Chromium / CloakBrowser)            │
│  ├─ [Headed]   Visible windows & tabs for debugging   │
│  └─ [Headless] Background execution with low overhead │
└───────────────────────────────────────────────────────┘
```

---

## 🛠️ Setup & Installation

### Prerequisites
- Python 3.9+
- Linux (Debian/Ubuntu/Fedora/etc.), macOS, or Windows

### 1. Run Setup Script
Run the automated installation script to install Python dependencies and Playwright Chromium drivers, and copy the default config template:

```bash
chmod +x setup.sh
./setup.sh
```

*(Alternatively, manually run `pip install -r requirements.txt -r requirements-dev.txt`, followed by `playwright install chromium`)*

### 2. Configure Core of Potato
Copy `config.example.json` to `config.json` and adjust configurations:
```bash
cp config.example.json config.json
```

Key configuration options in `config.json`:
- `host`: The host address to bind the server to (default: `"127.0.0.1"`).
- `port`: The port the gateway will bind to (default: `2809`).
- `log_level`: Severity level for system console logs (default: `"INFO"`).
- `job_accept_timeout`: Maximum time in seconds to wait for a worker slot to become available before rejecting a job (default: `10`).
- `job_result_timeout`: Maximum time in seconds to wait for the automation script to complete a single prompt (default: `180`).
- `log_retention_days`: Number of days to retain daily logs in `data/logs/` before automatic cleanup (default: `3`).
- `url_default_mode`: Default caching strategy for session URLs (`"usage_based"`, `"time_based"`, or `"fixed"`).
- `url_default_max_uses`: Number of times a cached URL can be used under usage-based caching before getting discarded (default: `10`).
- `url_default_ttl_minutes`: Time in minutes a cached URL is valid under time-based caching before getting discarded (default: `30`).
- `default_urls`: Starting landing page URLs for each automated browser platform.
- `workers`: Configure how many parallel slots are opened for each platform (e.g., `"grok": 3, "gemini": 1, "chatgpt": 2`).
- `browser.show_browser_window`: Set to `true` to run browsers in headed mode (visible windows) for debugging, or `false` to run silently in headless mode (default: `true`). **Note:** Headless mode triggers bot protections on Grok and ChatGPT, causing them to fail or timeout. It is recommended to keep this `true` unless you are exclusively using Gemini.
- `browser.user_data_dir`: Directory where persistent browser login sessions, cookies, and local storage states are saved (`"./data/browser_profiles"`).
- `browser.viewport`: Resolution dimensions for the virtual browser instances.
- `security.admin_token`: Secret authorization token for accessing administrative REST API endpoints (default: `"admin-token-change-me"`).
- `security.require_auth`: Set to `true` to restrict access to the `/v1/chat/completions` API endpoint, requiring a valid caller mapping.

### 3. Initialize Caller Mapping
The system uses 2-character caller prefixes to validate and identify clients (e.g. `OC` for OpenClaw). While `config.json` contains a default seed configuration, the active caller mapping is stored and maintained dynamically in `data/caller_map.json`. At startup, this file is loaded, and any additions/removals made through the Control Panel Hub UI are written directly to it.

Default content of `data/caller_map.json`:
```json
{
  "OC": "OpenClaw",
  "CD": "OpenCode"
}
```

---

## 🏃 Running the Server

Start Core of Potato with:
```bash
python3 -m core
```

Once running:
- **API Gateway**: `http://localhost:2809/v1/chat/completions`
- **Control Panel Hub**: Open `http://localhost:2809/hub` in your browser.

---

## 🖥️ Control Panel Hub (Local Dashboard)

Core of Potato serves a premium, dark-themed control panel locally at `http://localhost:2809/hub` (and automatically launches it in a Playwright tab at start). It provides real-time telemetry, configuration tools, and log management:

### 1. Telemetry Sidebar (Left)
- **Status Indicators**: Displays total configured slots, active/busy worker tabs, and server uptime.
- **Launch Workers**: Configure active slot counts for Grok, Gemini, and ChatGPT. Clicking **"🚀 Load Workers"** dynamically opens or safely closes Stealth browser tabs in the background.
- **Default URLs**: Set default starting web URLs for each platform. Saving updates `config.json` and adjusts the active browser tabs.
- **URL Management (per Job Key)**: Manage conversation session URLs mapped to `NaModu` keys (e.g. `OCtest`). Set fixed, time-based, or usage-based cache TTL/limits, or delete keys to reset sessions.
- **Log Management**: Filter system log exports by caller faction (`OC`, `CD`, or custom), dynamically add new caller prefixes via the **`+`** button (writes to `data/caller_map.json` and invalidates memory cache instantly), and clear log files.

### 2. Main Console (Right)
- **Worker Slots Status**: Real-time cards showing the current state (`Idle`, `Busy` with prompt details, or `Offline`) of every active Chromium tab. Status badges indicate the platform (Grok, Gemini, or ChatGPT).
- **JSON Output**: Live view displaying raw JSON response structures of the last completed job, including total execution times and session URLs, with a quick-copy button.
- **System Logs**: Streaming log console showing color-coded background process logs (API requests, browser automation actions, and errors) directly from the server.

---

## 📡 API Usage

Core of Potato accepts standard OpenAI Chat Completions requests. The user identity must follow the **NaModu format** (6 alphanumeric characters: 2-character caller prefix + 4-character module tag, e.g., `OCtest`). Core of Potato reads the NaModu from the request using 4 methods, tried in this priority order:

| Priority | Method | How to Pass |
|----------|--------|-------------|
| 1 | JSON Body | `"user": "OCtest"` in the request JSON payload |
| 2 | Bearer Token | `Authorization: Bearer OCtest` header |
| 3 | X-User Header | `X-User: OCtest` header |
| 4 | User Header | `User: OCtest` header |

The first non-empty value found is used. If none are provided, the request is rejected.

### Blocking Completion (cURL)
```bash
curl -X POST http://localhost:2809/v1/chat/completions \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer OCtest" \
     -d '{
       "model": "grok-fast",
       "messages": [
         {"role": "user", "content": "Explain quantum computing in one sentence."}
       ]
     }'
```

### Streaming Completion (cURL)
```bash
curl -X POST http://localhost:2809/v1/chat/completions \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer OCtest" \
     -d '{
       "model": "grok-fast",
       "messages": [
         {"role": "user", "content": "Write a short poem about code."}
       ],
       "stream": true
     }'
```

### Models Supported
Use the following values for the `"model"` field in completions:
- `grok`: Grok (xAI)
- `gemini`: Google Gemini
- `chatgpt` or `gpt`: OpenAI ChatGPT

**Note on Advanced Modes (Fast vs. Expert, Auto, etc.)**: 
Core of Potato no longer attempts to force platform-specific modes (like Grok Fast or Expert) via API model names. In practice, automated selection is unreliable and can lead to unexpected behavior (e.g. Fast mode giving poor answers, or Expert mode taking far too long for simple questions). 

**Recommended Setup**: Log in to the respective AI provider's web interface for each of your Browser Slots, select the model/mode that works best for your use case (e.g., set Grok to Auto or Expert, or set ChatGPT to GPT-4o), and leave it. Core of Potato will simply use whichever model is currently active in that browser session.

### NaModu Formatting & Validation
- **Etymology**: The term **"NaModu"** represents a combination of **Na** (Nation/Faction/Name prefix) and **Modu** (Module/Caller suffix), forming a 6-character session workspace tag.
- **Format**: The `user` identifier (passed via any of the 4 methods listed above) must be exactly 6 alphanumeric characters.
  - **`Na` (2 characters)**: The caller prefix (e.g., `OC` for OpenClaw, `CD` for OpenCode).
  - **`Modu` (4 characters)**: The module identifier (e.g., `test` for testing, `demo` for demo).
- **Validation**: When a request is received, Core of Potato extracts the `Na` prefix and validates it against `data/caller_map.json`. If the prefix is not registered, the server immediately rejects the request with an HTTP 400 Bad Request error. New callers can be added dynamically using the **`+`** button in the Control Panel Hub UI, which writes to `data/caller_map.json` and immediately invalidates the server cache.

### Concurrency & Queueing Mechanism
To prevent race conditions, overlapping prompts, and browser session corruption on the AI chatbot platforms (such as Grok, Gemini, ChatGPT), Core of Potato implements a state-aware concurrency queueing mechanism:
- **Same NaModu + Same Model** (e.g., two concurrent requests for `OCtest` using `grok`):
  - These requests share the same conversation URL key (`OCtest_grok`).
  - Core of Potato serializes these requests. The first request takes the available slot. The second request is queued and waits until the first job completes.
  - Once the first job finishes and updates the conversation URL in the database, the second job resumes, fetches the *latest conversation URL*, navigates to it, and runs sequentially.
- **Same NaModu + Different Models** (e.g., `OCtest` using `grok` and `OCtest` using `gemini` at the same time):
  - These requests have different conversation contexts and URLs (`OCtest_grok` vs `OCtest_gemini`).
  - They are processed as **two separate streams in parallel** on their respective platform worker slots (no queue wait, unless all slots for that platform are busy).
- **Different NaModus** (e.g., `OCtest` and `OCdemo` both using `grok` at the same time):
  - These are treated as independent users.
  - They run in **parallel** on separate slot pages (e.g., `grok-1` and `grok-2`), as long as multiple slots are configured.

---

## 🔒 Session URL Caching & Expiry Modes

To maintain session continuity across independent HTTP completions requests, Core of Potato persists conversation URLs in `data/jobs.json`. When a user requests a completion, the browser manager loads the last stored URL for that specific key. To prevent memory bloat and stale threads, Core of Potato supports three session caching behaviors, configurable per key or via global defaults:

1. **Fixed (`fixed`)**:
   - The session URL is stored permanently and never expires.
   - Ideal for long-term project threads or dedicated system testing sessions.
2. **Time-Based (`time_based`)**:
   - The session URL is discarded when its age exceeds `url_default_ttl_minutes` (default: 30 minutes) since the last usage.
   - Ideal for temporal context memory that naturally degrades over time.
3. **Usage-Based (`usage_based`)**:
   - The session URL expires and gets deleted after being reused `url_default_max_uses` times (default: 10 times).
   - Ideal for bounded workflows or strict execution scripts.

These parameters can be configured dynamically per caller key via the Hub UI dashboard or through the `/api/url/config` REST endpoint.

---

## 📡 Complete REST API Reference

All administrative endpoints (marked with 🔑) require authentication. Clients must provide the configured `X-Admin-Token` header:
`X-Admin-Token: <your-admin-token>` (or be requested from the same origin as the Hub UI dashboard).

### Public Endpoints

#### 1. API Health Check
* **Path**: `GET /api/health`
* **Description**: Returns server state, version info, active worker counts, and server uptime.
* **Response**:
  ```json
  {
    "status": "ok",
    "version": "1.0.1",
    "uptime_seconds": 120,
    "jobs_today": 5,
    "adapter": "Core of Potato",
    "port": 2809,
    "workers": { "grok": 3, "gemini": 1, "chatgpt": 2 },
    "timestamp": "2026-06-06T09:41:00Z"
  }
  ```

#### 2. Get Job Result
* **Path**: `GET /api/jobs/{job_id}`
* **Description**: Polls the status of a specific background chat completion job.
* **Response**:
  ```json
  {
    "status": "completed",
    "jobId": "job_123456",
    "response": "Here is the response from the AI...",
    "elapsed_seconds": 12.4,
    "session_url": "https://grok.com/chat/abc-123"
  }
  ```

#### 3. Retrieve Page Screenshot/Image
* **Path**: `GET /api/image/{img_id}`
* **Description**: Returns binary image data (e.g. PNG screenshots) stored in memory, useful for visual status checks.

---

### Admin/Management Endpoints (🔑 Requires Admin Token)

#### 4. System Status
* **Path**: `GET /api/status`
* **Description**: Comprehensive diagnostic status of the server and all active Playwright worker slots.

#### 5. Configure Session Expiry
* **Path**: `POST /api/url/config`
* **Request Payload**:
  ```json
  {
    "key": "OCtest_grok",
    "mode": "usage_based",
    "ttl_minutes": 30,
    "max_uses": 5
  }
  ```
* **Description**: Configures custom TTL and usage limits for a specific session URL.

#### 6. Delete Session URL
* **Path**: `DELETE /api/url/{key}`
* **Description**: Discards the cached session URL mapped to `{key}`, forcing the next request to spawn a fresh thread.

#### 7. Clear All Sessions
* **Path**: `POST /api/url/clear_all`
* **Description**: Discards all cached conversation URLs in `data/jobs.json`.

#### 8. List Session Configurations
* **Path**: `GET /api/url/configs`
* **Description**: Returns details on all currently cached URLs, usage counts, and expiry times.

#### 9. Get Log Summary
* **Path**: `GET /api/logs`
* **Query Parameters**: `?date=YYYY-MM-DD` (default: today)
* **Description**: Returns the count of today's completed requests and a list of the last 50 entries.

#### 10. Streaming System Logs
* **Path**: `GET /api/logs/system`
* **Query Parameters**: `?since=timestamp`
* **Description**: Fetches recent color-coded console logs output by the Core of Potato engine.

#### 11. Export JSON Logs
* **Path**: `GET /api/logs/export`
* **Query Parameters**: `?date=YYYY-MM-DD&caller=caller_name`
* **Description**: Exports the full structured logs database for the given date, optionally filtered by caller (e.g., `OC`).

#### 12. Retrieve Specific Log Entry
* **Path**: `GET /api/logs/detail`
* **Query Parameters**: `?id=request_id`
* **Description**: Returns all logs, execution times, and payload properties for a single request.

#### 13. Clear All Logs
* **Path**: `POST /api/logs/clear`
* **Description**: Erases historical logs databases from the server filesystem.

#### 14. List Worker Slots
* **Path**: `GET /api/slots`
* **Description**: Returns statuses of all workers (whether they are `Idle`, `Busy` with a job, or `Offline`).

#### 15. Manage Default Landing URLs
* **Path**: `GET` / `POST` `/api/default-urls`
* **Request Payload (for POST)**:
  ```json
  {
    "grok": "https://grok.com",
    "gemini": "https://gemini.google.com/app",
    "chatgpt": "https://chatgpt.com"
  }
  ```
* **Description**: Updates and saves default home URLs for each chatbot in `config.json`.

#### 16. Manage Caller Authorization Map
* **Path**: `GET` / `POST` `/api/caller-map`
* **Request Payload (for POST)**:
  ```json
  {
    "OC": "OpenClaw",
    "CD": "OpenCode",
    "UX": "CustomClient"
  }
  ```
* **Description**: Read or modify the mapping of 2-character caller prefixes to client names. Updates `data/caller_map.json` and clears the memory cache instantly.

#### 17. Toggle Headless Visibility
* **Path**: `POST /api/browser/toggle-visibility`
* **Description**: Dynamically toggles browser visibility. Terminates active Chromium sessions, flips the headless flag, spawns a new Chromium context with reversed headed/headless settings, and recovers all active worker page states.

#### 18. Hot-Reload Workers Config
* **Path**: `POST /api/config`
* **Request Payload**:
  ```json
  {
    "workers": {
      "grok": 4,
      "gemini": 2,
      "chatgpt": 2
    }
  }
  ```
* **Description**: Safely opens or closes browser slots on the fly to match the requested numbers, saving settings to `config.json` without rebooting the server.

---

## 🛠️ Extending Core of Potato: Adding Custom Drivers

Core of Potato uses an extensible driver architecture. All automation drivers reside under `core/drivers/` and inherit from `BaseDriver` defined in `core/drivers/base.py`.

To add support for a new chatbot platform:

1. **Create the Driver Class**:
   Create a new file (e.g., `core/drivers/mybot.py`) implementing the abstract methods:
   ```python
   from core.drivers.base import BaseDriver

   class MyBotDriver(BaseDriver):
       async def send_prompt(self, prompt: str) -> None:
           # Locate input element, type prompt, and trigger send (click/enter)
           pass

       async def wait_for_response(self) -> str:
           # Poll DOM selectors until reply text is fully generated and stable
           pass

       async def wait_for_response_streaming(self):
           # Yield partial text chunks as they appear in the DOM
           pass
   ```

2. **Register the Driver**:
   Import and register your class inside `core/drivers/__init__.py`:
   ```python
   from .mybot import MyBotDriver

   DRIVERS = {
       # ... existing
       'mybot': MyBotDriver
   }
   ```

3. **Define Model Mapping**:
   Link model names to your driver in `core/server.py` under the `MODEL_MAP` dictionary (e.g., `"mybot": ("mybot", "auto")`).

---

## 🧪 Testing

We use `pytest` for integration and unit testing:
```bash
pytest
```

To run lint checks:
```bash
ruff check .
```

---

## 🤝 Contributing

Contributions are welcome! Please check our [Contributing Guidelines](CONTRIBUTING.md) for details.

---

## ⚖️ License & Disclaimer

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

Refer to [DISCLAIMER.md](DISCLAIMER.md) for terms regarding the educational and personal research nature of this tool.
