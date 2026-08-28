const state = { monitors: [], recipients: [], editingMonitorId: null, refreshTimer: null };

const $ = (selector) => document.querySelector(selector);
const field = (form, name) => form.elements.namedItem(name);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", "'":"&#39;", '"':"&quot;" }[char]));

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = payload?.detail?.message || payload?.detail || `요청 처리에 실패했습니다. (${response.status})`;
    throw new Error(message);
  }
  return payload;
}

function toast(message, isError = false) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.toggle("error", isError);
  element.classList.add("show");
  window.clearTimeout(element._timer);
  element._timer = window.setTimeout(() => element.classList.remove("show"), 4200);
}

function dateTime(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("ko-KR", { dateStyle: "short", timeStyle: "medium" }).format(new Date(value));
}

function statusBadge(status) {
  const label = { UP: "정상", DOWN: "장애", UNKNOWN: "미점검" }[status] || status;
  return `<span class="badge ${String(status).toLowerCase()}">${label}</span>`;
}

function resultMarkup(monitor) {
  if (monitor.status === "UNKNOWN") return '<span class="subtle">아직 점검 결과가 없습니다.</span>';
  const headline = monitor.last_status_code ? `HTTP ${monitor.last_status_code}` : (monitor.last_error || "요청 실패");
  const timing = monitor.last_response_time_ms !== null ? ` · ${monitor.last_response_time_ms}ms` : "";
  const error = monitor.last_server_error_message || (monitor.last_error && monitor.last_status_code ? monitor.last_error : "");
  return `<div class="result-main">${escapeHtml(headline)}${timing}</div>${error ? `<div class="result-error">${escapeHtml(error)}</div>` : ""}<div class="subtle">${dateTime(monitor.last_checked_at)}</div>`;
}

function renderMonitors() {
  const target = $("#monitor-list");
  if (!state.monitors.length) {
    target.innerHTML = '<tr><td colspan="5" class="empty">등록된 모니터가 없습니다. “모니터 등록”으로 첫 대상을 추가하세요.</td></tr>';
    return;
  }
  target.innerHTML = state.monitors.map((monitor) => `
    <tr>
      <td>${statusBadge(monitor.status)}</td>
      <td><div class="monitor-name">${escapeHtml(monitor.name)} ${monitor.auth ? '<span class="subtle">JWT</span>' : ""}</div><div class="monitor-url">${escapeHtml(monitor.url)}</div>${!monitor.enabled ? '<div class="subtle">정기 점검 중지됨</div>' : ""}</td>
      <td>${resultMarkup(monitor)}</td>
      <td class="subtle">${dateTime(monitor.next_check_at)}</td>
      <td><div class="actions"><button class="button secondary small" data-action="check" data-id="${monitor.id}">점검</button><button class="button secondary small" data-action="edit" data-id="${monitor.id}">수정</button><button class="button ${monitor.enabled ? "secondary" : "primary"} small" data-action="toggle" data-id="${monitor.id}">${monitor.enabled ? "중지" : "활성화"}</button><button class="button danger small" data-action="delete" data-id="${monitor.id}">삭제</button></div></td>
    </tr>`).join("");
}

function renderRecipients() {
  const target = $("#recipient-list");
  if (!state.recipients.length) {
    target.innerHTML = '<li class="empty">등록된 수신자가 없습니다.</li>';
    return;
  }
  target.innerHTML = state.recipients.map((recipient) => `
    <li class="${recipient.enabled ? "" : "disabled"}">
      <span class="status-dot ${recipient.enabled ? "" : "off"}"></span>
      <div class="recipient-info"><strong>${escapeHtml(recipient.name || "이름 없음")}</strong><span>${escapeHtml(recipient.email)}</span></div>
      <button class="button secondary small" data-recipient-action="toggle" data-id="${recipient.id}">${recipient.enabled ? "중지" : "활성화"}</button>
      <button class="button danger small" data-recipient-action="delete" data-id="${recipient.id}">삭제</button>
    </li>`).join("");
}

function renderSummary(summary) {
  $("#total-count").textContent = summary.total;
  $("#up-count").textContent = summary.up;
  $("#down-count").textContent = summary.down;
  $("#unknown-count").textContent = summary.unknown;
  $("#last-refreshed").textContent = `${summary.scheduler_running ? "스케줄러 실행 중" : "스케줄러 중지"} · ${new Date().toLocaleTimeString("ko-KR")}`;
}

