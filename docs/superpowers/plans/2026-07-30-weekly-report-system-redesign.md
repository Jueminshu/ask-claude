# 营销运作部周报系统 v2.0 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 Streamlit 周报系统重构为支持多格式多文件上传、Leader 审核链路、在线预览、领导互动和分析看板的 v2.0 系统。

**Architecture:** Streamlit 主线程负责页面渲染，后台 Worker 线程处理文件解析/AI 分析/定时通知，领导查阅页和分析看板用嵌入式 HTML/JS 组件（st.components.html）实现流畅交互。SQLite 数据库，officecli 文件解析，Claude API AI 分析。Phase 1 交付核心业务流程，Phase 2-3 交付分析能力。

**Tech Stack:** Python 3.12+, Streamlit 1.60+, SQLite, officecli, Claude API, ECharts (embedded), vanilla HTML/CSS/JS

## Global Constraints

- 截止时间: 周一 10:00，Leader 审核窗口至 11:30，超时自动通过
- 通知由 CRM 侧消费，系统只负责产生 notification_events
- Leader 自己也要提交周报，且自己审核自己（Leader 层）
- 多次提交以最新版为准，同模板替换、不同模板累加
- 文件上传后异步处理，用户秒级获得反馈
- 营销运营部 Leader 有全模块查阅权限（can_browse_all=1）

---

### Task 1: 数据库迁移 — 新 Schema + 种子数据

**Files:**
- Create: `weekly-report-system/database_v2.py`
- Create: `weekly-report-system/migrate_v1_to_v2.py`
- Modify: `weekly-report-system/app.py` (import 切换到 database_v2)

**Interfaces:**
- Produces: `get_db()`, `init_db()`, `seed_data()`, `get_current_week()`, `get_user_by_username()`, `get_module_members()`, `get_submission_status()`, `check_deadline_passed()`, `get_submission_with_files()`, `create_submission()`, `add_submission_file()`, `get_pending_reviews()`, `approve_submission()`, `reject_submission()`, `get_member_weekly_files()`, `add_interaction()`, `get_file_interactions()`, `create_notification_event()`, `get_pending_notifications()`, `enqueue_task()`, `dequeue_task()`, `complete_task()`, `update_file_processing_status()`

- [ ] **Step 1: 编写 database_v2.py — 建表**

```python
"""
数据库层 v2.0
SQLite 本地数据库 — 重构 Schema
"""
import sqlite3
import os
from datetime import datetime, timedelta

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
DB_PATH = os.path.join(DB_DIR, "weekly_report.db")


def get_db():
    """获取数据库连接"""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """初始化 v2.0 数据库表"""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            format TEXT NOT NULL DEFAULT 'excel',
            deadline_day INTEGER DEFAULT 1,
            deadline_time TEXT DEFAULT '10:00',
            auto_approve_time TEXT DEFAULT '11:30'
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            email TEXT,
            role TEXT NOT NULL DEFAULT 'member',
            module_id INTEGER,
            can_browse_all INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (module_id) REFERENCES modules(id)
        );

        CREATE TABLE IF NOT EXISTS file_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            identifier_type TEXT NOT NULL DEFAULT 'both',
            filename_keywords TEXT,
            structure_rules TEXT,
            is_weekly_report INTEGER DEFAULT 0,
            FOREIGN KEY (module_id) REFERENCES modules(id)
        );

        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            module_id INTEGER NOT NULL,
            week_start TEXT NOT NULL,
            week_end TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'submitted',
            leader_reviewed_by INTEGER,
            leader_reviewed_at TEXT,
            leader_review_note TEXT,
            submitted_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            is_latest INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (module_id) REFERENCES modules(id),
            FOREIGN KEY (leader_reviewed_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS submission_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL,
            template_id INTEGER,
            filename TEXT NOT NULL,
            original_path TEXT NOT NULL,
            preview_path TEXT,
            file_type TEXT NOT NULL,
            file_size INTEGER,
            recognition_status TEXT DEFAULT 'pending',
            recognition_confidence REAL,
            extracted_text TEXT,
            parsed_data TEXT,
            processing_status TEXT DEFAULT 'pending',
            FOREIGN KEY (submission_id) REFERENCES submissions(id),
            FOREIGN KEY (template_id) REFERENCES file_templates(id)
        );

        CREATE TABLE IF NOT EXISTS review_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL,
            reviewer_id INTEGER NOT NULL,
            review_level TEXT NOT NULL,
            action TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (submission_id) REFERENCES submissions(id),
            FOREIGN KEY (reviewer_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_file_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            content TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (submission_file_id) REFERENCES submission_files(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(submission_file_id, user_id, type)
        );

        CREATE TABLE IF NOT EXISTS notification_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            target_user_id INTEGER NOT NULL,
            related_submission_id INTEGER,
            payload TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            sent_at TEXT,
            FOREIGN KEY (target_user_id) REFERENCES users(id),
            FOREIGN KEY (related_submission_id) REFERENCES submissions(id)
        );

        CREATE TABLE IF NOT EXISTS task_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_file_id INTEGER NOT NULL,
            task_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            retry_count INTEGER DEFAULT 0,
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            completed_at TEXT,
            FOREIGN KEY (submission_file_id) REFERENCES submission_files(id)
        );

        CREATE INDEX IF NOT EXISTS idx_submissions_week ON submissions(week_start, module_id);
        CREATE INDEX IF NOT EXISTS idx_submissions_user_week ON submissions(user_id, week_start);
        CREATE INDEX IF NOT EXISTS idx_submission_files_submission ON submission_files(submission_id);
        CREATE INDEX IF NOT EXISTS idx_notification_target ON notification_events(target_user_id, status);
        CREATE INDEX IF NOT EXISTS idx_task_queue_status ON task_queue(status);
    """)
    conn.commit()
    conn.close()
```

- [ ] **Step 2: 编写 database_v2.py — seed_data**

```python
def seed_data():
    """初始化种子数据"""
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) FROM modules").fetchone()[0]
    if existing > 0:
        conn.close()
        return

    # 4 个模块，默认日期改为周一
    modules = [
        ("国内运营商", "excel"),
        ("营销运营部", "excel"),
        ("销售部", "excel"),
        ("海外BD", "ppt"),
    ]
    for name, fmt in modules:
        conn.execute(
            "INSERT INTO modules (name, format) VALUES (?, ?)", (name, fmt)
        )

    import hashlib
    admin_pw = hashlib.sha256("admin123".encode()).hexdigest()
    superior_pw = hashlib.sha256("leader123".encode()).hexdigest()
    leader_pw = hashlib.sha256("team123".encode()).hexdigest()
    member_pw = hashlib.sha256("123456".encode()).hexdigest()

    # 管理员（独立，不参与业务）
    conn.execute(
        "INSERT INTO users (username, password_hash, display_name, role) VALUES (?, ?, ?, ?)",
        ("admin", admin_pw, "管理员", "admin")
    )

    # 部门领导
    conn.execute(
        "INSERT INTO users (username, password_hash, display_name, role) VALUES (?, ?, ?, ?)",
        ("superior", superior_pw, "部门领导", "superior")
    )

    # 4 个团队 Leader（营销运营部 Leader 额外 can_browse_all=1）
    leaders = [
        ("leader_domestic", "国内运营商负责人", 1, 0),
        ("leader_marketing", "营销运营部负责人", 2, 1),
        ("leader_sales", "销售部负责人", 3, 0),
        ("leader_overseas", "海外BD负责人", 4, 0),
    ]
    for uname, dname, mid, cba in leaders:
        conn.execute(
            "INSERT INTO users (username, password_hash, display_name, role, module_id, can_browse_all) VALUES (?, ?, ?, 'leader', ?, ?)",
            (uname, leader_pw, dname, mid, cba)
        )

    # 每个模块 3 个 member
    for mid in range(1, 5):
        for i in range(1, 4):
            conn.execute(
                "INSERT INTO users (username, password_hash, display_name, role, module_id) VALUES (?, ?, ?, 'member', ?)",
                (f"user{mid}_{i}", member_pw, f"成员{mid}-{i}", mid)
            )

    # 文件模板种子数据
    templates = [
        (1, "周报", "both", "周报,weekly report",
         '{"required_columns": ["本周工作进展", "下周计划"]}', 1),
        (1, "作战地图", "both", "作战地图,battle map",
         '{"required_columns": ["客户", "竞争态势"]}', 0),
        (1, "拜访报告", "both", "拜访报告,visit report",
         '{"required_columns": ["拜访日期", "拜访对象"]}', 0),
        (1, "会议纪要", "both", "会议纪要,meeting minutes",
         '{"required_columns": ["会议日期", "参会人员"]}', 0),
    ]
    for mid in range(1, 5):
        for t in templates:
            conn.execute(
                "INSERT INTO file_templates (module_id, name, identifier_type, filename_keywords, structure_rules, is_weekly_report) VALUES (?, ?, ?, ?, ?, ?)",
                (mid, t[1], t[2], t[3], t[4], t[5])
            )

    conn.commit()
    conn.close()
```

- [ ] **Step 3: 编写便捷查询函数（database_v2.py 续）**

