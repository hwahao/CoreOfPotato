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
  const badge = $("conn-badge");
  const text = $("conn-text");
  if (!badge || !text) return;
  if (connected) {
    badge.classList.add("connected");
    text.textContent = "Server Connected";
  } else {
    badge.classList.remove("connected");
    text.textContent = "Disconnected";
  }
}

function initSlotsDOM(slotsData) {
  const container = $("slots-row");
  if (!container) return;
  
  slotsData.forEach(slot => {
    let card = $(`slot-${slot.id}`);
    if (!card) {
      card = document.createElement("div");
      card.className = "slot-card offline";
      card.id = `slot-${slot.id}`;
      
      const driverClass = (slot.driver || "").toLowerCase();
      
      card.innerHTML = `
        <div class="slot-header">
          <div class="slot-meta">
            <span class="slot-dot offline"></span>
            <span class="slot-id-badge">#${slot.id}</span>
          </div>
          <span class="slot-driver-badge driver-${driverClass}">${slot.driver}</span>
        </div>
        <div class="slot-status" id="slot-${slot.id}-status">Offline</div>
      `;
      container.appendChild(card);
    }
    
    const dot = card.querySelector(".slot-dot");
    const statusEl = $(`slot-${slot.id}-status`);
    
    card.className = "slot-card " + slot.status;
    if (dot) dot.className = "slot-dot " + slot.status;
    
    statusEl.textContent = slot.status === "idle" ? "Idle — Ready" :
      slot.status === "busy" ? (slot.currentJob || "Working...") :
      slot.status;
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
    state.uptime = data.uptime || 0;
    if (data.show_browser_window !== undefined) {
      state.show_browser_window = data.show_browser_window;
      const btn = $("btn-headless");
      if (btn) btn.textContent = `👁 Show Browser: ${state.show_browser_window ? "ON" : "OFF"}`;
    }
    
    initSlotsDOM(state.slots);
    
    $("sb-slots").textContent = `Slots: ${state.slots.filter(s => s.status !== 'offline').length}/${state.slots.length} online`;
    $("sb-active").textContent = `Active: ${state.activeCount} (Queue: ${state.queueCount})`;
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
      $("btn-headless").textContent = `👁 Show Browser: ${state.show_browser_window ? "ON" : "OFF"}`;
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
      const txt = $("json-output").value;
      if (!txt) return;
      navigator.clipboard.writeText(txt).then(() => {
        btnCopy.textContent = "✅";
        setTimeout(() => { btnCopy.textContent = "📋"; }, 2000);
      });
    });
  }
  
  if (pollInterval) clearInterval(pollInterval);
  if (logPollInterval) clearInterval(logPollInterval);
  
  pollInterval = setInterval(fetchStatus, 1000);
  logPollInterval = setInterval(fetchLogs, 2000);
  
  fetchStatus();
}

document.addEventListener("DOMContentLoaded", init);
