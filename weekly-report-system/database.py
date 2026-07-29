"""
数据库层
SQLite 本地数据库：用户、模块、提交、工作流状态
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
    """初始化数据库表"""
    conn = get_db()
    conn.executescript("""
        -- 模块表（国内运营商/销售部/营销运营部/海外BD）
        CREATE TABLE IF NOT EXISTS modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,       -- 模块名称
            format TEXT NOT NULL DEFAULT 'excel',  -- excel / ppt
            deadline_day INTEGER DEFAULT 7,  -- 截止日（7=周日）
            deadline_time TEXT DEFAULT '23:59'  -- 截止时间
        );

        -- 用户表
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            email TEXT,
            role TEXT NOT NULL DEFAULT 'member',  -- admin / leader / member
            module_id INTEGER,                     -- 所属模块
            is_superior INTEGER DEFAULT 0,         -- 是否是领导
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (module_id) REFERENCES modules(id)
        );

        -- 周报提交表
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            module_id INTEGER NOT NULL,
            week_start TEXT NOT NULL,           -- 周起始日期 (ISO周一)
            week_end TEXT NOT NULL,             -- 周结束日期 (ISO周日)
            filename TEXT NOT NULL,             -- 上传的文件名
            file_path TEXT NOT NULL,            -- 存储路径
            row_count INTEGER DEFAULT 0,        -- 数据行数
            status TEXT NOT NULL DEFAULT 'submitted',  -- submitted/reviewed/approved/rejected
            reviewed_by INTEGER,                -- 审核人
            reviewed_at TEXT,                   -- 审核时间
            notes TEXT,                         -- 审核备注
            submitted_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (module_id) REFERENCES modules(id),
            FOREIGN KEY (reviewed_by) REFERENCES users(id)
        );

        -- 周报汇总记录
        CREATE TABLE IF NOT EXISTS weekly_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_id INTEGER NOT NULL,
            week_start TEXT NOT NULL,
            week_end TEXT NOT NULL,
            output_path TEXT NOT NULL,           -- 合并文件路径
            total_people INTEGER DEFAULT 0,
            total_items INTEGER DEFAULT 0,
            risk_count INTEGER DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'generated',  -- generated/reviewed/delivered
            generated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            delivered_at TEXT,
            FOREIGN KEY (module_id) REFERENCES modules(id)
        );

        -- 周报库归档索引表
        CREATE TABLE IF NOT EXISTS report_archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT NOT NULL,
            week_end TEXT NOT NULL,
            module_id INTEGER,
            file_type TEXT NOT NULL DEFAULT 'individual',
            file_path TEXT NOT NULL,
            user_id INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (module_id) REFERENCES modules(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    conn.commit()
    conn.close()


def seed_data():
    """初始化种子数据"""
    conn = get_db()

    # 检查是否已有数据
    existing = conn.execute("SELECT COUNT(*) FROM modules").fetchone()[0]
    if existing > 0:
        conn.close()
        return

    # 创建 4 个模块
    modules = [
        ("国内运营商", "excel"),
        ("销售部", "excel"),
        ("营销运营部", "excel"),
        ("海外BD", "ppt"),
    ]
    for name, fmt in modules:
        conn.execute(
            "INSERT INTO modules (name, format) VALUES (?, ?)",
            (name, fmt)
        )

    # 创建管理员账号
    import hashlib
    admin_pw = hashlib.sha256("admin123".encode()).hexdigest()
    conn.execute(
        "INSERT INTO users (username, password_hash, display_name, role, is_superior) VALUES (?, ?, ?, ?, ?)",
        ("admin", admin_pw, "管理员", "admin", 0)
    )

    # 创建领导账号
    leader_pw = hashlib.sha256("leader123".encode()).hexdigest()
    conn.execute(
        "INSERT INTO users (username, password_hash, display_name, role, is_superior) VALUES (?, ?, ?, ?, ?)",
        ("leader", leader_pw, "领导", "member", 1)
    )

    # 创建团队 leader 示例
    leader_pw2 = hashlib.sha256("team123".encode()).hexdigest()
    conn.execute(
        "INSERT INTO users (username, password_hash, display_name, role, module_id) VALUES (?, ?, ?, ?, ?)",
        ("team_leader1", leader_pw2, "国内运营商负责人", "leader", 1)
    )

    # 创建成员示例
    member_pw = hashlib.sha256("123456".encode()).hexdigest()
    for i in range(1, 4):
        conn.execute(
            "INSERT INTO users (username, password_hash, display_name, role, module_id) VALUES (?, ?, ?, ?, ?)",
            (f"user{i}", member_pw, f"成员{i}", "member", 1)
        )

    conn.commit()
    conn.close()
    print("数据库初始化完成")


# ===== 便捷查询函数 =====

def get_current_week():
    """获取当前 ISO 周的起止日期"""
    today = datetime.now()
    # ISO 周：周一开始
    weekday = today.weekday()  # 0=周一, 6=周日
    monday = today - timedelta(days=weekday)
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


def get_user_by_username(username):
    """根据用户名获取用户"""
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)).fetchone()
    conn.close()
    return user


