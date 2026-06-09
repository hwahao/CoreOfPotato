"use strict";

const $ = (id) => document.getElementById(id);

let state = {
  show_browser_window: true,
  connected: false,
  slots: [],
  queueCount: 0,
  activeCount: 0,
  uptime: 0,
};

let pollInterval = null;
let logPollInterval = null;
let lastLogTime = 0;
let currentCallerMap = {};
let lastFetchedJsonText = "";

function log(msg, type = "info") {
  const el = $("system-log");
  if (!el) return;
  const entry = document.createElement("div");
  entry.className = "log-entry " + type;
  const time = new Date().toLocaleTimeString("en-US", { hour12: false });
  entry.textContent = `[${time}] ${msg}`;
  el.appendChild(entry);
  el.scrollTop = el.scrollHeight;
  while (el.children.length > 200) el.removeChild(el.firstChild);
}

function updateConnBadge(connected) {
  state.connected = connected;
  const dot = $("conn-dot");
  const text = $("conn-text");
  if (!dot || !text) return;
  if (connected) {
    dot.className = "w-2 h-2 rounded-full bg-green-500";
    text.textContent = "Connected";
  } else {
    dot.className = "w-2 h-2 rounded-full bg-gray-400";
    text.textContent = "Disconnected";
  }
}

function initSlotsDOM(slotsData) {
  const container = $("slots-row");
  if (!container) return;
  
  slotsData.forEach(slot => {
    let card = $(`slot-${slot.id}`);
    const statText = slot.status === "idle" ? "Ready" : slot.status === "busy" ? (slot.currentJob || "Running") : "Offline";
    const driverName = slot.driver || "Worker";
    
    let dotColor = "bg-gray-400";
    if (slot.status === "idle") dotColor = "bg-green-500";
    if (slot.status === "busy") dotColor = "bg-yellow-500";
    if (slot.status === "error") dotColor = "bg-red-500";

    if (!card) {
      card = document.createElement("div");
      card.id = `slot-${slot.id}`;
      card.className = `border border-outline-variant rounded p-sm flex flex-col justify-between bg-surface-container-low`;
      card.innerHTML = `
        <div class="flex justify-between items-start">
          <span class="font-label-md text-label-md font-bold">WRK-${slot.id}</span>
          <div class="w-2 h-2 rounded-full status-dot"></div>
        </div>
        <span class="font-label-sm text-label-sm text-on-surface-variant mt-sm slot-driver"></span>
      `;
      container.appendChild(card);
    }
    
    const dot = card.querySelector(".status-dot");
    const driverEl = card.querySelector(".slot-driver");
    
    if (dot) dot.className = `w-2 h-2 rounded-full status-dot ${dotColor}`;
    if (driverEl) driverEl.textContent = `${driverName} (${statText})`;
  });

  const currentSlotIds = slotsData.map(s => `slot-${s.id}`);
  Array.from(container.children).forEach(child => {
    if (!currentSlotIds.includes(child.id)) {
      child.remove();
    }
  });
}

