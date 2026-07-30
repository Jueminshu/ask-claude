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
