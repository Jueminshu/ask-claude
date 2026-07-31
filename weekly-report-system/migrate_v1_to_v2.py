"""v1.0 -> v2.0 数据迁移脚本"""
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

    # 迁移用户数据（映射 role: leader->leader, member->member, admin->admin, is_superior->superior）
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

    # 填充种子模板数据（seed_data 会检测 modules 已有数据 -> 跳过模块和用户的插入，但要补模板）
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