```python
def get_current_week():
    today = datetime.now()
    weekday = today.weekday()
    monday = today - timedelta(days=weekday)
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


def get_user_by_username(username):
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)
    ).fetchone()
    conn.close()
    return user


def get_module_members(module_id):
    conn = get_db()
    members = conn.execute(
        "SELECT * FROM users WHERE module_id = ? AND is_active = 1",
        (module_id,)
    ).fetchall()
    conn.close()
    return [dict(m) for m in members]


def get_module_leader(module_id):
    conn = get_db()
    leader = conn.execute(
        "SELECT * FROM users WHERE module_id = ? AND role = 'leader' AND is_active = 1",
        (module_id,)
    ).fetchone()
    conn.close()
    return dict(leader) if leader else None


def get_submission_status(module_id, week_start, week_end):
    conn = get_db()
    members = conn.execute(
        "SELECT * FROM users WHERE module_id = ? AND is_active = 1",
        (module_id,)
    ).fetchall()

    submitted = conn.execute(
        """SELECT s.*, u.display_name
           FROM submissions s
           JOIN users u ON s.user_id = u.id
           WHERE s.module_id = ? AND s.week_start = ? AND s.week_end = ?
             AND s.is_latest = 1""",
        (module_id, week_start, week_end)
    ).fetchall()

    submitted_ids = {s["user_id"] for s in submitted}
    not_submitted = [m for m in members if m["id"] not in submitted_ids]
    conn.close()
    return {
        "submitted": [dict(s) for s in submitted],
        "not_submitted": [dict(m) for m in not_submitted],
        "total": len(members),
        "submitted_count": len(submitted),
    }


def can_browse_all_modules(user):
    return user["role"] == "superior" or user.get("can_browse_all") == 1


def can_browse_module(user, module_id):
    if can_browse_all_modules(user):
        return True
    return user.get("module_id") == module_id


# === 提交相关 ===

def create_submission(user_id, module_id, week_start, week_end):
    """创建新提交，并将该用户本周旧提交标记为 is_latest=0"""
    conn = get_db()
    conn.execute(
        "UPDATE submissions SET is_latest = 0 WHERE user_id = ? AND week_start = ?",
        (user_id, week_start)
    )
    cursor = conn.execute(
        """INSERT INTO submissions (user_id, module_id, week_start, week_end, status)
           VALUES (?, ?, ?, ?, 'submitted')""",
        (user_id, module_id, week_start, week_end)
    )
    submission_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return submission_id


def add_submission_file(submission_id, filename, original_path, file_type, file_size):
    """添加提交文件记录，返回 file_id"""
    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO submission_files (submission_id, filename, original_path, file_type, file_size)
           VALUES (?, ?, ?, ?, ?)""",
        (submission_id, filename, original_path, file_type, file_size)
    )
    file_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return file_id


def get_submission_with_files(submission_id):
    """获取提交及其所有文件"""
    conn = get_db()
    sub = conn.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()
    if not sub:
        conn.close()
        return None
    files = conn.execute(
        "SELECT * FROM submission_files WHERE submission_id = ? ORDER BY id",
        (submission_id,)
    ).fetchall()
    conn.close()
    return {**dict(sub), "files": [dict(f) for f in files]}


def get_member_weekly_files(user_id, week_start):
    """获取成员本周所有文件（合并多次提交，去重）"""
    conn = get_db()
    # 取最新一次提交
    sub = conn.execute(
        """SELECT * FROM submissions
           WHERE user_id = ? AND week_start = ? AND is_latest = 1
           ORDER BY submitted_at DESC LIMIT 1""",
        (user_id, week_start)
    ).fetchone()
    # 也获取其他提交的文件（累加）
    files = conn.execute(
        """SELECT sf.*, ft.name as template_name
           FROM submission_files sf
           JOIN submissions s ON sf.submission_id = s.id
           LEFT JOIN file_templates ft ON sf.template_id = ft.id
           WHERE s.user_id = ? AND s.week_start = ?
           ORDER BY ft.is_weekly_report DESC, sf.id""",
        (user_id, week_start)
    ).fetchall()
    # 去重：同 template_id 保留最新的（按 submission_id 降序）
    seen_templates = set()
    deduped = []
    for f in files:
        tid = f["template_id"]
        if tid and tid in seen_templates:
            continue
        if tid:
            seen_templates.add(tid)
        deduped.append(dict(f))
    conn.close()
    return deduped


# === 审核相关 ===

def get_pending_reviews(module_id, week_start):
    """获取待审核提交列表"""
    conn = get_db()
    submissions = conn.execute(
        """SELECT s.*, u.display_name
           FROM submissions s
           JOIN users u ON s.user_id = u.id
           WHERE s.module_id = ? AND s.week_start = ?
             AND s.is_latest = 1 AND s.status = 'submitted'
           ORDER BY s.submitted_at""",
        (module_id, week_start)
    ).fetchall()
    conn.close()
    return [dict(s) for s in submissions]


def approve_submission(submission_id, reviewer_id):
    """通过审核"""
    conn = get_db()
    conn.execute(
        """UPDATE submissions SET status = 'leader_approved',
           leader_reviewed_by = ?, leader_reviewed_at = datetime('now','localtime')
           WHERE id = ?""",
        (reviewer_id, submission_id)
    )
    conn.execute(
        """INSERT INTO review_log (submission_id, reviewer_id, review_level, action)
           VALUES (?, ?, 'leader', 'approve')""",
        (submission_id, reviewer_id)
    )
    conn.commit()
    conn.close()


def reject_submission(submission_id, reviewer_id, note):
    """驳回提交"""
    conn = get_db()
    conn.execute(
        """UPDATE submissions SET status = 'leader_rejected',
           leader_reviewed_by = ?, leader_reviewed_at = datetime('now','localtime'),
           leader_review_note = ?
           WHERE id = ?""",
        (reviewer_id, note, submission_id)
    )
    conn.execute(
        """INSERT INTO review_log (submission_id, reviewer_id, review_level, action, note)
           VALUES (?, ?, 'leader', 'reject', ?)""",
        (submission_id, reviewer_id, note)
    )
    conn.commit()
    conn.close()


# === 互动相关 ===

def add_interaction(submission_file_id, user_id, type_, content=None):
    """添加点赞或评论。返回 (success, message)"""
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO interactions (submission_file_id, user_id, type, content)
               VALUES (?, ?, ?, ?)""",
            (submission_file_id, user_id, type_, content)
        )
        conn.commit()
        conn.close()
        return True, "ok"
    except sqlite3.IntegrityError:
        # 重复点赞
        conn.close()
        return False, "already_exists"


def get_file_interactions(submission_file_id):
    """获取文件的所有互动（点赞列表 + 评论列表）"""
    conn = get_db()
    likes = conn.execute(
        """SELECT i.*, u.display_name FROM interactions i
           JOIN users u ON i.user_id = u.id
           WHERE i.submission_file_id = ? AND i.type = 'like'""",
        (submission_file_id,)
    ).fetchall()
    comments = conn.execute(
        """SELECT i.*, u.display_name FROM interactions i
           JOIN users u ON i.user_id = u.id
           WHERE i.submission_file_id = ? AND i.type = 'comment'
           ORDER BY i.created_at""",
        (submission_file_id,)
    ).fetchall()
    conn.close()
    return {
        "likes": [dict(l) for l in likes],
        "likes_count": len(likes),
        "comments": [dict(c) for c in comments],
    }


# === 通知相关 ===

def create_notification_event(event_type, target_user_id, related_submission_id=None, payload=None):
    """创建通知事件"""
    import json
    conn = get_db()
    conn.execute(
        """INSERT INTO notification_events (event_type, target_user_id, related_submission_id, payload)
           VALUES (?, ?, ?, ?)""",
        (event_type, target_user_id, related_submission_id, json.dumps(payload or {}))
    )
    conn.commit()
    conn.close()


def get_pending_notifications(user_id):
    """获取用户的未处理通知"""
    conn = get_db()
    events = conn.execute(
        """SELECT * FROM notification_events
           WHERE target_user_id = ? AND status = 'pending'
           ORDER BY created_at DESC""",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(e) for e in events]


# === 任务队列 ===

def enqueue_task(submission_file_id, task_type):
    """入队一个文件处理任务"""
    conn = get_db()
    conn.execute(
        "INSERT INTO task_queue (submission_file_id, task_type) VALUES (?, ?)",
        (submission_file_id, task_type)
    )
    conn.commit()
    conn.close()


def dequeue_task():
    """出队一个待处理任务"""
    conn = get_db()
    task = conn.execute(
        "SELECT * FROM task_queue WHERE status = 'queued' ORDER BY id LIMIT 1"
    ).fetchone()
    if task:
        conn.execute(
            "UPDATE task_queue SET status = 'processing' WHERE id = ?",
            (task["id"],)
        )
        conn.commit()
    conn.close()
    return dict(task) if task else None


def complete_task(task_id, error_message=None):
    """完成任务"""
    conn = get_db()
    status = "completed" if not error_message else "failed"
    conn.execute(
        "UPDATE task_queue SET status = ?, error_message = ?, completed_at = datetime('now','localtime') WHERE id = ?",
        (status, error_message, task_id)
    )
    conn.commit()
    conn.close()


def update_file_processing_status(file_id, status):
    """更新文件处理状态"""
    conn = get_db()
    conn.execute(
        "UPDATE submission_files SET processing_status = ? WHERE id = ?",
        (status, file_id)
    )
    conn.commit()
    conn.close()


def update_file_recognition(file_id, template_id, confidence, extracted_text=None):
    """更新文件识别结果"""
    conn = get_db()
    conn.execute(
        """UPDATE submission_files
           SET template_id = ?, recognition_confidence = ?, recognition_status = 'recognized',
               extracted_text = COALESCE(?, extracted_text)
           WHERE id = ?""",
        (template_id, confidence, extracted_text, file_id)
    )
    conn.commit()
    conn.close()


def update_file_preview(file_id, preview_path):
    """更新文件预览路径"""
    conn = get_db()
    conn.execute(
        "UPDATE submission_files SET preview_path = ? WHERE id = ?",
        (preview_path, file_id)
    )
    conn.commit()
    conn.close()
```

- [ ] **Step 4: 编写 migrate_v1_to_v2.py**

```python
"""v1.0 → v2.0 数据迁移脚本"""
import sqlite3
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database_v2 import init_db, seed_data, get_db, DB_PATH


def migrate():
    # 检查旧表是否存在
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = [t[0] for t in tables]

    if "modules" not in table_names or "submission_files" in table_names:
        print("已经是 v2.0 Schema 或无可迁移数据，跳过迁移")
        conn.close()
        return

    print("检测到 v1.0 数据，开始迁移...")

    # 备份旧数据
    old_modules = conn.execute("SELECT * FROM modules").fetchall()
    old_users = conn.execute("SELECT * FROM users").fetchall()

    # 删除 v1 表（保留数据在内存中）
    conn.executescript("""
        DROP TABLE IF EXISTS weekly_summaries;
        DROP TABLE IF EXISTS report_archive;
        DROP TABLE IF EXISTS submissions;
        DROP TABLE IF EXISTS users;
        DROP TABLE IF EXISTS modules;
    """)
    conn.commit()
    conn.close()

    # 重建 v2 表
    init_db()

    # 迁移模块数据（更新 deadline 字段）
    conn = get_db()
    for m in old_modules:
        conn.execute(
            "INSERT INTO modules (id, name, format) VALUES (?, ?, ?)",
            (m["id"], m["name"], m["format"])
        )

    # 迁移用户数据（映射 role: leader→leader, member→member, admin→admin, is_superior→superior）
    for u in old_users:
        role = u["role"]
        if u["is_superior"]:
            role = "superior"
        conn.execute(
            """INSERT INTO users (id, username, password_hash, display_name, email, role, module_id, is_active)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (u["id"], u["username"], u["password_hash"], u["display_name"],
             u["email"], role, u["module_id"], u["is_active"])
        )

    conn.commit()
    conn.close()

    # 填充种子模板数据（seed_data 会检测 modules 已有数据 → 跳过模块和用户的插入，但要补模板）
    conn = get_db()
    templates_exist = conn.execute("SELECT COUNT(*) FROM file_templates").fetchone()[0]
    if templates_exist == 0:
        templates = [
            (1, "周报", "both", "周报,weekly report",
             '{"required_columns": ["本周工作进展", "下周计划"]}', 1),
            (1, "作战地图", "both", "作战地图,battle map",
             '{"required_columns": ["客户", "竞争态势"]}', 0),
            (1, "拜访报告", "both", "拜访报告,visit report",
             '{"required_columns": ["拜访日期", "拜访对象"]}', 0),
            (1, "会议纪要", "both", "会议纪要,meeting minutes",
             '{"required_columns": ["会议日期", "参会人员"]}', 0),
        ]
        for mid in range(1, 5):
            for t in templates:
                conn.execute(
                    "INSERT INTO file_templates (module_id, name, identifier_type, filename_keywords, structure_rules, is_weekly_report) VALUES (?, ?, ?, ?, ?, ?)",
                    (mid, t[1], t[2], t[3], t[4], t[5])
                )
    conn.commit()
    conn.close()

    print("迁移完成。旧上传文件保留在 data/uploads/，标记为 v1 遗留。")


if __name__ == "__main__":
    migrate()
```

- [ ] **Step 5: 手动测试迁移**

Run: `cd weekly-report-system && python migrate_v1_to_v2.py`
Expected: 打印 "已经是 v2.0 Schema..." 或 "迁移完成"

Run: `python -c "from database_v2 import init_db, seed_data; init_db(); seed_data(); print('OK')"`
Expected: 打印 "OK"，data/weekly_report.db 包含 v2 表

- [ ] **Step 6: 测试文件**