async function loadEmailConfig() {
  try {
    const config = await request("/email-config");
    const form = $("#email-form");
    field(form, "smtp_host").value = config.smtp_host;
    field(form, "smtp_port").value = config.smtp_port;
    field(form, "from_address").value = config.from_address;
    field(form, "username").value = config.username || "";
    field(form, "use_starttls").checked = config.use_starttls;
    $("#email-config-summary").textContent = `설정됨 · ${config.smtp_host}:${config.smtp_port} · ${config.password_configured ? "비밀번호 설정됨" : "비밀번호 미설정"}`;
  } catch (error) {
    $("#email-config-summary").textContent = "SMTP 설정이 없습니다. IP Relay를 쓸 경우 사용자명과 비밀번호는 비워 두세요.";
  }
}

async function refresh() {
  try {
    const [summary, monitors, recipients] = await Promise.all([
      request("/status"), request("/monitors"), request("/recipients"),
    ]);
    state.monitors = monitors;
    state.recipients = recipients;
    renderSummary(summary);
    renderMonitors();
    renderRecipients();
    await loadEmailConfig();
  } catch (error) {
    toast(error.message, true);
  }
}

function parseCodes(value) {
  const codes = value.split(",").map((part) => Number(part.trim())).filter(Number.isInteger);
  if (!codes.length) throw new Error("정상 상태 코드를 한 개 이상 입력하세요.");
  return codes;
}

function monitorPayload(form, isUpdate) {
  const data = new FormData(form);
  const payload = {
    name: data.get("name").trim(),
    url: data.get("url").trim(),
    method: data.get("method"),
    interval_seconds: Number(data.get("interval_seconds")),
    timeout_seconds: Number(data.get("timeout_seconds")),
    max_attempts: Number(data.get("max_attempts")),
    retry_delay_seconds: Number(data.get("retry_delay_seconds")),
    expected_status_codes: parseCodes(data.get("expected_status_codes")),
  };
  const loginUrl = data.get("login_url").trim();
  const tokenPath = data.get("token_response_path").trim();
  const loginPayload = data.get("login_payload").trim();
  if (loginPayload) {
    if (!loginUrl || !tokenPath) throw new Error("JWT 인증에는 로그인 URL, 토큰 경로, 로그인 JSON 본문이 모두 필요합니다.");
    try {
      payload.auth = {
        type: "JWT_LOGIN", login_url: loginUrl, token_response_path: tokenPath,
        login_payload: JSON.parse(loginPayload),
        token_header_name: data.get("token_header_name").trim() || "Authorization",
        token_prefix: data.get("token_prefix").trim() || "Bearer",
      };
    } catch (_) { throw new Error("로그인 JSON 본문 형식이 올바르지 않습니다."); }
  } else if (!isUpdate && (loginUrl || tokenPath)) {
    throw new Error("JWT 인증에는 로그인 URL, 토큰 경로, 로그인 JSON 본문이 모두 필요합니다.");
  } else if (!isUpdate) {
    payload.auth = null;
  }
  return payload;
}

function resetMonitorForm() {
  const form = $("#monitor-form");
  form.reset();
  field(form, "method").value = "GET";
  field(form, "interval_seconds").value = 30;
  field(form, "timeout_seconds").value = 5;
  field(form, "max_attempts").value = 3;
  field(form, "retry_delay_seconds").value = 5;
  field(form, "expected_status_codes").value = "200";
  form.querySelector("details").open = false;
  state.editingMonitorId = null;
  $("#monitor-form-title").textContent = "모니터 등록";
}

