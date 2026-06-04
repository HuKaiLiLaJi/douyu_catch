const form = document.querySelector("#capture-form");
const roomInput = document.querySelector("#room-id");
const durationInput = document.querySelector("#duration");
const durationUnitInput = document.querySelector("#duration-unit");
const button = document.querySelector("#capture-button");
const statusEl = document.querySelector("#status");
const summaryEl = document.querySelector("#summary");
const sessionsEl = document.querySelector("#sessions");
const runningStatusEl = document.querySelector("#running-status");
const runningListEl = document.querySelector("#running-list");
const refreshRunningButton = document.querySelector("#refresh-running");
const historyStatusEl = document.querySelector("#history-status");
const historyListEl = document.querySelector("#history-list");
const refreshHistoryButton = document.querySelector("#refresh-history");

const tasks = new Map();
const historyPanels = new Map();

function setStatus(message, mode = "idle") {
  statusEl.textContent = message;
  statusEl.dataset.mode = mode;
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function formatCountdown(seconds) {
  const normalized = Math.max(0, Math.ceil(seconds));
  const minutes = Math.floor(normalized / 60);
  const restSeconds = normalized % 60;
  return `${String(minutes).padStart(2, "0")}:${String(restSeconds).padStart(2, "0")}`;
}

function formatDuration(seconds) {
  const normalized = Math.max(0, Math.floor(seconds || 0));
  const minutes = Math.floor(normalized / 60);
  const restSeconds = normalized % 60;
  return `${String(minutes).padStart(2, "0")}:${String(restSeconds).padStart(2, "0")}`;
}

function statusLabel(status) {
  const labels = {
    starting: "\u542f\u52a8\u4e2d",
    checking: "\u68c0\u67e5\u4e2d",
    running: "\u8fd0\u884c\u4e2d",
    cancelling: "\u505c\u6b62\u4e2d",
    completed: "\u5df2\u5b8c\u6210",
    rejected: "\u672a\u5f00\u64ad",
    failed: "\u5931\u8d25",
    cancelled: "\u5df2\u505c\u6b62",
  };
  return labels[status] || status || "-";
}

function stateMode(status) {
  if (status === "completed") return "success";
  if (status === "failed" || status === "rejected" || status === "cancelled") return "error";
  return "loading";
}

function makeCell(text, className = "") {
  const cell = document.createElement("td");
  cell.textContent = text;
  if (className) cell.className = className;
  return cell;
}

function removeEmptySessions() {
  const empty = sessionsEl.querySelector(".empty-sessions");
  if (empty) empty.remove();
}

function createEmptyRow(message = "\u7b49\u5f85\u5f39\u5e55...") {
  const row = document.createElement("tr");
  row.className = "empty-row";
  const cell = document.createElement("td");
  cell.colSpan = 4;
  cell.textContent = message;
  row.append(cell);
  return row;
}

function createMessageTable(emptyMessage) {
  const tableWrap = document.createElement("div");
  tableWrap.className = "table-wrap";
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["\u65f6\u95f4", "\u6635\u79f0", "\u7b49\u7ea7", "\u5f39\u5e55\u5185\u5bb9"].forEach((label) => {
    const th = document.createElement("th");
    th.textContent = label;
    headRow.append(th);
  });
  thead.append(headRow);
  const tbody = document.createElement("tbody");
  tbody.append(createEmptyRow(emptyMessage));
  table.append(thead, tbody);
  tableWrap.append(table);
  return { tableWrap, tbody };
}

function createPanelShell({ id, titleText, metaText, stateText, mode = "loading", prepend = true }) {
  removeEmptySessions();

  const panel = document.createElement("article");
  panel.className = "session-panel";
  panel.dataset.panelId = id;

  const header = document.createElement("div");
  header.className = "session-header";

  const titleWrap = document.createElement("div");
  const title = document.createElement("h2");
  title.textContent = titleText;
  const meta = document.createElement("p");
  meta.className = "session-meta";
  meta.textContent = metaText;
  titleWrap.append(title, meta);

  const controls = document.createElement("div");
  controls.className = "session-controls";

  const state = document.createElement("div");
  state.className = "session-state";
  state.dataset.mode = mode;
  state.textContent = stateText;

  controls.append(state);
  header.append(titleWrap, controls);

  const summary = document.createElement("div");
  summary.className = "session-summary";

  const { tableWrap, tbody } = createMessageTable("\u7b49\u5f85\u5f39\u5e55...");
  panel.append(header, summary, tableWrap);
  if (prepend) {
    sessionsEl.prepend(panel);
  } else {
    sessionsEl.append(panel);
  }

  return { panel, title, meta, state, controls, summary, tbody };
}

function createTaskPanel(taskInfo) {
  return createPanelShell({
    id: taskInfo.task_id,
    titleText: `\u623f\u95f4 ${taskInfo.room_id}`,
    metaText: `\u4efb\u52a1 ${taskInfo.task_id}`,
    stateText: "\u521b\u5efa\u4e2d",
  });
}

function updateTaskSummary(task, prefix, data = {}) {
  const roomId = data.room_id || task.roomId;
  const roomName = data.room_name ? `\uff08${data.room_name}\uff09` : "";
  const table = data.table ? `\uff0c\u8868 ${data.table}` : "";
  const session = data.session_id ? `\uff0c\u4f1a\u8bdd ${data.session_id}` : "";
  task.nodes.summary.textContent = `${prefix}\uff1a\u623f\u95f4 ${roomId}${roomName}${table}${session}`;
}

function setTaskState(task, message, mode = "loading") {
  task.nodes.state.textContent = message;
  task.nodes.state.dataset.mode = mode;
}

function clearTaskMessages(task, message = "\u672c\u6b21\u4f1a\u8bdd\u5f39\u5e55\u5df2\u6e05\u7a7a") {
  task.nodes.tbody.textContent = "";
  task.nodes.tbody.append(createEmptyRow(message));
}

function setTaskCancelButtonVisible(task, visible) {
  if (!task.cancelButton) return;
  task.cancelButton.hidden = !visible;
  task.cancelButton.disabled = !visible;
}

function addCancelButton(task) {
  const cancelButton = document.createElement("button");
  cancelButton.type = "button";
  cancelButton.className = "danger-button";
  cancelButton.textContent = "\u505c\u6b62";
  cancelButton.addEventListener("click", () => cancelTask(task));
  task.nodes.controls.append(cancelButton);
  task.cancelButton = cancelButton;
}

function startTaskCountdown(task, durationSeconds) {
  stopTaskCountdown(task);
  task.endsAt = Date.now() + durationSeconds * 1000;
  updateTaskCountdown(task);
  task.countdownTimer = window.setInterval(() => updateTaskCountdown(task), 1000);
}

function updateTaskCountdown(task) {
  if (!task.endsAt) return;
  const remainingSeconds = (task.endsAt - Date.now()) / 1000;
  setTaskState(task, `\u5012\u8ba1\u65f6 ${formatCountdown(remainingSeconds)}`, "loading");
}

function stopTaskCountdown(task) {
  if (task.countdownTimer) {
    window.clearInterval(task.countdownTimer);
    task.countdownTimer = null;
  }
  task.endsAt = 0;
}

function appendMessage(tbody, message) {
  const emptyRow = tbody.querySelector(".empty-row");
  if (emptyRow) emptyRow.remove();

  const row = document.createElement("tr");
  row.append(
    makeCell(formatTime(message.received_at)),
    makeCell(message.nickname || "\u533f\u540d\u7528\u6237"),
    makeCell(message.level || "-"),
    makeCell(message.text || "", "message-text"),
  );
  tbody.append(row);
}

function attachTaskStream(task, streamUrl) {
  task.stream = new EventSource(streamUrl);

  task.stream.addEventListener("snapshot", (event) => {
    const data = JSON.parse(event.data);
    if (data.room_name) {
      task.nodes.title.textContent = `\u623f\u95f4 ${data.room_id}\uff08${data.room_name}\uff09`;
    }
    if (data.status === "running") {
      startTaskCountdown(task, Math.max(1, data.duration - Math.floor(data.elapsed || 0)));
      updateTaskSummary(task, "\u6b63\u5728\u67e5\u770b\u4efb\u52a1", data);
    }
  });

  task.stream.addEventListener("status", (event) => {
    const data = JSON.parse(event.data);
    setTaskState(task, data.message, "loading");
  });

  task.stream.addEventListener("ready", (event) => {
    const data = JSON.parse(event.data);
    task.meta = data;
    setTaskCancelButtonVisible(task, true);
    task.nodes.title.textContent = data.room_name ? `\u623f\u95f4 ${data.room_id}\uff08${data.room_name}\uff09` : `\u623f\u95f4 ${data.room_id}`;
    task.nodes.meta.textContent = `\u4efb\u52a1 ${data.task_id}\uff0c\u4f1a\u8bdd ${data.session_id}`;
    startTaskCountdown(task, data.duration);
    updateTaskSummary(task, "\u4efb\u52a1\u5df2\u542f\u52a8", data);
  });

  task.stream.addEventListener("message", (event) => {
    const data = JSON.parse(event.data);
    task.count = data.count;
    appendMessage(task.nodes.tbody, data.message);
    updateTaskSummary(task, `\u5df2\u6293\u53d6 ${task.count} \u6761`, task.meta || data);
  });

  task.stream.addEventListener("done", (event) => {
    const data = JSON.parse(event.data);
    stopTaskCountdown(task);
    setTaskCancelButtonVisible(task, false);
    setTaskState(task, "\u5df2\u5b8c\u6210", "success");
    task.nodes.summary.textContent = `\u8fd0\u884c ${data.elapsed} \u79d2\uff0c\u5171 ${data.count} \u6761\uff0c\u4f1a\u8bdd ${data.session_id}\uff0c\u5df2\u5199\u5165\u8868 ${data.table}`;
    closeTaskStream(task);
    loadRunningTasks();
loadHistorySessions();
  });

  task.stream.addEventListener("cancelled", (event) => {
    const data = JSON.parse(event.data);
    stopTaskCountdown(task);
    setTaskCancelButtonVisible(task, false);
    setTaskState(task, "\u5df2\u505c\u6b62", "error");
    task.count = 0;
    clearTaskMessages(task);
    task.nodes.summary.textContent = `${data.message}\uff0c\u5220\u9664 ${data.deleted_count || 0} \u6761`;
    closeTaskStream(task);
    loadRunningTasks();
loadHistorySessions();
  });

  task.stream.addEventListener("error", (event) => {
    stopTaskCountdown(task);
    setTaskCancelButtonVisible(task, false);
    if (event.data) {
      const data = JSON.parse(event.data);
      setTaskState(task, "\u5931\u8d25", "error");
      task.nodes.summary.textContent = data.error || "\u6293\u53d6\u5931\u8d25";
    } else {
      setTaskState(task, "\u8fde\u63a5\u4e2d\u65ad", "error");
      task.nodes.summary.textContent = "\u5b9e\u65f6\u8fde\u63a5\u5df2\u4e2d\u65ad\uff0c\u540e\u53f0\u4efb\u52a1\u4ecd\u4f1a\u7ee7\u7eed\u8fd0\u884c";
    }
    closeTaskStream(task);
    loadRunningTasks();
loadHistorySessions();
  });
}

function closeTaskStream(task) {
  if (task.stream) {
    task.stream.close();
    task.stream = null;
  }
}

async function cancelTask(task) {
  if (!task || task.cancelRequested) return;
  task.cancelRequested = true;
  if (task.cancelButton) {
    task.cancelButton.disabled = true;
    task.cancelButton.textContent = "\u505c\u6b62\u4e2d";
  }
  setTaskState(task, "\u505c\u6b62\u4e2d", "loading");
  task.nodes.summary.textContent = "\u6b63\u5728\u505c\u6b62\u4efb\u52a1\uff0c\u5e76\u6e05\u7406\u672c\u6b21\u4f1a\u8bdd\u5f39\u5e55...";

  try {
    const response = await fetch(`/api/tasks/${task.taskId}/cancel`, { method: "POST" });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "\u505c\u6b62\u4efb\u52a1\u5931\u8d25");
    }
    setStatus("\u5df2\u53d1\u9001\u505c\u6b62\u8bf7\u6c42", "loading");
  } catch (error) {
    task.cancelRequested = false;
    if (task.cancelButton) {
      task.cancelButton.disabled = false;
      task.cancelButton.textContent = "\u505c\u6b62";
    }
    setTaskState(task, "\u8fd0\u884c\u4e2d", "loading");
    setStatus(error.message || "\u505c\u6b62\u4efb\u52a1\u5931\u8d25", "error");
  }
}