function formatUptime(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${h}h ${m}m ${s}s`;
}

async function fetchStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) throw new Error("Server Error");
    const data = await res.json();
    
    if (!state.connected) {
      updateConnBadge(true);
      log("🟢 Connected to Core of Potato Server", "success");
      loadCallerMap();
      loadDefaultUrls();
    }
    
    state.slots = data.slots || [];
    state.queueCount = data.queue_count || 0;
    state.activeCount = data.active_count || 0;
    state.uptime = data.uptime_seconds || data.uptime || 0;
    if (data.show_browser_window !== undefined) {
      state.show_browser_window = data.show_browser_window;
      const btn = $("btn-headless");
      if (btn) btn.textContent = `👁 Show Browser: ${state.show_browser_window ? "ON" : "OFF"}`;
    }
    
    initSlotsDOM(state.slots);
    
    $("sb-slots").textContent = `${state.slots.filter(s => s.status !== 'offline').length}/${state.slots.length} online`;
    $("sb-active").textContent = `${state.activeCount} (Queue: ${state.queueCount})`;
    $("sb-uptime").textContent = `Uptime: ${formatUptime(state.uptime)}`;
    
  } catch (err) {
    if (state.connected) {
      updateConnBadge(false);
      log("🔴 Disconnected from Server", "error");
    }
  }
}

async function fetchLogs() {
  if (!state.connected) return;
  try {
    const res = await fetch(`/api/logs/system?since=${lastLogTime}`);
    if (res.ok) {
      const data = await res.json();
      if (data.logs && data.logs.length > 0) {
        data.logs.forEach(l => {
          log(l.message, l.level);
          lastLogTime = Math.max(lastLogTime, l.timestamp);
        });
      }
    }
  } catch (err) {}
}

async function toggleVisibility() {
  try {
    state.show_browser_window = !state.show_browser_window;
    const res = await fetch("/api/browser/toggle-visibility", {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    });
    if (res.ok) {
      const icon = $("btn-headless").querySelector('.material-symbols-outlined');
      if (icon) {
        icon.textContent = state.show_browser_window ? "visibility" : "visibility_off";
        if (state.show_browser_window) {
          $("btn-headless").classList.remove('text-primary');
        } else {
          $("btn-headless").classList.add('text-primary');
        }
      }
      log(`Browser window visibility set to ${state.show_browser_window}`, "info");
    } else {
      state.show_browser_window = !state.show_browser_window; 
      log("Failed to toggle browser window", "error");
    }
  } catch (err) {
    state.show_browser_window = !state.show_browser_window; 
    log("Error toggling browser window: " + err, "error");
  }
}

async function applyConfig() {
  const grok = parseInt($("cfg-grok").value, 10);
  const gemini = parseInt($("cfg-gemini").value, 10);
  const chatgpt = parseInt($("cfg-chatgpt").value, 10);
  
  try {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workers: { grok, gemini, chatgpt } })
    });
    if (res.ok) {
      log("Applied new worker config", "success");
    } else {
      log("Failed to apply config", "error");
    }
  } catch (err) {
    log("Error applying config: " + err, "error");
  }
}

function loadDefaultUrls() {
  fetch("/api/default-urls")
    .then(r => r.json())
    .then(urls => {
      if (urls.grok) $("url-grok").value = urls.grok;
      if (urls.gemini) $("url-gemini").value = urls.gemini;
      if (urls.chatgpt) $("url-chatgpt").value = urls.chatgpt;
    });
}

function saveDefaultUrls() {
  const payload = {
    grok: $("url-grok").value,
    gemini: $("url-gemini").value,
    chatgpt: $("url-chatgpt").value
  };
  fetch("/api/default-urls", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  })
  .then(r => r.json())
  .then(res => {
    if (res.status === "ok") {
      log("✅ Saved Default URLs", "success");
    } else {
      log("❌ Failed to save Default URLs", "error");
    }
  });
}

function loadCallerMap() {
  fetch("/api/caller-map")
  .then(r => r.json())
  .then(map => {
    currentCallerMap = map;
    const select = $("log-caller");
    if (!select) return;
    
    const selectedVal = select.value;
    select.innerHTML = '<option value="all">All</option>';
    
    for (const [key, name] of Object.entries(map)) {
      if (key === "Ma") continue;
      const opt = document.createElement("option");
      opt.value = key;
      opt.textContent = name.includes("(") ? name : `${key} (${name})`;
      select.appendChild(opt);
    }
    
    if (select.querySelector(`option[value="${selectedVal}"]`)) {
      select.value = selectedVal;
    }
  });
}

function saveUrlConfig() {
  const key = $("mgmt-key").value.trim();
  const mode = $("mgmt-mode").value;
  const ttl = parseInt($("mgmt-ttl").value, 10);
  const uses = parseInt($("mgmt-uses").value, 10);

  if (!key) return alert("Please enter Module Key (e.g. OCtest)");

  fetch("/api/url/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, mode, ttl_minutes: ttl, max_uses: uses })
  })
  .then(r => r.json())
  .then(res => {
    if (res.status === "ok") {
      log(`✅ Saved config for key: ${key}`, "success");
    } else {
      log(`❌ Failed to save config: ${res.error}`, "error");
    }
  });
}

function forceDeleteUrl() {
  const key = $("mgmt-key").value.trim();
  if (!key) {
    if (confirm("Are you sure you want to delete ALL saved URLs?")) {
      fetch("/api/url/clear_all", { method: "POST" })
      .then(r => r.json())
      .then(res => log(`✅ ${res.message}`, "success"));
    }
    return;
  }
  
  if (confirm(`Delete URL for key: ${key}?`)) {
    fetch(`/api/url/${key}`, { method: "DELETE" })
    .then(r => r.json())
    .then(res => log(`✅ Deleted URL for key: ${key}`, "success"));
  }
}

function showAddCallerBox() {
  $("add-caller-box").style.display = "flex";
  $("new-caller-input").focus();
}

function hideAddCallerBox() {
  $("add-caller-box").style.display = "none";
  $("new-caller-input").value = "";
}

function parseAndNormalizeCaller(rawText) {
  rawText = rawText.trim();
  if (rawText.length < 2) return null;
  const prefix = rawText.slice(0, 2).toUpperCase();
  if (!/^[A-Z]{2}$/.test(prefix)) return null;

  let rest = rawText.slice(2).trim();
  if (rest.startsWith('(')) rest = rest.slice(1).trim();
  if (rest.endsWith(')')) rest = rest.slice(0, -1).trim();

  if (!rest) return null;

  const titleCaseRest = rest.split(/\s+/).map(word => {
    if (!word) return '';
    return word.charAt(0).toUpperCase() + word.slice(1);
  }).join(' ');

  return {
    key: prefix,
    value: `${prefix}  (${titleCaseRest})`
  };
}

function saveNewCaller() {
  const rawText = $("new-caller-input").value;
  const parsed = parseAndNormalizeCaller(rawText);
  if (!parsed) {
    alert("Invalid format! Must start with 2 uppercase letters followed by name (e.g. CA Cong an)");
    return;
  }

  currentCallerMap[parsed.key] = parsed.value;
  
  fetch("/api/caller-map", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(currentCallerMap)
  })
  .then(r => r.json())
  .then(res => {
    if (res.status === "ok") {
      log(`✅ Added Caller: ${parsed.value}`, "success");
      loadCallerMap();
      hideAddCallerBox();
    }
  });
}

function renderJSON(obj, container, isRoot = false) {
  if (typeof obj === 'object' && obj !== null) {
    const isArray = Array.isArray(obj);
    const wrap = document.createElement('div');
    wrap.className = 'json-node';
    
    for (let key in obj) {
      const row = document.createElement('div');
      row.className = 'json-row';
      
      const keySpan = document.createElement('span');
      keySpan.className = 'json-key';
      keySpan.textContent = (isArray ? '' : `"${key}": `);
      
      const val = obj[key];
      if (typeof val === 'object' && val !== null) {
        const toggle = document.createElement('span');
        // By default, collapse if it's not the root to reduce redundant display
        const shouldCollapse = !isRoot;
        toggle.className = 'json-toggle' + (shouldCollapse ? ' collapsed' : '');
        toggle.textContent = shouldCollapse ? '▶ ' : '▼ ';
        
        row.appendChild(toggle);
        row.appendChild(keySpan);
        
        const preview = document.createElement('span');
        preview.className = 'json-preview';
        preview.textContent = Array.isArray(val) ? `[${val.length} items]` : '{...}';
        if (!shouldCollapse) preview.style.display = 'none';
        row.appendChild(preview);
        
        const children = document.createElement('div');
        children.className = 'json-children';
        if (shouldCollapse) children.style.display = 'none';
        renderJSON(val, children, false);
        
        toggle.onclick = (e) => {
          e.stopPropagation();
          const isColl = children.style.display === 'none';
          children.style.display = isColl ? 'block' : 'none';
          preview.style.display = isColl ? 'none' : 'inline';
          toggle.textContent = isColl ? '▼ ' : '▶ ';
          toggle.classList.toggle('collapsed', !isColl);
        };
        preview.onclick = toggle.onclick;
        
        row.appendChild(children);
      } else {
        const valSpan = document.createElement('span');
        const type = val === null ? 'null' : typeof val;
        valSpan.className = 'json-val ' + type;
        valSpan.textContent = type === 'string' ? `"${val}"` : val;
        row.appendChild(keySpan);
        row.appendChild(valSpan);
      }
      wrap.appendChild(row);
    }
    container.appendChild(wrap);
  } else {
    container.textContent = obj;
  }
}

async function fetchAndRenderJsonLogs() {
  const container = $("json-output");
  const btn = $("btn-fetch-json");
  if (!container || !btn) return;
  
  btn.textContent = "⏳ Loading...";
  btn.disabled = true;
  container.innerHTML = '<div class="json-placeholder">Fetching logs...</div>';
  
  try {
    const res = await fetch("/api/logs/export");
    if (!res.ok) throw new Error("Failed to fetch logs");
    const data = await res.json();
    lastFetchedJsonText = JSON.stringify(data, null, 2);
    container.innerHTML = "";
    renderJSON(data, container, true);
  } catch (err) {
    container.innerHTML = `<div class="json-placeholder" style="color:var(--red)">Error: ${err.message}</div>`;
    lastFetchedJsonText = "";
  } finally {
    btn.textContent = "🔄 Load Logs";
    btn.disabled = false;
  }
}

function init() {
  $("btn-headless").addEventListener("click", toggleVisibility);
  $("btn-launch").addEventListener("click", applyConfig);
  $("btn-clear-all-logs").addEventListener("click", () => { $("system-log").innerHTML = ""; });
  
  $("btn-save-urls").addEventListener("click", saveDefaultUrls);
  $("btn-save-url-config").addEventListener("click", saveUrlConfig);
  $("btn-force-delete").addEventListener("click", forceDeleteUrl);
  
  $("btn-add-caller").addEventListener("click", showAddCallerBox);
  $("btn-cancel-caller").addEventListener("click", hideAddCallerBox);
  $("btn-save-new-caller").addEventListener("click", saveNewCaller);
  
  $("btn-export-logs").addEventListener("click", () => {
    window.open("/api/logs/export", "_blank");
  });

  const btnCopy = $("btn-copy-json");
  if (btnCopy) {
    btnCopy.addEventListener("click", () => {
      const txt = lastFetchedJsonText;
      if (!txt) return;
      navigator.clipboard.writeText(txt).then(() => {
        btnCopy.textContent = "✅";
        setTimeout(() => { btnCopy.textContent = "📋"; }, 2000);
      });
    });
  }

  const btnFetchJson = $("btn-fetch-json");
  if (btnFetchJson) {
    btnFetchJson.addEventListener("click", fetchAndRenderJsonLogs);
  }
  
  if (pollInterval) clearInterval(pollInterval);
  if (logPollInterval) clearInterval(logPollInterval);
  
  pollInterval = setInterval(fetchStatus, 1000);
  logPollInterval = setInterval(fetchLogs, 2000);
  
  fetchStatus();
  initHelpSystem();
}

const HELP_TEXTS = {
  workers: "Configure the number of active browser tabs (Workers) for Grok, Gemini, and ChatGPT. Clicking \"Launch Fleet\" will dynamically open new tabs or safely close idle ones in the background to match your configured limits.",
  slots: "Real-time monitoring of all active Chromium browser slots. Displays the current state of each worker: Idle (ready for tasks), Busy (currently generating a response), or Offline.",
  default_urls: "Set the default landing web URLs for each AI platform. Saving these updates the config.json file and automatically navigates the active browser tabs to the new URLs.",
  url_mgmt: "Manage conversation session URLs mapped to NaModu keys (e.g. OCtest). Configure cache expiry rules: Fixed (permanent), Time-based (expires after N minutes), or Usage-based (expires after N uses). Use Force Delete to manually discard a session.",
  logs: "Manage registered caller prefixes and filter system log exports. View a real-time console of background system events and inspect the raw JSON output payload of the most recently completed job."
};

function initHelpSystem() {
  const modal = $("help-modal");
  const content = $("help-content");
  const btnClose = $("btn-close-help");
  if (!modal || !content || !btnClose) return;

  const triggers = document.querySelectorAll(".help-trigger");
  triggers.forEach(trigger => {
    trigger.addEventListener("click", (e) => {
      const key = trigger.getAttribute("data-help");
      if (HELP_TEXTS[key]) {
        content.textContent = HELP_TEXTS[key];
        modal.classList.remove("hidden");
      }
    });
  });

  btnClose.addEventListener("click", () => {
    modal.classList.add("hidden");
  });

  modal.addEventListener("click", (e) => {
    if (e.target === modal) {
      modal.classList.add("hidden");
    }
  });
}

document.addEventListener("DOMContentLoaded", init);

