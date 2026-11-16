"use strict";

/* ==========================================================================
   TestMaster Bot Studio — Interactive Simulator, Web Quiz Player & Admin UI
   ========================================================================== */

const state = {
  categories: [],
  quizzes: [],
  users: [],
  editorQuestions: [],
  authUsername: null,
  activeCategoryFilter: null,
  selectedQuizId: null,
  selectedUserId: null,
  selectedUserDetail: null,
  simAwaitingInput: null,
  webQuiz: null,
  webTimerHandle: null,
};

// ---------------------------------------------------------------------------
// Core DOM, Formatting & Safe HTML Helpers
// ---------------------------------------------------------------------------

function $id(id) {
  return document.getElementById(id);
}

function showGlobalToast(msg, duration = 3000) {
  const el = $id("globalToast");
  if (!el) return;
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.add("hidden"), duration);
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = String(text ?? "");
  return div.innerHTML;
}

function escapeAttr(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function togglePasswordVisibility(inputId, btnEl) {
  const input = $id(inputId);
  if (!input) return;
  const isPassword = input.type === "password";
  input.type = isPassword ? "text" : "password";
  if (btnEl) {
    btnEl.textContent = isPassword ? "🙈" : "👁";
  }
}

async function apiFetch(url, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const res = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers,
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && url !== "/api/auth/login" && url !== "/api/auth/me") {
    handleUnauthorized();
  }
  if (!res.ok) {
    throw new Error(data.detail || "So'rovda xatolik yuz berdi");
  }
  return data;
}

function renderSafeTelegramHtml(rawHtml) {
  const allowed = new Set(["B", "STRONG", "I", "EM", "CODE", "PRE"]);
  const doc = new DOMParser().parseFromString(String(rawHtml || ""), "text/html");

  function walk(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      return escapeHtml(node.textContent).replace(/\n/g, "<br>");
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return "";
    const childrenHtml = Array.from(node.childNodes).map(walk).join("");
    if (allowed.has(node.tagName)) {
      const tag = node.tagName.toLowerCase();
      return `<${tag}>${childrenHtml}</${tag}>`;
    }
    return childrenHtml;
  }

  return Array.from(doc.body.childNodes).map(walk).join("");
}

function formatDuration(seconds) {
  const sec = Math.max(0, Number(seconds) || 0);
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function diffBadge(diff) {
  if (diff === "oson") return "🟢 Oson";
  if (diff === "qiyin") return "🔴 Qiyin";
  return "🟡 O'rta";
}

// ---------------------------------------------------------------------------
// Authentication, Modal & Navigation
// ---------------------------------------------------------------------------

function showAuthOverlay(errorMsg = "") {
  $id("appShell")?.classList.add("hidden");
  $id("authOverlay")?.classList.remove("hidden");
  closeStudioModal();
  const errBox = $id("authErrorBox");
  if (!errBox) return;
  if (errorMsg) {
    errBox.textContent = errorMsg;
    errBox.classList.remove("hidden");
  } else {
    errBox.textContent = "";
    errBox.classList.add("hidden");
  }
}

function showAppShell(username) {
  state.authUsername = username || "admin";
  $id("authOverlay")?.classList.add("hidden");
  $id("appShell")?.classList.remove("hidden");
  const badge = $id("adminUsernameText");
  if (badge) badge.textContent = state.authUsername;
  const credUser = $id("credNewUsername");
  if (credUser && !credUser.value) credUser.value = state.authUsername;
}

function handleUnauthorized() {
  if (!$id("authOverlay")?.classList.contains("hidden")) return;
  showAuthOverlay("Sessiya muddati tugagan. Iltimos, qayta kiring.");
}

async function loginStudio(e) {
  e.preventDefault();
  const username = $id("loginUsername").value.trim();
  const password = $id("loginPassword").value;
  const errBox = $id("authErrorBox");
  const btn = $id("loginSubmitBtn");
  errBox.classList.add("hidden");
  btn.disabled = true;
  try {
    const res = await apiFetch("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    $id("loginPassword").value = "";
    showAppShell(res.username);
    await refreshAll();
    await simSendText("/start", false);
    showGlobalToast(`🔓 Xush kelibsiz, ${res.username}!`);
  } catch (err) {
    errBox.textContent = err.message || "Login yoki parol noto'g'ri";
    errBox.classList.remove("hidden");
  } finally {
    btn.disabled = false;
  }
}

async function logoutStudio() {
  try {
    await apiFetch("/api/auth/logout", { method: "POST" });
  } catch {
    // Ignore logout transport errors
  }
  state.authUsername = null;
  showAuthOverlay();
  showGlobalToast("🚪 Tizimdan chiqdingiz");
}

async function updateStudioCredentials(e) {
  e.preventDefault();
  const currentPassword = $id("credCurrentPassword").value;
  const newUsername = $id("credNewUsername").value.trim();
  const newPassword = $id("credNewPassword").value;
  try {
    const res = await apiFetch("/api/auth/credentials", {
      method: "POST",
      body: JSON.stringify({
        current_password: currentPassword,
        new_username: newUsername,
        new_password: newPassword,
      }),
    });
    $id("credCurrentPassword").value = "";
    $id("credNewPassword").value = "";
    showAppShell(res.username);
    showGlobalToast(`🔑 Login (${res.username}) va parol yangilandi!`);
  } catch (err) {
    showGlobalToast(`❌ ${err.message}`, 4500);
  }
}

function openStudioModal(title, bodyHtml) {
  $id("studioModalTitle").textContent = title;
  const body = $id("studioModalBody");
  body.innerHTML = bodyHtml;
  $id("studioModal").classList.remove("hidden");
  const firstInput = body.querySelector("input, textarea, select");
  if (firstInput) {
    setTimeout(() => firstInput.focus(), 20);
  }
}

function closeStudioModal() {
  $id("studioModal")?.classList.add("hidden");
}

// ---------------------------------------------------------------------------
// Zenith Sidebar, Theme Customizer & Mini App Helpers
// ---------------------------------------------------------------------------

const ZENITH_PREFS_KEY = "tm_zenith_prefs";

function loadZenithPrefs() {
  try {
    const raw = localStorage.getItem(ZENITH_PREFS_KEY);
    const prefs = raw ? JSON.parse(raw) : {};
    applyZenithPrefs({
      theme: prefs.theme || "dark",
      preset: prefs.preset || "teal",
      density: prefs.density || "default",
      layout: prefs.layout || "sidebar",
    });
  } catch {
    applyZenithPrefs({ theme: "dark", preset: "teal", density: "default", layout: "sidebar" });
  }
}

function applyZenithPrefs(prefs) {
  const root = document.documentElement;
  root.setAttribute("data-theme", prefs.theme);
  root.setAttribute("data-preset", prefs.preset);
  root.setAttribute("data-density", prefs.density);
  root.setAttribute("data-layout", prefs.layout);

  const modeBtn = $id("themeModeBtn");
  if (modeBtn) {
    modeBtn.textContent = prefs.theme === "light" ? "☀️" : "🌙";
  }

  document.querySelectorAll("[data-theme-opt]").forEach((b) => {
    b.classList.toggle("active", b.dataset.themeOpt === prefs.theme);
  });
  document.querySelectorAll("[data-preset-opt]").forEach((b) => {
    b.classList.toggle("active", b.dataset.presetOpt === prefs.preset);
  });
  document.querySelectorAll("[data-density-opt]").forEach((b) => {
    b.classList.toggle("active", b.dataset.densityOpt === prefs.density);
  });
  document.querySelectorAll("[data-layout-opt]").forEach((b) => {
    b.classList.toggle("active", b.dataset.layoutOpt === prefs.layout);
  });
}

function setZenithPref(key, value) {
  const root = document.documentElement;
  const current = {
    theme: root.getAttribute("data-theme") || "dark",
    preset: root.getAttribute("data-preset") || "teal",
    density: root.getAttribute("data-density") || "default",
    layout: root.getAttribute("data-layout") || "sidebar",
  };
  current[key] = value;
  applyZenithPrefs(current);
  try {
    localStorage.setItem(ZENITH_PREFS_KEY, JSON.stringify(current));
  } catch {
    // Ignore storage quota errors
  }
}

function toggleThemeMode() {
  const cur = document.documentElement.getAttribute("data-theme") || "dark";
  setZenithPref("theme", cur === "dark" ? "light" : "dark");
}

function toggleThemeCustomizer() {
  $id("themeCustomizer")?.classList.toggle("hidden");
}

function toggleSidebar() {
  const sidebar = $id("zenithSidebar");
  if (!sidebar) return;
  if (window.innerWidth <= 900) {
    const isOpen = sidebar.classList.toggle("mobile-open");
    $id("sidebarBackdrop")?.classList.toggle("hidden", !isOpen);
  } else {
    sidebar.classList.toggle("collapsed");
  }
}

function closeMobileSidebar() {
  $id("zenithSidebar")?.classList.remove("mobile-open");
  $id("sidebarBackdrop")?.classList.add("hidden");
}

function reloadMiniAppFrame() {
  const frame = $id("miniAppIframe");
  if (frame) {
    frame.src = `/webapp?t=${Date.now()}`;
    showGlobalToast("🔄 Mini App yangilandi");
  }
}

function copyMiniAppUrl() {
  const field = $id("miniAppUrlField");
  if (!field) return;
  navigator.clipboard?.writeText(field.value).catch(() => {});
  showGlobalToast("📋 Mini App URL nusxalandi!");
}

function switchTab(tabName) {
  let activeTitle = "Dashboard";
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    const isActive = btn.dataset.tab === tabName;
    btn.classList.toggle("active", isActive);
    btn.setAttribute("aria-selected", isActive ? "true" : "false");
    if (isActive && btn.dataset.title) {
      activeTitle = btn.dataset.title;
    }
  });
  const bc = $id("activeBreadcrumb");
  if (bc) bc.textContent = activeTitle;

  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `tab-${tabName}`);
  });

  closeMobileSidebar();

  if (tabName === "miniapp") {
    const urlInput = $id("miniAppUrlField");
    if (urlInput && window.location.origin) {
      urlInput.value = `${window.location.origin}/webapp`;
    }
  }
  if (tabName === "users") loadUsers();
  if (tabName === "leaderboard") loadLeaderboard();
  if (tabName === "settings") loadBotStatus();
}