function renderRunningTasks(runningTasks) {
  runningListEl.textContent = "";
  if (!runningTasks.length) {
    runningStatusEl.textContent = "\u5f53\u524d\u6ca1\u6709\u6b63\u5728\u8fd0\u884c\u7684\u91c7\u96c6\u4efb\u52a1";
    return;
  }

  runningStatusEl.textContent = `\u5171 ${runningTasks.length} \u4e2a\u8fd0\u884c\u4efb\u52a1`;
  runningTasks.forEach((task) => {
    const item = document.createElement("div");
    item.className = "running-item";

    const main = document.createElement("div");
    const roomName = task.room_name ? `\uff08${task.room_name}\uff09` : "";
    const title = document.createElement("strong");
    title.textContent = `\u623f\u95f4 ${task.room_id}${roomName}`;

    const elapsed = task.elapsed || 0;
    const remaining = Math.max(0, (task.duration || 0) - elapsed);
    const meta = document.createElement("span");
    const session = task.session_id ? `\uff0c\u4f1a\u8bdd ${task.session_id}` : "";
    meta.textContent = `\u5df2\u6293\u53d6 ${task.count || 0} \u6761\uff0c\u8fd0\u884c ${formatDuration(elapsed)}\uff0c\u5269\u4f59 ${formatDuration(remaining)}${session}`;
    main.append(title, meta);

    const badge = document.createElement("span");
    badge.className = "history-badge";
    badge.dataset.mode = stateMode(task.status);
    badge.textContent = statusLabel(task.status);

    item.append(main, badge);
    runningListEl.append(item);
  });
}