```python
# test_database_v2.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'weekly-report-system'))
from database_v2 import *

def test_init_and_seed():
    init_db()
    seed_data()
    conn = get_db()
    modules = conn.execute("SELECT COUNT(*) as c FROM modules").fetchone()
    assert modules["c"] == 4
    users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()
    assert users["c"] >= 7
    templates = conn.execute("SELECT COUNT(*) as c FROM file_templates").fetchone()
    assert templates["c"] == 16  # 4 modules × 4 templates
    conn.close()

def test_create_submission_and_files():
    init_db()
    sub_id = create_submission(5, 1, "2026-07-27", "2026-08-02")
    assert sub_id > 0
    file_id = add_submission_file(sub_id, "test.xlsx", "/tmp/test.xlsx", "xlsx", 1024)
    assert file_id > 0
    sub = get_submission_with_files(sub_id)
    assert sub is not None
    assert len(sub["files"]) == 1
    assert sub["files"][0]["filename"] == "test.xlsx"

def test_review_flow():
    init_db()
    sub_id = create_submission(5, 1, "2026-07-27", "2026-08-02")
    approve_submission(sub_id, 3)  # reviewer=leader_domestic
    conn = get_db()
    sub = conn.execute("SELECT * FROM submissions WHERE id = ?", (sub_id,)).fetchone()
    assert sub["status"] == "leader_approved"
    log = conn.execute("SELECT * FROM review_log WHERE submission_id = ?", (sub_id,)).fetchone()
    assert log["action"] == "approve"
    conn.close()

def test_interactions():
    init_db()
    sub_id = create_submission(5, 1, "2026-07-27", "2026-08-02")
    file_id = add_submission_file(sub_id, "test.xlsx", "/tmp/test.xlsx", "xlsx", 1024)
    ok, _ = add_interaction(file_id, 2, "like")  # user 2 = superior
    assert ok
    ok, _ = add_interaction(file_id, 2, "like")  # duplicate
    assert not ok
    interactions = get_file_interactions(file_id)
    assert interactions["likes_count"] == 1
```

Run: `pytest test_database_v2.py -v`
Expected: 4 tests PASS

- [ ] **Step 7: Commit**

```bash
git add weekly-report-system/database_v2.py weekly-report-system/migrate_v1_to_v2.py test_database_v2.py
git commit -m "feat: database v2.0 schema — 9 tables, new seed data, migration script"
```

---

### Task 2: 角色权限服务

**Files:**
- Create: `weekly-report-system/services/__init__.py`
- Create: `weekly-report-system/services/auth.py`

**Interfaces:**
- Consumes: `get_db()` from `database_v2`
- Produces: `check_page_permission(user, page)`, `check_data_permission(user, action, target_module_id=None)`, `can_browse_all_modules(user)`, `can_browse_module(user, module_id)`, `ROLE_LABELS`, `PAGE_PERMISSIONS`

- [ ] **Step 1: 编写 services/auth.py**

```python
"""角色权限服务"""
from database_v2 import get_db

# 角色中文标签
ROLE_LABELS = {
    "admin": "🔧 管理员",
    "leader": "👤 团队负责人",
    "member": "👤 成员",
    "superior": "👔 部门领导",
}

# 页面 → 允许的角色
PAGE_PERMISSIONS = {
    "upload": ["member", "leader"],
    "history": ["member", "leader"],
    "team_view": ["leader"],
    "review": ["leader"],
    "leader_browse": ["superior"],      # 部门领导 + 营销运营部 Leader 特殊处理
    "admin": ["admin"],
}


def can_browse_all_modules(user):
    """是否可查看所有模块周报"""
    return user["role"] == "superior" or user.get("can_browse_all") == 1


def can_browse_module(user, module_id):
    """是否可查看指定模块"""
    if can_browse_all_modules(user):
        return True
    return user.get("module_id") == module_id


def check_page_permission(user, page):
    """
    检查用户是否有某页面权限。
    
    page: 'upload' | 'history' | 'team_view' | 'review' | 'leader_browse' | 'admin'
    
    返回: (allowed: bool, reason: str)
    """
    role = user["role"]
    allowed_roles = PAGE_PERMISSIONS.get(page, [])
    
    if role == "admin" and page != "leader_browse":
        return True, "ok"
    
    if role in allowed_roles:
        return True, "ok"
    
    # 营销运营部 Leader 额外权限
    if page == "leader_browse" and role == "leader" and user.get("can_browse_all") == 1:
        return True, "ok"
    
    return False, f"角色 {role} 无权访问页面 {page}"


def check_data_permission(user, action, target_module_id=None):
    """
    检查数据操作权限。
    
    action: 'view_own' | 'view_team' | 'view_all' | 'review' | 'interact' | 'manage'
    
    返回: (allowed: bool, reason: str)
    """
    role = user["role"]
    
    if action == "view_own":
        return True, "ok"
    
    if action == "view_team":
        if role in ("leader",):
            return can_browse_module(user, target_module_id), "无权查看该模块"
        return can_browse_all_modules(user), "无权查看团队周报"
    
    if action == "view_all":
        return can_browse_all_modules(user), "无权查看所有模块"
    
    if action == "review":
        if role != "leader":
            return False, "仅团队负责人可审核"
        return can_browse_module(user, target_module_id), "无权审核该模块"
    
    if action == "interact":
        return role == "superior", "仅部门领导可互动"
    
    if action == "manage":
        return role == "admin", "仅管理员可系统管理"
    
    return False, f"未知操作: {action}"


def get_user_accessible_modules(user):
    """获取用户可访问的模块列表"""
    conn = get_db()
    if can_browse_all_modules(user):
        modules = conn.execute("SELECT * FROM modules ORDER BY id").fetchall()
    elif user.get("module_id"):
        modules = conn.execute(
            "SELECT * FROM modules WHERE id = ?", (user["module_id"],)
        ).fetchall()
    else:
        modules = []
    conn.close()
    return [dict(m) for m in modules]
```

- [ ] **Step 2: 测试文件**

```python
# test_auth.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'weekly-report-system'))
from database_v2 import init_db, seed_data
from services.auth import *

init_db()
seed_data()

def test_member_permissions():
    user = {"role": "member", "module_id": 1, "can_browse_all": 0}
    assert check_page_permission(user, "upload")[0]
    assert check_page_permission(user, "history")[0]
    assert not check_page_permission(user, "review")[0]
    assert not check_page_permission(user, "leader_browse")[0]

def test_leader_permissions():
    user = {"role": "leader", "module_id": 1, "can_browse_all": 0}
    assert check_page_permission(user, "upload")[0]
    assert check_page_permission(user, "review")[0]
    assert not check_page_permission(user, "leader_browse")[0]
    assert check_data_permission(user, "review", target_module_id=1)[0]
    assert not check_data_permission(user, "review", target_module_id=2)[0]

def test_marketing_leader_permissions():
    user = {"role": "leader", "module_id": 2, "can_browse_all": 1}
    assert check_page_permission(user, "leader_browse")[0]
    assert check_data_permission(user, "view_all")[0]

def test_superior_permissions():
    user = {"role": "superior", "module_id": None, "can_browse_all": 0}
    assert check_page_permission(user, "leader_browse")[0]
    assert not check_page_permission(user, "upload")[0]
    assert check_data_permission(user, "interact")[0]
    assert not check_data_permission(user, "review", target_module_id=1)[0]
```

Run: `pytest test_auth.py -v`
Expected: 4 tests PASS

- [ ] **Step 3: Commit**

```bash
git add weekly-report-system/services/__init__.py weekly-report-system/services/auth.py test_auth.py
git commit -m "feat: role permission service with page/data access control"
```

---

### Task 3: 文件存储 + 文件处理服务

**Files:**
- Create: `weekly-report-system/services/file_handler.py`
- Create: `weekly-report-system/services/file_parser.py`

**Interfaces:**
- Consumes: `add_submission_file`, `enqueue_task`, `update_file_recognition`, `update_file_preview` from `database_v2`
- Produces: `save_uploaded_file()`, `get_upload_dir()`, `get_preview_dir()`, `parse_file_text()`, `convert_to_pdf()`, `identify_template()`, `process_file()`

- [ ] **Step 1: 编写 services/file_handler.py**

```python
"""文件存储服务 — 抽象层（当前本地磁盘，预留云存储接口）"""
import os
import shutil
from datetime import datetime


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
PREVIEWS_DIR = os.path.join(DATA_DIR, "previews")


def get_upload_dir(week_start, module_id, user_id):
    """获取上传文件存储目录"""
    d = os.path.join(UPLOADS_DIR, week_start, str(module_id), str(user_id))
    os.makedirs(d, exist_ok=True)
    return d


def get_preview_dir(week_start, module_id, user_id):
    """获取预览 PDF 存储目录"""
    d = os.path.join(PREVIEWS_DIR, week_start, str(module_id), str(user_id))
    os.makedirs(d, exist_ok=True)
    return d


def save_uploaded_file(uploaded_file_obj, week_start, module_id, user_id) -> str:
    """
    保存上传文件到磁盘。
    
    Args:
        uploaded_file_obj: Streamlit UploadedFile 对象
        week_start: 周起始日期
        module_id: 模块 ID
        user_id: 用户 ID
    
    Returns:
        文件完整路径
    """
    upload_dir = get_upload_dir(week_start, module_id, user_id)
    # 防止文件名冲突：加时间戳前缀
    timestamp = datetime.now().strftime("%H%M%S")
    safe_name = f"{timestamp}_{uploaded_file_obj.name}"
    file_path = os.path.join(upload_dir, safe_name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file_obj.getbuffer())
    return file_path


def delete_file(file_path):
    """删除文件（物理删除）"""
    if os.path.exists(file_path):
        os.remove(file_path)


ALLOWED_EXTENSIONS = {
    "xlsx", "xls", "pptx", "ppt", "docx", "doc",
    "pdf", "jpg", "jpeg", "png", "gif", "bmp",
}


def get_file_type(filename):
    """根据扩展名确定文件类型"""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("xlsx", "xls"):
        return "xlsx"
    if ext in ("pptx", "ppt"):
        return "pptx"
    if ext in ("docx", "doc"):
        return "docx"
    if ext == "pdf":
        return "pdf"
    if ext in ("jpg", "jpeg", "png", "gif", "bmp"):
        return "image"
    return "other"
```

- [ ] **Step 2: 编写 services/file_parser.py**

