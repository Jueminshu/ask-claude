"""领导查阅页 — Streamlit ←→ 嵌入式 HTML 组件桥接"""
import streamlit as st
import json
import os
from database_v2 import (
    get_db, get_current_week, get_member_weekly_files,
    get_file_interactions, add_interaction,
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
    result = st.components.v1.html(full_html, height=800)

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
            try:
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
            except Exception:
                pass  # 重复点赞静默忽略

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
        st.components.v1.html(files_script, height=0)
