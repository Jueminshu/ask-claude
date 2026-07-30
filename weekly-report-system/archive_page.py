"""
周报库页面
按角色展示归档周报，支持按周筛选和下载
"""
import os
import streamlit as st
from database import get_archive_files, get_db


def render_archive_page(user):
    """渲染周报库页面"""
    st.title("📚 周报库")

    role = user["role"]
    module_id = user.get("module_id")

    # 获取所有历史周期（从 archive 表和 submissions 表）
    conn = get_db()
    weeks = conn.execute(
        """SELECT DISTINCT week_start, week_end FROM report_archive
           UNION
           SELECT DISTINCT week_start, week_end FROM submissions
           ORDER BY week_start DESC"""
    ).fetchall()
    conn.close()

    if not weeks:
        st.info("暂无归档数据")
        return

    # 周期筛选
    week_options = [f"{w['week_start']} ~ {w['week_end']}" for w in weeks]
    selected_week = st.selectbox("选择周期", week_options)

    if selected_week:
        week_start, week_end = selected_week.split(" ~ ")

        # 按角色加载归档文件
        records = get_archive_files(role, user["id"], module_id)

        # 过滤当前选中的周期
        filtered = [r for r in records
                    if r["week_start"] == week_start and r["week_end"] == week_end]

        if not filtered:
            st.info(f"该周期暂无归档文件")
            return

        # 分组展示
        individual_files = [r for r in filtered if r["file_type"] == "individual"]
        summary_files = [r for r in filtered if r["file_type"] == "module_summary"]
        total_files = [r for r in filtered if r["file_type"] == "total_summary"]

        # 个人周报
        if individual_files:
            st.subheader("📄 个人周报")
            for r in individual_files:
                with st.container(border=True):
                    col1, col2 = st.columns([3, 1])
                    col1.markdown(f"**{r.get('display_name', '成员')}** — {r.get('module_name', '')}")
                    col1.caption(f"上传时间: {r['created_at']}")
                    _file_download_button(col2, r["file_path"])

        # 团队汇总
        if summary_files:
            st.subheader("📊 模块汇总")
            for r in summary_files:
                with st.container(border=True):
                    col1, col2 = st.columns([3, 1])
                    col1.markdown(f"**{r.get('module_name', '')}** — 周期: {r['week_start']}~{r['week_end']}")
                    _file_download_button(col2, r["file_path"])

        # 总汇总
        if total_files:
            st.subheader("📋 四模块总汇总")
            for r in total_files:
                with st.container(border=True):
                    col1, col2 = st.columns([3, 1])
                    col1.markdown(f"**营销运作部总汇总** — {r['week_start']}~{r['week_end']}")
                    _file_download_button(col2, r["file_path"])


def _file_download_button(col, file_path):
    """渲染下载按钮（如果文件存在）"""
    if os.path.exists(file_path):
        fname = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            col.download_button(
                label="📥 下载",
                data=f,
                file_name=fname,
                key=f"dl_{file_path}",
            )
    else:
        col.caption("文件已删除")
