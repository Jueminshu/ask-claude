"""
营销运作部周报收集系统 — Web 应用
====================================
Streamlit 多页面应用

启动: streamlit run app.py
"""

import streamlit as st
import hashlib
import os
import sys
from datetime import datetime, timedelta

# 页面配置必须在最前面
st.set_page_config(
    page_title="营销运作部周报系统",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import (
    init_db, seed_data, get_db, get_user_by_username,
    get_current_week, get_submission_status, check_deadline_passed,
)
from merger.excel_merger import ExcelMerger


# ===== 初始化 =====
init_db()
seed_data()

# ===== 登录 =====
if "user" not in st.session_state:
    st.session_state.user = None
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False


def login_page():
    """登录页面"""
    st.markdown("<h1 style='text-align:center; margin-top:100px;'>📋 营销运作部周报系统</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:#666;'>请登录后使用</p>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("用户名", placeholder="请输入用户名")
            password = st.text_input("密码", type="password", placeholder="请输入密码")
            submitted = st.form_submit_button("登 录", use_container_width=True)

            if submitted:
                if not username or not password:
                    st.error("请输入用户名和密码")
                else:
                    user = get_user_by_username(username)
                    if user:
                        pw_hash = hashlib.sha256(password.encode()).hexdigest()
                        if pw_hash == user["password_hash"]:
                            st.session_state.user = dict(user)
                            st.session_state.authenticated = True
                            st.rerun()
                        else:
                            st.error("密码错误")
                    else:
                        st.error("用户不存在")

    st.markdown("<p style='text-align:center; color:#999; margin-top:30px;'>默认管理员: admin / admin123 | 成员: user1 / 123456</p>", unsafe_allow_html=True)


# ===== 主界面 =====
def main_app():
    user = st.session_state.user
    role = user["role"]
    module_id = user.get("module_id")

    # 侧边栏
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/report-file.png", width=48) if False else st.markdown("## 📋")
        st.markdown(f"### {user['display_name']}")
        st.caption(f"角色: {_role_label(role)}")

        st.divider()

        # 当前周期
        week_start, week_end = get_current_week()
        st.markdown(f"**📅 本周**: {week_start} ~ {week_end}")
        st.markdown(f"**⏰ 截止**: 周日 23:59")

        st.divider()

        # 导航
        page = st.radio(
            "导航",
            _get_pages(role),
            label_visibility="collapsed",
        )

        st.divider()

        if st.button("🚪 退出登录", use_container_width=True):
            st.session_state.user = None
            st.session_state.authenticated = False
            st.rerun()

    # 页面路由
    if "周报库" in page:
        from archive_page import render_archive_page
        render_archive_page(user)
    elif "上传周报" in page:
        upload_page(user, week_start, week_end)
    elif "审核周报" in page:
        review_page(user, week_start, week_end)
    elif "团队周报" in page:
        team_view_page(user, week_start, week_end)
    elif "提交历史" in page:
        history_page(user)
    elif "系统管理" in page:
        admin_page()


def _role_label(role):
    return {"admin": "🔧 管理员", "leader": "👤 团队负责人", "member": "👤 成员"}.get(role, role)


def _get_pages(role):
    pages = []
    pages.append("📤 上传周报")
    pages.append("📚 周报库")
    pages.append("📋 提交历史")

    if role == "admin":
        pages.append("✅ 审核周报")
        pages.append("👥 团队周报")
        pages.append("🔧 系统管理")
    elif role == "leader":
        pages.append("👥 团队周报")

    return pages


# ===== 上传周报页面 =====
def upload_page(user, week_start, week_end):
    st.title("📤 上传周报")

    module_name = _get_module_name(user.get("module_id"))
    st.markdown(f"**模块**: {module_name} | **周期**: {week_start} ~ {week_end}")

    # 检查截止时间
    deadline_passed, deadline_msg = check_deadline_passed()
    if deadline_passed:
        st.warning(f"⏰ {deadline_msg}")
        st.info("如需补交，请联系管理员。")
        return

    # 检查是否已提交
    conn = get_db()
    existing = conn.execute(
        "SELECT * FROM submissions WHERE user_id = ? AND week_start = ? AND week_end = ?",
        (user["id"], week_start, week_end)
    ).fetchall()
    conn.close()

    if existing:
        st.success("✅ 你已提交本周周报")
        for s in existing:
            status_label = {"submitted": "已提交", "reviewed": "审核中", "approved": "已通过", "rejected": "需修改"}.get(s["status"], s["status"])
            st.info(f"📎 {s['filename']} — {status_label} (提交于 {s['submitted_at']})")

            # 如果被驳回，允许重新上传
            if s["status"] == "rejected":
                st.warning(f"驳回原因: {s['notes'] or '无'}")

    # 上传区域
    if not deadline_passed:
        with st.form("upload_form", clear_on_submit=True):
            uploaded_file = st.file_uploader(
                "选择周报文件（Excel）",
                type=["xlsx", "xls"],
                help="请上传基于模板填写的周报 Excel 文件",
            )

            if st.form_submit_button("📤 提交周报", use_container_width=True, type="primary"):
                if uploaded_file is None:
                    st.error("请先选择文件")
                else:
                    # 验证文件
                    if not uploaded_file.name.endswith((".xlsx", ".xls")):
                        st.error("仅支持 Excel 文件 (.xlsx / .xls)")
                    else:
                        # 保存文件
                        upload_dir = os.path.join(
                            os.path.dirname(os.path.abspath(__file__)),
                            "data", "uploads",
                            week_start,
                            str(user["module_id"] or 1)
                        )
                        os.makedirs(upload_dir, exist_ok=True)
                        file_path = os.path.join(upload_dir, f"{user['display_name']}_{uploaded_file.name}")
                        with open(file_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())

                        # 记录提交
                        conn = get_db()
                        conn.execute(
                            """INSERT INTO submissions
                               (user_id, module_id, week_start, week_end, filename, file_path, status)
                               VALUES (?, ?, ?, ?, ?, ?, 'submitted')""",
                            (user["id"], user.get("module_id") or 1, week_start, week_end, uploaded_file.name, file_path)
                        )
                        conn.commit()
                        conn.close()

                        st.success("✅ 周报提交成功！")
                        st.rerun()

    # 本周提交状态
    st.divider()
    st.subheader("📊 本周提交情况")
    if user.get("module_id"):
        status = get_submission_status(user["module_id"], week_start, week_end)
        col1, col2, col3 = st.columns(3)
        col1.metric("应提交", status["total"])
        col2.metric("已提交", status["submitted_count"])
        col3.metric("未提交", status["total"] - status["submitted_count"])


# ===== 审核周报页面（管理员） =====
def review_page(user, week_start, week_end):
    st.title("✅ 审核周报")

    # 获取所有模块
    conn = get_db()
    modules = conn.execute("SELECT * FROM modules").fetchall()

    selected_module = st.selectbox(
        "选择模块",
        [m["id"] for m in modules],
        format_func=lambda x: _get_module_name(x),
    )

    if selected_module:
        status_data = get_submission_status(selected_module, week_start, week_end)

        st.markdown(f"### 📊 {_get_module_name(selected_module)}")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("应提交", status_data["total"])
        col2.metric("已提交", status_data["submitted_count"])
        col3.metric("未提交", status_data["total"] - status_data["submitted_count"])

        # 审核状态
        reviewed_count = sum(1 for s in status_data["submitted"] if s["status"] in ("reviewed", "approved"))
        col4.metric("已审核", reviewed_count)

        st.divider()

        # 未提交名单
        if status_data["not_submitted"]:
            with st.expander(f"⚠️ 未提交人员 ({len(status_data['not_submitted'])}人)", expanded=False):
                for m in status_data["not_submitted"]:
                    st.write(f"• {m['display_name']} ({m['username']})")

        # 已提交列表
        st.subheader("📋 已提交周报")
        for s in status_data["submitted"]:
            status_label = {"submitted": "🟡 待审核", "reviewed": "🟢 已审核", "approved": "✅ 已通过", "rejected": "🔴 需修改"}.get(s["status"], s["status"])

            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 1, 2])
                col1.markdown(f"**{s['display_name']}** — {s['filename']} ({s['row_count']}条)")
                col2.markdown(status_label)

                if s["status"] == "submitted":
                    if col3.button("✅ 通过", key=f"approve_{s['id']}"):
                        conn2 = get_db()
                        conn2.execute(
                            "UPDATE submissions SET status='approved', reviewed_by=?, reviewed_at=datetime('now','localtime') WHERE id=?",
                            (user["id"], s["id"])
                        )
                        conn2.commit()
                        conn2.close()
                        st.rerun()

                    if col3.button("🔴 驳回", key=f"reject_{s['id']}"):
                        # 这里简化处理，实际可弹出输入框
                        conn2 = get_db()
                        conn2.execute(
                            "UPDATE submissions SET status='rejected', reviewed_by=?, reviewed_at=datetime('now','localtime'), notes='请修改后重新提交' WHERE id=?",
                            (user["id"], s["id"])
                        )
                        conn2.commit()
                        conn2.close()
                        st.rerun()
                elif s["status"] == "approved":
                    col3.caption(f"✅ 已通过 (审核时间: {s.get('reviewed_at', 'N/A')})")

    conn.close()

    # 生成汇总按钮
    st.divider()
    if st.button("📊 生成本周汇总", type="primary", use_container_width=True):
        with st.spinner("正在生成汇总..."):
            all_outputs = []
            for m in modules:
                merger = ExcelMerger(str(m["id"]))
                output_path = merger.merge_from_uploads(m["id"], week_start, week_end)
                if output_path:
                    all_outputs.append(output_path)
            if all_outputs:
                st.success(f"✅ 已生成 {len(all_outputs)} 个模块汇总")
                for p in all_outputs:
                    st.write(f"📎 {p}")
            else:
                st.warning("未找到可汇总的数据")


