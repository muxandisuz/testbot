/* TestMaster Bot Studio — Interactive Simulator, Web Quiz Player, and Admin Panel */

const state = {
  categories: [],
  quizzes: [],
  activeCategoryFilter: null,
  selectedQuizId: null,
  simAwaitingInput: null,
  webQuiz: null,
  webTimerHandle: null,
};

// ---------------------------------------------------------------------------
// Helpers & Safe Telegram HTML Rendering
// ---------------------------------------------------------------------------

function showGlobalToast(msg, duration = 3000) {
  const el = document.getElementById("globalToast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.add("hidden"), duration);
}

async function apiFetch(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || "So'rovda xatolik yuz berdi");
  }
  return data;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = String(text ?? "");
  return div.innerHTML;
}

function renderSafeTelegramHtml(rawHtml) {
  // Parse HTML and whitelist only safe Telegram inline formatting tags (b, i, code, pre, strong, em)
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
// Navigation & Initial Load
// ---------------------------------------------------------------------------

function switchTab(tabName) {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `tab-${tabName}`);
  });
  if (tabName === "leaderboard") loadLeaderboard();
  if (tabName === "settings") loadBotStatus();
}

async function refreshAll() {
  await Promise.all([loadStats(), loadCategories(), loadQuizzes()]);
  renderSimQuizChips();
  renderWebQuizLobby();
  renderAdminLists();
  populateLeaderboardFilter();
}

async function loadStats() {
  const data = await apiFetch("/api/stats");
  document.getElementById("kpiCategories").textContent = data.categories_count;
  document.getElementById("kpiQuizzes").textContent = data.quizzes_count;
  document.getElementById("kpiQuestions").textContent = data.questions_count;
  document.getElementById("kpiUsers").textContent = data.users_count;
  document.getElementById("kpiAvg").textContent = `${data.avg_percentage}%`;
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
  const pill = document.getElementById("botStatusBadge");
  const txt = document.getElementById("botStatusText");
  const simTitle = document.getElementById("simBotTitle");
  const banner = document.getElementById("settingsStatusBox");
  const adminInput = document.getElementById("adminIdsInput");

  if (adminInput && adminIds !== undefined && !adminInput.value) {
    adminInput.value = adminIds;
  }

  pill.classList.remove("status-live", "status-sim", "status-err");
  if (status && status.running) {
    pill.classList.add("status-live");
    txt.textContent = `Faol: @${status.bot_username}`;
    simTitle.textContent = `${status.bot_name || "TestMaster"} (@${status.bot_username})`;
    if (banner) {
      banner.innerHTML = `🟢 <strong>Telegram bot faol ishlamoqda!</strong> <a href="https://t.me/${escapeHtml(status.bot_username)}" target="_blank" style="color:#7dd3fc;">@${escapeHtml(status.bot_username)}</a>`;
    }
  } else if (status && status.error) {
    pill.classList.add("status-err");
    txt.textContent = "Token xatosi";
    if (banner) {
      banner.innerHTML = `🔴 <strong>Ulanish xatosi:</strong> ${escapeHtml(status.error)}`;
    }
  } else {
    pill.classList.add("status-sim");
    txt.textContent = "Simulyator rejimi (Token kiritilmagan)";
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
    full_name: document.getElementById("simUserName").value.trim() || "Mehmon Foydalanuvchi",
    username: "simulator_user",
    is_admin: document.getElementById("simUserRole").value === "true",
  };
}

function showSimToast(msg) {
  const toast = document.getElementById("tgToast");
  if (!msg) return;
  toast.textContent = msg;
  toast.classList.remove("hidden");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toast.classList.add("hidden"), 2500);
}

function appendUserBubble(text) {
  const area = document.getElementById("tgMessages");
  const bubble = document.createElement("div");
  bubble.className = "tg-user-bubble";
  bubble.textContent = text;
  area.appendChild(bubble);
  scrollChatBottom();
}

function renderBotCard(resp, replaceLast = false) {
  const area = document.getElementById("tgMessages");
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
        b.onclick = () => simSendCallback(btnSpec.callback_data);
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
  const chat = document.getElementById("tgChatArea");
  chat.scrollTop = chat.scrollHeight;
}

