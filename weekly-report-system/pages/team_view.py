"""团队视图页面 — Leader 查看团队提交概况"""
import streamlit as st
from database_v2 import get_db, get_current_week, get_submission_status, get_member_weekly_files, get_week_risks, get_support_items


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
            "submitted": "🟡 待审核",
            "leader_approved": "✅ 已通过",
            "leader_rejected": "🔴 已驳回",
        }.get(s["status"], s["status"])

        with st.expander(f"{s['display_name']} — {status_icon}"):
            try:
                files = get_member_weekly_files(s["user_id"], week_start)
                if not files:
                    st.caption("暂无文件")
                for f in files:
                    tname = f.get("template_name") or "未识别"
                    pstatus = {
                        "pending": "⏳ 处理中",
                        "ready": "✅ 就绪",
                        "error": "❌ 错误",
                    }.get(f["processing_status"], "❓")
                    st.write(f"📎 {f['filename']} — {tname} ({pstatus})")
            except Exception as e:
                st.error(f"加载文件失败：{e}")

    # 未提交
    if status_data["not_submitted"]:
        st.subheader("⚠️ 未提交")
        for m in status_data["not_submitted"]:
            st.write(f"• {m['display_name']}")

    # 风险与支持汇总
    st.divider()
    st.subheader("⚠️ 风险与支持汇总")

    try:
        risks = get_week_risks(week_start, module_id=module_id)
        support_items = get_support_items(week_start=week_start, module_id=module_id)

        # 合并为按成员分组的数据
        member_items = {}  # {display_name: [entries]}

        for r in risks:
            name = r.get("display_name") or f"用户{r['user_id']}"
            if name not in member_items:
                member_items[name] = []
            member_items[name].append({
                "type": "risk",
                "customer": r.get("customer"),
                "description": r.get("risk_description", ""),
                "severity": r.get("severity", "medium"),
            })

        for s in support_items:
            name = s.get("display_name") or f"用户{s['user_id']}"
            if name not in member_items:
                member_items[name] = []
            member_items[name].append({
                "type": "support",
                "customer": s.get("customer"),
                "description": s.get("support_description", ""),
            })

        if member_items:
            for member_name, items in member_items.items():
                for item in items:
                    prefix = "🔴" if item.get("severity") == "high" else "🟡"
                    type_label = "风险" if item["type"] == "risk" else "需支持"
                    customer_str = f"[{item['customer']}] " if item.get("customer") else ""
                    st.write(f"{prefix} **{member_name}**: {customer_str}{item['description'][:120]}  _{type_label}_")
        else:
            st.caption("本周暂无风险或支持事项")
    except Exception as e:
        st.caption(f"加载风险与支持汇总失败：{e}")
