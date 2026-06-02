"""Flask web UI for the Douyu danmu collector."""

from __future__ import annotations

import json
import os
import time

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from .client import DouyuDanmuClient
from .models import MySQLConfig
from .room_status import fetch_room_status
from .storage import MySQLDanmuWriter, room_table_name


DEFAULT_DANMU_HOST = "danmuproxy.douyu.com"
DEFAULT_DANMU_PORT = 8601
MAX_CAPTURE_SECONDS = 3600


def web_mysql_config() -> MySQLConfig:
    return MySQLConfig(
        host=os.getenv("DOUYU_MYSQL_HOST", "localhost"),
        port=int(os.getenv("DOUYU_MYSQL_PORT", "3306")),
        user=os.getenv("DOUYU_MYSQL_USER", "root"),
        password=os.getenv("DOUYU_MYSQL_PASSWORD", os.getenv("MYSQL_PWD", "root")),
        database=os.getenv("DOUYU_MYSQL_DB", "douyu_danmu"),
        per_room_tables=True,
    )


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

    @app.get("/api/capture-stream")
    def capture_stream():
        room_id = str(request.args.get("room_id", "")).strip()
        try:
            duration_seconds = int(request.args.get("duration", "10"))
        except ValueError:
            return jsonify({"error": "\u6293\u53d6\u65f6\u957f\u5fc5\u987b\u662f\u6574\u6570\u79d2"}), 400

        if not room_id:
            return jsonify({"error": "\u8bf7\u8f93\u5165\u6597\u9c7c\u623f\u95f4\u53f7"}), 400
        if duration_seconds <= 0:
            return jsonify({"error": "\u6293\u53d6\u65f6\u957f\u5fc5\u987b\u5927\u4e8e 0 \u79d2"}), 400
        if duration_seconds > MAX_CAPTURE_SECONDS:
            return jsonify({"error": f"\u5355\u6b21\u6700\u591a\u6293\u53d6 {MAX_CAPTURE_SECONDS} \u79d2"}), 400

        return Response(
            stream_with_context(_capture_events(room_id, duration_seconds)),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return app


def _capture_events(room_id: str, duration_seconds: int):
    client = None
    mysql_writer = None
    count = 0
    started_at = time.monotonic()

    try:
        yield _sse("status", {"message": "\u6b63\u5728\u5224\u65ad\u76f4\u64ad\u95f4\u72b6\u6001..."})
        status = fetch_room_status(room_id)

        if not status.is_live:
            yield _sse("error", {
                "error": f"\u8be5\u4e3b\u64ad\u6ca1\u6709\u5f00\u64ad\uff0c\u5f53\u524d\u72b6\u6001\uff1a{status.label}",
                "room_id": status.room_id,
                "room_name": status.room_name,
                "status": status.status,
                "status_label": status.label,
            })
            return

        table_name = room_table_name(status.room_id)
        yield _sse("ready", {
            "message": "\u76f4\u64ad\u95f4\u6b63\u5728\u5f00\u64ad\uff0c\u5f00\u59cb\u6293\u53d6\u5f39\u5e55",
            "room_id": status.room_id,
            "room_name": status.room_name,
            "status": status.status,
            "status_label": status.label,
            "table": table_name,
            "duration": duration_seconds,
        })

        client = DouyuDanmuClient(
            status.room_id,
            host=DEFAULT_DANMU_HOST,
            port=DEFAULT_DANMU_PORT,
            read_timeout=1.0,
        )
        mysql_writer = MySQLDanmuWriter(web_mysql_config())
        client.connect()
        mysql_writer.connect()

        for message in client.messages_for(duration_seconds):
            mysql_writer.write(message)
            count += 1
            yield _sse("message", {"count": count, "message": message.as_dict()})

        elapsed = round(time.monotonic() - started_at, 1)
        yield _sse("done", {
            "message": "\u6293\u53d6\u5b8c\u6210",
            "room_id": status.room_id,
            "room_name": status.room_name,
            "status": status.status,
            "status_label": status.label,
            "table": table_name,
            "count": count,
            "elapsed": elapsed,
        })
    except Exception as exc:
        yield _sse("error", {"error": f"\u6293\u53d6\u5931\u8d25: {exc}"})
    finally:
        if client is not None:
            client.close()
        if mysql_writer is not None:
            mysql_writer.close()


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)