async function simSendText(text, showEcho = true) {
  if (!text) return;
  if (text === "/start") {
    document.getElementById("tgMessages").innerHTML = "";
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
  const inp = document.getElementById("simTextInput");
  const txt = inp.value.trim();
  if (!txt) return;
  inp.value = "";
  simSendText(txt, true);
}

function renderSimQuizChips() {
  const wrap = document.getElementById("simQuizCodes");
  wrap.innerHTML = state.quizzes
    .map(
      (qz) => `
      <button class="code-chip" onclick="simSendText('${escapeHtml(qz.code)}')">
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
  const filterWrap = document.getElementById("webCategoryFilter");
  const pills = [
    `<button class="pill-btn ${state.activeCategoryFilter === null ? "active" : ""}" onclick="setWebCategoryFilter(null)">🌐 Barchasi</button>`,
    ...state.categories.map(
      (c) =>
        `<button class="pill-btn ${state.activeCategoryFilter === c.id ? "active" : ""}" onclick="setWebCategoryFilter(${c.id})">${escapeHtml(c.icon)} ${escapeHtml(c.name)}</button>`
    ),
  ];
  filterWrap.innerHTML = pills.join("");

  const filtered = state.activeCategoryFilter
    ? state.quizzes.filter((q) => q.category_id === state.activeCategoryFilter)
    : state.quizzes;

  const grid = document.getElementById("webQuizzesGrid");
  if (!filtered.length) {
    grid.innerHTML = `<div class="glass-card"><p class="muted">Ushbu yo'nalishda testlar topilmadi.</p></div>`;
    return;
  }

  grid.innerHTML = filtered
    .map(
      (qz) => `
      <div class="quiz-card">
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
          <button class="btn btn-primary btn-sm" ${qz.question_count ? "" : "disabled"} onclick="webStartQuiz(${qz.id}, 'practice')">▶️ Test ishlash (1 dan oxirigacha)</button>
          <button class="btn btn-ghost btn-sm" ${qz.question_count ? "" : "disabled"} onclick="webStartQuiz(${qz.id}, 'exam')">🎓 Imtihon</button>
        </div>
      </div>`
    )
    .join("");
}

function setWebCategoryFilter(catId) {
  state.activeCategoryFilter = catId;
  renderWebQuizLobby();
}

async function webStartByCode() {
  const code = document.getElementById("webCodeInput").value.trim().toUpperCase();
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
        full_name: document.getElementById("simUserName").value.trim() || "Web Foydalanuvchi",
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
    document.getElementById("webQuizLobby").classList.add("hidden");
    document.getElementById("webQuizRunner").classList.remove("hidden");
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
    const timerEl = document.getElementById("webRunnerTimer");
    if (timerEl) timerEl.textContent = formatDuration(state.webQuiz.remainingSec);
    if (state.webQuiz.remainingSec <= 0 && state.webQuiz.attempt.mode === "exam") {
      clearInterval(state.webTimerHandle);
      webFinishQuiz(true);
    }
  }, 1000);
}

