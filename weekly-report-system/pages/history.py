"""提交历史页面"""
import streamlit as st
from database_v2 import get_db, get_current_week


def render_history_page(user):
    st.title("📋 提交历史")

    week_start, week_end = get_current_week()
    conn = get_db()

    try:
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
            return

        for s in submissions:
            status_emoji = {
                "submitted": "🟡",
                "leader_approved": "✅",
                "leader_rejected": "🔴",
            }.get(s["status"], "❓")

            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 2, 2])
                col1.markdown(
                    f"{status_emoji} **{s['week_start']} ~ {s['week_end']}** — {s['module_name']}"
                )
                if user["role"] != "member":
                    col1.markdown(f"*{s.get('display_name', '')}*")
                col2.markdown(f"状态: {s['status']}")
                col3.markdown(f"提交: {s['submitted_at']}")

                if s["status"] == "leader_rejected" and s.get("leader_review_note"):
                    st.caption(f"驳回原因: {s['leader_review_note']}")
    finally:
        conn.close()