function showMonitorForm(monitor = null) {
  const form = $("#monitor-form");
  resetMonitorForm();
  if (monitor) {
    state.editingMonitorId = monitor.id;
    $("#monitor-form-title").textContent = "모니터 수정";
    field(form, "name").value = monitor.name;
    field(form, "url").value = monitor.url;
    field(form, "method").value = monitor.method;
    field(form, "interval_seconds").value = monitor.interval_seconds;
    field(form, "timeout_seconds").value = monitor.timeout_seconds;
    field(form, "max_attempts").value = monitor.max_attempts;
    field(form, "retry_delay_seconds").value = monitor.retry_delay_seconds;
    field(form, "expected_status_codes").value = monitor.expected_status_codes.join(", ");
    if (monitor.auth) {
      form.querySelector("details").open = true;
      field(form, "login_url").value = monitor.auth.login_url;
      field(form, "token_response_path").value = monitor.auth.token_response_path;
      field(form, "token_header_name").value = monitor.auth.token_header_name;
      field(form, "token_prefix").value = monitor.auth.token_prefix;
      field(form, "login_payload").placeholder = "기존 로그인 JSON은 보안을 위해 표시되지 않습니다. 변경할 때만 새 값 입력";
    }
  }
  form.classList.remove("hidden");
  form.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function submitMonitor(event) {
  event.preventDefault();
  try {
    const isUpdate = Boolean(state.editingMonitorId);
    const payload = monitorPayload(event.currentTarget, isUpdate);
    await request(isUpdate ? `/monitors/${state.editingMonitorId}` : "/monitors", { method: isUpdate ? "PATCH" : "POST", body: JSON.stringify(payload) });
    toast(isUpdate ? "모니터 설정을 수정했습니다." : "모니터를 등록했습니다.");
    $("#monitor-form").classList.add("hidden");
    resetMonitorForm();
    await refresh();
  } catch (error) { toast(error.message, true); }
}

async function handleMonitorAction(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const monitor = state.monitors.find((item) => item.id === button.dataset.id);
  if (!monitor) return;
  try {
    if (button.dataset.action === "edit") return showMonitorForm(monitor);
    if (button.dataset.action === "check") {
      button.disabled = true; button.textContent = "점검 중…";
      await request(`/monitors/${monitor.id}/check`, { method: "POST" });
      toast("즉시 점검을 완료했습니다.");
    }
    if (button.dataset.action === "toggle") {
      await request(`/monitors/${monitor.id}`, { method: "PATCH", body: JSON.stringify({ enabled: !monitor.enabled }) });
      toast(monitor.enabled ? "정기 점검을 중지했습니다." : "정기 점검을 활성화했습니다.");
    }
    if (button.dataset.action === "delete") {
      if (!window.confirm(`“${monitor.name}” 모니터를 삭제할까요?`)) return;
      await request(`/monitors/${monitor.id}`, { method: "DELETE" });
      toast("모니터를 삭제했습니다.");
    }
    await refresh();
  } catch (error) { toast(error.message, true); await refresh(); }
}

async function submitRecipient(event) {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    await request("/recipients", { method: "POST", body: JSON.stringify({ name: field(form, "name").value.trim() || null, email: field(form, "email").value.trim(), enabled: true }) });
    form.reset(); toast("이메일 수신자를 등록했습니다."); await refresh();
  } catch (error) { toast(error.message, true); }
}

async function handleRecipientAction(event) {
  const button = event.target.closest("button[data-recipient-action]");
  if (!button) return;
  const recipient = state.recipients.find((item) => item.id === button.dataset.id);
  if (!recipient) return;
  try {
    if (button.dataset.recipientAction === "delete") {
      if (!window.confirm(`${recipient.email} 수신자를 삭제할까요?`)) return;
      await request(`/recipients/${recipient.id}`, { method: "DELETE" });
      toast("수신자를 삭제했습니다.");
    } else {
      await request(`/recipients/${recipient.id}`, { method: "PATCH", body: JSON.stringify({ enabled: !recipient.enabled }) });
      toast(recipient.enabled ? "수신자를 비활성화했습니다." : "수신자를 활성화했습니다.");
    }
    await refresh();
  } catch (error) { toast(error.message, true); }
}

async function submitEmailConfig(event) {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    await request("/email-config", { method: "PUT", body: JSON.stringify({
      smtp_host: field(form, "smtp_host").value.trim(), smtp_port: Number(field(form, "smtp_port").value),
      username: field(form, "username").value.trim() || null, password: field(form, "password").value || null,
      use_starttls: field(form, "use_starttls").checked, from_address: field(form, "from_address").value.trim(),
    }) });
    field(form, "password").value = "";
    toast("SMTP 설정을 저장했습니다."); await loadEmailConfig();
  } catch (error) { toast(error.message, true); }
}

async function sendEmailTest() {
  try { await request("/email-config/test", { method: "POST" }); toast("테스트 이메일을 전송했습니다."); }
  catch (error) { toast(error.message, true); }
}

document.addEventListener("DOMContentLoaded", () => {
  $("#refresh-button").addEventListener("click", refresh);
  $("#show-monitor-form").addEventListener("click", () => showMonitorForm());
  $("#cancel-monitor-edit").addEventListener("click", () => { $("#monitor-form").classList.add("hidden"); resetMonitorForm(); });
  $("#monitor-form").addEventListener("submit", submitMonitor);
  $("#monitor-list").addEventListener("click", handleMonitorAction);
  $("#recipient-form").addEventListener("submit", submitRecipient);
  $("#recipient-list").addEventListener("click", handleRecipientAction);
  $("#email-form").addEventListener("submit", submitEmailConfig);
  $("#send-email-test").addEventListener("click", sendEmailTest);
  refresh();
  state.refreshTimer = window.setInterval(refresh, 15000);
});
