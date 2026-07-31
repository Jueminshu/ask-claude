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