# ===== 团队周报页面 =====
def team_view_page(user, week_start, week_end):
    st.title("👥 团队周报")

    module_id = user.get("module_id")

    # admin 可以看到所有模块
    if user["role"] == "admin":
        conn = get_db()
        modules = conn.execute("SELECT * FROM modules").fetchall()
        conn.close()
        module_id = st.selectbox(
            "选择模块",
            [m["id"] for m in modules],
            format_func=lambda x: _get_module_name(x),
            key="team_view_module"
        )

    if module_id:
        status_data = get_submission_status(module_id, week_start, week_end)

        st.markdown(f"### {_get_module_name(module_id)} — {week_start} ~ {week_end}")

        col1, col2, col3 = st.columns(3)
        col1.metric("应提交", status_data["total"])
        col2.metric("已提交", status_data["submitted_count"])
        col3.metric("提交率", f"{round(status_data['submitted_count'] / max(status_data['total'], 1) * 100)}%")

        # 已提交详细
        st.subheader("已提交")
        for s in status_data["submitted"]:
            with st.container(border=True):
                st.markdown(f"**{s['display_name']}** — {s['filename']} ({s['row_count']}条)")
                st.caption(f"提交时间: {s['submitted_at']} | 状态: {s['status']}")

        # 未提交
        if status_data["not_submitted"]:
            st.subheader("⚠️ 未提交")
            for m in status_data["not_submitted"]:
                st.write(f"• {m['display_name']}")


