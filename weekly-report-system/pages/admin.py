"""系统管理页面"""
import streamlit as st
from database_v2 import get_db


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
                role_labels = {
                    "admin": "🔧 管理员",
                    "leader": "👤 Leader",
                    "member": "👤 Member",
                    "superior": "👔 部门领导",
                }
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
