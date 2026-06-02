const form = document.querySelector("#capture-form");
const roomInput = document.querySelector("#room-id");
const durationInput = document.querySelector("#duration");
const durationUnitInput = document.querySelector("#duration-unit");
const button = document.querySelector("#capture-button");
const statusEl = document.querySelector("#status");
const summaryEl = document.querySelector("#summary");
const messagesEl = document.querySelector("#messages");

let stream = null;
let currentCount = 0;
let currentMeta = null;
let countdownTimer = null;
let captureEndsAt = 0;

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

function clearMessages() {
  currentCount = 0;
  currentMeta = null;
  messagesEl.textContent = "";
  const row = document.createElement("tr");
  row.className = "empty-row";
  const cell = document.createElement("td");
  cell.colSpan = 4;
  cell.textContent = "\u7b49\u5f85\u5f39\u5e55...";
  row.append(cell);
  messagesEl.append(row);
}

function appendMessage(message) {
  const emptyRow = messagesEl.querySelector(".empty-row");
  if (emptyRow) emptyRow.remove();

  const row = document.createElement("tr");
  const timeCell = document.createElement("td");
  const nickCell = document.createElement("td");
  const levelCell = document.createElement("td");
  const textCell = document.createElement("td");

  timeCell.textContent = formatTime(message.received_at);
  nickCell.textContent = message.nickname || "\u533f\u540d\u7528\u6237";
  levelCell.textContent = message.level || "-";
  textCell.textContent = message.text || "";
  textCell.className = "message-text";

  row.append(timeCell, nickCell, levelCell, textCell);
  messagesEl.append(row);
}

function durationLabel(seconds) {
  if (seconds >= 60 && seconds % 60 === 0) return `${seconds / 60} \u5206\u949f`;
  return `${seconds} \u79d2`;
}

function formatCountdown(seconds) {
  const normalized = Math.max(0, Math.ceil(seconds));
  const minutes = Math.floor(normalized / 60);
  const restSeconds = normalized % 60;
  return `${String(minutes).padStart(2, "0")}:${String(restSeconds).padStart(2, "0")}`;
}

function updateCountdown() {
  if (!captureEndsAt) return;
  const remainingSeconds = (captureEndsAt - Date.now()) / 1000;
  setStatus(`\u6b63\u5728\u6293\u53d6\uff0c\u5012\u8ba1\u65f6 ${formatCountdown(remainingSeconds)}`, "loading");
}

function startCountdown(durationSeconds) {
  stopCountdown();
  captureEndsAt = Date.now() + durationSeconds * 1000;
  updateCountdown();
  countdownTimer = window.setInterval(updateCountdown, 1000);
}

function stopCountdown() {
  if (countdownTimer) {
    window.clearInterval(countdownTimer);
    countdownTimer = null;
  }
  captureEndsAt = 0;
}

function closeStream() {
  if (stream) {
    stream.close();
    stream = null;
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  closeStream();
  stopCountdown();

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
  clearMessages();
  summaryEl.textContent = "";
  setStatus("\u6b63\u5728\u5224\u65ad\u76f4\u64ad\u95f4\u72b6\u6001...", "loading");

  const params = new URLSearchParams({ room_id: roomId, duration: String(durationSeconds) });
  stream = new EventSource(`/api/capture-stream?${params.toString()}`);

  stream.addEventListener("status", (event) => {
    const data = JSON.parse(event.data);
    setStatus(data.message, "loading");
  });

  stream.addEventListener("ready", (event) => {
    currentMeta = JSON.parse(event.data);
    startCountdown(currentMeta.duration);
    const roomName = currentMeta.room_name ? `\uff08${currentMeta.room_name}\uff09` : "";
    summaryEl.textContent = `\u623f\u95f4 ${currentMeta.room_id}${roomName}\uff0c\u72b6\u6001 ${currentMeta.status_label}\uff0c\u5199\u5165\u8868 ${currentMeta.table}`;
  });

  stream.addEventListener("message", (event) => {
    const data = JSON.parse(event.data);
    currentCount = data.count;
    appendMessage(data.message);
    if (currentMeta) {
      const roomName = currentMeta.room_name ? `\uff08${currentMeta.room_name}\uff09` : "";
      summaryEl.textContent = `\u623f\u95f4 ${currentMeta.room_id}${roomName}\uff0c\u5df2\u6293\u53d6 ${currentCount} \u6761\uff0c\u5199\u5165\u8868 ${currentMeta.table}`;
    }
  });

  stream.addEventListener("done", (event) => {
    const data = JSON.parse(event.data);
    stopCountdown();
    setStatus("\u6293\u53d6\u5b8c\u6210", "success");
    const roomName = data.room_name ? `\uff08${data.room_name}\uff09` : "";
    summaryEl.textContent = `\u623f\u95f4 ${data.room_id}${roomName}\uff0c\u8fd0\u884c ${data.elapsed} \u79d2\uff0c\u5171 ${data.count} \u6761\uff0c\u5df2\u5199\u5165\u8868 ${data.table}`;
    closeStream();
    button.disabled = false;
  });

  stream.addEventListener("error", (event) => {
    stopCountdown();
    if (event.data) {
      const data = JSON.parse(event.data);
      setStatus(data.error || "\u6293\u53d6\u5931\u8d25", "error");
    } else {
      setStatus("\u8fde\u63a5\u5df2\u4e2d\u65ad", "error");
    }
    closeStream();
    button.disabled = false;
  });
});

window.addEventListener("beforeunload", () => {
  stopCountdown();
  closeStream();
});
