"""Flask web UI for the Douyu danmu collector."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import os
import threading
import time
from typing import Any
from uuid import uuid4

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from .client import DouyuDanmuClient
from .models import MySQLConfig
from .room_status import fetch_room_status
from .storage import MySQLDanmuWriter, room_table_name


DEFAULT_DANMU_HOST = "danmuproxy.douyu.com"
DEFAULT_DANMU_PORT = 8601
MAX_CAPTURE_SECONDS = 3600
TASK_EVENT_TIMEOUT_SECONDS = 1.0


@dataclass
class TaskEvent:
    seq: int
    name: str
    payload: dict[str, Any]


@dataclass
class CaptureTask:
    task_id: str
    room_id: str
    duration_seconds: int
    status: str = "created"
    status_label: str = ""
    room_name: str = ""
    table_name: str = ""
    count: int = 0
    session_id: int | None = None
    error: str = ""
    started_at: float = field(default_factory=time.monotonic)
    ended_at: float | None = None
    events: list[TaskEvent] = field(default_factory=list)
    condition: threading.Condition = field(default_factory=threading.Condition)
    cancel_requested: threading.Event = field(default_factory=threading.Event)

    def add_event(self, name: str, payload: dict[str, Any]) -> None:
        payload = {"task_id": self.task_id, **payload}
        with self.condition:
            event = TaskEvent(len(self.events), name, payload)
            self.events.append(event)
            self.condition.notify_all()

    def snapshot(self) -> dict[str, Any]:
        elapsed = time.monotonic() - self.started_at
        if self.ended_at is not None:
            elapsed = self.ended_at - self.started_at
        return {
            "task_id": self.task_id,
            "room_id": self.room_id,
            "duration": self.duration_seconds,
            "status": self.status,
            "status_label": self.status_label,
            "room_name": self.room_name,
            "table": self.table_name,
            "count": self.count,
            "session_id": self.session_id,
            "error": self.error,
            "elapsed": round(max(elapsed, 0), 1),
            "done": self.ended_at is not None,
            "cancel_requested": self.cancel_requested.is_set(),
        }


class CaptureTaskManager:
    def __init__(self) -> None:
        self._tasks: dict[str, CaptureTask] = {}
        self._lock = threading.Lock()

    def start(self, room_id: str, duration_seconds: int) -> CaptureTask:
        task = CaptureTask(
            task_id=str(uuid4()),
            room_id=str(room_id),
            duration_seconds=duration_seconds,
            table_name=room_table_name(room_id),
        )
        with self._lock:
            self._tasks[task.task_id] = task
        thread = threading.Thread(target=self._run_task, args=(task,), daemon=True)
        thread.start()
        return task

    def get(self, task_id: str) -> CaptureTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def cancel(self, task_id: str) -> tuple[CaptureTask | None, str]:
        task = self.get(task_id)
        if task is None:
            return None, "missing"
        if task.ended_at is not None:
            return task, "finished"
        task.cancel_requested.set()
        task.status = "cancelling"
        task.add_event("status", {"message": "\u6b63\u5728\u505c\u6b62\u4efb\u52a1\uff0c\u5e76\u6e05\u7406\u672c\u6b21\u4f1a\u8bdd\u5f39\u5e55..."})
        return task, "cancelling"

    def _run_task(self, task: CaptureTask) -> None:
        client = None
        mysql_writer = None
        session_id = None

        try:
            task.status = "checking"
            task.add_event("status", {"message": "\u6b63\u5728\u5224\u65ad\u76f4\u64ad\u95f4\u72b6\u6001..."})

            mysql_writer = MySQLDanmuWriter(web_mysql_config())
            mysql_writer.connect()
            session_id = mysql_writer.create_session(
                task.task_id,
                task.room_id,
                task.duration_seconds,
                task.table_name,
            )
            task.session_id = session_id

            status = fetch_room_status(task.room_id)
            task.room_id = status.room_id
            task.room_name = status.room_name
            task.status_label = status.label
            task.table_name = room_table_name(status.room_id)

            if task.cancel_requested.is_set():
                deleted_count = mysql_writer.delete_session_messages(session_id) or 0
                task.count = 0
                task.status = "cancelled"
                mysql_writer.update_session(
                    session_id,
                    status="cancelled",
                    room_name=status.room_name,
                    room_status=status.status,
                    message_count=0,
                    error_message="\u7528\u6237\u624b\u52a8\u505c\u6b62\uff0c\u5df2\u6e05\u7406\u672c\u6b21\u4f1a\u8bdd\u5f39\u5e55",
                    ended_at=datetime.utcnow(),
                )
                task.add_event("cancelled", {
                    "message": "\u4efb\u52a1\u5df2\u505c\u6b62\uff0c\u5df2\u6e05\u7406\u672c\u6b21\u4f1a\u8bdd\u5f39\u5e55",
                    "room_id": task.room_id,
                    "room_name": task.room_name,
                    "status": "cancelled",
                    "table": task.table_name,
                    "count": 0,
                    "deleted_count": deleted_count,
                    "elapsed": task.snapshot()["elapsed"],
                    "session_id": session_id,
                })
                return

            if not status.is_live:
                task.status = "rejected"
                task.error = f"\u8be5\u4e3b\u64ad\u6ca1\u6709\u5f00\u64ad\uff0c\u5f53\u524d\u72b6\u6001\uff1a{status.label}"
                mysql_writer.update_session(
                    session_id,
                    status="rejected",
                    room_name=status.room_name,
                    room_status=status.status,
                    message_count=0,
                    error_message=task.error,
                    ended_at=datetime.utcnow(),
                )
                task.add_event("error", {
                    "error": task.error,
                    "room_id": status.room_id,
                    "room_name": status.room_name,
                    "status": status.status,
                    "status_label": status.label,
                    "session_id": session_id,
                })
                return

            task.status = "running"
            mysql_writer.update_session(
                session_id,
                status="running",
                room_name=status.room_name,
                room_status=status.status,
            )
            task.add_event("ready", {
                "message": "\u76f4\u64ad\u95f4\u6b63\u5728\u5f00\u64ad\uff0c\u5f00\u59cb\u6293\u53d6\u5f39\u5e55",
                "room_id": status.room_id,
                "room_name": status.room_name,
                "status": status.status,
                "status_label": status.label,
                "table": task.table_name,
                "duration": task.duration_seconds,
                "session_id": session_id,
            })

            client = DouyuDanmuClient(
                status.room_id,
                host=DEFAULT_DANMU_HOST,
                port=DEFAULT_DANMU_PORT,
                read_timeout=1.0,
            )
            client.connect()

            for message in client.messages_for(task.duration_seconds, should_stop=task.cancel_requested.is_set):
                if task.cancel_requested.is_set():
                    break
                mysql_writer.write(message, session_id=session_id)
                task.count += 1
                task.add_event("message", {"count": task.count, "message": message.as_dict()})

            if task.cancel_requested.is_set():
                deleted_count = mysql_writer.delete_session_messages(session_id) or 0
                task.count = 0
                task.status = "cancelled"
                mysql_writer.update_session(
                    session_id,
                    status="cancelled",
                    message_count=0,
                    error_message="\u7528\u6237\u624b\u52a8\u505c\u6b62\uff0c\u5df2\u6e05\u7406\u672c\u6b21\u4f1a\u8bdd\u5f39\u5e55",
                    ended_at=datetime.utcnow(),
                )
                task.add_event("cancelled", {
                    "message": "\u4efb\u52a1\u5df2\u505c\u6b62\uff0c\u5df2\u6e05\u7406\u672c\u6b21\u4f1a\u8bdd\u5f39\u5e55",
                    "room_id": task.room_id,
                    "room_name": task.room_name,
                    "status": "cancelled",
                    "table": task.table_name,
                    "count": 0,
                    "deleted_count": deleted_count,
                    "elapsed": task.snapshot()["elapsed"],
                    "session_id": session_id,
                })
                return

            task.status = "completed"
            mysql_writer.update_session(
                session_id,
                status="completed",
                message_count=task.count,
                ended_at=datetime.utcnow(),
            )
            task.add_event("done", {
                "message": "\u6293\u53d6\u5b8c\u6210",
                "room_id": task.room_id,
                "room_name": task.room_name,
                "status": status.status,
                "status_label": status.label,
                "table": task.table_name,
                "count": task.count,
                "elapsed": task.snapshot()["elapsed"],
                "session_id": session_id,
            })
        except Exception as exc:
            task.status = "failed"
            task.error = f"\u6293\u53d6\u5931\u8d25: {exc}"
            if mysql_writer is not None and session_id is not None:
                try:
                    mysql_writer.update_session(
                        session_id,
                        status="failed",
                        message_count=task.count,
                        error_message=task.error,
                        ended_at=datetime.utcnow(),
                    )
                except Exception:
                    pass
            task.add_event("error", {"error": task.error, "count": task.count, "session_id": session_id})
        finally:
            task.ended_at = time.monotonic()
            with task.condition:
                task.condition.notify_all()
            if client is not None:
                client.close()
            if mysql_writer is not None:
                mysql_writer.close()


def web_mysql_config() -> MySQLConfig:
    return MySQLConfig(
        host=os.getenv("DOUYU_MYSQL_HOST", "localhost"),
        port=int(os.getenv("DOUYU_MYSQL_PORT", "3306")),
        user=os.getenv("DOUYU_MYSQL_USER", "root"),
        password=os.getenv("DOUYU_MYSQL_PASSWORD", os.getenv("MYSQL_PWD", "root")),
        database=os.getenv("DOUYU_MYSQL_DB", "douyu_danmu"),
        per_room_tables=True,
    )


task_manager = CaptureTaskManager()


def create_app() -> Flask:
    app = Flask(__name__, template_folder="../templates", static_folder="../static")

    @app.after_request
    def set_utf8_headers(response):
        if response.content_type.startswith("text/html"):
            response.headers["Content-Type"] = "text/html; charset=utf-8"
        elif response.content_type.startswith("text/javascript"):
            response.headers["Content-Type"] = "text/javascript; charset=utf-8"
        elif response.content_type.startswith("text/css"):
            response.headers["Content-Type"] = "text/css; charset=utf-8"
        elif response.content_type.startswith("text/event-stream"):
            response.headers["Content-Type"] = "text/event-stream; charset=utf-8"
        return response

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.post("/api/tasks")
    def create_capture_task():
        data = request.get_json(silent=True) or {}
        room_id = str(data.get("room_id", "")).strip()
        try:
            duration_seconds = int(data.get("duration", 10))
        except (TypeError, ValueError):
            return jsonify({"error": "\u6293\u53d6\u65f6\u957f\u5fc5\u987b\u662f\u6574\u6570\u79d2"}), 400

        error = validate_capture_request(room_id, duration_seconds)
        if error:
            return jsonify({"error": error}), 400

        task = task_manager.start(room_id, duration_seconds)
        return jsonify({
            "task_id": task.task_id,
            "room_id": task.room_id,
            "duration": task.duration_seconds,
            "status_url": f"/api/tasks/{task.task_id}",
            "stream_url": f"/api/tasks/{task.task_id}/stream",
        }), 202

    @app.get("/api/tasks/<task_id>")
    def get_capture_task(task_id: str):
        task = task_manager.get(task_id)
        if task is None:
            return jsonify({"error": "\u4efb\u52a1\u4e0d\u5b58\u5728"}), 404
        return jsonify(task.snapshot())

    @app.post("/api/tasks/<task_id>/cancel")
    def cancel_capture_task(task_id: str):
        task, result = task_manager.cancel(task_id)
        if task is None:
            return jsonify({"error": "\u4efb\u52a1\u4e0d\u5b58\u5728"}), 404
        if result == "finished":
            return jsonify({"error": "\u4efb\u52a1\u5df2\u7ed3\u675f\uff0c\u4e0d\u80fd\u505c\u6b62", "task": task.snapshot()}), 409
        return jsonify({"message": "\u5df2\u53d1\u9001\u505c\u6b62\u8bf7\u6c42", "task": task.snapshot()})

    @app.get("/api/tasks/<task_id>/stream")
    def stream_capture_task(task_id: str):
        task = task_manager.get(task_id)
        if task is None:
            return jsonify({"error": "\u4efb\u52a1\u4e0d\u5b58\u5728"}), 404
        return Response(
            stream_with_context(_stream_task_events(task)),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/sessions")
    def list_capture_sessions():
        try:
            limit = int(request.args.get("limit", "50"))
        except ValueError:
            return jsonify({"error": "\u67e5\u8be2\u6570\u91cf\u5fc5\u987b\u662f\u6574\u6570"}), 400

        writer = MySQLDanmuWriter(web_mysql_config())
        try:
            sessions = writer.list_sessions(limit=limit)
        except Exception as exc:
            return jsonify({"error": f"\u67e5\u8be2\u4f1a\u8bdd\u5931\u8d25: {exc}"}), 500
        finally:
            writer.close()
        return jsonify({"sessions": sessions})

    @app.get("/api/sessions/<int:session_id>/messages")
    def list_capture_session_messages(session_id: int):
        try:
            limit = int(request.args.get("limit", "500"))
        except ValueError:
            return jsonify({"error": "\u67e5\u8be2\u6570\u91cf\u5fc5\u987b\u662f\u6574\u6570"}), 400

        writer = MySQLDanmuWriter(web_mysql_config())
        try:
            result = writer.list_session_messages(session_id, limit=limit)
        except Exception as exc:
            return jsonify({"error": f"\u67e5\u8be2\u5f39\u5e55\u5931\u8d25: {exc}"}), 500
        finally:
            writer.close()

        if result is None:
            return jsonify({"error": "\u4f1a\u8bdd\u4e0d\u5b58\u5728"}), 404
        session, messages = result
        return jsonify({"session": session, "messages": messages})

    @app.get("/api/capture-stream")
    def capture_stream_compat():
        room_id = str(request.args.get("room_id", "")).strip()
        try:
            duration_seconds = int(request.args.get("duration", "10"))
        except ValueError:
            return jsonify({"error": "\u6293\u53d6\u65f6\u957f\u5fc5\u987b\u662f\u6574\u6570\u79d2"}), 400

        error = validate_capture_request(room_id, duration_seconds)
        if error:
            return jsonify({"error": error}), 400

        task = task_manager.start(room_id, duration_seconds)
        return Response(
            stream_with_context(_stream_task_events(task)),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return app


def validate_capture_request(room_id: str, duration_seconds: int) -> str:
    if not room_id:
        return "\u8bf7\u8f93\u5165\u6597\u9c7c\u623f\u95f4\u53f7"
    try:
        room_table_name(room_id)
    except ValueError:
        return "\u623f\u95f4\u53f7\u53ea\u80fd\u5305\u542b\u6570\u5b57\u3001\u5b57\u6bcd\u6216\u4e0b\u5212\u7ebf"
    if duration_seconds <= 0:
        return "\u6293\u53d6\u65f6\u957f\u5fc5\u987b\u5927\u4e8e 0 \u79d2"
    if duration_seconds > MAX_CAPTURE_SECONDS:
        return f"\u5355\u6b21\u6700\u591a\u6293\u53d6 {MAX_CAPTURE_SECONDS} \u79d2"
    return ""


def _stream_task_events(task: CaptureTask):
    next_seq = 0
    yield _sse("snapshot", task.snapshot())

    while True:
        heartbeat = False
        with task.condition:
            if next_seq >= len(task.events) and task.ended_at is None:
                task.condition.wait(TASK_EVENT_TIMEOUT_SECONDS)
                heartbeat = next_seq >= len(task.events) and task.ended_at is None

            pending = task.events[next_seq:]
            next_seq = len(task.events)
            done = task.ended_at is not None and next_seq >= len(task.events)

        if heartbeat:
            yield ": heartbeat\n\n"
        for event in pending:
            yield _sse(event.name, event.payload)
        if done:
            return


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)