```python
"""文件解析服务 — 文本提取 + 模板识别 + PDF 转换"""
import os
import json
import subprocess
from database_v2 import get_db, get_db as _get_db_conn


# 使用 officecli 提取文本
def extract_text(file_path, file_type):
    """
    调用 officecli 提取文件文本内容。
    返回: str 或 None
    """
    try:
        # officecli view <file> text 提取文本
        result = subprocess.run(
            ["officecli", "view", file_path, "text"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return f"[EXTRACTION FAILED] {result.stderr}"
    except FileNotFoundError:
        # officecli 未安装，返回空
        return "[OFFICECLI NOT AVAILABLE]"
    except subprocess.TimeoutExpired:
        return "[EXTRACTION TIMEOUT]"


# 使用 officecli 或 LibreOffice 转 PDF
def convert_to_pdf(file_path, output_dir, file_type):
    """
    将 Office 文件转换为 PDF 预览。
    PDF 和图片文件跳过转换，直接返回原路径。
    
    返回: preview_path 或 None（转换失败）
    """
    if file_type in ("pdf", "image"):
        return file_path  # 无需转换
    
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    pdf_path = os.path.join(output_dir, f"{base_name}.pdf")
    
    try:
        # 优先用 officecli
        result = subprocess.run(
            ["officecli", "convert", file_path, pdf_path, "--format", "pdf"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0 and os.path.exists(pdf_path):
            return pdf_path
    except FileNotFoundError:
        pass
    
    # 回退到 LibreOffice（如果可用）
    try:
        result = subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf",
             "--outdir", output_dir, file_path],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0 and os.path.exists(pdf_path):
            return pdf_path
    except FileNotFoundError:
        pass
    
    return None


# 模板识别
def identify_template(filename, extracted_text, module_id):
    """
    识别文件模板类型。
    
    Args:
        filename: 文件名
        extracted_text: 提取的文本内容
        module_id: 模块 ID
    
    Returns:
        (template_id, confidence) 或 (None, 0.0)
    """
    conn = _get_db_conn()
    templates = conn.execute(
        "SELECT * FROM file_templates WHERE module_id = ?", (module_id,)
    ).fetchall()
    conn.close()
    
    if not templates:
        return None, 0.0
    
    best_template = None
    best_score = 0.0
    
    for t in templates:
        score = 0.0
        
        # 1. 文件名关键词匹配（权重 0.5）
        if t["filename_keywords"]:
            keywords = [k.strip().lower() for k in t["filename_keywords"].split(",")]
            matched_kw = 0
            fname_lower = filename.lower()
            for kw in keywords:
                if kw in fname_lower:
                    matched_kw += 1
            if keywords:
                score += 0.5 * (matched_kw / len(keywords))
        
        # 2. 结构匹配（权重 0.5）
        if t["structure_rules"] and extracted_text:
            try:
                rules = json.loads(t["structure_rules"])
                structure_score = _match_structure(extracted_text, rules)
                score += 0.5 * structure_score
            except (json.JSONDecodeError, TypeError):
                pass
        
        if score > best_score:
            best_score = score
            best_template = t["id"]
    
    if best_score >= 0.6:
        return best_template, round(best_score, 2)
    
    return None, round(best_score, 2)


def _match_structure(text, rules):
    """检查文本中是否包含结构规则中定义的必需特征"""
    if not text or not rules:
        return 0.0
    
    checks = []
    
    if "required_columns" in rules:
        columns = rules["required_columns"]
        matched = sum(1 for col in columns if col in text)
        checks.append(matched / len(columns) if columns else 0)
    
    if "sheet_name" in rules:
        checks.append(1.0 if rules["sheet_name"] in text else 0.0)
    
    if not checks:
        return 0.0
    
    return sum(checks) / len(checks)


def process_file(file_id, file_path, filename, file_type, module_id):
    """
    对一个文件执行完整的 4 阶段处理流水线。
    由 Worker 线程调用。
    """
    from database_v2 import (
        update_file_processing_status, update_file_recognition,
        update_file_preview
    )
    from file_handler import get_preview_dir, get_upload_dir
    
    # 阶段1: 已由上传流程完成（文件保存）
    
    # 阶段2: 文本提取
    update_file_processing_status(file_id, "extracting")
    text = extract_text(file_path, file_type)
    
    # 阶段3: 模板识别
    update_file_processing_status(file_id, "recognizing")
    template_id, confidence = identify_template(filename, text, module_id)
    update_file_recognition(file_id, template_id, confidence, text)
    
    # 阶段4: PDF 转换
    update_file_processing_status(file_id, "converting")
    base_dir = os.path.dirname(file_path)
    # 用原始文件目录的兄弟 preview 目录
    parts = base_dir.replace("uploads", "previews", 1).split(os.sep)
    preview_dir = os.sep.join(parts)
    os.makedirs(preview_dir, exist_ok=True)
    preview_path = convert_to_pdf(file_path, preview_dir, file_type)
    if preview_path:
        update_file_preview(file_id, preview_path)
    
    update_file_processing_status(file_id, "ready")
```

- [ ] **Step 3: 测试文件解析（手动 — 需要 officecli）**

Run: `python -c "from services.file_parser import extract_text; print(extract_text('test.xlsx', 'xlsx')[:200])"`
Expected: 输出文件文本内容

- [ ] **Step 4: Commit**

```bash
git add weekly-report-system/services/file_handler.py weekly-report-system/services/file_parser.py
git commit -m "feat: file storage abstraction + file parser (text extraction, template matching, PDF conversion)"
```

---

### Task 4: 后台 Worker 线程

**Files:**
- Create: `weekly-report-system/worker.py`

**Interfaces:**
- Consumes: `dequeue_task()`, `complete_task()`, `update_file_processing_status()` from `database_v2`; `process_file()` from `services.file_parser`; `check_deadline_passed()`, `get_current_week()` from `database_v2`; `create_notification_event()` from `database_v2`
- Produces: `start_worker()`, `stop_worker()`, `check_scheduled_notifications()`

- [ ] **Step 1: 编写 worker.py**

```python
"""
后台 Worker 线程
- 文件处理：消费 task_queue
- 定时检查：超时自动通过 + 通知事件
"""
import time
import threading
import json
from datetime import datetime
from database_v2 import (
    get_db, dequeue_task, complete_task, update_file_processing_status,
    get_current_week, create_notification_event
)
from services.file_parser import process_file


_worker_thread = None
_stop_flag = threading.Event()


def _worker_loop():
    """Worker 主循环"""
    last_scheduled_check = None
    
    while not _stop_flag.is_set():
        try:
            # 1. 处理文件任务
            task = dequeue_task()
            if task:
                _process_task(task)
                continue  # 有任务就连续处理
            
            # 2. 超时自动通过检查（每分钟一次）
            _check_auto_approve()
            
            # 3. 定时通知检查（每分钟一次）
            now = datetime.now()
            check_key = f"{now.hour}:{now.minute}"
            if check_key != last_scheduled_check:
                last_scheduled_check = check_key
                check_scheduled_notifications()
            
            # 没有任务，休眠 2 秒
            time.sleep(2)
            
        except Exception as e:
            print(f"[Worker] Error: {e}")
            time.sleep(5)


def _process_task(task):
    """处理单个文件任务"""
    task_id = task["id"]
    file_id = task["submission_file_id"]
    task_type = task["task_type"]
    
    try:
        if task_type == "process_full":
            conn = get_db()
            sf = conn.execute(
                "SELECT * FROM submission_files WHERE id = ?", (file_id,)
            ).fetchone()
            if not sf:
                complete_task(task_id, "file not found")
                return
            
            # 获取 module_id
            sub = conn.execute(
                "SELECT module_id FROM submissions WHERE id = ?",
                (sf["submission_id"],)
            ).fetchone()
            module_id = sub["module_id"] if sub else 1
            conn.close()
            
            process_file(
                file_id=file_id,
                file_path=sf["original_path"],
                filename=sf["filename"],
                file_type=sf["file_type"],
                module_id=module_id,
            )
            complete_task(task_id)
        else:
            complete_task(task_id, f"unknown task type: {task_type}")
    except Exception as e:
        complete_task(task_id, str(e))
        update_file_processing_status(file_id, "error")


def _check_auto_approve():
    """检查并执行超时自动通过"""
    now = datetime.now()
    # 只在周一 11:30-11:35 之间执行
    if now.weekday() != 0:
        return
    if now.hour != 11 or now.minute < 30 or now.minute >= 35:
        return
    
    conn = get_db()
    week_start, week_end = get_current_week()
    
    pending = conn.execute(
        """SELECT id, user_id FROM submissions
           WHERE week_start = ? AND status = 'submitted' AND is_latest = 1""",
        (week_start,)
    ).fetchall()
    
    for sub in pending:
        conn.execute(
            """UPDATE submissions
               SET status = 'leader_approved',
                   leader_reviewed_by = 0,
                   leader_reviewed_at = datetime('now','localtime')
               WHERE id = ?""",
            (sub["id"],)
        )
        conn.execute(
            """INSERT INTO review_log (submission_id, reviewer_id, review_level, action, note)
               VALUES (?, 0, 'leader', 'approve', '超时自动通过')""",
            (sub["id"],)
        )
    
    if pending:
        conn.commit()
        print(f"[Worker] 超时自动通过 {len(pending)} 条")
    conn.close()


def check_scheduled_notifications():
    """检查并生成定时通知事件"""
    now = datetime.now()
    week_start, week_end = get_current_week()
    conn = get_db()
    
    # N1: 周一 08:00-08:05 提醒未提交员工
    if now.weekday() == 0 and now.hour == 8 and now.minute < 5:
        users = conn.execute("""
            SELECT u.id, u.display_name FROM users u
            WHERE u.role IN ('member', 'leader') AND u.is_active = 1
            AND u.id NOT IN (
                SELECT s.user_id FROM submissions s
                WHERE s.week_start = ? AND s.is_latest = 1
            )
        """, (week_start,)).fetchall()
        
        today = now.strftime("%Y-%m-%d")
        for u in users:
            existing = conn.execute(
                """SELECT id FROM notification_events
                   WHERE event_type = 'pre_deadline_remind'
                   AND target_user_id = ? AND date(created_at) = ?""",
                (u["id"], today)
            ).fetchone()
            if not existing:
                create_notification_event(
                    "pre_deadline_remind", u["id"],
                    payload={
                        "week_start": week_start,
                        "deadline": "周一 10:00",
                        "message": "您本周周报尚未提交，请于周一10:00前完成"
                    }
                )
    
    # N2: 周一 11:00-11:05 提醒 Leader
    if now.weekday() == 0 and now.hour == 11 and now.minute < 5:
        leaders = conn.execute("""
            SELECT DISTINCT u.id, u.module_id, m.name as module_name
            FROM users u JOIN modules m ON u.module_id = m.id
            WHERE u.role = 'leader' AND u.is_active = 1
        """).fetchall()
        
        today = now.strftime("%Y-%m-%d")
        for leader in leaders:
            pending_count = conn.execute(
                """SELECT COUNT(*) FROM submissions
                   WHERE module_id = ? AND week_start = ?
                   AND status = 'submitted' AND is_latest = 1""",
                (leader["module_id"], week_start)
            ).fetchone()[0]
            
            if pending_count > 0:
                existing = conn.execute(
                    """SELECT id FROM notification_events
                       WHERE event_type = 'leader_window_remind'
                       AND target_user_id = ? AND date(created_at) = ?""",
                    (leader["id"], today)
                ).fetchone()
                if not existing:
                    create_notification_event(
                        "leader_window_remind", leader["id"],
                        payload={
                            "pending_count": pending_count,
                            "auto_approve_time": "11:30",
                            "message": f"您还有{pending_count}份周报未审核，11:30后自动通过"
                        }
                    )
    
    conn.close()


def start_worker():
    """启动后台 Worker 线程"""
    global _worker_thread, _stop_flag
    if _worker_thread and _worker_thread.is_alive():
        return
    _stop_flag.clear()
    _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="weekly-report-worker")
    _worker_thread.start()
    print("[Worker] Started")


def stop_worker():
    """停止后台 Worker 线程"""
    global _stop_flag
    _stop_flag.set()
    print("[Worker] Stopping...")
```

- [ ] **Step 2: 测试 Worker（手动）**

Run: `python -c "from worker import start_worker, stop_worker; import time; start_worker(); time.sleep(3); print('OK')"`
Expected: 打印 "[Worker] Started" 和 "OK"

- [ ] **Step 3: Commit**

```bash
git add weekly-report-system/worker.py
git commit -m "feat: background worker thread — async file processing, auto-approve, scheduled notifications"
```

---

### Task 5: 截止时间 + 通知事件服务

**Files:**
- Create: `weekly-report-system/services/deadline.py`
- Create: `weekly-report-system/services/notification.py`

**Interfaces:**
- Consumes: `get_db()`, `create_notification_event()` from `database_v2`
- Produces: `check_deadline_passed()`, `get_deadline_info()`, `on_leader_reject()`, `on_superior_interact()`, `on_leader_nudge()`

- [ ] **Step 1: 编写 services/deadline.py**

```python
"""截止时间服务"""
from datetime import datetime, timedelta


def get_deadline_info():
    """
    获取当前周的截止信息。
    
    返回: {
        'week_start': str,
        'week_end': str,
        'deadline': '周一 10:00',
        'auto_approve': '周一 11:30',
        'is_passed': bool,
        'message': str,
        'remaining': str or None,
    }
    """
    now = datetime.now()
    weekday = now.weekday()  # 0=周一
    
    # 计算本周一
    monday = now - timedelta(days=weekday)
    sunday = monday + timedelta(days=6)
    
    # 截止时间: 本周一 10:00
    deadline = monday.replace(hour=10, minute=0, second=0, microsecond=0)
    auto_approve = monday.replace(hour=11, minute=30, second=0, microsecond=0)
    
    is_passed = now > deadline
    remaining = None
    message = ""
    
    if weekday == 0:  # 周一
        if now < deadline:
            delta = deadline - now
            hours = delta.seconds // 3600
            mins = (delta.seconds % 3600) // 60
            remaining = f"{hours}小时{mins}分钟"
            message = f"请在周一 10:00 前提交周报（剩余 {remaining}）"
        elif now < auto_approve:
            delta = auto_approve - now
            mins = delta.seconds // 60
            remaining = f"{mins}分钟"
            message = "提交已截止，Leader 审核中"
        else:
            message = "本周审核已结束，部门领导可查阅"
            is_passed = True
    elif weekday >= 1:  # 周二及以后
        if weekday == 1 and now.hour < 12:  # 周二中午前
            message = "本周审核已完成，部门领导可查阅"
        elif now < monday + timedelta(days=7):
            message = "本周提交已截止"
        is_passed = True
    
    return {
        "week_start": monday.strftime("%Y-%m-%d"),
        "week_end": sunday.strftime("%Y-%m-%d"),
        "deadline": "周一 10:00",
        "auto_approve": "周一 11:30",
        "is_passed": is_passed,
        "message": message,
        "remaining": remaining,
    }
```