async function refreshAll() {
  await Promise.all([loadStats(), loadCategories(), loadQuizzes(), loadUsers()]);
  renderSimQuizChips();
  renderWebQuizLobby();
  renderAdminLists();
  renderUsersTable();
  populateLeaderboardFilter();
}

// ---------------------------------------------------------------------------
// TAB 4: User Management & Broadcast
// ---------------------------------------------------------------------------

function formatDateTime(isoStr) {
  if (!isoStr) return "—";
  const d = new Date(isoStr);
  if (Number.isNaN(d.getTime())) return String(isoStr).slice(0, 16);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

async function loadUsers() {
  state.users = await apiFetch("/api/users");
  renderUsersTable();
  if (state.selectedUserId) {
    const stillExists = state.users.some((u) => u.id === state.selectedUserId);
    if (stillExists) {
      await refreshSelectedUserChats();
    } else {
      closeUserDetailPanel();
    }
  }
}

function renderUsersTable() {
  const wrap = $id("usersTableWrap");
  if (!wrap) return;
  const search = ($id("userSearchInput")?.value || "").trim().toLowerCase();
  const roleFilter = $id("userRoleFilter")?.value || "all";

  const filtered = state.users.filter((u) => {
    if (roleFilter === "admin" && !u.is_admin) return false;
    if (roleFilter === "user" && u.is_admin) return false;
    if (!search) return true;
    const hay = `${u.full_name} ${u.username || ""} ${u.telegram_id}`.toLowerCase();
    return hay.includes(search);
  });

  if (!filtered.length) {
    wrap.innerHTML = `<p class="muted">Mos keluvchi foydalanuvchi topilmadi.</p>`;
    return;
  }

  wrap.innerHTML = `
    <table class="data-table responsive-table">
      <thead>
        <tr>
          <th>Foydalanuvchi</th>
          <th>Telegram ID</th>
          <th>Rol</th>
          <th>XP</th>
          <th>Testlar</th>
          <th>Aniqlik</th>
          <th>Amallar</th>
        </tr>
      </thead>
      <tbody>
        ${filtered
          .map(
            (u) => `
          <tr class="clickable-row ${state.selectedUserId === u.id ? "selected-row" : ""}" onclick="openUserProfileAndChats(${u.id})">
            <td data-label="Foydalanuvchi">
              <div>
                <strong>${escapeHtml(u.full_name)}</strong>
                ${u.username ? `<div class="muted text-sm">@${escapeHtml(u.username)}</div>` : ""}
              </div>
            </td>
            <td data-label="Telegram ID" class="mono">${u.telegram_id}</td>
            <td data-label="Rol">
              <span class="badge ${u.is_admin ? "badge-admin" : "badge-user"}">
                ${u.is_admin ? "🛡 Admin" : "👤 Foydalanuvchi"}
              </span>
            </td>
            <td data-label="XP"><strong>${u.xp}</strong> XP</td>
            <td data-label="Testlar">${u.tests_completed}</td>
            <td data-label="Aniqlik">${u.accuracy}% (${u.correct_answers}/${u.total_questions})</td>
            <td data-label="Amallar" onclick="event.stopPropagation()">
              <div class="actions-cell">
                <button type="button" class="btn btn-primary btn-sm" title="Profil va chatlar tarixini ko'rish" onclick="openUserProfileAndChats(${u.id})">💬 Chatlar</button>
                <button type="button" class="btn btn-ghost btn-sm" title="Tahrirlash" onclick="openEditUserModal(${u.id})">✏️</button>
                <button type="button" class="btn btn-ghost btn-sm" title="Telegram xabar yuborish" onclick="openMessageUserModal(${u.id})">✉️</button>
                <button type="button" class="btn btn-ghost btn-sm" title="Statistikani nollash" onclick="resetUserStatsConfirm(${u.id})">🔄</button>
                <button type="button" class="btn btn-danger btn-sm" title="O'chirish" onclick="deleteUserConfirm(${u.id})">🗑</button>
              </div>
            </td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderChatBubbleItem(msg, userFullName) {
  const senderClass =
    msg.sender === "user" ? "is-user" : msg.sender === "admin" ? "is-admin" : "is-bot";
  const senderLabel =
    msg.sender === "user"
      ? `👤 ${escapeHtml(userFullName || "Foydalanuvchi")}`
      : msg.sender === "admin"
      ? "👑 Admin xabari"
      : "🤖 TestMaster Bot";
  const typeTag =
    msg.action_type === "callback"
      ? "📲 Tugma"
      : msg.action_type === "admin_message"
      ? "📨 Telegram xabar"
      : "";
  const bodyHtml =
    msg.sender === "user"
      ? escapeHtml(msg.content).replace(/\n/g, "<br>")
      : renderSafeTelegramHtml(msg.content);

  return `
    <div class="chat-msg-item ${senderClass}">
      <div class="chat-msg-meta">
        <strong>${senderLabel}</strong>
        ${typeTag ? `<span>· ${typeTag}</span>` : ""}
        <span class="mono">${formatDateTime(msg.created_at)}</span>
      </div>
      <div class="chat-msg-bubble">${bodyHtml}</div>
    </div>
  `;
}

async function openUserProfileAndChats(userId) {
  state.selectedUserId = userId;
  renderUsersTable();
  try {
    const data = await apiFetch(`/api/users/${userId}/chats`);
    state.selectedUserDetail = data;
    renderSelectedUserDetail();
    const panel = $id("userDetailPanel");
    if (panel) {
      panel.classList.remove("hidden");
      panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  } catch (err) {
    showGlobalToast(`❌ ${err.message}`, 4500);
  }
}

async function refreshSelectedUserChats() {
  if (!state.selectedUserId) return;
  try {
    const data = await apiFetch(`/api/users/${state.selectedUserId}/chats`);
    state.selectedUserDetail = data;
    renderSelectedUserDetail();
  } catch {
    // Ignore background refresh error
  }
}

function renderSelectedUserDetail() {
  const detail = state.selectedUserDetail;
  if (!detail || !detail.user) return;
  const u = detail.user;
  const attempts = detail.attempts || [];

  $id("userDetailAvatar").textContent = u.is_admin ? "🛡" : "👤";
  $id("userDetailTitle").textContent = `${u.full_name} ${u.username ? `(@${u.username})` : ""}`;
  $id("userDetailMeta").textContent = `Telegram ID: ${u.telegram_id} · Ro'yxatdan o'tgan: ${formatDateTime(u.created_at)}`;

  const editBtn = $id("userDetailEditBtn");
  if (editBtn) {
    editBtn.onclick = () => openEditUserModal(u.id);
  }

  $id("userDetailStats").innerHTML = `
    <div class="kpi-card"><span class="kpi-icon">💎</span><div><div class="kpi-val">${u.xp} XP</div><div class="kpi-lbl">Ball</div></div></div>
    <div class="kpi-card"><span class="kpi-icon">📝</span><div><div class="kpi-val">${u.tests_completed} ta</div><div class="kpi-lbl">Yakunlangan test</div></div></div>
    <div class="kpi-card"><span class="kpi-icon">🎯</span><div><div class="kpi-val">${u.accuracy}%</div><div class="kpi-lbl">Aniqlik</div></div></div>
    <div class="kpi-card"><span class="kpi-icon">✅</span><div><div class="kpi-val">${u.correct_answers}/${u.total_questions}</div><div class="kpi-lbl">To'g'ri / Jami</div></div></div>
  `;

  const attWrap = $id("userDetailAttempts");
  if (!attempts.length) {
    attWrap.innerHTML = `<p class="muted text-sm">Hozircha ishlangan testlar yo'q.</p>`;
  } else {
    attWrap.innerHTML = `
      <table class="data-table responsive-table">
        <thead>
          <tr>
            <th>Test</th>
            <th>Rejim</th>
            <th>Natija</th>
            <th>Vaqt</th>
            <th>Sana</th>
          </tr>
        </thead>
        <tbody>
          ${attempts
            .map(
              (a) => `
            <tr>
              <td data-label="Test"><strong>${escapeHtml(a.quiz_title)}</strong> <span class="mono muted">#${escapeHtml(a.quiz_code)}</span></td>
              <td data-label="Rejim">${a.mode === "practice" ? "⚡️ Mashq" : "🎓 Imtihon"}</td>
              <td data-label="Natija">
                ${
                  a.is_completed
                    ? `<strong>${a.percentage}%</strong> (✅ ${a.correct_count} / ❌ ${a.wrong_count})`
                    : `<span class="badge">⏳ Jarayonda</span>`
                }
              </td>
              <td data-label="Vaqt" class="mono">${formatDuration(a.duration_sec)}</td>
              <td data-label="Sana" class="mono text-sm">${formatDateTime(a.finished_at || a.started_at)}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>
    `;
  }

  renderSelectedUserChatMessages();
}

function renderSelectedUserChatMessages() {
  const detail = state.selectedUserDetail;
  if (!detail || !detail.user) return;
  const allMessages = detail.messages || [];
  const query = ($id("userChatSearchInput")?.value || "").trim().toLowerCase();
  const filtered = query
    ? allMessages.filter((m) => String(m.content || "").toLowerCase().includes(query))
    : allMessages;

  $id("userChatCount").textContent = allMessages.length;
  const listEl = $id("userChatHistoryList");
  if (!listEl) return;

  if (!filtered.length) {
    listEl.innerHTML = `<p class="muted text-sm m-0">${
      query ? "Qidiruv bo'yicha yozishma topilmadi." : "Ushbu foydalanuvchida hozircha chat yozishmalari mavjud emas."
    }</p>`;
    return;
  }

  listEl.innerHTML = filtered.map((m) => renderChatBubbleItem(m, detail.user.full_name)).join("");
  listEl.scrollTop = listEl.scrollHeight;
}

function closeUserDetailPanel() {
  state.selectedUserId = null;
  state.selectedUserDetail = null;
  $id("userDetailPanel")?.classList.add("hidden");
  renderUsersTable();
}

async function clearSelectedUserChatsConfirm() {
  const detail = state.selectedUserDetail;
  if (!detail || !detail.user) return;
  if (!confirm(`"${detail.user.full_name}" ning chatlar tarixi tozalansinmi?`)) return;
  try {
    const res = await apiFetch(`/api/users/${detail.user.id}/chats`, { method: "DELETE" });
    await refreshSelectedUserChats();
    showGlobalToast(`🧹 Chat tarixi tozalandi (${res.deleted_count} ta xabar)`);
  } catch (err) {
    showGlobalToast(`❌ ${err.message}`, 4500);
  }
}

async function sendSelectedUserChatReply(e) {
  e.preventDefault();
  const detail = state.selectedUserDetail;
  if (!detail || !detail.user) return;
  const input = $id("userChatReplyInput");
  const text = input.value.trim();
  if (!text) return;
  try {
    const res = await apiFetch("/api/bot/broadcast", {
      method: "POST",
      body: JSON.stringify({ text, telegram_id: detail.user.telegram_id }),
    });
    input.value = "";
    await refreshSelectedUserChats();
    if (res.sent > 0) {
      showGlobalToast("✅ Xabar yuborildi va chat tarixiga qo'shildi");
    } else {
      showGlobalToast("⚠️ Chat tarixiga yozildi, ammo foydalanuvchi botni bloklagan bo'lishi mumkin", 4500);
    }
  } catch (err) {
    showGlobalToast(`❌ ${err.message}`, 4500);
  }
}

function openCreateUserModal() {
  openStudioModal(
    "➕ Yangi Foydalanuvchi Qo'shish",
    `<form onsubmit="submitCreateUser(event)" class="stack-form">
      <div>
        <label class="field-lbl" for="newUserTgId">Telegram ID</label>
        <input id="newUserTgId" class="input mono" type="number" required placeholder="Masalan: 123456789" />
      </div>
      <div>
        <label class="field-lbl" for="newUserFullName">To'liq ism</label>
        <input id="newUserFullName" class="input" type="text" required placeholder="Ali Valiyev" />
      </div>
      <div class="form-row-2">
        <div>
          <label class="field-lbl" for="newUserUsername">Username (@ siz)</label>
          <input id="newUserUsername" class="input" type="text" placeholder="alivaliyev" />
        </div>
        <div>
          <label class="field-lbl" for="newUserXp">Boshlang'ich XP</label>
          <input id="newUserXp" class="input" type="number" min="0" value="0" />
        </div>
      </div>
      <label class="check-row">
        <input id="newUserIsAdmin" type="checkbox" />
        <span>🛡 Telegram Bot Admin huquqini berish</span>
      </label>
      <div class="btn-row">
        <button type="submit" class="btn btn-primary">💾 Saqlash</button>
        <button type="button" class="btn btn-ghost" onclick="closeStudioModal()">Bekor qilish</button>
      </div>
    </form>`
  );
}

async function submitCreateUser(e) {
  e.preventDefault();
  try {
    await apiFetch("/api/users", {
      method: "POST",
      body: JSON.stringify({
        telegram_id: Number($id("newUserTgId").value),
        full_name: $id("newUserFullName").value.trim(),
        username: $id("newUserUsername").value.trim().replace(/^@/, ""),
        xp: Number($id("newUserXp").value) || 0,
        is_admin: $id("newUserIsAdmin").checked,
      }),
    });
    closeStudioModal();
    await refreshAll();
    showGlobalToast("✅ Yangi foydalanuvchi qo'shildi");
  } catch (err) {
    showGlobalToast(`❌ ${err.message}`, 4500);
  }
}

function openEditUserModal(userId) {
  const user = state.users.find((u) => u.id === userId);
  if (!user) return;
  openStudioModal(
    `✏️ Foydalanuvchini Tahrirlash (#${user.id})`,
    `<form onsubmit="submitEditUser(event, ${user.id})" class="stack-form">
      <div>
        <label class="field-lbl" for="editUserFullName">To'liq ism</label>
        <input id="editUserFullName" class="input" type="text" value="${escapeAttr(user.full_name)}" required />
      </div>
      <div class="form-row-2">
        <div>
          <label class="field-lbl" for="editUserUsername">Username (@ siz)</label>
          <input id="editUserUsername" class="input" type="text" value="${escapeAttr(user.username || "")}" />
        </div>
        <div>
          <label class="field-lbl" for="editUserTgId">Telegram ID</label>
          <input id="editUserTgId" class="input mono" type="number" value="${user.telegram_id}" required />
        </div>
      </div>
      <div class="form-row-2">
        <div>
          <label class="field-lbl" for="editUserXp">XP ball</label>
          <input id="editUserXp" class="input" type="number" min="0" value="${user.xp}" required />
        </div>
        <div>
          <label class="field-lbl" for="editUserTests">Yakunlangan testlar</label>
          <input id="editUserTests" class="input" type="number" min="0" value="${user.tests_completed}" required />
        </div>
      </div>
      <div class="form-row-2">
        <div>
          <label class="field-lbl" for="editUserCorrect">To'g'ri javoblar</label>
          <input id="editUserCorrect" class="input" type="number" min="0" value="${user.correct_answers}" required />
        </div>
        <div>
          <label class="field-lbl" for="editUserTotalQ">Jami savollar</label>
          <input id="editUserTotalQ" class="input" type="number" min="0" value="${user.total_questions}" required />
        </div>
      </div>
      <label class="check-row">
        <input id="editUserIsAdmin" type="checkbox" ${user.is_admin ? "checked" : ""} />
        <span>🛡 Telegram Bot Admin (barcha boshqaruv buyruqlariga ruxsat)</span>
      </label>
      <div class="btn-row">
        <button type="submit" class="btn btn-primary">💾 O'zgarishlarni Saqlash</button>
        <button type="button" class="btn btn-ghost" onclick="closeStudioModal()">Bekor qilish</button>
      </div>
    </form>

    <div class="divider"></div>
    <div class="row-between mb-2">
      <h4 class="subhead m-0">💬 Chatlar tarixi</h4>
      <button type="button" class="btn btn-ghost btn-sm" onclick="closeStudioModal(); openUserProfileAndChats(${user.id})">
        🔍 To'liq chat oynasida ochish
      </button>
    </div>
    <div class="chat-history-frame">
      <div id="modalUserChatList" class="chat-history-messages modal-chat-box">
        <p class="muted text-sm m-0">Yuklanmoqda...</p>
      </div>
    </div>`
  );
  loadModalUserChatPreview(user.id, user.full_name);
}

async function loadModalUserChatPreview(userId, userFullName) {
  const box = $id("modalUserChatList");
  if (!box) return;
  try {
    const data = await apiFetch(`/api/users/${userId}/chats?limit=50`);
    const msgs = data.messages || [];
    if (!msgs.length) {
      box.innerHTML = `<p class="muted text-sm m-0">Hozircha chat yozishmalari mavjud emas.</p>`;
      return;
    }
    box.innerHTML = msgs.map((m) => renderChatBubbleItem(m, userFullName)).join("");
    box.scrollTop = box.scrollHeight;
  } catch {
    box.innerHTML = `<p class="muted text-sm m-0">Chat tarixini yuklab bo'lmadi.</p>`;
  }
}

async function submitEditUser(e, userId) {
  e.preventDefault();
  try {
    await apiFetch(`/api/users/${userId}`, {
      method: "PUT",
      body: JSON.stringify({
        full_name: $id("editUserFullName").value.trim(),
        username: $id("editUserUsername").value.trim().replace(/^@/, ""),
        telegram_id: Number($id("editUserTgId").value),
        xp: Number($id("editUserXp").value) || 0,
        tests_completed: Number($id("editUserTests").value) || 0,
        correct_answers: Number($id("editUserCorrect").value) || 0,
        total_questions: Number($id("editUserTotalQ").value) || 0,
        is_admin: $id("editUserIsAdmin").checked,
      }),
    });
    closeStudioModal();
    await refreshAll();
    showGlobalToast("✅ Foydalanuvchi ma'lumotlari saqlandi");
  } catch (err) {
    showGlobalToast(`❌ ${err.message}`, 4500);
  }
}

function openMessageUserModal(userId) {
  const user = state.users.find((u) => u.id === userId);
  if (!user) return;
  openStudioModal(
    `✉️ ${escapeHtml(user.full_name)} ga Telegram Xabar`,
    `<form onsubmit="submitDirectMessage(event, ${user.telegram_id})" class="stack-form">
      <p class="muted text-sm m-0">Qabul qiluvchi Telegram ID: <code class="mono text-accent">${user.telegram_id}</code></p>
      <div>
        <label class="field-lbl" for="directMsgText">Xabar matni</label>
        <textarea id="directMsgText" class="input" rows="4" required placeholder="Salom! Sizga xabar..."></textarea>
      </div>
      <div class="btn-row">
        <button type="submit" class="btn btn-primary">📨 Yuborish</button>
        <button type="button" class="btn btn-ghost" onclick="closeStudioModal()">Bekor qilish</button>
      </div>
    </form>`
  );
}

async function submitDirectMessage(e, telegramId) {
  e.preventDefault();
  const text = $id("directMsgText").value.trim();
  if (!text) return;
  try {
    const res = await apiFetch("/api/bot/broadcast", {
      method: "POST",
      body: JSON.stringify({ text, telegram_id: telegramId }),
    });
    closeStudioModal();
    if (res.sent > 0) {
      showGlobalToast("✅ Telegram xabar yuborildi");
    } else {
      showGlobalToast("⚠️ Xabar yuborilmadi (botga start bosmagan bo'lishi mumkin)", 4500);
    }
  } catch (err) {
    showGlobalToast(`❌ ${err.message}`, 4500);
  }
}

async function sendBroadcast(e) {
  e.preventDefault();
  const input = $id("broadcastTextInput");
  const text = input.value.trim();
  if (!text) return;
  if (!confirm("Haqiqatan ham barcha Telegram foydalanuvchilarga xabar yuborilsinmi?")) return;
  try {
    const res = await apiFetch("/api/bot/broadcast", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    input.value = "";
    showGlobalToast(`📢 Yuborildi: ${res.sent}/${res.total} ta (xato: ${res.failed})`, 4500);
  } catch (err) {
    showGlobalToast(`❌ ${err.message}`, 4500);
  }
}

async function resetUserStatsConfirm(userId) {
  const user = state.users.find((u) => u.id === userId);
  if (!user) return;
  if (!confirm(`"${user.full_name}" ning XP, statistika va barcha test urinishlari nollansinmi?`)) return;
  try {
    await apiFetch(`/api/users/${userId}/reset`, { method: "POST" });
    await refreshAll();
    showGlobalToast("🔄 Foydalanuvchi statistikasi nollandi");
  } catch (err) {
    showGlobalToast(`❌ ${err.message}`, 4500);
  }
}

async function deleteUserConfirm(userId) {
  const user = state.users.find((u) => u.id === userId);
  if (!user) return;
  if (!confirm(`"${user.full_name}" va uning barcha test natijalari butunlay o'chirilsinmi?`)) return;
  try {
    await apiFetch(`/api/users/${userId}`, { method: "DELETE" });
    await refreshAll();
    showGlobalToast("🗑 Foydalanuvchi o'chirildi");
  } catch (err) {
    showGlobalToast(`❌ ${err.message}`, 4500);
  }
}

// ---------------------------------------------------------------------------
// Dashboard KPI & Status Updates
// ---------------------------------------------------------------------------

async function loadStats() {
  const data = await apiFetch("/api/stats");
  $id("kpiCategories").textContent = data.categories_count;
  $id("kpiQuizzes").textContent = data.quizzes_count;
  $id("kpiQuestions").textContent = data.questions_count;
  $id("kpiUsers").textContent = data.users_count;
  $id("kpiAvg").textContent = `${data.avg_percentage}%`;
  updateBotStatusUI(data.bot_status, data.admin_ids);
  renderRecentAttempts(data.recent_attempts || []);
}

async function loadCategories() {
  state.categories = await apiFetch("/api/categories");
}

async function loadQuizzes() {
  state.quizzes = await apiFetch("/api/quizzes");
}

function updateBotStatusUI(status, adminIds) {
  const pill = $id("botStatusBadge");
  const txt = $id("botStatusText");
  const simTitle = $id("simBotTitle");
  const banner = $id("settingsStatusBox");
  const adminInput = $id("adminIdsInput");

  if (adminInput && adminIds !== undefined && !adminInput.value) {
    adminInput.value = adminIds;
  }

  pill.classList.remove("status-live", "status-sim", "status-err");
  if (status && status.running) {
    pill.classList.add("status-live");
    txt.textContent = `Faol: @${status.bot_username}`;
    simTitle.textContent = `${status.bot_name || "TestMaster"} (@${status.bot_username})`;
    if (banner) {
      banner.innerHTML = `🟢 <strong>Telegram bot faol ishlamoqda!</strong> <a href="https://t.me/${escapeAttr(status.bot_username)}" target="_blank" rel="noopener noreferrer" class="link-accent">@${escapeHtml(status.bot_username)}</a>`;
    }
  } else if (status && status.error) {
    pill.classList.add("status-err");
    txt.textContent = "Token xatosi";
    if (banner) {
      banner.innerHTML = `🔴 <strong>Ulanish xatosi:</strong> ${escapeHtml(status.error)}`;
    }
  } else {
    pill.classList.add("status-sim");
    txt.textContent = "Simulyator rejimi";
    simTitle.textContent = "TestMaster Bot";
    if (banner) {
      banner.innerHTML = `🟡 <strong>Simulyator rejimi faol.</strong> Haqiqiy Telegram'ga ulash uchun quyida <code>BOT_TOKEN</code> kiriting.`;
    }
  }
}

// ---------------------------------------------------------------------------
// TAB 1: Telegram Bot Simulator
// ---------------------------------------------------------------------------

function simIdentity() {
  return {
    telegram_id: 999000111,
    full_name: $id("simUserName").value.trim() || "Mehmon Foydalanuvchi",
    username: "simulator_user",
    is_admin: $id("simUserRole").value === "true",
  };
}

function showSimToast(msg) {
  const toast = $id("tgToast");
  if (!toast || !msg) return;
  toast.textContent = msg;
  toast.classList.remove("hidden");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toast.classList.add("hidden"), 2500);
}

function appendUserBubble(text) {
  const area = $id("tgMessages");
  const bubble = document.createElement("div");
  bubble.className = "tg-user-bubble";
  bubble.textContent = text;
  area.appendChild(bubble);
  scrollChatBottom();
}

function renderBotCard(resp, replaceLast = false) {
  const area = $id("tgMessages");
  const card = document.createElement("div");
  card.className = "tg-bot-card";

  const bubble = document.createElement("div");
  bubble.className = "tg-bubble";
  bubble.innerHTML = renderSafeTelegramHtml(resp.text);
  card.appendChild(bubble);

  if (resp.keyboard && resp.keyboard.length) {
    const kbWrap = document.createElement("div");
    kbWrap.className = "tg-inline-kb";
    resp.keyboard.forEach((row) => {
      const rowDiv = document.createElement("div");
      rowDiv.className = "tg-kb-row";
      row.forEach((btnSpec) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "tg-kb-btn";
        b.textContent = btnSpec.text;
        b.title = btnSpec.text;
        if (btnSpec.web_app_url) {
          b.onclick = () => {
            switchTab("miniapp");
            showGlobalToast("📱 Mini App rejimi ochildi");
          };
        } else {
          b.onclick = () => simSendCallback(btnSpec.callback_data);
        }
        rowDiv.appendChild(b);
      });
      kbWrap.appendChild(rowDiv);
    });
    card.appendChild(kbWrap);
  }

  const last = area.lastElementChild;
  if (replaceLast && last && last.classList.contains("tg-bot-card")) {
    area.replaceChild(card, last);
  } else {
    area.appendChild(card);
  }
  if (resp.toast) showSimToast(resp.toast);
  state.simAwaitingInput = resp.awaiting_input || null;
  scrollChatBottom();
}

function scrollChatBottom() {
  const chat = $id("tgChatArea");
  if (chat) chat.scrollTop = chat.scrollHeight;
}

async function simSendText(text, showEcho = true) {
  if (!text) return;
  if (text === "/start") {
    $id("tgMessages").innerHTML = "";
  }
  if (showEcho) appendUserBubble(text);
  const resp = await apiFetch("/api/simulator/action", {
    method: "POST",
    body: JSON.stringify({ ...simIdentity(), text }),
  });
  renderBotCard(resp, false);
  loadStats();
}

async function simSendCallback(callbackData) {
  const resp = await apiFetch("/api/simulator/action", {
    method: "POST",
    body: JSON.stringify({ ...simIdentity(), callback_data: callbackData }),
  });
  renderBotCard(resp, true);
  if (callbackData.startsWith("qz:fc:") || callbackData === "m:main") {
    loadStats();
  }
}

function simSubmitForm(e) {
  e.preventDefault();
  const inp = $id("simTextInput");
  const txt = inp.value.trim();
  if (!txt) return;
  inp.value = "";
  simSendText(txt, true);
}

function renderSimQuizChips() {
  const wrap = $id("simQuizCodes");
  if (!wrap) return;
  wrap.innerHTML = state.quizzes
    .map(
      (qz) => `
      <button type="button" class="code-chip" onclick="simSendText('${escapeAttr(qz.code)}')">
        <div class="cc-code">#${escapeHtml(qz.code)} · ${qz.question_count} savol</div>
        <div class="cc-title">${escapeHtml(qz.category_icon)} ${escapeHtml(qz.title)}</div>
      </button>`
    )
    .join("");
}

// ---------------------------------------------------------------------------
// TAB 2: Web Quiz Player
// ---------------------------------------------------------------------------

function renderWebQuizLobby() {
  const filterWrap = $id("webCategoryFilter");
  if (!filterWrap) return;
  const pills = [
    `<button type="button" class="pill-btn ${state.activeCategoryFilter === null ? "active" : ""}" onclick="setWebCategoryFilter(null)">🌐 Barchasi</button>`,
    ...state.categories.map(
      (c) =>
        `<button type="button" class="pill-btn ${state.activeCategoryFilter === c.id ? "active" : ""}" onclick="setWebCategoryFilter(${c.id})">${escapeHtml(c.icon)} ${escapeHtml(c.name)}</button>`
    ),
  ];
  filterWrap.innerHTML = pills.join("");

  const filtered = state.activeCategoryFilter
    ? state.quizzes.filter((q) => q.category_id === state.activeCategoryFilter)
    : state.quizzes;

  const grid = $id("webQuizzesGrid");
  if (!filtered.length) {
    grid.innerHTML = `<div class="glass-card"><p class="muted m-0">Ushbu yo'nalishda testlar topilmadi.</p></div>`;
    return;
  }

  grid.innerHTML = filtered
    .map(
      (qz) => `
      <article class="quiz-card">
        <div>
          <div class="quiz-card-top">
            <span class="badge">${escapeHtml(qz.category_icon)} ${escapeHtml(qz.category_name)}</span>
            <span class="badge mono">#${escapeHtml(qz.code)}</span>
          </div>
          <h3>${escapeHtml(qz.title)}</h3>
          <p class="muted text-sm">${escapeHtml(qz.description || "Bilimingizni sinab ko'ring.")}</p>
          <div class="quiz-meta">
            <span>${diffBadge(qz.difficulty)}</span>
            <span>❓ ${qz.question_count} savol</span>
            <span>⏱ ${formatDuration(qz.time_limit_sec)}</span>
          </div>
        </div>
        <div class="btn-row">
          <button type="button" class="btn btn-primary btn-sm" ${qz.question_count ? "" : "disabled"} onclick="webStartQuiz(${qz.id}, 'practice')">▶️ Test ishlash (1–${qz.question_count})</button>
          <button type="button" class="btn btn-ghost btn-sm" ${qz.question_count ? "" : "disabled"} onclick="webStartQuiz(${qz.id}, 'exam')">🎓 Imtihon</button>
        </div>
      </article>`
    )
    .join("");
}

function setWebCategoryFilter(catId) {
  state.activeCategoryFilter = catId;
  renderWebQuizLobby();
}

async function webStartByCode() {
  const code = $id("webCodeInput").value.trim().toUpperCase();
  if (!code) {
    showGlobalToast("Test kodini kiriting");
    return;
  }
  const match = state.quizzes.find((q) => q.code.toUpperCase() === code);
  if (!match) {
    showGlobalToast(`#${code} kodi bo'yicha test topilmadi`);
    return;
  }
  await webStartQuiz(match.id, "practice");
}

async function webStartQuiz(quizId, mode) {
  try {
    const data = await apiFetch("/api/web-quiz/start", {
      method: "POST",
      body: JSON.stringify({
        quiz_id: quizId,
        mode,
        full_name: $id("simUserName").value.trim() || "Web Foydalanuvchi",
      }),
    });
    state.webQuiz = {
      attempt: data.attempt,
      quiz: data.quiz,
      questions: data.questions,
      index: 0,
      answers: {},
      feedback: {},
      startedMs: Date.now(),
      remainingSec: data.quiz.time_limit_sec,
    };
    $id("webQuizLobby").classList.add("hidden");
    $id("webQuizRunner").classList.remove("hidden");
    startWebTimer();
    renderWebRunner();
  } catch (err) {
    showGlobalToast(err.message);
  }
}

function startWebTimer() {
  clearInterval(state.webTimerHandle);
  state.webTimerHandle = setInterval(() => {
    if (!state.webQuiz) {
      clearInterval(state.webTimerHandle);
      return;
    }
    const elapsed = Math.floor((Date.now() - state.webQuiz.startedMs) / 1000);
    state.webQuiz.remainingSec = Math.max(0, state.webQuiz.quiz.time_limit_sec - elapsed);
    const timerEl = $id("webRunnerTimer");
    if (timerEl) timerEl.textContent = formatDuration(state.webQuiz.remainingSec);
    if (state.webQuiz.remainingSec <= 0 && state.webQuiz.attempt.mode === "exam") {
      clearInterval(state.webTimerHandle);
      webFinishQuiz(true);
    }
  }, 1000);
}

function renderWebRunner() {
  const wq = state.webQuiz;
  if (!wq) return;
  const container = $id("webQuizRunner");
  const q = wq.questions[wq.index];
  const total = wq.questions.length;
  const pct = Math.round(((wq.index + 1) / total) * 100);
  const selected = wq.answers[q.id];
  const fb = wq.feedback[q.id];
  const isPractice = wq.attempt.mode === "practice";

  const opts = [
    ["A", q.option_a],
    ["B", q.option_b],
    ["C", q.option_c],
    ["D", q.option_d],
  ];

  const optionHtml = opts
    .map(([letter, text]) => {
      let cls = "opt-btn";
      if (fb) {
        if (letter === fb.correct_option) cls += " correct";
        else if (letter === fb.selected_option) cls += " wrong";
      } else if (selected === letter) {
        cls += " selected";
      }
      const disabled = isPractice && fb ? "disabled" : "";
      const isCorrOpt = letter === q.correct_option;
      return `
        <button type="button" class="${cls}" ${disabled} onclick="webSelectOption(${q.id}, '${letter}')">
          <span class="opt-letter">${letter}</span>
          <span>${escapeHtml(text)}${isCorrOpt ? " ✅" : ""}</span>
        </button>`;
    })
    .join("");

  let fbHtml = "";
  if (fb) {
    fbHtml = `
      <div class="explanation-box">
        <strong>${fb.is_correct ? "✅ To'g'ri javob!" : `❌ Noto'g'ri! To'g'ri javob: ${fb.correct_option}`}</strong>
        ${fb.explanation ? `<p class="mt-1 m-0">💡 ${escapeHtml(fb.explanation)}</p>` : ""}
      </div>`;
  }

  const dotsHtml = wq.questions
    .map(
      (item, idx) =>
        `<button type="button" class="dot-btn ${idx === wq.index ? "active" : ""} ${wq.answers[item.id] ? "answered" : ""}" onclick="webJumpQuestion(${idx})">${idx + 1}</button>`
    )
    .join("");

  container.innerHTML = `
    <div class="glass-card runner-wrap">
      <div class="row-between">
        <div>
          <span class="badge">${isPractice ? "⚡️ Mashq rejimi" : "🎓 Imtihon rejimi"}</span>
          <h2 class="runner-title">${escapeHtml(wq.quiz.title)}</h2>
        </div>
        <div class="btn-row">
          <span class="badge mono">⏱ <span id="webRunnerTimer">${formatDuration(wq.remainingSec)}</span></span>
          <button type="button" class="btn btn-danger btn-sm" onclick="webFinishQuiz(false)">🚪 Chiqish va yakunlash</button>
        </div>
      </div>

      <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
      <div class="row-between text-sm muted m-0">
        <span>Savol <strong>${wq.index + 1} / ${total}</strong></span>
        <span>Belgilangan: <strong>${Object.keys(wq.answers).length} / ${total}</strong></span>
      </div>

      <h3 class="runner-question-title">${wq.index + 1}. ${escapeHtml(q.question_text)}</h3>
      <div class="option-grid">${optionHtml}</div>
      ${fbHtml}

      <div class="row-between mt-4">
        <button type="button" class="btn btn-ghost" ${wq.index === 0 ? "disabled" : ""} onclick="webJumpQuestion(${wq.index - 1})">⬅️ Oldingi</button>
        ${
          wq.index + 1 < total
            ? `<button type="button" class="btn btn-primary" onclick="webJumpQuestion(${wq.index + 1})">Keyingi savol ➡️</button>`
            : `<button type="button" class="btn btn-emerald" onclick="webFinishQuiz(false)">🏁 Natijani ko'rish</button>`
        }
      </div>

      <div class="runner-dots">${dotsHtml}</div>
    </div>
  `;
}

async function webSelectOption(questionId, letter) {
  const wq = state.webQuiz;
  if (!wq) return;
  if (wq.attempt.mode === "practice" && wq.feedback[questionId]) return;
  wq.answers[questionId] = letter;
  const res = await apiFetch("/api/web-quiz/answer", {
    method: "POST",
    body: JSON.stringify({
      attempt_id: wq.attempt.id,
      question_id: questionId,
      selected_option: letter,
    }),
  });
  if (wq.attempt.mode === "practice") {
    wq.feedback[questionId] = res;
  }
  renderWebRunner();
}

function webJumpQuestion(idx) {
  const wq = state.webQuiz;
  if (!wq) return;
  wq.index = Math.max(0, Math.min(idx, wq.questions.length - 1));
  renderWebRunner();
}

async function webFinishQuiz(autoExpired = false) {
  clearInterval(state.webTimerHandle);
  const wq = state.webQuiz;
  if (!wq) return;
  const durationSec = Math.max(1, Math.floor((Date.now() - wq.startedMs) / 1000));
  const res = await apiFetch("/api/web-quiz/finish", {
    method: "POST",
    body: JSON.stringify({ attempt_id: wq.attempt.id, duration_sec: durationSec }),
  });
  state.webQuiz = null;
  await loadStats();

  const att = res.attempt;
  const container = $id("webQuizRunner");
  const reviewHtml = (res.review_items || [])
    .map((item) => {
      const q = item.question;
      const badge = item.is_correct ? "✅ To'g'ri" : item.selected_option ? "❌ Noto'g'ri" : "⏭ O'tkazilgan";
      return `
        <div class="q-item">
          <div class="row-between">
            <strong>${item.number}. ${escapeHtml(q.question_text)}</strong>
            <span class="badge">${badge}</span>
          </div>
          <p class="text-sm muted mt-1">
            Sizning javobingiz: <strong>${item.selected_option || "—"}</strong> · To'g'ri javob: <strong class="text-emerald">${q.correct_option}</strong>
            ${q.explanation ? `<br>💡 ${escapeHtml(q.explanation)}` : ""}
          </p>
        </div>`;
    })
    .join("");

  container.innerHTML = `
    <div class="glass-card runner-wrap">
      ${autoExpired ? `<div class="status-banner">⏰ Ajratilgan vaqt tugadi! Test avtomatik yakunlandi.</div>` : ""}
      <div class="row-between">
        <div>
          <span class="badge">🎉 Test yakunlandi</span>
          <h2 class="runner-title">${escapeHtml(res.quiz.title)}</h2>
        </div>
        <button type="button" class="btn btn-primary" onclick="webExitRunner()">📚 Testlar ro'yxatiga</button>
      </div>
      <div class="kpi-grid mt-3">
        <div class="kpi-card"><span class="kpi-icon">🎯</span><div><div class="kpi-val">${att.percentage}%</div><div class="kpi-lbl">Natija</div></div></div>
        <div class="kpi-card"><span class="kpi-icon">✅</span><div><div class="kpi-val">${att.correct_count}</div><div class="kpi-lbl">To'g'ri</div></div></div>
        <div class="kpi-card"><span class="kpi-icon">❌</span><div><div class="kpi-val">${att.wrong_count}</div><div class="kpi-lbl">Noto'g'ri</div></div></div>
        <div class="kpi-card"><span class="kpi-icon">💎</span><div><div class="kpi-val">${att.score}/${att.total_points}</div><div class="kpi-lbl">Ball</div></div></div>
        <div class="kpi-card kpi-card-wide"><span class="kpi-icon">⏱</span><div><div class="kpi-val">${formatDuration(att.duration_sec)}</div><div class="kpi-lbl">Vaqt</div></div></div>
      </div>
      <h3 class="mt-3 mb-2">📋 Savollar tahlili</h3>
      <div class="questions-list questions-scroll">${reviewHtml}</div>
    </div>
  `;
}

function webExitRunner() {
  clearInterval(state.webTimerHandle);
  state.webQuiz = null;
  $id("webQuizRunner").classList.add("hidden");
  $id("webQuizLobby").classList.remove("hidden");
}

// ---------------------------------------------------------------------------
// TAB 3: Admin Panel (Categories, Quizzes & Questions)
// ---------------------------------------------------------------------------

function renderAdminLists() {
  const catSelect = $id("quizCatSelect");
  if (catSelect) {
    catSelect.innerHTML = state.categories
      .map((c) => `<option value="${c.id}">${escapeHtml(c.icon)} ${escapeHtml(c.name)}</option>`)
      .join("");
  }

  const catList = $id("adminCategoriesList");
  if (catList) {
    catList.innerHTML = state.categories
      .map(
        (c) => `
        <div class="list-item">
          <div>
            <strong>${escapeHtml(c.icon)} ${escapeHtml(c.name)}</strong>
            <div class="muted text-sm">${c.quiz_count} ta test · ${c.question_count} ta savol</div>
          </div>
          <div class="btn-row">
            <button type="button" class="btn btn-ghost btn-sm" title="Kategoriyani tahrirlash" onclick="openEditCategoryModal(${c.id})">✏️</button>
            <button type="button" class="btn btn-danger btn-sm" title="O'chirish" onclick="adminDeleteCategory(${c.id})">🗑</button>
          </div>
        </div>`
      )
      .join("");
  }

  const qList = $id("adminQuizzesList");
  if (qList) {
    qList.innerHTML = state.quizzes
      .map(
        (qz) => `
        <div class="list-item clickable ${state.selectedQuizId === qz.id ? "active-item" : ""}" onclick="openQuestionEditor(${qz.id})">
          <div>
            <strong>${escapeHtml(qz.category_icon)} ${escapeHtml(qz.title)}</strong>
            <div class="muted text-sm">
              Kod: <code class="text-accent">${escapeHtml(qz.code)}</code> · ${diffBadge(qz.difficulty)} · ${qz.question_count} ta savol · ⏱ ${formatDuration(qz.time_limit_sec)}
            </div>
          </div>
          <div class="btn-row" onclick="event.stopPropagation()">
            <button type="button" class="btn btn-ghost btn-sm" onclick="openQuestionEditor(${qz.id})">📝 Savollar</button>
            <button type="button" class="btn btn-ghost btn-sm" title="Testni tahrirlash" onclick="openEditQuizModal(${qz.id})">✏️</button>
            <button type="button" class="btn btn-danger btn-sm" title="O'chirish" onclick="adminDeleteQuiz(${qz.id})">🗑</button>
          </div>
        </div>`
      )
      .join("");
  }
}

function openEditCategoryModal(catId) {
  const cat = state.categories.find((c) => c.id === catId);
  if (!cat) return;
  openStudioModal(
    "✏️ Kategoriyani Tahrirlash",
    `<form onsubmit="submitEditCategory(event, ${cat.id})" class="stack-form">
      <div class="form-row-2">
        <div>
          <label class="field-lbl" for="editCatIcon">Ikonka (emoji)</label>
          <input id="editCatIcon" class="input" type="text" value="${escapeAttr(cat.icon)}" required />
        </div>
        <div>
          <label class="field-lbl" for="editCatName">Kategoriya nomi</label>
          <input id="editCatName" class="input" type="text" value="${escapeAttr(cat.name)}" required />
        </div>
      </div>
      <div>
        <label class="field-lbl" for="editCatDesc">Tavsif</label>
        <input id="editCatDesc" class="input" type="text" value="${escapeAttr(cat.description || "")}" />
      </div>
      <label class="check-row">
        <input id="editCatActive" type="checkbox" ${cat.is_active ? "checked" : ""} />
        <span>Faol holatda</span>
      </label>
      <div class="btn-row">
        <button type="submit" class="btn btn-primary">💾 Saqlash</button>
        <button type="button" class="btn btn-ghost" onclick="closeStudioModal()">Bekor qilish</button>
      </div>
    </form>`
  );
}

async function submitEditCategory(e, catId) {
  e.preventDefault();
  try {
    await apiFetch(`/api/categories/${catId}`, {
      method: "PUT",
      body: JSON.stringify({
        icon: $id("editCatIcon").value.trim() || "📚",
        name: $id("editCatName").value.trim(),
        description: $id("editCatDesc").value.trim(),
        is_active: $id("editCatActive").checked,
      }),
    });
    closeStudioModal();
    await refreshAll();
    showGlobalToast("✅ Kategoriya yangilandi");
  } catch (err) {
    showGlobalToast(`❌ ${err.message}`, 4500);
  }
}

function openEditQuizModal(quizId) {
  const qz = state.quizzes.find((q) => q.id === quizId);
  if (!qz) return;
  const catOpts = state.categories
    .map(
      (c) =>
        `<option value="${c.id}" ${c.id === qz.category_id ? "selected" : ""}>${escapeHtml(c.icon)} ${escapeHtml(c.name)}</option>`
    )
    .join("");
  const diffOpts = ["oson", "orta", "qiyin"]
    .map((d) => `<option value="${d}" ${qz.difficulty === d ? "selected" : ""}>${diffBadge(d)}</option>`)
    .join("");

  openStudioModal(
    "✏️ Testni Tahrirlash",
    `<form onsubmit="submitEditQuiz(event, ${qz.id})" class="stack-form">
      <div>
        <label class="field-lbl" for="editQuizCat">Kategoriya</label>
        <select id="editQuizCat" class="input">${catOpts}</select>
      </div>
      <div class="form-row-2">
        <div>
          <label class="field-lbl" for="editQuizTitle">Test nomi</label>
          <input id="editQuizTitle" class="input" type="text" value="${escapeAttr(qz.title)}" required />
        </div>
        <div>
          <label class="field-lbl" for="editQuizCode">Test kodi (#)</label>
          <input id="editQuizCode" class="input mono" type="text" value="${escapeAttr(qz.code)}" required />
        </div>
      </div>
      <div class="form-row-2">
        <div>
          <label class="field-lbl" for="editQuizDiff">Qiyinlik darajasi</label>
          <select id="editQuizDiff" class="input">${diffOpts}</select>
        </div>
        <div>
          <label class="field-lbl" for="editQuizTime">Vaqt limiti (soniya)</label>
          <input id="editQuizTime" class="input" type="number" min="30" max="7200" value="${qz.time_limit_sec}" required />
        </div>
      </div>
      <div>
        <label class="field-lbl" for="editQuizDesc">Tavsif</label>
        <input id="editQuizDesc" class="input" type="text" value="${escapeAttr(qz.description || "")}" />
      </div>
      <label class="check-row">
        <input id="editQuizActive" type="checkbox" ${qz.is_active ? "checked" : ""} />
        <span>Faol test</span>
      </label>
      <div class="btn-row">
        <button type="submit" class="btn btn-primary">💾 Saqlash</button>
        <button type="button" class="btn btn-ghost" onclick="closeStudioModal()">Bekor qilish</button>
      </div>
    </form>`
  );
}

async function submitEditQuiz(e, quizId) {
  e.preventDefault();
  try {
    await apiFetch(`/api/quizzes/${quizId}`, {
      method: "PUT",
      body: JSON.stringify({
        category_id: Number($id("editQuizCat").value),
        title: $id("editQuizTitle").value.trim(),
        code: $id("editQuizCode").value.trim(),
        difficulty: $id("editQuizDiff").value,
        time_limit_sec: Number($id("editQuizTime").value) || 300,
        description: $id("editQuizDesc").value.trim(),
        is_active: $id("editQuizActive").checked,
      }),
    });
    closeStudioModal();
    await refreshAll();
    if (state.selectedQuizId === quizId) {
      await openQuestionEditor(quizId);
    }
    showGlobalToast("✅ Test ma'lumotlari yangilandi");
  } catch (err) {
    showGlobalToast(`❌ ${err.message}`, 4500);
  }
}

async function adminCreateCategory(e) {
  e.preventDefault();
  try {
    await apiFetch("/api/categories", {
      method: "POST",
      body: JSON.stringify({
        icon: $id("catIconInput").value.trim() || "📚",
        name: $id("catNameInput").value.trim(),
        description: $id("catDescInput").value.trim(),
      }),
    });
    $id("catNameInput").value = "";
    $id("catDescInput").value = "";
    showGlobalToast("✅ Yangi fan qo'shildi");
    await refreshAll();
  } catch (err) {
    showGlobalToast(err.message);
  }
}

async function adminDeleteCategory(id) {
  if (!confirm("Ushbu fan va uning ichidagi barcha testlar o'chirilsinmi?")) return;
  await apiFetch(`/api/categories/${id}`, { method: "DELETE" });
  showGlobalToast("🗑 Fan o'chirildi");
  if (state.selectedQuizId) closeQuestionEditor();
  await refreshAll();
}

async function adminCreateQuiz(e) {
  e.preventDefault();
  try {
    const qz = await apiFetch("/api/quizzes", {
      method: "POST",
      body: JSON.stringify({
        category_id: Number($id("quizCatSelect").value),
        title: $id("quizTitleInput").value.trim(),
        code: $id("quizCodeInput").value.trim() || null,
        difficulty: $id("quizDiffSelect").value,
        time_limit_sec: Number($id("quizTimeInput").value || 5) * 60,
        description: $id("quizDescInput").value.trim(),
      }),
    });
    $id("quizTitleInput").value = "";
    $id("quizCodeInput").value = "";
    $id("quizDescInput").value = "";
    showGlobalToast(`✅ Test yaratildi! Kod: #${qz.code}`);
    await refreshAll();
    openQuestionEditor(qz.id);
  } catch (err) {
    showGlobalToast(err.message);
  }
}

async function adminDeleteQuiz(id) {
  if (!confirm("Testni o'chirishga ishonchingiz komilmi?")) return;
  await apiFetch(`/api/quizzes/${id}`, { method: "DELETE" });
  if (state.selectedQuizId === id) closeQuestionEditor();
  showGlobalToast("🗑 Test o'chirildi");
  await refreshAll();
}

async function openQuestionEditor(quizId) {
  state.selectedQuizId = quizId;
  renderAdminLists();
  const data = await apiFetch(`/api/quizzes/${quizId}/questions`);
  state.editorQuestions = data.questions || [];
  const editor = $id("adminQuestionEditor");
  editor.classList.remove("hidden");
  $id("editorQuizTitle").textContent = `${data.quiz.category_icon} ${data.quiz.title}`;
  $id("editorQuizMeta").textContent = `Kod: #${data.quiz.code} · ${diffBadge(data.quiz.difficulty)}`;
  $id("editorQuestionsCount").textContent = state.editorQuestions.length;

  renderEditorQuestionsList();
  editor.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderEditorQuestionsList() {
  const list = $id("editorQuestionsList");
  if (!list) return;
  const query = ($id("editorQuestionSearch")?.value || "").trim().toLowerCase();

  const indexed = state.editorQuestions.map((q, idx) => ({ q, idx }));
  const filtered = query
    ? indexed.filter(({ q }) =>
        `${q.question_text} ${q.option_a} ${q.option_b} ${q.option_c} ${q.option_d}`
          .toLowerCase()
          .includes(query)
      )
    : indexed;

  if (!state.editorQuestions.length) {
    list.innerHTML = `<p class="muted">Hozircha savollar yo'q. Yuqoridagi forma orqali savol qo'shing!</p>`;
    return;
  }

  if (!filtered.length) {
    list.innerHTML = `<p class="muted">Qidiruv bo'yicha savol topilmadi.</p>`;
    return;
  }

  list.innerHTML = filtered
    .map(
      ({ q, idx }) => `
      <div class="q-item">
        <div class="row-between">
          <strong>${idx + 1}. ${escapeHtml(q.question_text)}</strong>
          <div class="btn-row">
            <button type="button" class="btn btn-ghost btn-sm" title="Savolni tahrirlash" onclick="openEditQuestionModal(${q.id})">✏️</button>
            <button type="button" class="btn btn-danger btn-sm" title="Savolni o'chirish" onclick="adminDeleteQuestion(${q.id})">🗑</button>
          </div>
        </div>
        <div class="q-item-opts">
          <div class="${q.correct_option === "A" ? "is-corr" : ""}">A) ${escapeHtml(q.option_a)}${q.correct_option === "A" ? " ✅" : ""}</div>
          <div class="${q.correct_option === "B" ? "is-corr" : ""}">B) ${escapeHtml(q.option_b)}${q.correct_option === "B" ? " ✅" : ""}</div>
          <div class="${q.correct_option === "C" ? "is-corr" : ""}">C) ${escapeHtml(q.option_c)}${q.correct_option === "C" ? " ✅" : ""}</div>
          <div class="${q.correct_option === "D" ? "is-corr" : ""}">D) ${escapeHtml(q.option_d)}${q.correct_option === "D" ? " ✅" : ""}</div>
        </div>
        ${q.explanation ? `<div class="muted text-sm mt-1">💡 ${escapeHtml(q.explanation)}</div>` : ""}
      </div>`
    )
    .join("");
}

function openEditQuestionModal(questionId) {
  const q = state.editorQuestions.find((item) => item.id === questionId);
  if (!q) return;
  const optLetters = ["A", "B", "C", "D"]
    .map((l) => `<option value="${l}" ${q.correct_option === l ? "selected" : ""}>${l}</option>`)
    .join("");

  openStudioModal(
    `✏️ Savolni Tahrirlash (#${q.id})`,
    `<form onsubmit="submitEditQuestion(event, ${q.id})" class="stack-form">
      <div>
        <label class="field-lbl" for="editQText">Savol matni</label>
        <textarea id="editQText" class="input" rows="3" required>${escapeHtml(q.question_text)}</textarea>
      </div>
      <div class="form-row-2">
        <div>
          <label class="field-lbl" for="editQA">A variant</label>
          <input id="editQA" class="input" type="text" value="${escapeAttr(q.option_a)}" required />
        </div>
        <div>
          <label class="field-lbl" for="editQB">B variant</label>
          <input id="editQB" class="input" type="text" value="${escapeAttr(q.option_b)}" required />
        </div>
      </div>
      <div class="form-row-2">
        <div>
          <label class="field-lbl" for="editQC">C variant</label>
          <input id="editQC" class="input" type="text" value="${escapeAttr(q.option_c)}" required />
        </div>
        <div>
          <label class="field-lbl" for="editQD">D variant</label>
          <input id="editQD" class="input" type="text" value="${escapeAttr(q.option_d)}" required />
        </div>
      </div>
      <div class="form-row-2">
        <div>
          <label class="field-lbl" for="editQCorrect">To'g'ri javob</label>
          <select id="editQCorrect" class="input">${optLetters}</select>
        </div>
        <div>
          <label class="field-lbl" for="editQPoints">Ball (points)</label>
          <input id="editQPoints" class="input" type="number" min="1" max="100" value="${q.points || 10}" required />
        </div>
      </div>
      <div>
        <label class="field-lbl" for="editQExpl">Izoh (ixtiyoriy)</label>
        <input id="editQExpl" class="input" type="text" value="${escapeAttr(q.explanation || "")}" />
      </div>
      <div class="btn-row">
        <button type="submit" class="btn btn-primary">💾 Saqlash</button>
        <button type="button" class="btn btn-ghost" onclick="closeStudioModal()">Bekor qilish</button>
      </div>
    </form>`
  );
}

async function submitEditQuestion(e, questionId) {
  e.preventDefault();
  try {
    await apiFetch(`/api/questions/${questionId}`, {
      method: "PUT",
      body: JSON.stringify({
        question_text: $id("editQText").value.trim(),
        option_a: $id("editQA").value.trim(),
        option_b: $id("editQB").value.trim(),
        option_c: $id("editQC").value.trim(),
        option_d: $id("editQD").value.trim(),
        correct_option: $id("editQCorrect").value,
        points: Number($id("editQPoints").value) || 10,
        explanation: $id("editQExpl").value.trim(),
      }),
    });
    closeStudioModal();
    if (state.selectedQuizId) {
      await openQuestionEditor(state.selectedQuizId);
    }
    await refreshAll();
    showGlobalToast("✅ Savol tahrirlandi");
  } catch (err) {
    showGlobalToast(`❌ ${err.message}`, 4500);
  }
}

function closeQuestionEditor() {
  state.selectedQuizId = null;
  $id("adminQuestionEditor")?.classList.add("hidden");
  renderAdminLists();
}

function toggleEditorMode(mode, btn) {
  btn.parentElement.querySelectorAll(".pill-btn").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  $id("singleQuestionForm").classList.toggle("hidden", mode !== "single");
  $id("bulkQuestionForm").classList.toggle("hidden", mode !== "bulk");
}

async function adminCreateQuestion(e) {
  e.preventDefault();
  if (!state.selectedQuizId) return;
  try {
    await apiFetch(`/api/quizzes/${state.selectedQuizId}/questions`, {
      method: "POST",
      body: JSON.stringify({
        question_text: $id("qTextInput").value.trim(),
        option_a: $id("qOptA").value.trim(),
        option_b: $id("qOptB").value.trim(),
        option_c: $id("qOptC").value.trim(),
        option_d: $id("qOptD").value.trim(),
        correct_option: $id("qCorrectSelect").value,
        points: Number($id("qPointsInput").value || 10),
        explanation: $id("qExplanationInput").value.trim(),
      }),
    });
    e.target.reset();
    $id("qPointsInput").value = 10;
    showGlobalToast("✅ Savol qo'shildi");
    await refreshAll();
    await openQuestionEditor(state.selectedQuizId);
  } catch (err) {
    showGlobalToast(err.message);
  }
}

async function adminBulkQuestions(e) {
  e.preventDefault();
  if (!state.selectedQuizId) return;
  const raw = $id("bulkRawInput").value.trim();
  const res = await apiFetch(`/api/quizzes/${state.selectedQuizId}/questions/bulk`, {
    method: "POST",
    body: JSON.stringify({ raw_text: raw }),
  });
  if (res.created_count > 0) {
    $id("bulkRawInput").value = "";
  }
  const errNote = res.errors && res.errors.length ? ` (${res.errors.length} ta xato qator)` : "";
  showGlobalToast(`✅ ${res.created_count} ta savol qo'shildi${errNote}`);
  await refreshAll();
  await openQuestionEditor(state.selectedQuizId);
}

async function adminDeleteQuestion(questionId) {
  await apiFetch(`/api/questions/${questionId}`, { method: "DELETE" });
  showGlobalToast("🗑 Savol o'chirildi");
  await refreshAll();
  if (state.selectedQuizId) await openQuestionEditor(state.selectedQuizId);
}

// ---------------------------------------------------------------------------
// TAB 5: Leaderboard & Recent Activity
// ---------------------------------------------------------------------------

function populateLeaderboardFilter() {
  const sel = $id("lbCatFilter");
  if (!sel) return;
  const current = sel.value;
  sel.innerHTML =
    `<option value="">🌍 Umumiy reyting</option>` +
    state.categories
      .map((c) => `<option value="${c.id}">${escapeHtml(c.icon)} ${escapeHtml(c.name)}</option>`)
      .join("");
  if (current) sel.value = current;
}

async function loadLeaderboard() {
  const catId = $id("lbCatFilter").value;
  const url = catId ? `/api/leaderboard?category_id=${catId}` : "/api/leaderboard";
  const rows = await apiFetch(url);
  const wrap = $id("leaderboardTableWrap");
  if (!rows.length) {
    wrap.innerHTML = `<p class="muted">Ushbu yo'nalishda hali natijalar yo'q.</p>`;
    return;
  }
  const medals = ["🥇", "🥈", "🥉"];
  const scoreLabel = catId ? "Ball" : "XP";
  const accLabel = catId ? "O'rtacha" : "Aniqlik";
  wrap.innerHTML = `
    <table class="data-table responsive-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Ishtirokchi</th>
          <th>${scoreLabel}</th>
          <th>${accLabel}</th>
          <th>Testlar</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map((r, i) => {
            const place = medals[i] || `${i + 1}.`;
            return `
            <tr>
              <td data-label="O'rin">${place}</td>
              <td data-label="Ishtirokchi"><strong>${escapeHtml(r.full_name)}</strong></td>
              <td data-label="${scoreLabel}" class="mono">${catId ? `${r.category_score} ball` : `${r.xp} XP`}</td>
              <td data-label="${accLabel}">${catId ? `${r.avg_percentage}%` : `${r.accuracy}%`}</td>
              <td data-label="Testlar">${catId ? r.category_tests : r.tests_completed}</td>
            </tr>`;
          })
          .join("")}
      </tbody>
    </table>
  `;
  await loadStats();
}

function renderRecentAttempts(attempts) {
  const wrap = $id("recentAttemptsWrap");
  if (!wrap) return;
  if (!attempts.length) {
    wrap.innerHTML = `<p class="muted">Hali birorta test yakunlanmagan.</p>`;
    return;
  }
  wrap.innerHTML = `
    <table class="data-table responsive-table">
      <thead>
        <tr>
          <th>Foydalanuvchi</th>
          <th>Test</th>
          <th>Natija</th>
          <th>Vaqt</th>
          <th>Amallar</th>
        </tr>
      </thead>
      <tbody>
        ${attempts
          .map(
            (a) => `
          <tr>
            <td data-label="Foydalanuvchi"><strong>${escapeHtml(a.user_name)}</strong></td>
            <td data-label="Test">${escapeHtml(a.quiz_title)} <span class="mono muted">#${escapeHtml(a.quiz_code)}</span></td>
            <td data-label="Natija"><strong>${a.percentage}%</strong> (${a.correct_count}/${a.correct_count + a.wrong_count + a.skipped_count})</td>
            <td data-label="Vaqt" class="mono">${formatDuration(a.duration_sec)}</td>
            <td data-label="Amallar">
              <button type="button" class="btn btn-danger btn-sm" title="Natijani o'chirish" onclick="deleteAttemptConfirm(${a.id})">🗑</button>
            </td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>
  `;
}

async function deleteAttemptConfirm(attemptId) {
  if (!confirm("Ushbu test natijasi o'chirilsinmi? Foydalanuvchi statistikasi qayta hisoblanadi.")) return;
  try {
    await apiFetch(`/api/attempts/${attemptId}`, { method: "DELETE" });
    await Promise.all([loadLeaderboard(), refreshAll()]);
    showGlobalToast("🗑 Test natijasi o'chirildi");
  } catch (err) {
    showGlobalToast(`❌ ${err.message}`, 4500);
  }
}

async function clearAllAttemptsConfirm() {
  if (!confirm("DIQQAT! Barcha yakunlangan va faol test natijalari hamda XP ballar o'chirilsinmi?")) return;
  try {
    const res = await apiFetch("/api/attempts", { method: "DELETE" });
    await Promise.all([loadLeaderboard(), refreshAll()]);
    showGlobalToast(`🧹 Tozalandi: ${res.deleted_count} ta natija o'chirildi`);
  } catch (err) {
    showGlobalToast(`❌ ${err.message}`, 4500);
  }
}

// ---------------------------------------------------------------------------
// TAB 6: Telegram Bot Token Management
// ---------------------------------------------------------------------------

async function loadBotStatus() {
  const status = await apiFetch("/api/bot/status");
  updateBotStatusUI(status, status.admin_ids);
}

async function saveBotToken(e) {
  e.preventDefault();
  const token = $id("botTokenInput").value.trim();
  const adminIds = $id("adminIdsInput").value.trim();
  const res = await apiFetch("/api/bot/token", {
    method: "POST",
    body: JSON.stringify({ bot_token: token, admin_ids: adminIds }),
  });
  updateBotStatusUI(res, res.admin_ids);
  if (res.running) {
    showGlobalToast(`✅ Bot ulandi: @${res.bot_username}`);
  } else if (res.error) {
    showGlobalToast(`❌ ${res.error}`, 5000);
  } else {
    showGlobalToast("🟡 Simulyator rejimiga o'tkazildi");
  }
}

async function disconnectBotToken() {
  $id("botTokenInput").value = "";
  const adminIds = $id("adminIdsInput").value.trim();
  const res = await apiFetch("/api/bot/token", {
    method: "POST",
    body: JSON.stringify({ bot_token: "", admin_ids: adminIds }),
  });
  updateBotStatusUI(res, res.admin_ids);
  showGlobalToast("🔌 Telegram bot to'xtatildi");
}

// ---------------------------------------------------------------------------
// Keyboard Shortcuts & Boot
// ---------------------------------------------------------------------------

window.addEventListener("keydown", (e) => {
  // Close studio modal with Escape
  if (e.key === "Escape" && !$id("studioModal")?.classList.contains("hidden")) {
    closeStudioModal();
    return;
  }

  // Web Quiz keyboard shortcuts when runner is active and user is not typing
  const tag = (e.target?.tagName || "").toUpperCase();
  if (["INPUT", "TEXTAREA", "SELECT"].includes(tag)) return;
  if (!state.webQuiz || !$id("tab-webquiz")?.classList.contains("active")) return;

  const wq = state.webQuiz;
  const currentQ = wq.questions[wq.index];
  if (!currentQ) return;

  const keyUpper = e.key.toUpperCase();
  const keyMap = { "1": "A", "2": "B", "3": "C", "4": "D", A: "A", B: "B", C: "C", D: "D" };
  if (keyMap[keyUpper]) {
    e.preventDefault();
    webSelectOption(currentQ.id, keyMap[keyUpper]);
  } else if (e.key === "ArrowRight" && wq.index + 1 < wq.questions.length) {
    e.preventDefault();
    webJumpQuestion(wq.index + 1);
  } else if (e.key === "ArrowLeft" && wq.index > 0) {
    e.preventDefault();
    webJumpQuestion(wq.index - 1);
  }
});

async function checkSessionAndBoot() {
  loadZenithPrefs();
  try {
    const me = await apiFetch("/api/auth/me");
    if (me.authenticated) {
      showAppShell(me.username);
      await refreshAll();
      await simSendText("/start", false);
      return;
    }
  } catch {
    // Fall back to login overlay when session check fails
  }
  showAuthOverlay();
}

window.addEventListener("DOMContentLoaded", checkSessionAndBoot);
