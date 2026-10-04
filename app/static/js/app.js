// JioTV IPTV Server Frontend Logic

let allChannels = [];

document.addEventListener("DOMContentLoaded", () => {
  fetchStatus();
  loadChannels();
  setupDynamicUrls();
});

// Setup dynamic URLs based on current browser origin if BASE_URL wasn't configured
function setupDynamicUrls() {
  const origin = window.location.origin;
  const m3uInput = document.getElementById("url-m3u");
  const epgInput = document.getElementById("url-epg");
  
  if (m3uInput && m3uInput.value.includes("tv.trylocalhost.com") && window.location.hostname !== "tv.trylocalhost.com") {
    m3uInput.value = `${origin}/playlist.m3u`;
  }
  if (epgInput && epgInput.value.includes("tv.trylocalhost.com") && window.location.hostname !== "tv.trylocalhost.com") {
    epgInput.value = `${origin}/epg.xml.gz`;
  }

  document.querySelectorAll(".url-preview-m3u").forEach(el => {
    if (m3uInput) el.textContent = m3uInput.value;
  });
  document.querySelectorAll(".url-preview-epg").forEach(el => {
    if (epgInput) el.textContent = epgInput.value;
  });
}

// Tab Switching
function switchTab(tabId) {
  document.querySelectorAll(".nav-tab").forEach(tab => {
    tab.classList.toggle("active", tab.dataset.tab === tabId);
  });
  document.querySelectorAll(".tab-pane").forEach(pane => {
    pane.classList.toggle("active", pane.id === `tab-content-${tabId}`);
  });
}

// Fetch Status
async function fetchStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const data = await res.json();

    const badge = document.getElementById("header-jio-badge");
    const subName = document.getElementById("card-subscriber-name");
    const subMobile = document.getElementById("card-subscriber-mobile");
    const chCount = document.getElementById("card-channel-count");
    const tabChCount = document.getElementById("tab-channel-count");
    const proxyStatusPill = document.getElementById("proxy-status-pill");

    if (data.jio_auth && data.jio_auth.logged_in) {
      if (badge) {
        badge.className = "status-badge online";
        badge.innerHTML = `<span class="pulse-dot"></span><span class="badge-text">${data.jio_auth.subscriber_name || 'Jio Active'}</span>`;
      }
      if (subName) subName.textContent = data.jio_auth.subscriber_name || "Jio Subscriber";
      if (subMobile) subMobile.textContent = data.jio_auth.mobile || "Logged In";
    } else {
      if (badge) {
        badge.className = "status-badge checking";
        badge.innerHTML = `<span class="pulse-dot"></span><span class="badge-text">Sign In Required</span>`;
      }
      if (subName) subName.textContent = "Not Authenticated";
      if (subMobile) subMobile.textContent = "Click 'Jio Login' to connect";
    }

    if (chCount) chCount.textContent = data.channels_count;
    if (tabChCount) tabChCount.textContent = data.channels_count;

    if (proxyStatusPill) {
      proxyStatusPill.className = data.proxy_enabled ? "badge badge-success" : "badge";
      proxyStatusPill.textContent = data.proxy_enabled ? "Proxy Active" : "Direct Connection";
    }
  } catch (err) {
    console.warn("Status fetch failed:", err);
  }
}

// Toggle Proxy Settings Visibility
function toggleProxyInputs() {
  const enabled = document.getElementById("input-proxy-enabled").checked;
  const pill = document.getElementById("proxy-status-pill");
  if (pill) {
    pill.className = enabled ? "badge badge-success" : "badge";
    pill.textContent = enabled ? "Proxy Active" : "Direct Connection";
  }
}