function renderWebRunner() {
  const wq = state.webQuiz;
  const container = document.getElementById("webQuizRunner");
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
        <button class="${cls}" ${disabled} onclick="webSelectOption(${q.id}, '${letter}')">
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
        ${fb.explanation ? `<p style="margin:6px 0 0;">💡 ${escapeHtml(fb.explanation)}</p>` : ""}
      </div>`;
  }

  const dotsHtml = wq.questions
    .map(
      (item, idx) =>
        `<button class="dot-btn ${idx === wq.index ? "active" : ""} ${wq.answers[item.id] ? "answered" : ""}" onclick="webJumpQuestion(${idx})">${idx + 1}</button>`
    )
    .join("");

  container.innerHTML = `
    <div class="glass-card runner-wrap">
      <div class="row-between">
        <div>
          <span class="badge">${isPractice ? "⚡️ Mashq rejimi" : "🎓 Imtihon rejimi"}</span>
          <h2 style="margin:6px 0 0;">${escapeHtml(wq.quiz.title)}</h2>
        </div>
        <div class="btn-row">
          <span class="badge mono">⏱ <span id="webRunnerTimer">${formatDuration(wq.remainingSec)}</span></span>
          <button class="btn btn-danger btn-sm" onclick="webFinishQuiz(false)">🚪 Chiqish va yakunlash</button>
        </div>
      </div>

      <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
      <div class="row-between text-sm muted">
        <span>Savol <strong>${wq.index + 1} / ${total}</strong></span>
        <span>Belgilangan: <strong>${Object.keys(wq.answers).length} / ${total}</strong></span>
      </div>

      <h3 style="margin:18px 0 6px; line-height:1.45;">${wq.index + 1}. ${escapeHtml(q.question_text)}</h3>
      <div class="option-grid">${optionHtml}</div>
      ${fbHtml}

      <div class="row-between" style="margin-top:20px;">
        <button class="btn btn-ghost" ${wq.index === 0 ? "disabled" : ""} onclick="webJumpQuestion(${wq.index - 1})">⬅️ Oldingi</button>
        ${
          wq.index + 1 < total
            ? `<button class="btn btn-primary" onclick="webJumpQuestion(${wq.index + 1})">Keyingi savol ➡️</button>`
            : `<button class="btn btn-emerald" onclick="webFinishQuiz(false)">🏁 Natijani ko'rish</button>`
        }
      </div>

      <div class="runner-dots">${dotsHtml}</div>
    </div>
  `;
}

async function webSelectOption(questionId, letter) {
  const wq = state.webQuiz;
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
  const container = document.getElementById("webQuizRunner");
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
          <p class="text-sm muted" style="margin:6px 0 0;">
            Sizning javobingiz: <strong>${item.selected_option || "—"}</strong> · To'g'ri javob: <strong style="color:#6ee7b7;">${q.correct_option}</strong>
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
          <h2 style="margin:6px 0 0;">${escapeHtml(res.quiz.title)}</h2>
        </div>
        <button class="btn btn-primary" onclick="webExitRunner()">📚 Testlar ro'yxatiga</button>
      </div>
      <div class="kpi-grid" style="margin-top:18px;">
        <div class="kpi-card"><span>🎯</span><div><div class="kpi-val">${att.percentage}%</div><div class="kpi-lbl">Natija</div></div></div>
        <div class="kpi-card"><span>✅</span><div><div class="kpi-val">${att.correct_count}</div><div class="kpi-lbl">To'g'ri</div></div></div>
        <div class="kpi-card"><span>❌</span><div><div class="kpi-val">${att.wrong_count}</div><div class="kpi-lbl">Noto'g'ri</div></div></div>
        <div class="kpi-card"><span>💎</span><div><div class="kpi-val">${att.score}/${att.total_points}</div><div class="kpi-lbl">Ball</div></div></div>
        <div class="kpi-card"><span>⏱</span><div><div class="kpi-val">${formatDuration(att.duration_sec)}</div><div class="kpi-lbl">Vaqt</div></div></div>
      </div>
      <h3 style="margin:18px 0 10px;">📋 Savollar tahlili</h3>
      <div class="questions-list">${reviewHtml}</div>
    </div>
  `;
}

function webExitRunner() {
  clearInterval(state.webTimerHandle);
  state.webQuiz = null;
  document.getElementById("webQuizRunner").classList.add("hidden");
  document.getElementById("webQuizLobby").classList.remove("hidden");
}

// ---------------------------------------------------------------------------
// TAB 3: Admin Panel
// ---------------------------------------------------------------------------

function renderAdminLists() {
  // Category select dropdown for quiz creation
  const catSelect = document.getElementById("quizCatSelect");
  catSelect.innerHTML = state.categories
    .map((c) => `<option value="${c.id}">${escapeHtml(c.icon)} ${escapeHtml(c.name)}</option>`)
    .join("");

  // Categories list
  const catList = document.getElementById("adminCategoriesList");
  catList.innerHTML = state.categories
    .map(
      (c) => `
      <div class="list-item">
        <div>
          <strong>${escapeHtml(c.icon)} ${escapeHtml(c.name)}</strong>
          <div class="muted text-sm">${c.quiz_count} ta test · ${c.question_count} ta savol</div>
        </div>
        <button class="btn btn-danger btn-sm" onclick="adminDeleteCategory(${c.id})">🗑</button>
      </div>`
    )
    .join("");

  // Quizzes list
  const qList = document.getElementById("adminQuizzesList");
  qList.innerHTML = state.quizzes
    .map(
      (qz) => `
      <div class="list-item clickable" onclick="openQuestionEditor(${qz.id})">
        <div>
          <strong>${escapeHtml(qz.category_icon)} ${escapeHtml(qz.title)}</strong>
          <div class="muted text-sm">
            Kod: <code style="color:#7dd3fc;">${escapeHtml(qz.code)}</code> · ${diffBadge(qz.difficulty)} · ${qz.question_count} ta savol · ⏱ ${formatDuration(qz.time_limit_sec)}
          </div>
        </div>
        <div class="btn-row" onclick="event.stopPropagation()">
          <button class="btn btn-ghost btn-sm" onclick="openQuestionEditor(${qz.id})">✏️ Savollar</button>
          <button class="btn btn-danger btn-sm" onclick="adminDeleteQuiz(${qz.id})">🗑</button>
        </div>
      </div>`
    )
    .join("");
}

