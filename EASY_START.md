# 🚀 Core of Potato — Quick Start Guide (Easy Start)

This document provides a quick step-by-step guide to installing, running, and using **Core of Potato** immediately after downloading it.

---

## 📋 System Prerequisites
* **Python 3.9+** must be installed on your machine.

---

## 🛠️ Installation & Execution (3 Simple Steps)

### **Step 1: Run the Automated Setup Script**
1. Open your terminal in the project root directory and run:
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```
   *This sets up the virtual environment (`venv`), installs dependencies (including `cloakbrowser`), automatically downloads the stealth Chromium binary, and generates/configures your `config.json` with the correct browser executable path.*

---

### **Step 2: Log In to AI Accounts**

1. **Launch the Core of Potato server:**
   ```bash
   ./venv/bin/python3 -m core
   ```
   * *By default, the server binds to port `2809`.*
   * *Core of Potato starts in **headed mode** (browser windows visible) so you can easily interact with it.*

2. **Log in to the AI platforms:**
   * Upon startup, empty Chromium windows for **Grok**, **Gemini**, and **ChatGPT** will automatically open.
   * Go ahead and **log in** to your respective accounts on those windows.
   * **Once logged in, simply keep them as is.** The browser cookies and session states will automatically persist in the `./data/browser_profiles` directory for future restarts.

---

### **Step 3: Open the Control Panel Hub**
Open your personal browser and navigate to:
👉 **[http://localhost:2809/hub](http://localhost:2809/hub)**

From this local dark-themed dashboard, you can:
* Monitor active slot statuses (`Idle`, `Busy` with details, or `Offline`).
* Manage client `NaModu` keys.
* Stream system background process logs in real time.

---

## 📡 Quick API Test (cURL)

You can send a test request to the OpenAI-compatible endpoint of Core of Potato using the following `cURL` command (make sure to set the `"model"` to `"gemini"`, `"chatgpt"`, or `"grok"` depending on which account you logged into in Step 2):

```bash
curl -X POST http://localhost:2809/v1/chat/completions \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer OCtest" \
     -d '{
       "model": "gemini",
       "messages": [
         {"role": "user", "content": "Hello, is the server running correctly?"}
       ]
     }'
```

* **Note on the `NaModu` identifier (`OCtest`):**
  * Must be exactly 6 alphanumeric characters: 2-character registered prefix (e.g. `OC` or `CD`) + 4-character session tag.
  * You can dynamically register new prefixes (which instantly updates `data/caller_map.json` and invalidates caches) by clicking the **`+`** button in the Control Panel Hub's log management section.

---

## ⚠️ Important Operating Tips
1. **Headed vs. Headless Mode:**
   * By default, the project runs in headed (visible browser windows) mode to bypass anti-bot challenges like Cloudflare.
   * Running completely hidden (headless) is only reliably supported on **Gemini**. It is highly recommended to keep browser windows enabled (`"show_browser_window": true` in `config.json`) for Grok and ChatGPT to prevent timeouts or bot blocks.
2. **Model Selection / Presets:**
   * We recommend manually selecting your preferred model/mode (e.g., Expert/Auto in Grok, or GPT-4o in ChatGPT) in the opened browser window once. Core of Potato will respect and use whatever active mode is selected on the web interfaces.