// Save Settings
async function saveSettings(e) {
  e.preventDefault();
  const enabled = document.getElementById("input-proxy-enabled").checked;
  const proxyUrl = document.getElementById("input-proxy-url").value.trim();
  const baseUrl = document.getElementById("input-base-url").value.trim();

  const btn = document.getElementById("btn-save-settings");
  btn.disabled = true;
  btn.textContent = "Saving...";

  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        proxy_enabled: enabled,
        proxy_url: proxyUrl,
        base_url: baseUrl
      })
    });
    const data = await res.json();
    showToast("Settings saved successfully!", "success");
    fetchStatus();
    setupDynamicUrls();
  } catch (err) {
    showToast("Failed to save settings: " + err.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Save Settings";
  }
}

// Test Connectivity
async function testConnectivity() {
  const panel = document.getElementById("connectivity-results");
  if (panel) panel.classList.remove("hidden");

  const pbBadge = document.getElementById("diag-playback-badge");
  const pbDetails = document.getElementById("diag-playback-details");
  const cdnBadge = document.getElementById("diag-cdn-badge");
  const cdnDetails = document.getElementById("diag-cdn-details");

  if (pbBadge) { pbBadge.className = "badge"; pbBadge.textContent = "Probing..."; }
  if (pbDetails) pbDetails.textContent = "Testing direct playback reachability...";
  if (cdnBadge) { cdnBadge.className = "badge"; cdnBadge.textContent = "Probing..."; }
  if (cdnDetails) cdnDetails.textContent = "Testing Jio Fastly CDN reachability...";

  const proxyUrl = document.getElementById("input-proxy-url") ? document.getElementById("input-proxy-url").value.trim() : null;

  try {
    const res = await fetch("/api/test-connectivity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ proxy_url: proxyUrl })
    });
    const results = await res.json();

    // Playback API
    if (results.direct_playback.reachable) {
      pbBadge.className = "badge badge-success";
      pbBadge.textContent = `${results.direct_playback.latency_ms} ms (OK)`;
      pbDetails.textContent = `Direct connection working properly. HTTP Status: ${results.direct_playback.status}. Zero streaming latency.`;
    } else {
      pbBadge.className = "badge badge-danger";
      pbBadge.textContent = "Unreachable";
      pbDetails.textContent = `Error: ${results.direct_playback.error}`;
    }

    // CDN Data
    if (results.cdn.reachable) {
      cdnBadge.className = "badge badge-success";
      cdnBadge.textContent = `${results.cdn.latency_ms} ms (OK)`;
      cdnDetails.textContent = results.cdn.proxied
        ? `Upstream Residential Proxy successfully bypassed Fastly 450 block. HTTP Status: ${results.cdn.status}.`
        : `Direct CDN connection active. HTTP Status: ${results.cdn.status}.`;
    } else {
      cdnBadge.className = "badge badge-danger";
      cdnBadge.textContent = results.cdn.status === 450 ? "HTTP 450 Blocked" : "Failed";
      cdnDetails.textContent = results.cdn.error || `HTTP Status: ${results.cdn.status}`;
    }
  } catch (err) {
    showToast("Connectivity test failed: " + err.message, "error");
  }
}