async function adminCreateCategory(e) {
  e.preventDefault();
  try {
    await apiFetch("/api/categories", {
      method: "POST",
      body: JSON.stringify({
        icon: document.getElementById("catIconInput").value.trim() || "📚",
        name: document.getElementById("catNameInput").value.trim(),
        description: document.getElementById("catDescInput").value.trim(),
      }),
    });
    document.getElementById("catNameInput").value = "";
    document.getElementById("catDescInput").value = "";
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
        category_id: Number(document.getElementById("quizCatSelect").value),
        title: document.getElementById("quizTitleInput").value.trim(),
        code: document.getElementById("quizCodeInput").value.trim() || null,
        difficulty: document.getElementById("quizDiffSelect").value,
        time_limit_sec: Number(document.getElementById("quizTimeInput").value || 5) * 60,
        description: document.getElementById("quizDescInput").value.trim(),
      }),
    });
    document.getElementById("quizTitleInput").value = "";
    document.getElementById("quizCodeInput").value = "";
    document.getElementById("quizDescInput").value = "";
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
  const data = await apiFetch(`/api/quizzes/${quizId}/questions`);
  const editor = document.getElementById("adminQuestionEditor");
  editor.classList.remove("hidden");
  document.getElementById("editorQuizTitle").textContent = `${data.quiz.category_icon} ${data.quiz.title}`;
  document.getElementById("editorQuizMeta").textContent = `Kod: #${data.quiz.code} · ${diffBadge(data.quiz.difficulty)}`;
  document.getElementById("editorQuestionsCount").textContent = data.questions.length;

  const list = document.getElementById("editorQuestionsList");
  list.innerHTML = data.questions.length
    ? data.questions
        .map(
          (q, idx) => `
          <div class="q-item">
            <div class="row-between">
              <strong>${idx + 1}. ${escapeHtml(q.question_text)}</strong>
              <button class="btn btn-danger btn-sm" onclick="adminDeleteQuestion(${q.id})">🗑</button>
            </div>
            <div class="q-item-opts">
              <div class="${q.correct_option === "A" ? "is-corr" : ""}">A) ${escapeHtml(q.option_a)}</div>
              <div class="${q.correct_option === "B" ? "is-corr" : ""}">B) ${escapeHtml(q.option_b)}</div>
              <div class="${q.correct_option === "C" ? "is-corr" : ""}">C) ${escapeHtml(q.option_c)}</div>
              <div class="${q.correct_option === "D" ? "is-corr" : ""}">D) ${escapeHtml(q.option_d)}</div>
            </div>
            ${q.explanation ? `<div class="muted text-sm" style="margin-top:6px;">💡 ${escapeHtml(q.explanation)}</div>` : ""}
          </div>`
        )
        .join("")
    : `<p class="muted">Hozircha savollar yo'q. Yuqoridagi forma orqali savol qo'shing!</p>`;

  editor.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function closeQuestionEditor() {
  state.selectedQuizId = null;
  document.getElementById("adminQuestionEditor").classList.add("hidden");
}

function toggleEditorMode(mode, btn) {
  btn.parentElement.querySelectorAll(".pill-btn").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  document.getElementById("singleQuestionForm").classList.toggle("hidden", mode !== "single");
  document.getElementById("bulkQuestionForm").classList.toggle("hidden", mode !== "bulk");
}

