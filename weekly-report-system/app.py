"""
营销运作部周报收集系统 v2.0 — Web 应用
========================================
Streamlit 多页面应用
启动: streamlit run app.py
"""
import streamlit as st
import hashlib
import os
import sys

st.set_page_config(
    page_title="营销运作部周报系统 v2.0",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database_v2 import (
    init_db, seed_data, get_user_by_username, get_current_week,
)
from services.auth import ROLE_LABELS
from services.deadline import get_deadline_info
from worker import start_worker

# ===== 初始化 =====
init_db()
seed_data()
start_worker()

# ===== 会话状态 =====
if "user" not in st.session_state:
    st.session_state.user = None
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False


def login_page():
    st.markdown(
        "<h1 style='text-align:center; margin-top:100px;'>📋 营销运作部周报系统</h1>",
        unsafe_allow_html=True,
    )
    st.markdown("<p style='text-align:center; color:#666;'>v2.0 · 请登录</p>", unsafe_allow_html=True)

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

    st.markdown(
        "<p style='text-align:center; color:#999; margin-top:30px;'>"
        "管理员: admin/admin123 | 领导: superior/leader123 | Leader: leader_domestic/team123 | 成员: user1_1/123456"
        "</p>",
        unsafe_allow_html=True,
    )


def main_app():
    user = st.session_state.user
    role = user["role"]

    with st.sidebar:
        st.markdown("## 📋 周报系统 v2.0")
        st.markdown(f"### {user['display_name']}")
        st.caption(f"角色: {ROLE_LABELS.get(role, role)}")
        st.divider()

        week_start, week_end = get_current_week()
        deadline_info = get_deadline_info(user.get("module_id"))
        st.markdown(f"**📅 本周**: {week_start} ~ {week_end}")
        st.markdown(f"**⏰ 截止**: {deadline_info['deadline']}")
        st.divider()

        page = st.radio("导航", _get_pages(user), label_visibility="collapsed")
        st.divider()

        if st.button("🚪 退出登录", use_container_width=True):
            st.session_state.user = None
            st.session_state.authenticated = False
            st.rerun()

    # 路由
    from pages.upload import render_upload_page
    from pages.review import render_review_page
    from pages.team_view import render_team_view_page
    from pages.history import render_history_page
    from pages.leader_browse import render_leader_browse_page
    from pages.admin import render_admin_page

    if "上传周报" in page:
        render_upload_page(user)
    elif "审核周报" in page:
        render_review_page(user)
    elif "团队周报" in page:
        render_team_view_page(user)
    elif "提交历史" in page:
        render_history_page(user)
    elif "领导查阅" in page:
        render_leader_browse_page(user)
    elif "系统管理" in page:
        render_admin_page()


def _get_pages(user):
    role = user["role"]
    pages = []
    if role in ("member", "leader"):
        pages.append("📤 上传周报")
    if role in ("member", "leader"):
        pages.append("📋 提交历史")
    if role == "leader":
        pages.append("👥 团队周报")
        pages.append("✅ 审核周报")
    if role == "superior" or (role == "leader" and user.get("can_browse_all")):
        pages.append("📊 领导查阅")
    if role == "admin":
        pages.append("🔧 系统管理")
    return pages


# ===== 入口 =====
if not st.session_state.authenticated:
    login_page()
else:
    main_app()