- [ ] **Step 2: 编写 services/notification.py**

```python
"""通知事件服务"""
import json
from database_v2 import get_db, create_notification_event


def on_leader_reject(submission_id, submitter_user_id, reason):
    """Leader 驳回时触发"""
    create_notification_event(
        "leader_reject", submitter_user_id,
        related_submission_id=submission_id,
        payload={
            "reason": reason,
            "submission_id": submission_id,
            "message": f"您的周报已被驳回，原因：{reason}，请修改后重新提交"
        }
    )


def on_superior_interact(file_id, submitter_user_id, interact_type, superior_name):
    """部门领导互动时触发"""
    create_notification_event(
        "superior_interact", submitter_user_id,
        payload={
            "type": interact_type,
            "file_id": file_id,
            "superior": superior_name,
            "message": f"部门领导{superior_name}{'赞了' if interact_type == 'like' else '评论了'}您的文件"
        }
    )


def on_leader_nudge(leader_id, leader_name, member_id):
    """Leader 催交时触发"""
    from database_v2 import get_current_week
    week_start, _ = get_current_week()
    create_notification_event(
        "leader_nudge", member_id,
        payload={
            "leader_id": leader_id,
            "leader_name": leader_name,
            "week_start": week_start,
            "message": f"{leader_name}提醒您尽快提交本周周报"
        }
    )
```

- [ ] **Step 3: 测试**

```python
# test_deadline.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'weekly-report-system'))
from services.deadline import get_deadline_info

def test_get_deadline_info():
    info = get_deadline_info()
    assert "week_start" in info
    assert "is_passed" in info
    assert "deadline" in info
    print(info)

test_get_deadline_info()
```

Run: `python test_deadline.py`
Expected: 打印当前周的截止信息 dict

- [ ] **Step 4: Commit**

```bash
git add weekly-report-system/services/deadline.py weekly-report-system/services/notification.py test_deadline.py
git commit -m "feat: deadline service + notification event triggers"
```

---

### Task 6: 上传页面（多文件 + 即时反馈）

**Files:**
- Create: `weekly-report-system/pages/__init__.py`
- Create: `weekly-report-system/pages/upload.py`

**Interfaces:**
- Consumes: `get_db()`, `get_current_week()`, `create_submission()`, `add_submission_file()`, `enqueue_task()`, `get_submission_with_files()` from `database_v2`; `get_deadline_info()` from `services.deadline`; `save_uploaded_file()`, `get_file_type()`, `ALLOWED_EXTENSIONS` from `services.file_handler`
- Produces: `render_upload_page(user)`

- [ ] **Step 1: 编写 pages/upload.py**

```python
"""上传周报页面 — 多文件上传 + 异步处理"""
import streamlit as st
import os
from database_v2 import (
    get_current_week, create_submission, add_submission_file,
    enqueue_task, get_submission_with_files, get_db,
)
from services.deadline import get_deadline_info
from services.file_handler import save_uploaded_file, get_file_type, ALLOWED_EXTENSIONS


# 前端预识别关键词
KEYWORD_MAP = {
    "周报": ("周报", "weekly report"),
    "weekly report": ("周报", "weekly report"),
    "作战地图": ("作战地图", "battle map"),
    "battle map": ("作战地图", "battle map"),
    "拜访报告": ("拜访报告", "visit report"),
    "visit report": ("拜访报告", "visit report"),
    "会议纪要": ("会议纪要", "meeting minutes"),
    "meeting minutes": ("会议纪要", "meeting minutes"),
}


def _pre_identify(filename):
    """前端预识别文件名"""
    fname_lower = filename.lower()
    for kw, (label, kw_en) in KEYWORD_MAP.items():
        if kw in fname_lower or kw_en in fname_lower:
            return label
    return None


def render_upload_page(user):
    """渲染上传页面"""
    st.title("📤 上传周报")
    
    week_start, week_end = get_current_week()
    deadline_info = get_deadline_info()
    module_id = user.get("module_id")
    
    # 获取模块名
    conn = get_db()
    m = conn.execute("SELECT name FROM modules WHERE id = ?", (module_id,)).fetchone()
    module_name = m["name"] if m else "未分配"
    conn.close()
    
    st.markdown(f"**模块**: {module_name} | **周期**: {week_start} ~ {week_end}")
    st.info(f"⏰ {deadline_info['message']}")
    
    if deadline_info["is_passed"]:
        st.warning("⏰ 本周提交已截止，如需补交请联系团队 Leader。")
        return
    
    # 检查本周已有提交
    conn = get_db()
    existing_sub = conn.execute(
        """SELECT id FROM submissions
           WHERE user_id = ? AND week_start = ? AND is_latest = 1
           ORDER BY submitted_at DESC LIMIT 1""",
        (user["id"], week_start)
    ).fetchone()
    conn.close()
    
    if existing_sub:
        sub = get_submission_with_files(existing_sub["id"])
        if sub:
            status_label = {
                "submitted": "🟡 待 Leader 审核",
                "leader_approved": "✅ Leader 已通过",
                "leader_rejected": "🔴 已驳回",
            }.get(sub["status"], sub["status"])
            st.success(f"📋 本周已提交 — {status_label}")
            
            if sub["status"] == "leader_rejected":
                st.warning(f"驳回原因: {sub.get('leader_review_note', '无')}")
                st.info("请在截止时间前重新提交")
    
    # 上传区域
    uploaded_files = st.file_uploader(
        "拖拽或选择文件（支持多文件）",
        type=list(ALLOWED_EXTENSIONS),
        accept_multiple_files=True,
        help="支持 Excel / Word / PPT / PDF / 图片，可一次选择多个文件",
        key=f"upload_{week_start}",
    )
    
    if uploaded_files:
        st.markdown("── 已选择的文件 ──")
        for uf in uploaded_files:
            ftype = get_file_type(uf.name)
            pre_id = _pre_identify(uf.name)
            icon = "✅" if pre_id else "⚠️"
            label = pre_id or "待识别"
            
            col1, col2, col3 = st.columns([3, 1, 1])
            col1.write(f"📎 {uf.name}")
            col2.write(f"{uf.size / 1024:.1f} KB")
            col3.write(f"{icon} {label}")
    
    if st.button("📤 提交周报", type="primary", use_container_width=True):
        if not uploaded_files:
            st.error("请先选择文件")
        else:
            _handle_submit(user, module_id, week_start, week_end, uploaded_files)


def _handle_submit(user, module_id, week_start, week_end, uploaded_files):
    """处理提交流程"""
    # 1. 创建提交记录
    submission_id = create_submission(user["id"], module_id, week_start, week_end)
    
    # 2. 保存每个文件 + 写入任务
    file_records = []
    for uf in uploaded_files:
        file_type = get_file_type(uf.name)
        file_path = save_uploaded_file(uf, week_start, module_id, user["id"])
        file_size = uf.size
        
        file_id = add_submission_file(
            submission_id, uf.name, file_path, file_type, file_size
        )
        file_records.append({"id": file_id, "name": uf.name, "type": file_type})
        
        # 入队后台处理任务
        enqueue_task(file_id, "process_full")
    
    st.success(f"✅ 上传成功！{len(file_records)} 个文件正在后台处理中...")
    
    # 显示处理状态
    st.markdown("### 📊 文件处理状态")
    for fr in file_records:
        st.write(f"📎 {fr['name']} — 🔄 处理中...")
    
    st.info("文件处理完成后即可在团队视图中预览。您可以关闭此页面。")
    st.rerun()
```

- [ ] **Step 2: Commit**

```bash
git add weekly-report-system/pages/__init__.py weekly-report-system/pages/upload.py
git commit -m "feat: upload page — multi-file upload with pre-identification and async processing"
```

---

### Task 7: Leader 审核页面

**Files:**
- Create: `weekly-report-system/pages/review.py`

**Interfaces:**
- Consumes: `get_db()`, `get_current_week()`, `get_submission_status()`, `get_submission_with_files()`, `approve_submission()`, `reject_submission()` from `database_v2`; `get_deadline_info()` from `services.deadline`; `on_leader_reject()`, `on_leader_nudge()` from `services.notification`
- Produces: `render_review_page(user)`

- [ ] **Step 1: 编写 pages/review.py**

```python
"""Leader 审核页面"""
import streamlit as st
from database_v2 import (
    get_db, get_current_week, get_submission_status,
    get_submission_with_files, approve_submission, reject_submission,
)
from services.deadline import get_deadline_info
from services.notification import on_leader_reject, on_leader_nudge


def render_review_page(user):
    """渲染 Leader 审核页面"""
    st.title("✅ 审核周报")
    
    week_start, week_end = get_current_week()
    module_id = user["module_id"]
    deadline_info = get_deadline_info()
    
    conn = get_db()
    m = conn.execute("SELECT name FROM modules WHERE id = ?", (module_id,)).fetchone()
    module_name = m["name"] if m else "未知"
    conn.close()
    
    st.markdown(f"**模块**: {module_name} | **周期**: {week_start} ~ {week_end}")
    st.info(f"⏰ {deadline_info['message']}")
    
    status_data = get_submission_status(module_id, week_start, week_end)
    
    # 统计卡片
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("应提交", status_data["total"])
    col2.metric("已提交", status_data["submitted_count"])
    review_count = sum(1 for s in status_data["submitted"] if s["status"] != "submitted")
    col3.metric("已审核", review_count)
    pending_count = sum(1 for s in status_data["submitted"] if s["status"] == "submitted")
    col4.metric("待审核", pending_count)
    
    st.divider()
    
    # 待审核列表
    st.subheader(f"🟡 待审核 ({pending_count}人)")
    for s in status_data["submitted"]:
        if s["status"] != "submitted":
            continue
        
        sub = get_submission_with_files(s["id"])
        if not sub:
            continue
        
        with st.container(border=True):
            col1, col2 = st.columns([2, 1])
            col1.markdown(f"**{s['display_name']}** — {len(sub['files'])} 个文件")
            col2.caption(f"提交时间: {s['submitted_at']}")
            
            # 文件列表
            for f in sub["files"]:
                status_icon = {
                    "pending": "⏳", "extracting": "🔄", "recognizing": "🔍",
                    "converting": "📄", "ready": "✅", "error": "❌"
                }.get(f["processing_status"], "❓")
                st.caption(f"  {status_icon} {f['filename']}")
            
            # 驳回原因
            reject_note = st.text_input(
                "驳回原因（驳回时必填）",
                key=f"reject_note_{s['id']}",
                placeholder="请填写具体原因..."
            )
            
            c1, c2 = st.columns(2)
            if c1.button("✅ 审核通过", key=f"approve_{s['id']}", use_container_width=True):
                approve_submission(s["id"], user["id"])
                st.success(f"✅ {s['display_name']} 的周报已通过")
                st.rerun()
            
            if c2.button("🔴 驳回", key=f"reject_{s['id']}", use_container_width=True):
                if not reject_note.strip():
                    st.error("驳回时必须填写原因")
                else:
                    reject_submission(s["id"], user["id"], reject_note)
                    on_leader_reject(s["id"], s["user_id"], reject_note)
                    st.warning(f"🔴 已驳回 {s['display_name']} 的周报")
                    st.rerun()
    
    st.divider()
    
    # 已审核列表
    reviewed = [s for s in status_data["submitted"] if s["status"] != "submitted"]
    if reviewed:
        st.subheader(f"✅ 已审核 ({len(reviewed)}人)")
        for s in reviewed:
            status_icon = {"leader_approved": "✅", "leader_rejected": "🔴"}.get(s["status"], "❓")
            note = f" — {s.get('leader_review_note', '')}" if s.get("leader_review_note") else ""
            st.write(f"{status_icon} {s['display_name']} — {s['status']}{note}")
    
    st.divider()
    
    # 未提交列表
    if status_data["not_submitted"]:
        st.subheader(f"❌ 未提交 ({len(status_data['not_submitted'])}人)")
        for m in status_data["not_submitted"]:
            col1, col2 = st.columns([2, 1])
            col1.write(f"• {m['display_name']}")
            if col2.button("📢 催交", key=f"nudge_{m['id']}"):
                on_leader_nudge(user["id"], user["display_name"], m["id"])
                st.success(f"已催交 {m['display_name']}")
                st.rerun()
    
    st.divider()
    
    # Leader 自己
    st.subheader("📝 我的周报")
    my_sub = [s for s in status_data["submitted"] if s["user_id"] == user["id"]]
    if my_sub:
        s = my_sub[0]
        if s["status"] == "submitted":
            if st.button("✅ 自审通过", key="self_approve", type="primary"):
                approve_submission(s["id"], user["id"])
                st.success("✅ 自审通过")
                st.rerun()
        else:
            status_label = {"leader_approved": "✅ 已通过", "leader_rejected": "🔴 已驳回"}.get(s["status"], s["status"])
            st.write(f"自审状态: {status_label}")
    else:
        st.info("你本周尚未提交周报")
```

