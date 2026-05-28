const statusEl = document.getElementById("status");
const qrWrap = document.getElementById("qr-wrap");
const qrImage = document.getElementById("qr-image");
const qrUrl = document.getElementById("qr-url");
const resultEl = document.getElementById("result");
const startBtn = document.getElementById("start-btn");
const retryBtn = document.getElementById("retry-btn");

let ws = null;
let currentSessionId = null;

function setStatus(text) {
  statusEl.textContent = text;
}

function showQr(session) {
  const scanReady =
    session.qr_scan_data ||
    session.qr_image_base64 ||
    session.qr_image_url ||
    session.qr_url;

  if (!scanReady) {
    return;
  }

  qrWrap.classList.remove("hidden");
  qrImage.classList.remove("hidden");
  qrUrl.classList.add("hidden");
  qrUrl.textContent = "";

  if (session.qr_image_base64) {
    qrImage.src = `data:image/png;base64,${session.qr_image_base64}`;
    return;
  }

  const sessionId = session.session_id || currentSessionId;
  if (sessionId) {
    const cacheBust = session.updated_at || Date.now();
    qrImage.src = `/api/onboard/sessions/${sessionId}/qr.png?v=${cacheBust}`;
    return;
  }

  qrImage.classList.add("hidden");
  qrUrl.classList.remove("hidden");
  qrUrl.textContent = session.qr_url || "";
}

function hideQr() {
  qrWrap.classList.add("hidden");
  qrImage.removeAttribute("src");
}

function showResult(html, isError = false) {
  resultEl.innerHTML = html;
  resultEl.classList.toggle("error", isError);
  resultEl.classList.remove("hidden");
}

function resetUi() {
  hideQr();
  resultEl.classList.add("hidden");
  retryBtn.classList.add("hidden");
  startBtn.disabled = false;
  currentSessionId = null;
  if (ws) {
    ws.close();
    ws = null;
  }
}

function renderSession(session) {
  if (session.session_id) {
    currentSessionId = session.session_id;
  }
  setStatus(session.message || session.status);

  if (session.status === "waiting" || session.status === "refreshing" || session.status === "qr") {
    showQr(session);
  }

  if (session.status === "scanned") {
    showQr(session);
  }

  if (session.status === "confirmed" || session.status === "starting_gateway") {
    hideQr();
  }

  if (session.status === "ready") {
    hideQr();
    startBtn.disabled = true;
    retryBtn.classList.remove("hidden");
    showResult(
      `<strong>绑定成功</strong><br/>
      Profile: <code>${session.profile}</code><br/>
      Bot: <code>${session.account_id || "-"}</code><br/>
      Gateway PID: <code>${session.gateway_pid || "-"}</code> (${session.gateway_mode || "unknown"})<br/>
      现在去微信给 bot 发一条消息即可开始对话。`,
    );
  }

  if (session.status === "failed") {
    hideQr();
    startBtn.disabled = true;
    retryBtn.classList.remove("hidden");
    showResult(`<strong>绑定失败</strong><br/>${session.error || session.message}`, true);
  }
}

function connectWs(sessionId) {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${protocol}://${location.host}/api/onboard/sessions/${sessionId}/ws`);
  ws.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    if (payload.session) {
      renderSession(payload.session);
    }
    if (payload.done && ws) {
      ws.close();
      ws = null;
    }
  };
  ws.onerror = () => {
    setStatus("实时连接失败，将使用轮询...");
    pollSession(sessionId);
  };
}

async function pollSession(sessionId) {
  for (let i = 0; i < 600; i += 1) {
    const res = await fetch(`/api/onboard/sessions/${sessionId}`);
    const data = await res.json();
    renderSession(data.session);
    if (data.session.status === "ready" || data.session.status === "failed") {
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}

async function startOnboard() {
  resetUi();
  startBtn.disabled = true;
  setStatus("正在创建绑定会话...");

  const res = await fetch("/api/onboard/sessions", { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    showResult(`无法开始绑定：${err.detail || res.statusText}`, true);
    retryBtn.classList.remove("hidden");
    return;
  }

  const data = await res.json();
  renderSession(data.session);
  connectWs(data.session.session_id);
}

startBtn.addEventListener("click", startOnboard);
retryBtn.addEventListener("click", () => {
  resetUi();
  setStatus("准备开始...");
});

const wikiBindForm = document.getElementById("wiki-bind-form");
const wikiUsernameInput = document.getElementById("wiki-username");
const wikiPasswordInput = document.getElementById("wiki-password");
const wikiCredentialOutput = document.getElementById("wiki-credential-output");
const wikiCredentialB64 = document.getElementById("wiki-credential-b64");
const wikiCopyBtn = document.getElementById("wiki-copy-btn");
const wikiCopyFeedback = document.getElementById("wiki-copy-feedback");

function encodeWikiCredential(username, password) {
  const raw = `${username}:${password}`;
  const bytes = new TextEncoder().encode(raw);
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

function formatWikiCredentialMessage(encoded) {
  return `请修改 zuiyou-doc-search skill 的 BASE64_TOKEN=${encoded}`;
}

function showWikiCredential(encoded) {
  wikiCredentialB64.textContent = formatWikiCredentialMessage(encoded);
  wikiCredentialOutput.classList.remove("hidden");
  wikiCopyFeedback.classList.add("hidden");
}

wikiBindForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  const username = wikiUsernameInput.value.trim();
  const password = wikiPasswordInput.value;
  if (!username || !password) {
    return;
  }
  showWikiCredential(encodeWikiCredential(username, password));
});

async function copyTextToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // 非 HTTPS / 非 localhost 时 Clipboard API 常被拒绝，走下方兜底
    }
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  textarea.setSelectionRange(0, text.length);

  let ok = false;
  try {
    ok = document.execCommand("copy");
  } finally {
    document.body.removeChild(textarea);
  }
  return ok;
}

wikiCopyBtn?.addEventListener("click", async () => {
  const text = wikiCredentialB64.textContent?.trim();
  if (!text) {
    return;
  }

  const copied = await copyTextToClipboard(text);
  wikiCopyFeedback.classList.remove("hidden");
  if (copied) {
    wikiCopyFeedback.textContent = "已复制到剪贴板";
    wikiCopyBtn.textContent = "已复制";
    window.setTimeout(() => {
      wikiCopyBtn.textContent = "一键复制";
    }, 2000);
    return;
  }

  wikiCopyFeedback.textContent = "复制失败，请手动选中上方编码后复制";
});

fetch("/api/health")
  .then((res) => res.json())
  .then((data) => {
    if (!data.weixin_ready) {
      setStatus("服务端缺少 Weixin 依赖，请运行 ./onboard-web/run.sh 安装依赖");
      startBtn.disabled = true;
      return;
    }
    if (!data.qr_render_ready) {
      setStatus("服务端无法渲染二维码图片，请确认已安装 Pillow (pip install -r onboard-web/requirements.txt)");
      startBtn.disabled = true;
    }
  })
  .catch(() => {
    setStatus("无法连接后端服务");
    startBtn.disabled = true;
  });