async function loadRunningTasks() {
  try {
    const response = await fetch("/api/tasks");
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "\u52a0\u8f7d\u8fd0\u884c\u4efb\u52a1\u5931\u8d25");
    }
    renderRunningTasks(data.tasks || []);
  } catch (error) {
    runningStatusEl.textContent = error.message || "\u52a0\u8f7d\u8fd0\u884c\u4efb\u52a1\u5931\u8d25";
  }
}

function renderHistoryList(sessions) {
  historyListEl.textContent = "";
  if (!sessions.length) {
    historyStatusEl.textContent = "\u6682\u65e0\u5386\u53f2\u4f1a\u8bdd";
    return;
  }

  historyStatusEl.textContent = `\u5171 ${sessions.length} \u6761\u6700\u8fd1\u4f1a\u8bdd`;
  sessions.forEach((session) => {
    const buttonEl = document.createElement("button");
    buttonEl.type = "button";
    buttonEl.className = "history-item";
    buttonEl.dataset.sessionId = session.id;

    const main = document.createElement("div");
    const roomName = session.room_name ? `\uff08${session.room_name}\uff09` : "";
    const title = document.createElement("strong");
    title.textContent = `#${session.id} \u623f\u95f4 ${session.room_id}${roomName}`;
    const meta = document.createElement("span");
    meta.textContent = `${formatTime(session.started_at)} \u00b7 ${session.message_count || 0} \u6761 \u00b7 ${session.table_name}`;
    main.append(title, meta);

    const badge = document.createElement("span");
    badge.className = "history-badge";
    badge.dataset.mode = stateMode(session.status);
    badge.textContent = statusLabel(session.status);

    buttonEl.append(main, badge);
    buttonEl.addEventListener("click", () => showHistorySession(session.id));
    historyListEl.append(buttonEl);
  });
}

