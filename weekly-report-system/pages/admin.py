"""系统管理页面"""
import streamlit as st
from database_v2 import get_db, create_user, update_user, deactivate_user, get_all_users
import hashlib


def render_admin_page():
    st.title("🔧 系统管理")

    tab1, tab2, tab3 = st.tabs(["用户管理", "模块设置", "文件模板"])

    with tab1:
        st.subheader("用户列表")

        # 获取模块列表（新增和编辑共用）
        conn = get_db()
        modules = conn.execute("SELECT id, name FROM modules ORDER BY id").fetchall()
        conn.close()
        module_options = {m["name"]: m["id"] for m in modules}

        # === 新增用户表单 ===
        with st.expander("➕ 新增用户", expanded=False):
            with st.form("new_user_form"):
                col1, col2 = st.columns(2)
                new_username = col1.text_input("用户名 *", key="new_username")
                new_display = col2.text_input("显示名 *", key="new_display")
                new_password = col1.text_input("密码 *", type="password", key="new_password")
                new_role = col2.selectbox("角色 *", ["member", "leader", "superior"], key="new_role")
                new_module = col1.selectbox("所属模块", list(module_options.keys()), key="new_module")
                new_can_browse = col2.checkbox("全模块浏览权限", key="new_can_browse")

                if st.form_submit_button("创建用户", use_container_width=True):
                    if not new_username or not new_display or not new_password:
                        st.error("用户名、显示名、密码为必填项")
                    else:
                        pw_hash = hashlib.sha256(new_password.encode()).hexdigest()
                        uid = create_user(
                            new_username, pw_hash, new_display, new_role,
                            module_options[new_module], 1 if new_can_browse else 0
                        )
                        if uid:
                            st.success(f"用户 {new_display} 创建成功")
                            st.rerun()
                        else:
                            st.error("用户名已存在")

        # === 用户列表 ===
        users = get_all_users(include_inactive=False)
        role_labels = {
            "admin": "🔧 管理员", "leader": "👤 Leader",
            "member": "👤 Member", "superior": "👔 部门领导",
        }

        for u in users:
            with st.container(border=True):
                if st.session_state.get(f"editing_{u['id']}", False):
                    # 编辑模式
                    with st.form(f"edit_user_{u['id']}"):
                        col1, col2, col3 = st.columns(3)
                        new_display = col1.text_input("显示名", value=u["display_name"], key=f"ed_name_{u['id']}")
                        new_role = col2.selectbox("角色", ["member", "leader", "superior"],
                            index=["member", "leader", "superior"].index(u["role"]) if u["role"] in ["member", "leader", "superior"] else 0,
                            key=f"ed_role_{u['id']}")
                        new_module_name = col3.selectbox("模块", list(module_options.keys()),
                            index=list(module_options.values()).index(u["module_id"]) if u["module_id"] in module_options.values() else 0,
                            key=f"ed_mod_{u['id']}")
                        new_cba = st.checkbox("全模块浏览", value=bool(u.get("can_browse_all")), key=f"ed_cba_{u['id']}")
                        new_pw = st.text_input("新密码（留空不修改）", type="password", key=f"ed_pw_{u['id']}")

                        c1, c2 = st.columns(2)
                        if c1.form_submit_button("💾 保存", use_container_width=True):
                            fields = {
                                "display_name": new_display,
                                "role": new_role,
                                "module_id": module_options[new_module_name],
                                "can_browse_all": 1 if new_cba else 0,
                            }
                            if new_pw.strip():
                                fields["password_hash"] = hashlib.sha256(new_pw.encode()).hexdigest()
                            update_user(u["id"], **fields)
                            st.session_state[f"editing_{u['id']}"] = False
                            st.success("已保存")
                            st.rerun()
                        if c2.form_submit_button("❌ 取消", use_container_width=True):
                            st.session_state[f"editing_{u['id']}"] = False
                            st.rerun()
                else:
                    # 查看模式
                    col1, col2, col3, col4, col5 = st.columns([2, 2, 1, 1, 1])
                    col1.markdown(f"**{u['display_name']}** ({u['username']})")
                    col2.markdown(f"模块: {u.get('module_name', '未分配')}")
                    col3.markdown(role_labels.get(u["role"], u["role"]))
                    if u.get("can_browse_all"):
                        col4.markdown("🌐 全模块")

                    # 编辑按钮（admin 不可被编辑）
                    if u["role"] != "admin":
                        if col5.button("✏️ 编辑", key=f"btn_ed_{u['id']}"):
                            st.session_state[f"editing_{u['id']}"] = True
                            st.rerun()

                    # 停用按钮（admin 不可停用自己）
                    if u["role"] != "admin":
                        if col5.button("🗑️ 停用", key=f"btn_del_{u['id']}"):
                            deactivate_user(u["id"])
                            st.warning(f"已停用用户 {u['display_name']}")
                            st.rerun()

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