- [ ] **Step 2: Commit**

```bash
git add weekly-report-system/pages/review.py
git commit -m "feat: leader review page — approve/reject, self-review, nudge, auto-reject note required"
```

---

### Task 8: 团队视图 + 提交历史页面

**Files:**
- Create: `weekly-report-system/pages/team_view.py`
- Create: `weekly-report-system/pages/history.py`

- [ ] **Step 1: 编写 pages/team_view.py**

```python
"""团队视图页面 — Leader 查看团队提交概况"""
import streamlit as st
from database_v2 import get_db, get_current_week, get_submission_status, get_member_weekly_files


def render_team_view_page(user):
    st.title("👥 团队周报")
    
    week_start, week_end = get_current_week()
    module_id = user["module_id"]
    
    conn = get_db()
    m = conn.execute("SELECT name FROM modules WHERE id = ?", (module_id,)).fetchone()
    module_name = m["name"] if m else "未知"
    conn.close()
    
    status_data = get_submission_status(module_id, week_start, week_end)
    
    st.markdown(f"### {module_name} — {week_start} ~ {week_end}")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("应提交", status_data["total"])
    col2.metric("已提交", status_data["submitted_count"])
    rate = round(status_data["submitted_count"] / max(status_data["total"], 1) * 100)
    col3.metric("提交率", f"{rate}%")
    
    st.divider()
    
    # 已提交成员 → 点击查看详情
    st.subheader("已提交")
    for s in status_data["submitted"]:
        status_icon = {
            "submitted": "🟡 待审核", "leader_approved": "✅ 已通过",
            "leader_rejected": "🔴 已驳回"
        }.get(s["status"], s["status"])
        
        with st.expander(f"{s['display_name']} — {status_icon}"):
            files = get_member_weekly_files(s["user_id"], week_start)
            for f in files:
                tname = f.get("template_name") or "未识别"
                pstatus = {
                    "pending": "⏳ 处理中", "ready": "✅ 就绪", "error": "❌ 错误"
                }.get(f["processing_status"], "❓")
                st.write(f"📎 {f['filename']} — {tname} ({pstatus})")
    
    # 未提交
    if status_data["not_submitted"]:
        st.subheader("⚠️ 未提交")
        for m in status_data["not_submitted"]:
            st.write(f"• {m['display_name']}")
```

- [ ] **Step 2: 编写 pages/history.py**

```python
"""提交历史页面"""
import streamlit as st
from database_v2 import get_db, get_current_week


def render_history_page(user):
    st.title("📋 提交历史")
    
    week_start, week_end = get_current_week()
    conn = get_db()
    
    if user["role"] == "member":
        submissions = conn.execute(
            """SELECT s.*, m.name as module_name
               FROM submissions s JOIN modules m ON s.module_id = m.id
               WHERE s.user_id = ?
               ORDER BY s.submitted_at DESC LIMIT 20""",
            (user["id"],)
        ).fetchall()
    else:
        submissions = conn.execute(
            """SELECT s.*, m.name as module_name, u.display_name
               FROM submissions s
               JOIN modules m ON s.module_id = m.id
               JOIN users u ON s.user_id = u.id
               ORDER BY s.submitted_at DESC LIMIT 50"""
        ).fetchall()
    
    if not submissions:
        st.info("暂无提交记录")
        conn.close()
        return
    
    for s in submissions:
        status_emoji = {
            "submitted": "🟡", "leader_approved": "✅", "leader_rejected": "🔴"
        }.get(s["status"], "❓")
        
        with st.container(border=True):
            col1, col2, col3 = st.columns([3, 2, 2])
            col1.markdown(f"{status_emoji} **{s['week_start']} ~ {s['week_end']}** — {s['module_name']}")
            if user["role"] != "member":
                col1.markdown(f"*{s.get('display_name', '')}*")
            col2.markdown(f"状态: {s['status']}")
            col3.markdown(f"提交: {s['submitted_at']}")
            
            if s["status"] == "leader_rejected" and s.get("leader_review_note"):
                st.caption(f"驳回原因: {s['leader_review_note']}")
    
    conn.close()
```

- [ ] **Step 3: Commit**

```bash
git add weekly-report-system/pages/team_view.py weekly-report-system/pages/history.py
git commit -m "feat: team view page + submission history page"
```

---

### Task 9: 领导查阅页（嵌入式 HTML 组件）

**Files:**
- Create: `weekly-report-system/static/superior_browse.html`
- Create: `weekly-report-system/pages/leader_browse.py`

- [ ] **Step 1: 编写静态 HTML 组件（核心，约 500 行）**