# ===== 提交历史页面 =====
def history_page(user):
    st.title("📋 提交历史")

    conn = get_db()
    week_start, week_end = get_current_week()

    # 获取用户的历史提交
    if user["role"] == "member":
        submissions = conn.execute(
            """SELECT s.*, m.name as module_name
               FROM submissions s
               JOIN modules m ON s.module_id = m.id
               WHERE s.user_id = ?
               ORDER BY s.submitted_at DESC
               LIMIT 20""",
            (user["id"],)
        ).fetchall()
    else:
        submissions = conn.execute(
            """SELECT s.*, m.name as module_name, u.display_name
               FROM submissions s
               JOIN modules m ON s.module_id = m.id
               JOIN users u ON s.user_id = u.id
               ORDER BY s.submitted_at DESC
               LIMIT 50"""
        ).fetchall()

    if submissions:
        for s in submissions:
            status_emoji = {"submitted": "🟡", "reviewed": "🟢", "approved": "✅", "rejected": "🔴"}.get(s["status"], "❓")
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 2, 2])
                col1.markdown(f"{status_emoji} **{s['filename']}** — {s['module_name']}")
                if user["role"] != "member":
                    col1.markdown(f"*{s.get('display_name', '')}*")
                col2.markdown(f"周期: {s['week_start']} ~ {s['week_end']}")
                col3.markdown(f"提交时间: {s['submitted_at']}")
    else:
        st.info("暂无提交记录")

    conn.close()


# ===== 系统管理页面（管理员） =====
def admin_page():
    st.title("🔧 系统管理")

    tab1, tab2, tab3 = st.tabs(["用户管理", "模块设置", "截止时间"])

    with tab1:
        st.subheader("用户列表")
        conn = get_db()
        users = conn.execute(
            """SELECT u.*, m.name as module_name
               FROM users u LEFT JOIN modules m ON u.module_id = m.id
               WHERE u.is_active = 1"""
        ).fetchall()

        for u in users:
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
                col1.markdown(f"**{u['display_name']}** ({u['username']})")
                col2.markdown(f"模块: {u.get('module_name', '未分配')}")
                col3.markdown(_role_label(u["role"]))
                if u["is_superior"]:
                    col4.markdown("👔 领导")

        conn.close()

    with tab2:
        st.subheader("模块列表")
        conn = get_db()
        modules = conn.execute("SELECT * FROM modules").fetchall()
        for m in modules:
            with st.container(border=True):
                st.markdown(f"**{m['name']}** — 格式: {m['format']} | 截止: 周{m['deadline_day']} {m['deadline_time']}")
        conn.close()

    with tab3:
        st.subheader("截止时间设置")
        st.info("当前设置: 每周日 23:59 截止提交")
        st.caption("修改截止时间功能待开发")


def _get_module_name(module_id):
    if not module_id:
        return "未分配"
    conn = get_db()
    m = conn.execute("SELECT name FROM modules WHERE id = ?", (module_id,)).fetchone()
    conn.close()
    return m["name"] if m else "未知"


# ===== 入口 =====
if not st.session_state.authenticated:
    login_page()
else:
    main_app()