def get_module_members(module_id):
    """获取模块成员"""
    conn = get_db()
    members = conn.execute(
        "SELECT * FROM users WHERE module_id = ? AND role = 'member' AND is_active = 1",
        (module_id,)
    ).fetchall()
    conn.close()
    return members


def get_submission_status(module_id, week_start, week_end):
    """
    获取模块本周提交状态
    返回: {提交列表, 未提交列表}
    """
    conn = get_db()
    members = conn.execute(
        "SELECT * FROM users WHERE module_id = ? AND role = 'member' AND is_active = 1",
        (module_id,)
    ).fetchall()

    submitted = conn.execute(
        """SELECT s.*, u.display_name
           FROM submissions s
           JOIN users u ON s.user_id = u.id
           WHERE s.module_id = ? AND s.week_start = ? AND s.week_end = ?""",
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
        "rate": f"{len(submitted)}/{len(members)}"
    }


def check_deadline_passed():
    """检查是否已过截止时间（周日 24:00 = 周一 00:00）"""
    now = datetime.now()
    # 如果当前是周一或更晚，且在本周内，说明截止时间已过
    weekday = now.weekday()
    if weekday >= 1:  # 周二到周六
        return True, "截止时间已过，系统已锁定提交"
    elif weekday == 0:  # 周一
        # 周一零点后
        return True, "截止时间已过（周日24:00），系统已锁定提交"
    else:  # 周日
        return False, f"请在今晚 23:59 前提交周报"


def get_archive_files(role, user_id, module_id=None):
    """
    按角色获取周报库归档文件列表。
    member: 只看本人的 individual 文件
    leader: 本团队 individual + 本模块 module_summary
    admin/superior: 全部
    """
    conn = get_db()
    if role == "member":
        rows = conn.execute(
            """SELECT ra.*, m.name as module_name
               FROM report_archive ra
               LEFT JOIN modules m ON ra.module_id = m.id
               WHERE ra.user_id = ? AND ra.file_type = 'individual'
               ORDER BY ra.week_start DESC, ra.created_at DESC""",
            (user_id,)
        ).fetchall()
    elif role == "leader":
        rows = conn.execute(
            """SELECT ra.*, m.name as module_name
               FROM report_archive ra
               LEFT JOIN modules m ON ra.module_id = m.id
               WHERE ra.module_id = ?
                 AND ra.file_type IN ('individual', 'module_summary')
               ORDER BY ra.week_start DESC, ra.created_at DESC""",
            (module_id,)
        ).fetchall()
    else:  # admin, superior
        rows = conn.execute(
            """SELECT ra.*, m.name as module_name, u.display_name
               FROM report_archive ra
               LEFT JOIN modules m ON ra.module_id = m.id
               LEFT JOIN users u ON ra.user_id = u.id
               ORDER BY ra.week_start DESC, ra.created_at DESC"""
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_archive_record(week_start, week_end, module_id, file_type, file_path, user_id=None):
    """写入归档记录"""
    conn = get_db()
    conn.execute(
        """INSERT INTO report_archive (week_start, week_end, module_id, file_type, file_path, user_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (week_start, week_end, module_id, file_type, file_path, user_id)
    )
    conn.commit()
    conn.close()