// Sync Channels Now
async function syncChannelsNow() {
  showToast("Triggering channel catalog & EPG sync...", "success");
  try {
    const res = await fetch("/api/sync", { method: "POST" });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Sync failed");
    }
    const data = await res.json();
    showToast(`Successfully synced ${data.channels_synced} channels!`, "success");
    fetchStatus();
    loadChannels();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// Load Channels
async function loadChannels() {
  const grid = document.getElementById("channel-grid");
  if (!grid) return;

  try {
    const res = await fetch("/api/channels");
    const data = await res.json();
    allChannels = data.channels || [];
    renderChannels(allChannels);
  } catch (err) {
    grid.innerHTML = `<div class="info-alert alert-error">Failed to load channels: ${err.message}</div>`;
  }
}

// Filter Channels
function filterChannels() {
  const search = document.getElementById("filter-search").value.toLowerCase().trim();
  const lang = document.getElementById("filter-language").value.toLowerCase();
  const genre = document.getElementById("filter-genre").value.toLowerCase();

  const filtered = allChannels.filter(c => {
    const matchSearch = !search || c.channel_name.toLowerCase().includes(search) || String(c.channel_id).includes(search);
    const matchLang = !lang || (c.language && c.language.toLowerCase() === lang);
    const matchGenre = !genre || (c.genre && c.genre.toLowerCase() === genre);
    return matchSearch && matchLang && matchGenre;
  });

  renderChannels(filtered);
}

// Render Channels Grid
function renderChannels(channels) {
  const grid = document.getElementById("channel-grid");
  if (!grid) return;

  if (channels.length === 0) {
    grid.innerHTML = '<div class="metric-sub" style="grid-column: 1 / -1; text-align: center; padding: 2rem;">No channels match the filter.</div>';
    return;
  }

  grid.innerHTML = channels.map(c => `
    <div class="channel-card">
      <div class="channel-logo-wrap">
        <img class="channel-logo" src="${c.logo || 'data:image/svg+xml;utf8,<svg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 24 24\' fill=\'none\' stroke=\'%2364748b\'><rect x=\'2\' y=\'7\' width=\'20\' height=\'15\' rx=\'2\'/><polyline points=\'17 2 12 7 7 2\'/></svg>'}" alt="${c.channel_name}" loading="lazy">
      </div>
      <div class="channel-name" title="${c.channel_name}">${c.channel_name}</div>
      <div class="channel-meta">
        <span class="badge">${c.language || 'TV'}</span>
        ${c.is_hd ? '<span class="badge badge-success">HD</span>' : ''}
      </div>
      <a href="/live/${c.channel_id}" target="_blank" class="btn btn-secondary btn-sm btn-block">
        Play Stream
      </a>
    </div>
  `).join("");
}

// Copy Utilities
function copyInput(elementId) {
  const el = document.getElementById(elementId);
  if (el) copyText(el.value);
}

function copyText(text) {
  navigator.clipboard.writeText(text).then(() => {
    showToast("Copied to clipboard!", "success");
  }).catch(() => {
    showToast("Failed to copy", "error");
  });
}

// OTP Modal Handlers
let pendingMobile = "";

function openOtpModal() {
  document.getElementById("otp-modal").classList.remove("hidden");
  resetOtpStep();
}

function closeOtpModal() {
  document.getElementById("otp-modal").classList.add("hidden");
}

function resetOtpStep() {
  document.getElementById("otp-step-1").classList.remove("hidden");
  document.getElementById("otp-step-2").classList.add("hidden");
  document.getElementById("otp-mobile-input").value = "";
  document.getElementById("otp-code-input").value = "";
}

async function sendOtp() {
  const mobileInput = document.getElementById("otp-mobile-input");
  const rawMobile = mobileInput.value.trim();
  if (rawMobile.length < 10) {
    showToast("Please enter a valid 10-digit mobile number", "error");
    return;
  }
  pendingMobile = "+91" + rawMobile.slice(-10);

  const btn = document.getElementById("btn-send-otp");
  btn.disabled = true;
  btn.textContent = "Sending SMS...";

  try {
    const res = await fetch("/api/auth/otp/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mobile: pendingMobile })
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to send OTP");
    }
    showToast("OTP sent to " + pendingMobile, "success");
    document.getElementById("otp-step-1").classList.add("hidden");
    document.getElementById("otp-step-2").classList.remove("hidden");
    document.getElementById("otp-target-number").textContent = pendingMobile;
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Send OTP SMS";
  }
}

async function verifyOtp() {
  const code = document.getElementById("otp-code-input").value.trim();
  if (code.length < 4) {
    showToast("Please enter the OTP received", "error");
    return;
  }

  const btn = document.getElementById("btn-verify-otp");
  btn.disabled = true;
  btn.textContent = "Verifying...";

  try {
    const res = await fetch("/api/auth/otp/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mobile: pendingMobile, otp: code })
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Invalid OTP");
    }
    showToast("Authenticated successfully!", "success");
    closeOtpModal();
    fetchStatus();
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Verify & Sign In";
  }
}

// Toast Notifications
function showToast(message, type = "success") {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 3500);
}