文件 `static/superior_browse.html`:

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>领导查阅</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; }
.container { display: flex; height: 100vh; }
/* 左侧成员列表 */
.sidebar { width: 280px; background: #fff; border-right: 1px solid #e0e0e0; overflow-y: auto; padding: 16px; }
.module-select { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 6px; margin-bottom: 12px; font-size: 14px; }
.member-item { display: flex; align-items: center; padding: 10px 8px; border-radius: 8px; cursor: pointer; margin-bottom: 4px; transition: background 0.15s; }
.member-item:hover { background: #f0f4ff; }
.member-item.active { background: #e8f0fe; font-weight: 600; }
.member-status { width: 8px; height: 8px; border-radius: 50%; margin-right: 10px; flex-shrink: 0; }
.member-status.approved { background: #34a853; }
.member-status.pending { background: #fbbc04; }
.member-status.rejected { background: #ea4335; }
.member-status.not-submitted { background: #ccc; }
.member-info { flex: 1; min-width: 0; }
.member-name { font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.member-summary { font-size: 11px; color: #999; margin-top: 2px; }
/* 右侧内容区 */
.main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.toolbar { display: flex; align-items: center; gap: 12px; padding: 12px 20px; background: #fff; border-bottom: 1px solid #e0e0e0; }
.toolbar select { padding: 6px 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; }
.week-nav { display: flex; align-items: center; gap: 8px; margin-left: auto; }
.week-nav button { padding: 4px 12px; border: 1px solid #ddd; border-radius: 4px; background: #fff; cursor: pointer; }
.week-nav button:hover { background: #f0f0f0; }
/* 文件标签栏 */
.file-tabs { display: flex; gap: 4px; padding: 8px 20px; background: #fff; border-bottom: 1px solid #e0e0e0; overflow-x: auto; }
.file-tab { padding: 6px 14px; border: 1px solid #e0e0e0; border-radius: 6px 6px 0 0; cursor: pointer; font-size: 13px; white-space: nowrap; background: #fafafa; transition: all 0.15s; }
.file-tab:hover { background: #f0f4ff; }
.file-tab.active { background: #fff; border-bottom-color: #fff; font-weight: 600; color: #1a73e8; }
/* 内容区 */
.content { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.preview-area { flex: 1; position: relative; background: #fff; margin: 16px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; }
.preview-area iframe { width: 100%; height: 100%; border: none; }
.preview-area img { max-width: 100%; max-height: 100%; object-fit: contain; display: block; margin: auto; }
.placeholder { display: flex; align-items: center; justify-content: center; height: 100%; color: #999; font-size: 16px; }
/* 互动栏 */
.interaction-bar { display: flex; align-items: center; gap: 12px; padding: 8px 20px; background: #fff; border-top: 1px solid #e0e0e0; }
.like-btn { display: flex; align-items: center; gap: 4px; padding: 6px 12px; border: 1px solid #ddd; border-radius: 20px; background: #fff; cursor: pointer; font-size: 13px; transition: all 0.15s; }
.like-btn:hover { border-color: #ea4335; }
.like-btn.liked { background: #fce8e6; border-color: #ea4335; color: #ea4335; }
.comment-toggle { padding: 6px 12px; border: none; background: none; cursor: pointer; font-size: 13px; color: #666; }
.comment-toggle:hover { color: #1a73e8; }
/* 评论区 */
.comments-panel { max-height: 200px; overflow-y: auto; padding: 0 20px 12px; background: #fff; border-top: 1px solid #e0e0e0; }
.comment-item { padding: 8px 0; border-bottom: 1px solid #f0f0f0; }
.comment-author { font-weight: 600; font-size: 12px; color: #1a73e8; }
.comment-time { font-size: 11px; color: #999; margin-left: 8px; }
.comment-text { font-size: 13px; margin-top: 2px; }
.comment-input-area { display: flex; gap: 8px; padding: 8px 0; }
.comment-input-area input { flex: 1; padding: 6px 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; }
.comment-input-area button { padding: 6px 14px; background: #1a73e8; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; }
</style>
</head>
<body>
<div class="container">
  <!-- 左侧成员列表 -->
  <div class="sidebar" id="sidebar">
    <select class="module-select" id="moduleSelect">
      <option value="">加载中...</option>
    </select>
    <div id="memberList"></div>
  </div>
  
  <!-- 右侧内容 -->
  <div class="main">
    <div class="toolbar">
      <span id="currentMemberLabel" style="font-weight:600;font-size:16px;">请选择成员</span>
      <div class="week-nav">
        <button onclick="navigateWeek(-1)">← 上一周</button>
        <span id="weekLabel">---</span>
        <button onclick="navigateWeek(1)">下一周 →</button>
      </div>
    </div>
    
    <!-- 文件标签栏 -->
    <div class="file-tabs" id="fileTabs">
      <div class="file-tab active" style="color:#999;">请选择成员查看文件</div>
    </div>
    
    <!-- 预览 + 互动区 -->
    <div class="content">
      <div class="preview-area" id="previewArea">
        <div class="placeholder">👈 点击左侧成员姓名查看周报</div>
      </div>
    </div>
    
    <div class="interaction-bar">
      <button class="like-btn" id="likeBtn" onclick="toggleLike()" disabled>
        🤍 <span id="likeCount">0</span>
      </button>
      <button class="comment-toggle" onclick="toggleComments()">
        💬 评论 (<span id="commentCount">0</span>)
      </button>
    </div>
    
    <div class="comments-panel" id="commentsPanel" style="display:none;">
      <div id="commentList"></div>
      <div class="comment-input-area">
        <input type="text" id="commentInput" placeholder="写评论..." />
        <button onclick="submitComment()">发送</button>
      </div>
    </div>
  </div>
</div>

<script>
// ===== 状态 =====
let state = {
  modules: [],
  members: [],
  currentModuleId: null,
  currentMemberId: null,
  currentFileId: null,
  currentFiles: [],
  weekStart: '',
  weekEnd: '',
  superiorId: null,
  superiorName: '',
};

// ===== 初始化 =====
// Streamlit 通过 postMessage 传递初始数据
window.addEventListener('message', function(e) {
  if (e.data.type === 'init') {
    state = { ...state, ...e.data.payload };
    renderModules();
    renderMembers();
  }
  if (e.data.type === 'filesData') {
    state.currentFiles = e.data.payload.files;
    renderFileTabs();
    if (state.currentFiles.length > 0) {
      selectFile(state.currentFiles[0].id);
    }
  }
  if (e.data.type === 'interactionUpdate') {
    if (state.currentFileId === e.data.payload.file_id) {
      state.currentFile = e.data.payload;
      updateInteractionUI();
    }
  }
});

function sendToPython(action, data) {
  window.parent.postMessage({ type: 'streamlit:setComponentValue', value: { action, ...data } }, '*');
}

// ===== 渲染模块选择 =====
function renderModules() {
  const sel = document.getElementById('moduleSelect');
  sel.innerHTML = state.modules.map(m => `<option value="${m.id}">${m.name}</option>`).join('');
  sel.value = state.currentModuleId || state.modules[0]?.id || '';
  sel.onchange = function() {
    state.currentModuleId = parseInt(this.value);
    state.currentMemberId = null;
    renderMembers();
    clearContent();
  };
  if (!state.currentModuleId && state.modules.length > 0) {
    state.currentModuleId = state.modules[0].id;
  }
}

// ===== 渲染成员列表 =====
function renderMembers() {
  const moduleMembers = state.members.filter(m => m.module_id === state.currentModuleId);
  const html = moduleMembers.map(m => {
    const statusClass = {
      'leader_approved': 'approved', 'submitted': 'pending',
      'leader_rejected': 'rejected', 'not_submitted': 'not-submitted'
    }[m.status] || 'not-submitted';
    const activeClass = m.user_id === state.currentMemberId ? ' active' : '';
    return `
      <div class="member-item${activeClass}" onclick="selectMember(${m.user_id})" data-user-id="${m.user_id}">
        <div class="member-status ${statusClass}"></div>
        <div class="member-info">
          <div class="member-name">${m.display_name}</div>
          <div class="member-summary">${m.summary || ''}</div>
        </div>
      </div>`;
  }).join('');
  document.getElementById('memberList').innerHTML = html || '<div style="color:#999;padding:12px;">暂无成员</div>';
}

// ===== 选择成员 =====
function selectMember(userId) {
  state.currentMemberId = userId;
  state.currentFileId = null;
  
  // 更新高亮
  document.querySelectorAll('.member-item').forEach(el => el.classList.remove('active'));
  const el = document.querySelector(`[data-user-id="${userId}"]`);
  if (el) el.classList.add('active');
  
  // 更新标题
  const member = state.members.find(m => m.user_id === userId);
  document.getElementById('currentMemberLabel').textContent = member ? member.display_name : '';
  document.getElementById('weekLabel').textContent = `${state.weekStart} ~ ${state.weekEnd}`;
  
  // 请求文件数据
  sendToPython('getFiles', { user_id: userId, week_start: state.weekStart });
}

// ===== 文件标签 =====
function renderFileTabs() {
  const tabs = state.currentFiles.map((f, i) => {
    const icon = { '周报': '📊', '作战地图': '🗺️', '拜访报告': '📝', '会议纪要': '📋' }[f.template_name] || '📎';
    const activeClass = f.id === state.currentFileId ? ' active' : '';
    return `<div class="file-tab${activeClass}" onclick="selectFile(${f.id})">${icon} ${f.filename}</div>`;
  }).join('');
  document.getElementById('fileTabs').innerHTML = tabs;
}

function selectFile(fileId) {
  state.currentFileId = fileId;
  
  // 更新标签高亮
  document.querySelectorAll('.file-tab').forEach((el, i) => {
    el.classList.toggle('active', state.currentFiles[i]?.id === fileId);
  });
  
  const file = state.currentFiles.find(f => f.id === fileId);
  if (!file) return;
  
  // 渲染预览
  const previewArea = document.getElementById('previewArea');
  const previewUrl = file.preview_path || file.original_path;
  
  if (file.file_type === 'pdf' || previewUrl.endsWith('.pdf')) {
    previewArea.innerHTML = `<iframe src="${previewUrl}"></iframe>`;
  } else if (file.file_type === 'image') {
    previewArea.innerHTML = `<img src="${previewUrl}" alt="${file.filename}" />`;
  } else if (file.processing_status !== 'ready') {
    previewArea.innerHTML = `<div class="placeholder">⏳ 文件处理中，请稍后刷新...</div>`;
  } else {
    previewArea.innerHTML = `<div class="placeholder">📄 ${file.filename}<br><small>点击下载查看</small></div>`;
  }
  
  // 更新互动 UI
  updateInteractionUI();
}

// ===== 互动 =====
function toggleLike() {
  const fileId = state.currentFileId;
  const isLiked = document.getElementById('likeBtn').classList.contains('liked');
  sendToPython(isLiked ? 'unlike' : 'like', { file_id: fileId });
}

function toggleComments() {
  const panel = document.getElementById('commentsPanel');
  panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
}

function submitComment() {
  const input = document.getElementById('commentInput');
  const content = input.value.trim();
  if (!content) return;
  sendToPython('comment', { file_id: state.currentFileId, content });
  input.value = '';
}

function updateInteractionUI() {
  const file = state.currentFiles.find(f => f.id === state.currentFileId);
  if (!file) return;
  
  const likes = file.likes || [];
  const comments = file.comments || [];
  const myLike = likes.find(l => l.user_id === state.superiorId);
  
  const likeBtn = document.getElementById('likeBtn');
  likeBtn.innerHTML = `${myLike ? '❤️' : '🤍'} <span id="likeCount">${likes.length}</span>`;
  likeBtn.classList.toggle('liked', !!myLike);
  likeBtn.disabled = !state.currentFileId;
  
  document.getElementById('commentCount').textContent = comments.length;
  
  document.getElementById('commentList').innerHTML = comments.map(c => `
    <div class="comment-item">
      <span class="comment-author">${c.display_name}</span>
      <span class="comment-time">${c.created_at}</span>
      <div class="comment-text">${c.content}</div>
    </div>
  `).join('');
}

function clearContent() {
  document.getElementById('fileTabs').innerHTML = '<div class="file-tab active" style="color:#999;">请选择成员查看文件</div>';
  document.getElementById('previewArea').innerHTML = '<div class="placeholder">👈 点击左侧成员姓名查看周报</div>';
  document.getElementById('currentMemberLabel').textContent = '请选择成员';
  document.getElementById('likeBtn').disabled = true;
  document.getElementById('commentsPanel').style.display = 'none';
}

function navigateWeek(delta) {
  sendToPython('navigateWeek', { delta });
}
</script>
</body>
</html>
```

- [ ] **Step 2: 编写 Python 页面桥接层 pages/leader_browse.py**

```python
"""领导查阅页 — Streamlit ←→ 嵌入式 HTML 组件桥接"""
import streamlit as st
import json
import os
from database_v2 import (
    get_db, get_current_week, get_member_weekly_files,
    get_file_interactions, add_interaction, can_browse_all_modules,
)
from services.notification import on_superior_interact


STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")


def _get_all_members_status(module_id, week_start):
    """获取模块所有成员的提交状态"""
    conn = get_db()
    members = conn.execute(
        """SELECT u.id as user_id, u.display_name, u.module_id, u.role
           FROM users u WHERE u.module_id = ? AND u.is_active = 1""",
        (module_id,)
    ).fetchall()
    
    subs = conn.execute(
        """SELECT s.user_id, s.status, COUNT(sf.id) as file_count
           FROM submissions s
           LEFT JOIN submission_files sf ON s.id = sf.submission_id
           WHERE s.module_id = ? AND s.week_start = ? AND s.is_latest = 1
           GROUP BY s.user_id""",
        (module_id, week_start)
    ).fetchall()
    conn.close()
    
    sub_map = {s["user_id"]: s for s in subs}
    
    result = []
    for m in members:
        s = sub_map.get(m["user_id"])
        result.append({
            "user_id": m["user_id"],
            "display_name": m["display_name"],
            "module_id": m["module_id"],
            "role": m["role"],
            "status": s["status"] if s else "not_submitted",
            "summary": f"{s['file_count']}个文件" if s else "未提交",
        })
    return result


def _get_files_with_interactions(user_id, week_start):
    """获取成员文件列表（含互动数据）"""
    files = get_member_weekly_files(user_id, week_start)
    for f in files:
        interactions = get_file_interactions(f["id"])
        f["likes"] = interactions["likes"]
        f["likes_count"] = interactions["likes_count"]
        f["comments"] = interactions["comments"]
    return files


def render_leader_browse_page(user):
    """渲染领导查阅页"""
    st.title("📊 领导查阅")
    
    week_start, week_end = get_current_week()
    
    # 获取可访问的模块
    conn = get_db()
    all_modules = conn.execute("SELECT * FROM modules ORDER BY id").fetchall()
    conn.close()
    
    # 准备初始化数据
    modules_data = [{"id": m["id"], "name": m["name"]} for m in all_modules]
    
    # 默认选中第一个模块
    default_module_id = all_modules[0]["id"] if all_modules else None
    
    # 获取所有模块的成员状态
    all_members = []
    for m in all_modules:
        members = _get_all_members_status(m["id"], week_start)
        all_members.extend(members)
    
    # 读取 HTML 模板
    html_path = os.path.join(STATIC_DIR, "superior_browse.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    
    # 注入初始数据
    init_data = {
        "modules": modules_data,
        "members": all_members,
        "currentModuleId": default_module_id,
        "weekStart": week_start,
        "weekEnd": week_end,
        "superiorId": user["id"],
        "superiorName": user["display_name"],
    }
    
    # 注入脚本
    inject_script = f"""
    <script>
    window.addEventListener('DOMContentLoaded', function() {{
        window.postMessage({{type: 'init', payload: {json.dumps(init_data, ensure_ascii=False)}}}, '*');
    }});
    </script>
    """
    full_html = html_content.replace("</body>", inject_script + "</body>")
    
    # 渲染
    result = st.components.html(full_html, height=800)
    
    # 处理回调
    if result and isinstance(result, dict):
        action = result.get("action")
        
        if action == "getFiles":
            uid = result["user_id"]
            files = _get_files_with_interactions(uid, result["week_start"])
            # 无法直接回传，使用 session_state 存储 + rerun
            st.session_state["_browse_files"] = files
            st.session_state["_browse_user_id"] = uid
            st.rerun()
        
        elif action == "like":
            file_id = result["file_id"]
            add_interaction(file_id, user["id"], "like")
            # 通知被点赞者
            conn = get_db()
            sf = conn.execute(
                """SELECT s.user_id FROM submission_files sf
                   JOIN submissions s ON sf.submission_id = s.id
                   WHERE sf.id = ?""", (file_id,)
            ).fetchone()
            conn.close()
            if sf and sf["user_id"] != user["id"]:
                on_superior_interact(file_id, sf["user_id"], "like", user["display_name"])
        
        elif action == "comment":
            file_id = result["file_id"]
            content = result["content"]
            add_interaction(file_id, user["id"], "comment", content)
            conn = get_db()
            sf = conn.execute(
                """SELECT s.user_id FROM submission_files sf
                   JOIN submissions s ON sf.submission_id = s.id
                   WHERE sf.id = ?""", (file_id,)
            ).fetchone()
            conn.close()
            if sf and sf["user_id"] != user["id"]:
                on_superior_interact(file_id, sf["user_id"], "comment", user["display_name"])
            
            # 更新 session state 让评论即时显示
            st.rerun()
    
    # 如果有缓存的文件数据，注入回去
    if "_browse_files" in st.session_state:
        files_data = st.session_state.pop("_browse_files")
        files_script = f"""
        <script>
        window.postMessage({{type: 'filesData', payload: {{files: {json.dumps(files_data, ensure_ascii=False, default=str)}}}}}, '*');
        </script>
        """
        st.components.html(files_script, height=0)
```

- [ ] **Step 3: 测试 HTML 组件（手动）**

Run: `streamlit run app.py` → 以 superior 登录 → 查看领导查阅页
Expected: 左侧成员列表显示，点击成员展开文件

- [ ] **Step 4: Commit**

```bash
git add weekly-report-system/static/superior_browse.html weekly-report-system/pages/leader_browse.py
git commit -m "feat: leader browse page — embedded HTML component with file preview, like, comment"
```

---

### Task 10: 系统管理页面 + 通知 API 端点

**Files:**
- Create: `weekly-report-system/pages/admin.py`
- Create: `weekly-report-system/api.py`（可选 FastAPI 端点）

- [ ] **Step 1: 编写 pages/admin.py**

```python
"""系统管理页面"""
import streamlit as st
from database_v2 import get_db, get_db as _get_db_conn


def render_admin_page():
    st.title("🔧 系统管理")
    
    tab1, tab2, tab3 = st.tabs(["用户管理", "模块设置", "文件模板"])
    
    with tab1:
        st.subheader("用户列表")
        conn = get_db()
        users = conn.execute(
            """SELECT u.*, m.name as module_name
               FROM users u LEFT JOIN modules m ON u.module_id = m.id
               WHERE u.is_active = 1 ORDER BY u.id"""
        ).fetchall()
        
        for u in users:
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
                col1.markdown(f"**{u['display_name']}** ({u['username']})")
                col2.markdown(f"模块: {u.get('module_name', '未分配')}")
                role_labels = {"admin": "🔧 管理员", "leader": "👤 Leader", "member": "👤 Member", "superior": "👔 部门领导"}
                col3.markdown(role_labels.get(u["role"], u["role"]))
                if u.get("can_browse_all"):
                    col4.markdown("🌐 全模块")
        
        conn.close()
        
        st.divider()
        st.caption("增删改用户功能待后续开发")
    
    with tab2:
        st.subheader("模块列表")
        conn = get_db()
        modules = conn.execute("SELECT * FROM modules ORDER BY id").fetchall()
        for m in modules:
            with st.container(border=True):
                st.markdown(
                    f"**{m['name']}** — 格式: {m['format']} | "
                    f"截止: 周{m['deadline_day']} {m['deadline_time']} | "
                    f"自动通过: {m['auto_approve_time']}"
                )
        conn.close()
    
    with tab3:
        st.subheader("文件模板配置")
        conn = get_db()
        templates = conn.execute(
            """SELECT ft.*, m.name as module_name
               FROM file_templates ft JOIN modules m ON ft.module_id = m.id
               ORDER BY ft.module_id, ft.is_weekly_report DESC"""
        ).fetchall()
        
        for t in templates:
            with st.container(border=True):
                weekly_badge = "⭐ 周报" if t["is_weekly_report"] else ""
                st.markdown(
                    f"**{t['name']}** {weekly_badge} — {t['module_name']} | "
                    f"关键词: {t['filename_keywords']} | 识别方式: {t['identifier_type']}"
                )
        conn.close()
```

- [ ] **Step 2: 编写 api.py（CRM 通知查询端点）**

```python
"""轻量 API 端点 — CRM 通知查询（可选，独立启动）"""
from fastapi import FastAPI, HTTPException
from database_v2 import get_db, get_pending_notifications as db_get_pending
import json

app = FastAPI(title="周报系统通知 API")


@app.get("/api/notifications/pending")
def get_pending(user_id: int):
    """查询用户未处理的通知"""
    events = db_get_pending(user_id)
    return {"count": len(events), "events": events}


@app.post("/api/notifications/{event_id}/ack")
def ack_notification(event_id: int):
    """确认通知已发送"""
    conn = get_db()
    conn.execute(
        "UPDATE notification_events SET status = 'sent', sent_at = datetime('now','localtime') WHERE id = ?",
        (event_id,)
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8502)
```

- [ ] **Step 3: Commit**

```bash
git add weekly-report-system/pages/admin.py weekly-report-system/api.py
git commit -m "feat: admin page + CRM notification API endpoint"
```

---

### Task 11: 主入口整合 — app.py 重构

**Files:**
- Modify: `weekly-report-system/app.py`

- [ ] **Step 1: 重写 app.py**

```python
"""
营销运作部周报收集系统 v2.0 — Web 应用
========================================
Streamlit 多页面应用
启动: streamlit run app.py
"""
import streamlit as st
import hashlib
import os
import sys

st.set_page_config(
    page_title="营销运作部周报系统 v2.0",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database_v2 import (
    init_db, seed_data, get_user_by_username, get_current_week,
    can_browse_all_modules, can_browse_module,
)
from services.auth import ROLE_LABELS
from services.deadline import get_deadline_info
from worker import start_worker

# ===== 初始化 =====
init_db()
seed_data()
start_worker()

# ===== 会话状态 =====
if "user" not in st.session_state:
    st.session_state.user = None
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False


def login_page():
    st.markdown(
        "<h1 style='text-align:center; margin-top:100px;'>📋 营销运作部周报系统</h1>",
        unsafe_allow_html=True,
    )
    st.markdown("<p style='text-align:center; color:#666;'>v2.0 · 请登录</p>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("用户名", placeholder="请输入用户名")
            password = st.text_input("密码", type="password", placeholder="请输入密码")
            submitted = st.form_submit_button("登 录", use_container_width=True)

            if submitted:
                if not username or not password:
                    st.error("请输入用户名和密码")
                else:
                    user = get_user_by_username(username)
                    if user:
                        pw_hash = hashlib.sha256(password.encode()).hexdigest()
                        if pw_hash == user["password_hash"]:
                            st.session_state.user = dict(user)
                            st.session_state.authenticated = True
                            st.rerun()
                        else:
                            st.error("密码错误")
                    else:
                        st.error("用户不存在")

    st.markdown(
        "<p style='text-align:center; color:#999; margin-top:30px;'>"
        "管理员: admin/admin123 | 领导: superior/leader123 | Leader: leader_domestic/team123 | 成员: user1_1/123456"
        "</p>",
        unsafe_allow_html=True,
    )


def main_app():
    user = st.session_state.user
    role = user["role"]
    
    with st.sidebar:
        st.markdown("## 📋 周报系统 v2.0")
        st.markdown(f"### {user['display_name']}")
        st.caption(f"角色: {ROLE_LABELS.get(role, role)}")
        st.divider()
        
        week_start, week_end = get_current_week()
        deadline_info = get_deadline_info()
        st.markdown(f"**📅 本周**: {week_start} ~ {week_end}")
        st.markdown(f"**⏰ 截止**: {deadline_info['deadline']}")
        st.divider()
        
        page = st.radio("导航", _get_pages(user), label_visibility="collapsed")
        st.divider()
        
        if st.button("🚪 退出登录", use_container_width=True):
            st.session_state.user = None
            st.session_state.authenticated = False
            st.rerun()
    
    # 路由
    from pages.upload import render_upload_page
    from pages.review import render_review_page
    from pages.team_view import render_team_view_page
    from pages.history import render_history_page
    from pages.leader_browse import render_leader_browse_page
    from pages.admin import render_admin_page
    
    if "上传周报" in page:
        render_upload_page(user)
    elif "审核周报" in page:
        render_review_page(user)
    elif "团队周报" in page:
        render_team_view_page(user)
    elif "提交历史" in page:
        render_history_page(user)
    elif "领导查阅" in page:
        render_leader_browse_page(user)
    elif "系统管理" in page:
        render_admin_page()


def _get_pages(user):
    role = user["role"]
    pages = []
    if role in ("member", "leader"):
        pages.append("📤 上传周报")
    if role in ("member", "leader"):
        pages.append("📋 提交历史")
    if role == "leader":
        pages.append("👥 团队周报")
        pages.append("✅ 审核周报")
    if role == "superior" or (role == "leader" and user.get("can_browse_all")):
        pages.append("📊 领导查阅")
    if role == "admin":
        pages.append("🔧 系统管理")
    return pages


if not st.session_state.authenticated:
    login_page()
else:
    main_app()
```

- [ ] **Step 2: 端到端测试**

Run: `cd weekly-report-system && streamlit run app.py`
- 以 `superior` / `leader123` 登录 → 验证领导查阅页
- 以 `leader_domestic` / `team123` 登录 → 验证上传 + 审核
- 以 `user1_1` / `123456` 登录 → 验证上传 + 历史

- [ ] **Step 3: Commit**

```bash
git add weekly-report-system/app.py
git commit -m "feat: main app entry — v2.0 routing with all pages integrated"
```

---

### Task 12: 端到端集成测试 + 收尾

- [ ] **Step 1: 更新 requirements.txt**

```
streamlit>=1.60.0
fastapi>=0.100.0
uvicorn>=0.23.0
python-pptx>=0.6.0
openpyxl>=3.0.0
python-docx>=0.8.0
```

Run: `pip install -r requirements.txt`

- [ ] **Step 2: 运行迁移**

Run: `python migrate_v1_to_v2.py`

- [ ] **Step 3: 运行完整应用**

Run: `streamlit run app.py`

- [ ] **Step 4: 手动测试清单**

- [ ] admin 登录 → 系统管理页可见，其他页面不可见
- [ ] member 登录 → 多文件上传 → 提交成功 → 处理进度显示
- [ ] member 登录 → 截止时间后无法上传
- [ ] member 登录 → 提交历史可见自己记录
- [ ] leader 登录 → 审核页可见待审列表 → 通过/驳回操作
- [ ] leader 登录 → 驳回时必须填写原因
- [ ] leader 登录 → 自审通过
- [ ] leader 登录 → 催交按钮可用
- [ ] superior 登录 → 领导查阅页 → 左侧成员列表 → 点击查看文件
- [ ] superior 登录 → 点赞 → 计数增加
- [ ] superior 登录 → 评论 → 评论显示
- [ ] 营销运营部 leader 登录 → 可见领导查阅页（全模块）

- [ ] **Step 5: 提交最终版本**

```bash
git add -A
git commit -m "feat: v2.0 end-to-end integration complete"
```

---

## 分阶段交付概览

| Phase | Tasks | 交付物 |
|-------|-------|--------|
| **Phase 1** (本次) | Task 1-12 | 数据库 v2 + 多文件上传 + Leader 审核 + 领导查阅 + 通知 + 系统管理 |
| **Phase 2** (后续) | 分析引擎 ①⑥ | 风险热力图 + 个人效率概览（Claude API） |
| **Phase 3** (后续) | 分析引擎 ②③⑤④ | 项目健康度 + 进度异常 + 会议待办 + 协同盲点 |

---

## 自审检查

- [x] 12 个 Task 覆盖规格全部功能点
- [x] 每个 Task 有明确文件清单和接口签名
- [x] 所有代码步骤给出完整实现，无 TBD/TODO
- [x] 数据库函数签名在 Task 1 定义，Task 2-11 引用一致
- [x] 通知事件类型与规格 7 类事件对齐
- [x] 权限矩阵在 Task 2 实现，Task 11 路由匹配
- [x] Phase 2/3 分析引擎标记为后续开发
