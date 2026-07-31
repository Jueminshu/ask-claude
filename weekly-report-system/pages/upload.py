"""上传周报页面 — 多文件上传 + 异步处理"""
import streamlit as st
from database_v2 import (
    get_current_week, create_submission, add_submission_file,
    enqueue_task, get_submission_with_files, get_db,
)
from services.deadline import get_deadline_info
from services.file_handler import save_uploaded_file, get_file_type, ALLOWED_EXTENSIONS


# 前端预识别关键词
KEYWORD_MAP = {
    "周报": ("周报", "weekly report"),
    "weekly report": ("周报", "weekly report"),
    "作战地图": ("作战地图", "battle map"),
    "battle map": ("作战地图", "battle map"),
    "拜访报告": ("拜访报告", "visit report"),
    "visit report": ("拜访报告", "visit report"),
    "会议纪要": ("会议纪要", "meeting minutes"),
    "meeting minutes": ("会议纪要", "meeting minutes"),
}


def _pre_identify(filename):
    """前端预识别文件名"""
    fname_lower = filename.lower()
    for kw, (label, kw_en) in KEYWORD_MAP.items():
        if kw in fname_lower or kw_en in fname_lower:
            return label
    return None


def render_upload_page(user):
    """渲染上传页面"""
    st.title("📤 上传周报")

    week_start, week_end = get_current_week()
    deadline_info = get_deadline_info()
    module_id = user.get("module_id")

    # 获取模块名
    conn = get_db()
    m = conn.execute("SELECT name FROM modules WHERE id = ?", (module_id,)).fetchone()
    module_name = m["name"] if m else "未分配"
    conn.close()

    st.markdown(f"**模块**: {module_name} | **周期**: {week_start} ~ {week_end}")
    st.info(f"⏰ {deadline_info['message']}")

    if deadline_info["is_passed"]:
        st.warning("⏰ 本周提交已截止，如需补交请联系团队 Leader。")
        return

    # 检查本周已有提交
    conn = get_db()
    existing_sub = conn.execute(
        """SELECT id FROM submissions
           WHERE user_id = ? AND week_start = ? AND is_latest = 1
           ORDER BY submitted_at DESC LIMIT 1""",
        (user["id"], week_start)
    ).fetchone()
    conn.close()

    if existing_sub:
        sub = get_submission_with_files(existing_sub["id"])
        if sub:
            status_label = {
                "submitted": "🟡 待 Leader 审核",
                "leader_approved": "✅ Leader 已通过",
                "leader_rejected": "🔴 已驳回",
            }.get(sub["status"], sub["status"])
            st.success(f"📋 本周已提交 — {status_label}")

            if sub["status"] == "leader_rejected":
                st.warning(f"驳回原因: {sub.get('leader_review_note', '无')}")
                st.info("请在截止时间前重新提交")

    # 上传区域
    uploaded_files = st.file_uploader(
        "拖拽或选择文件（支持多文件）",
        type=list(ALLOWED_EXTENSIONS),
        accept_multiple_files=True,
        help="支持 Excel / Word / PPT / PDF / 图片，可一次选择多个文件",
        key=f"upload_{week_start}",
    )

    if uploaded_files:
        st.markdown("── 已选择的文件 ──")
        for uf in uploaded_files:
            ftype = get_file_type(uf.name)
            pre_id = _pre_identify(uf.name)
            icon = "✅" if pre_id else "⚠️"
            label = pre_id or "待识别"

            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            col1.write(f"📎 {uf.name}")
            col2.write(f"{uf.size / 1024:.1f} KB")
            col3.write(f"📄 {ftype}")
            col4.write(f"{icon} {label}")

    if st.button("📤 提交周报", type="primary", use_container_width=True):
        if not uploaded_files:
            st.error("请先选择文件")
        else:
            _handle_submit(user, module_id, week_start, week_end, uploaded_files)


def _handle_submit(user, module_id, week_start, week_end, uploaded_files):
    """处理提交流程"""
    submission_id = None
    try:
        # 1. 创建提交记录
        submission_id = create_submission(user["id"], module_id, week_start, week_end)

        # 2. 保存每个文件 + 写入任务
        file_records = []
        for uf in uploaded_files:
            file_type = get_file_type(uf.name)
            file_path = save_uploaded_file(uf, week_start, module_id, user["id"])
            file_size = uf.size

            file_id = add_submission_file(
                submission_id, uf.name, file_path, file_type, file_size
            )
            file_records.append({"id": file_id, "name": uf.name, "type": file_type})

            # 入队后台处理任务
            enqueue_task(file_id, "process_full")

        st.success(f"✅ 上传成功！{len(file_records)} 个文件正在后台处理中...")

        # 显示处理状态
        st.markdown("### 📊 文件处理状态")
        for fr in file_records:
            st.write(f"📎 {fr['name']} — 🔄 处理中...")

        st.info("文件处理完成后即可在团队视图中预览。您可以关闭此页面。")
        st.rerun()
    except Exception as e:
        st.error(f"❌ 提交失败：{e}")
        if submission_id:
            st.warning(
                "提交记录已创建但文件保存失败，请联系管理员处理 "
                f"(submission_id={submission_id})"
            )
