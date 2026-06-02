# Douyu Danmu Collector

A command-line Douyu live danmu collector. It connects to Douyu's barrage TCP
service, joins a room group, keeps the connection alive, and captures `chatmsg`
messages.

Use it responsibly and follow Douyu's platform rules and applicable laws.

## Basic Usage

Run from the project root:

```powershell
cd "D:\Project J data\test_project"
```

Collect danmu from a room:

```powershell
python -m src.douyu_danmu 93589 --host danmuproxy.douyu.com --port 8601
```

Collect 30 messages and save them as JSON Lines:

```powershell
python -m src.douyu_danmu 93589 --limit 30 --output douyu_93589.jsonl --host danmuproxy.douyu.com --port 8601
```

Print JSON Lines to the terminal too:

```powershell
python -m src.douyu_danmu 93589 --limit 30 --json --output douyu_93589.jsonl --host danmuproxy.douyu.com --port 8601
```


## Web UI

Start the local web app:

```powershell
python -m src.web_app
```

Open:

```text
http://127.0.0.1:5000
```

The page lets you enter a Douyu room id and a capture duration, then streams danmu to the browser in real time. Each new capture clears the current panel first. The backend uses `danmuproxy.douyu.com:8601`.

Captured messages are saved to MySQL by room. For room `4767111`, the table name is `danmu_room_4767111`. Multiple captures of the same room append to the same table. Query messages in time order with:

```sql
SELECT * FROM danmu_room_4767111 ORDER BY received_at ASC;
```
## MySQL

The recommended database/table schema is:

```sql
CREATE DATABASE IF NOT EXISTS douyu_danmu
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE douyu_danmu;

CREATE TABLE IF NOT EXISTS danmu_messages (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  room_id VARCHAR(32) NOT NULL,
  nickname VARCHAR(255) NOT NULL,
  text TEXT NOT NULL,
  user_id VARCHAR(64) DEFAULT '',
  level VARCHAR(32) DEFAULT '',
  raw_type VARCHAR(32) DEFAULT 'chatmsg',
  received_at DATETIME NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (id),
  KEY idx_room_received_at (room_id, received_at),
  KEY idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

Save messages to MySQL:

```powershell
python -m src.douyu_danmu 93589 --limit 30 --mysql --mysql-user douyu_user --mysql-password "your_password" --mysql-db douyu_danmu --host danmuproxy.douyu.com --port 8601

Per-room tables from CLI:

```powershell
python -m src.douyu_danmu 93589 --limit 30 --mysql --mysql-per-room --mysql-user douyu_user --mysql-password "your_password" --mysql-db douyu_danmu --host danmuproxy.douyu.com --port 8601
```
```

To avoid putting the password in command history:

```powershell
$env:DOUYU_MYSQL_PASSWORD="your_password"
python -m src.douyu_danmu 93589 --limit 30 --mysql --mysql-user douyu_user --mysql-db douyu_danmu --host danmuproxy.douyu.com --port 8601
```

You can save to both file and MySQL at the same time:

```powershell
python -m src.douyu_danmu 93589 --limit 30 --output douyu_93589.jsonl --mysql --mysql-user douyu_user --mysql-password "your_password" --host danmuproxy.douyu.com --port 8601
```

## Output Fields

Each message contains:

- `room_id`
- `nickname`
- `text`
- `user_id`
- `level`
- `raw_type`
- `received_at`

## Tests

```powershell
python -m unittest discover -s tests
```

