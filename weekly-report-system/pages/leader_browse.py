"""领导查阅页 — Streamlit ←→ 嵌入式 HTML 组件桥接"""
import streamlit as st
import json
import os
from database_v2 import (
    get_db, get_current_week, get_member_weekly_files,
    get_file_interactions, add_interaction, get_week_risks,
    get_market_intel,
)
from services.notification import on_superior_interact


STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
ANALYSIS_HTML_PATH = os.path.join(STATIC_DIR, "analysis_dashboard.html")


def _prepare_analysis_data(week_start):
    """准备分析看板所需的全部数据"""
    conn = get_db()
    risks = get_week_risks(week_start)
    all_modules = conn.execute("SELECT id, name FROM modules ORDER BY id").fetchall()
    conn.close()

    modules_data = [{"id": m["id"], "name": m["name"]} for m in all_modules]

    return {
        "risks": risks,
        "modules": modules_data,
        "weekStart": week_start,
    }


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


def _get_prev_week(week_start_str):
    """计算前一周的周一日期"""
    from datetime import datetime, timedelta
    dt = datetime.strptime(week_start_str, "%Y-%m-%d")
    prev = dt - timedelta(days=7)
    return prev.strftime("%Y-%m-%d")


def _prepare_market_intel_data(week_start):
    """准备市场情报数据"""
    conn = get_db()
    all_modules = conn.execute("SELECT id, name FROM modules ORDER BY id").fetchall()
    conn.close()

    intel_data = get_market_intel()

    # 计算本周新增
    prev_week_start = _get_prev_week(week_start)
    prev_data = get_market_intel(week_start=prev_week_start) if prev_week_start else []
    prev_keys = {(r["vendor"] or "", r["model"] or "") for r in prev_data}

    for r in intel_data:
        key = (r["vendor"] or "", r["model"] or "")
        r["is_new"] = 1 if (key not in prev_keys and r["week_start"] == week_start) else 0

    return {
        "intel": intel_data,
        "modules": [{"id": m["id"], "name": m["name"]} for m in all_modules],
        "weekStart": week_start,
    }


def render_leader_browse_page(user):
    """渲染领导查阅页"""
    st.title("📊 领导查阅")

    week_start, week_end = get_current_week()

    tab1, tab2, tab3 = st.tabs(["📋 周报查阅", "📊 分析看板", "📡 市场情报"])

    with tab1:
        _render_browse_tab(user, week_start, week_end)

    with tab2:
        st.caption(f"数据周期: {week_start} ~ {week_end}")
        analysis_data = _prepare_analysis_data(week_start)

        if os.path.exists(ANALYSIS_HTML_PATH):
            with open(ANALYSIS_HTML_PATH, "r", encoding="utf-8") as f:
                analysis_html = f.read()
        else:
            st.warning("分析看板组件文件未找到")
            return

        inject_script = f"""
        <script>
        window.addEventListener('DOMContentLoaded', function() {{
            window.postMessage({{type: 'analysisData', payload: {json.dumps(analysis_data, ensure_ascii=False, default=str)}}}, '*');
        }});
        </script>
        """
        full_html = analysis_html.replace("</body>", inject_script + "</body>")
        st.components.v1.html(full_html, height=900)

    with tab3:
        st.caption(f"数据周期: {week_start} ~ {week_end}")
        mi_data = _prepare_market_intel_data(week_start)

        html_path = os.path.join(STATIC_DIR, "market_intel.html")
        if os.path.exists(html_path):
            with open(html_path, "r", encoding="utf-8") as f:
                mi_html = f.read()
        else:
            st.warning("市场情报组件文件未找到")
            return

        inject_script = f"""
        <script>
        window.addEventListener('DOMContentLoaded', function() {{
            window.postMessage({{type: 'marketIntelData', payload: {json.dumps(mi_data, ensure_ascii=False, default=str)}}}, '*');
        }});
        </script>
        """
        full_html = mi_html.replace("</body>", inject_script + "</body>")
        st.components.v1.html(full_html, height=900)


def _render_browse_tab(user, week_start, week_end):
    """Tab 1: 周报查阅 — 原有完整逻辑"""
    # 获取可访问的模块
    conn = get_db()
    all_modules = conn.execute("SELECT * FROM modules ORDER BY id").fetchall()
    conn.close()

    modules_data = [{"id": m["id"], "name": m["name"]} for m in all_modules]
    default_module_id = all_modules[0]["id"] if all_modules else None

    all_members = []
    for m in all_modules:
        members = _get_all_members_status(m["id"], week_start)
        all_members.extend(members)

    html_path = os.path.join(STATIC_DIR, "superior_browse.html")
    if not os.path.exists(html_path):
        st.warning("查阅组件文件未找到")
        return

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    init_data = {
        "modules": modules_data,
        "members": all_members,
        "currentModuleId": default_module_id,
        "weekStart": week_start,
        "weekEnd": week_end,
        "superiorId": user["id"],
        "superiorName": user["display_name"],
    }

    inject_script = f"""
    <script>
    window.addEventListener('DOMContentLoaded', function() {{
        window.postMessage({{type: 'init', payload: {json.dumps(init_data, ensure_ascii=False)}}}, '*');
    }});
    </script>
    """
    full_html = html_content.replace("</body>", inject_script + "</body>")

    result = st.components.v1.html(full_html, height=800)

    if result and isinstance(result, dict):
        action = result.get("action")

        if action == "getFiles":
            uid = result["user_id"]
            files = _get_files_with_interactions(uid, result["week_start"])
            st.session_state["_browse_files"] = files
            st.session_state["_browse_user_id"] = uid
            st.rerun()

        elif action == "like":
            file_id = result["file_id"]
            try:
                add_interaction(file_id, user["id"], "like")
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
                pass

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
            st.rerun()

    if "_browse_files" in st.session_state:
        files_data = st.session_state.pop("_browse_files")
        files_script = f"""
        <script>
        window.postMessage({{type: 'filesData', payload: {{files: {json.dumps(files_data, ensure_ascii=False, default=str)}}}}}, '*');
        </script>
        """
        st.components.v1.html(files_script, height=0)
