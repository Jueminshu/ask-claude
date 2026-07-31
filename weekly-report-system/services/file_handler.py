"""文件存储服务 — 抽象层（当前本地磁盘，预留云存储接口）"""
import os
from datetime import datetime


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
PREVIEWS_DIR = os.path.join(DATA_DIR, "previews")


def get_upload_dir(week_start, module_id, user_id):
    """获取上传文件存储目录"""
    d = os.path.join(UPLOADS_DIR, week_start, str(module_id), str(user_id))
    os.makedirs(d, exist_ok=True)
    return d


def get_preview_dir(week_start, module_id, user_id):
    """获取预览 PDF 存储目录"""
    d = os.path.join(PREVIEWS_DIR, week_start, str(module_id), str(user_id))
    os.makedirs(d, exist_ok=True)
    return d


def save_uploaded_file(uploaded_file_obj, week_start, module_id, user_id) -> str:
    """
    保存上传文件到磁盘。

    Args:
        uploaded_file_obj: Streamlit UploadedFile 对象
        week_start: 周起始日期
        module_id: 模块 ID
        user_id: 用户 ID

    Returns:
        文件完整路径
    """
    upload_dir = get_upload_dir(week_start, module_id, user_id)
    # 防止文件名冲突：加时间戳前缀
    timestamp = datetime.now().strftime("%H%M%S")
    safe_name = f"{timestamp}_{uploaded_file_obj.name}"
    file_path = os.path.join(upload_dir, safe_name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file_obj.getbuffer())
    return file_path


def delete_file(file_path):
    """删除文件（物理删除）"""
    if os.path.exists(file_path):
        os.remove(file_path)


ALLOWED_EXTENSIONS = {
    "xlsx", "xls", "pptx", "ppt", "docx", "doc",
    "pdf", "jpg", "jpeg", "png", "gif", "bmp",
}


def get_file_type(filename):
    """根据扩展名确定文件类型"""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("xlsx", "xls"):
        return "xlsx"
    if ext in ("pptx", "ppt"):
        return "pptx"
    if ext in ("docx", "doc"):
        return "docx"
    if ext == "pdf":
        return "pdf"
    if ext in ("jpg", "jpeg", "png", "gif", "bmp"):
        return "image"
    return "other"
