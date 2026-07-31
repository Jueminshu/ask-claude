"""文件解析服务 — 文本提取 + 模板识别 + PDF 转换"""
import os
import json
import subprocess
from database_v2 import get_db as _get_db_conn


# 使用 officecli 提取文本
def extract_text(file_path, file_type):
    """
    调用 officecli 提取文件文本内容。
    返回: str 或 None
    """
    try:
        # officecli view <file> text 提取文本
        result = subprocess.run(
            ["officecli", "view", file_path, "text"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return f"[EXTRACTION FAILED] {result.stderr}"
    except FileNotFoundError:
        # officecli 未安装，返回空
        return "[OFFICECLI NOT AVAILABLE]"
    except subprocess.TimeoutExpired:
        return "[EXTRACTION TIMEOUT]"


# 使用 officecli 或 LibreOffice 转 PDF
def convert_to_pdf(file_path, output_dir, file_type):
    """
    将 Office 文件转换为 PDF 预览。
    PDF 和图片文件跳过转换，直接返回原路径。

    返回: preview_path 或 None（转换失败）
    """
    if file_type in ("pdf", "image"):
        return file_path  # 无需转换

    base_name = os.path.splitext(os.path.basename(file_path))[0]
    pdf_path = os.path.join(output_dir, f"{base_name}.pdf")

    try:
        # 优先用 officecli
        result = subprocess.run(
            ["officecli", "convert", file_path, pdf_path, "--format", "pdf"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0 and os.path.exists(pdf_path):
            return pdf_path
    except FileNotFoundError:
        pass

    # 回退到 LibreOffice（如果可用）
    try:
        result = subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf",
             "--outdir", output_dir, file_path],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0 and os.path.exists(pdf_path):
            return pdf_path
    except FileNotFoundError:
        pass

    return None


# 模板识别
def identify_template(filename, extracted_text, module_id):
    """
    识别文件模板类型。

    Args:
        filename: 文件名
        extracted_text: 提取的文本内容
        module_id: 模块 ID

    Returns:
        (template_id, confidence) 或 (None, 0.0)
    """
    conn = _get_db_conn()
    templates = conn.execute(
        "SELECT * FROM file_templates WHERE module_id = ?", (module_id,)
    ).fetchall()
    conn.close()

    if not templates:
        return None, 0.0

    best_template = None
    best_score = 0.0

    for t in templates:
        score = 0.0

        # 1. 文件名关键词匹配（权重 0.5）
        if t["filename_keywords"]:
            keywords = [k.strip().lower() for k in t["filename_keywords"].split(",")]
            matched_kw = 0
            fname_lower = filename.lower()
            for kw in keywords:
                if kw in fname_lower:
                    matched_kw += 1
            if keywords:
                score += 0.5 * (matched_kw / len(keywords))

        # 2. 结构匹配（权重 0.5）
        if t["structure_rules"] and extracted_text:
            try:
                rules = json.loads(t["structure_rules"])
                structure_score = _match_structure(extracted_text, rules)
                score += 0.5 * structure_score
            except (json.JSONDecodeError, TypeError):
                pass

        if score > best_score:
            best_score = score
            best_template = t["id"]

    if best_score >= 0.6:
        return best_template, round(best_score, 2)

    return None, round(best_score, 2)


def _match_structure(text, rules):
    """检查文本中是否包含结构规则中定义的必需特征"""
    if not text or not rules:
        return 0.0

    checks = []

    if "required_columns" in rules:
        columns = rules["required_columns"]
        matched = sum(1 for col in columns if col in text)
        checks.append(matched / len(columns) if columns else 0)

    if "sheet_name" in rules:
        checks.append(1.0 if rules["sheet_name"] in text else 0.0)

    if not checks:
        return 0.0

    return sum(checks) / len(checks)


def process_file(file_id, file_path, filename, file_type, module_id):
    """
    对一个文件执行完整的 4 阶段处理流水线。
    由 Worker 线程调用。
    """
    from database_v2 import (
        update_file_processing_status, update_file_recognition,
        update_file_preview
    )
    from . import file_handler

    # 阶段1: 已由上传流程完成（文件保存）

    # 阶段2: 文本提取
    update_file_processing_status(file_id, "extracting")
    text = extract_text(file_path, file_type)

    # 阶段3: 模板识别
    update_file_processing_status(file_id, "recognizing")
    template_id, confidence = identify_template(filename, text, module_id)
    update_file_recognition(file_id, template_id, confidence, text)

    # 阶段4: PDF 转换
    update_file_processing_status(file_id, "converting")
    # 推导预览目录：取文件目录相对于 uploads 的路径，映射到 previews 下
    upload_parent = os.path.dirname(file_path)
    rel = os.path.relpath(upload_parent, file_handler.UPLOADS_DIR)
    preview_dir = os.path.normpath(os.path.join(file_handler.PREVIEWS_DIR, rel))
    os.makedirs(preview_dir, exist_ok=True)
    preview_path = convert_to_pdf(file_path, preview_dir, file_type)
    if preview_path:
        update_file_preview(file_id, preview_path)

    update_file_processing_status(file_id, "ready")