async function adminCreateQuestion(e) {
  e.preventDefault();
  if (!state.selectedQuizId) return;
  try {
    await apiFetch(`/api/quizzes/${state.selectedQuizId}/questions`, {
      method: "POST",
      body: JSON.stringify({
        question_text: document.getElementById("qTextInput").value.trim(),
        option_a: document.getElementById("qOptA").value.trim(),
        option_b: document.getElementById("qOptB").value.trim(),
        option_c: document.getElementById("qOptC").value.trim(),
        option_d: document.getElementById("qOptD").value.trim(),
        correct_option: document.getElementById("qCorrectSelect").value,
        points: Number(document.getElementById("qPointsInput").value || 10),
        explanation: document.getElementById("qExplanationInput").value.trim(),
      }),
    });
    e.target.reset();
    document.getElementById("qPointsInput").value = 10;
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
  const raw = document.getElementById("bulkRawInput").value.trim();
  const res = await apiFetch(`/api/quizzes/${state.selectedQuizId}/questions/bulk`, {
    method: "POST",
    body: JSON.stringify({ raw_text: raw }),
  });
  if (res.created_count > 0) {
    document.getElementById("bulkRawInput").value = "";
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
// TAB 4: Leaderboard & Recent Activity
// ---------------------------------------------------------------------------

function populateLeaderboardFilter() {
  const sel = document.getElementById("lbCatFilter");
  const current = sel.value;
  sel.innerHTML =
    `<option value="">🌍 Umumiy reyting</option>` +
    state.categories
      .map((c) => `<option value="${c.id}">${escapeHtml(c.icon)} ${escapeHtml(c.name)}</option>`)
      .join("");
  if (current) sel.value = current;
}

async function loadLeaderboard() {
  const catId = document.getElementById("lbCatFilter").value;
  const url = catId ? `/api/leaderboard?category_id=${catId}` : "/api/leaderboard";
  const rows = await apiFetch(url);
  const wrap = document.getElementById("leaderboardTableWrap");
  if (!rows.length) {
    wrap.innerHTML = `<p class="muted">Ushbu yo'nalishda hali natijalar yo'q.</p>`;
    return;
  }
  const medals = ["🥇", "🥈", "🥉"];
  wrap.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Ishtirokchi</th>
          <th>${catId ? "Ball" : "XP"}</th>
          <th>${catId ? "O'rtacha" : "Aniqlik"}</th>
          <th>Testlar</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map((r, i) => {
            const place = medals[i] || `${i + 1}.`;
            return `
            <tr>
              <td>${place}</td>
              <td><strong>${escapeHtml(r.full_name)}</strong></td>
              <td class="mono">${catId ? `${r.category_score} ball` : `${r.xp} XP`}</td>
              <td>${catId ? `${r.avg_percentage}%` : `${r.accuracy}%`}</td>
              <td>${catId ? r.category_tests : r.tests_completed}</td>
            </tr>`;
          })
          .join("")}
      </tbody>
    </table>
  `;
  await loadStats();
}

function renderRecentAttempts(attempts) {
  const wrap = document.getElementById("recentAttemptsWrap");
  if (!attempts.length) {
    wrap.innerHTML = `<p class="muted">Hali birorta test yakunlanmagan.</p>`;
    return;
  }
  wrap.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Foydalanuvchi</th>
          <th>Test</th>
          <th>Natija</th>
          <th>Vaqt</th>
        </tr>
      </thead>
      <tbody>
        ${attempts
          .map(
            (a) => `
          <tr>
            <td><strong>${escapeHtml(a.user_name)}</strong></td>
            <td>${escapeHtml(a.quiz_title)} <span class="mono muted">#${escapeHtml(a.quiz_code)}</span></td>
            <td><strong>${a.percentage}%</strong> (${a.correct_count}/${a.correct_count + a.wrong_count + a.skipped_count})</td>
            <td class="mono">${formatDuration(a.duration_sec)}</td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>
  `;
}

// ---------------------------------------------------------------------------
// TAB 5: Telegram Bot Token Management
// ---------------------------------------------------------------------------

async function loadBotStatus() {
  const status = await apiFetch("/api/bot/status");
  updateBotStatusUI(status, status.admin_ids);
}

async function saveBotToken(e) {
  e.preventDefault();
  const token = document.getElementById("botTokenInput").value.trim();
  const adminIds = document.getElementById("adminIdsInput").value.trim();
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
  document.getElementById("botTokenInput").value = "";
  const adminIds = document.getElementById("adminIdsInput").value.trim();
  const res = await apiFetch("/api/bot/token", {
    method: "POST",
    body: JSON.stringify({ bot_token: "", admin_ids: adminIds }),
  });
  updateBotStatusUI(res, res.admin_ids);
  showGlobalToast("🔌 Telegram bot to'xtatildi");
}

// Boot
window.addEventListener("DOMContentLoaded", async () => {
  await refreshAll();
  await simSendText("/start", false);
});