async function loadHistorySessions() {
  historyStatusEl.textContent = "\u6b63\u5728\u52a0\u8f7d\u5386\u53f2\u4f1a\u8bdd...";
  try {
    const response = await fetch("/api/sessions?limit=50");
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "\u52a0\u8f7d\u5386\u53f2\u4f1a\u8bdd\u5931\u8d25");
    }
    renderHistoryList(data.sessions || []);
  } catch (error) {
    historyStatusEl.textContent = error.message || "\u52a0\u8f7d\u5386\u53f2\u4f1a\u8bdd\u5931\u8d25";
  }
}

async function showHistorySession(sessionId) {
  const existing = historyPanels.get(String(sessionId));
  if (existing) {
    existing.nodes.panel.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }

  setStatus("\u6b63\u5728\u52a0\u8f7d\u4f1a\u8bdd\u5f39\u5e55...", "loading");
  try {
    const response = await fetch(`/api/sessions/${sessionId}/messages?limit=1000`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "\u52a0\u8f7d\u4f1a\u8bdd\u5f39\u5e55\u5931\u8d25");
    }

    const session = data.session;
    const roomName = session.room_name ? `\uff08${session.room_name}\uff09` : "";
    const nodes = createPanelShell({
      id: `history-${session.id}`,
      titleText: `\u5386\u53f2 #${session.id} \u623f\u95f4 ${session.room_id}${roomName}`,
      metaText: `\u5f00\u59cb ${formatTime(session.started_at)}\uff0c\u4efb\u52a1 ${session.task_id}`,
      stateText: statusLabel(session.status),
      mode: stateMode(session.status),
      prepend: false,
    });
    nodes.panel.classList.add("history-panel");
    nodes.summary.textContent = `\u5171 ${data.messages.length} \u6761\uff0c\u8868 ${session.table_name}\uff0c\u4f1a\u8bdd ${session.id}`;
    nodes.tbody.textContent = "";
    if (data.messages.length) {
      data.messages.forEach((message) => appendMessage(nodes.tbody, message));
    } else {
      nodes.tbody.append(createEmptyRow("\u8fd9\u6b21\u4f1a\u8bdd\u6682\u65e0\u5f39\u5e55"));
    }

    historyPanels.set(String(session.id), { nodes });
    nodes.panel.scrollIntoView({ behavior: "smooth", block: "start" });
    setStatus("\u4f1a\u8bdd\u5f39\u5e55\u5df2\u52a0\u8f7d", "success");
  } catch (error) {
    setStatus(error.message || "\u52a0\u8f7d\u4f1a\u8bdd\u5f39\u5e55\u5931\u8d25", "error");
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const roomId = roomInput.value.trim();
  const durationValue = Number.parseInt(durationInput.value, 10);
  const unit = Number.parseInt(durationUnitInput.value, 10);
  const durationSeconds = durationValue * unit;

  if (!roomId) {
    setStatus("\u8bf7\u8f93\u5165\u623f\u95f4\u53f7", "error");
    roomInput.focus();
    return;
  }
  if (!Number.isInteger(durationSeconds) || durationSeconds <= 0) {
    setStatus("\u8bf7\u8f93\u5165\u6b63\u786e\u7684\u6293\u53d6\u65f6\u957f", "error");
    durationInput.focus();
    return;
  }
  if (durationSeconds > 3600) {
    setStatus("\u5355\u6b21\u6700\u591a\u6293\u53d6 60 \u5206\u949f", "error");
    durationInput.focus();
    return;
  }

  button.disabled = true;
  setStatus("\u6b63\u5728\u521b\u5efa\u540e\u53f0\u4efb\u52a1...", "loading");
  summaryEl.textContent = "";

  try {
    const response = await fetch("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room_id: roomId, duration: durationSeconds }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "\u521b\u5efa\u4efb\u52a1\u5931\u8d25");
    }

    const nodes = createTaskPanel(data);
    const task = {
      taskId: data.task_id,
      roomId: data.room_id,
      duration: data.duration,
      stream: null,
      countdownTimer: null,
      endsAt: 0,
      count: 0,
      meta: null,
      cancelRequested: false,
      cancelButton: null,
      nodes,
    };
    addCancelButton(task);
    setTaskCancelButtonVisible(task, false);
    tasks.set(task.taskId, task);
    attachTaskStream(task, data.stream_url);

    setStatus("\u540e\u53f0\u4efb\u52a1\u5df2\u521b\u5efa", "success");
    summaryEl.textContent = `\u65b0\u4efb\u52a1 ID\uff1a${data.task_id}`;
    loadRunningTasks();
    loadHistorySessions();
  } catch (error) {
    setStatus(error.message || "\u521b\u5efa\u4efb\u52a1\u5931\u8d25", "error");
  } finally {
    button.disabled = false;
  }
});

refreshRunningButton.addEventListener("click", loadRunningTasks);
refreshHistoryButton.addEventListener("click", loadHistorySessions);
window.setInterval(loadRunningTasks, 5000);

window.addEventListener("beforeunload", () => {
  tasks.forEach((task) => {
    stopTaskCountdown(task);
    closeTaskStream(task);
  });
});

loadRunningTasks();
loadHistorySessions();
