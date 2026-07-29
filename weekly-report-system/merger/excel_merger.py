"""
合并模块
将多个人员的 Excel 周报合并为一个文件
包含：目录 Sheet（超链接）+ 分析 Sheet + 各人员数据 Sheet
"""

import os
import copy
import yaml
from datetime import datetime
from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.worksheet.hyperlink import Hyperlink


class ExcelMerger:
    """Excel 合并器"""

    # 国内运营商模板列映射
    DOMESTIC_COLUMNS = {
        "A": "序号",
        "B": "重点项目",
        "C": "子目标/关键举措",
        "D": "本周工作进展",
        "E": "下周计划",
        "F": "风险及求助",
    }

    # 样式
    HEADER_FONT = Font(name="微软雅黑", size=11, bold=True, color="FFFFFF")
    HEADER_FILL = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")
    HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=True)
    CELL_ALIGNMENT = Alignment(vertical="top", wrap_text=True)
    LINK_FONT = Font(name="微软雅黑", size=11, color="0F766E", underline="single")
    TITLE_FONT = Font(name="微软雅黑", size=14, bold=True)
    THIN_BORDER = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin")
    )

    def __init__(self, config_path="config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

    def merge(self, module_id):
        """
        合并指定模块的所有周报
        参数:
            module_id: 模块 ID
        返回:
            输出文件路径
        """
        local_config = self.config.get("local", {})
        scan_dir = local_config.get("scan_dir", f"data/raw/{module_id}")

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        scan_dir = os.path.join(project_root, scan_dir)
        output_dir = os.path.join(project_root, "output")
        os.makedirs(output_dir, exist_ok=True)

        # 获取模块名称
        module_name = self._get_module_name(module_id)

        # 扫描文件
        import glob
        pattern = os.path.join(scan_dir, "*.xlsx")
        files = [f for f in glob.glob(pattern) if not os.path.basename(f).startswith("~$")]

        if not files:
            print(f"[提示] 在 {scan_dir} 中未找到 Excel 文件")
            return None

        print(f"找到 {len(files)} 个文件，开始合并...")

        # 今天的日期
        today = datetime.now().strftime("%Y%m%d")
        output_path = os.path.join(output_dir, f"【{module_name}】周报汇总_{today}.xlsx")

        # 创建新工作簿
        wb = Workbook()
        # 删除默认 Sheet
        wb.remove(wb.active)

        # 收集所有人员数据
        all_data = []
        for filepath in files:
            filename = os.path.basename(filepath)
            person_name = self._extract_name(filename)
            person_data = self._extract_data(filepath, person_name)
            all_data.append(person_data)

        # 按姓名排序
        all_data.sort(key=lambda x: x["name"])

        # 第一步：创建目录 Sheet
        toc_sheet = wb.create_sheet("📑 目录", 0)
        self._build_toc(toc_sheet, all_data, module_name, today)

        # 第二步：创建分析 Sheet
        analysis_sheet = wb.create_sheet("📊 本周分析")
        self._build_analysis(analysis_sheet, all_data, module_name)

        # 第三步：为每个人创建 Sheet
        for person in all_data:
            # Sheet 名不能超过 31 字符
            sheet_name = person["name"][:31]
            ws = wb.create_sheet(sheet_name)
            self._build_person_sheet(ws, person)

        # 保存
        wb.save(output_path)
        print(f"合并完成: 共 {len(all_data)} 人，输出 {output_path}")
        return output_path

    def merge_from_uploads(self, module_id, week_start, week_end):
        """从 Web 上传目录合并周报（供 app.py 调用）"""
        import glob

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        upload_dir = os.path.join(project_root, "data", "uploads", week_start, str(module_id))

        if not os.path.exists(upload_dir):
            print(f"[提示] 上传目录不存在: {upload_dir}")
            return None

        pattern = os.path.join(upload_dir, "*.xlsx")
        files = [f for f in glob.glob(pattern) if not os.path.basename(f).startswith("~$")]

        if not files:
            print(f"[提示] 未找到上传文件")
            return None

        module_name = self._get_module_name_by_id(module_id)
        output_dir = os.path.join(project_root, "output")
        os.makedirs(output_dir, exist_ok=True)

        today = datetime.now().strftime("%Y%m%d")
        output_path = os.path.join(output_dir, f"【{module_name}】周报汇总_{today}.xlsx")

        wb = Workbook()
        wb.remove(wb.active)

        all_data = []
        for filepath in files:
            filename = os.path.basename(filepath)
            person_name = self._extract_name(filename)
            person_data = self._extract_data(filepath, person_name)
            all_data.append(person_data)

        all_data.sort(key=lambda x: x["name"])

        # 更新提交记录的 row_count
        self._update_submission_counts(all_data, week_start, module_id)

        toc_sheet = wb.create_sheet("📑 目录", 0)
        self._build_toc(toc_sheet, all_data, module_name, today)
        analysis_sheet = wb.create_sheet("📊 本周分析")
        self._build_analysis(analysis_sheet, all_data, module_name)

        for person in all_data:
            sheet_name = person["name"][:31]
            ws = wb.create_sheet(sheet_name)
            self._build_person_sheet(ws, person)

        wb.save(output_path)
        return output_path

    def _get_module_name_by_id(self, module_id):
        """根据数字 ID 从数据库获取模块名"""
        try:
            import sqlite3
            db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "data")
            db_path = os.path.join(db_dir, "weekly_report.db")
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                row = conn.execute("SELECT name FROM modules WHERE id = ?", (module_id,)).fetchone()
                conn.close()
                if row:
                    return row[0]
        except Exception:
            pass
        return f"模块{module_id}"

    def _update_submission_counts(self, all_data, week_start, module_id):
        """更新提交记录的 row_count"""
        try:
            import sqlite3
            db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "data")
            db_path = os.path.join(db_dir, "weekly_report.db")
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                for person in all_data:
                    conn.execute(
                        """UPDATE submissions SET row_count = ?
                           WHERE module_id = ? AND week_start = ?
                           AND file_path LIKE ?""",
                        (len(person["rows"]), module_id, week_start, f"%{person['name']}%")
                    )
                conn.commit()
                conn.close()
        except Exception:
            pass

    def _get_module_name(self, module_id):
        modules = self.config.get("modules", [])
        for m in modules:
            if m.get("id") == module_id:
                return m.get("name", module_id)
        return module_id

    def _extract_name(self, filename):
        """从文件名提取姓名"""
        # 去掉扩展名
        name = os.path.splitext(filename)[0]
        # 常见命名模式清理
        for prefix in ["周报_", "周报-", "weekly_", "weekly-"]:
            if name.lower().startswith(prefix):
                name = name[len(prefix):]
        for suffix in ["_周报", "-周报", "_weekly", "-weekly"]:
            if name.lower().endswith(suffix):
                name = name[: -len(suffix)]
        return name.strip()

    def _extract_data(self, filepath, person_name):
        """从 Excel 文件提取数据，跳过空行"""
        wb = load_workbook(filepath, data_only=True)
        rows = []

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            # 判断表头行（第一行），从第二行开始读取数据
            for row in ws.iter_rows(min_row=2, values_only=True):
                # 跳过完全空行
                if all(c is None or str(c).strip() == "" for c in row):
                    continue
                # 跳过仅有序号无实质内容的行（B-F列全空）
                meaningful = [c for c in row[1:] if c is not None and str(c).strip() != ""]
                if not meaningful:
                    continue
                cleaned = []
                for c in row:
                    if c is None:
                        cleaned.append("")
                    else:
                        cleaned.append(str(c).strip())
                rows.append(cleaned)

        wb.close()
        return {"name": person_name, "filepath": filepath, "rows": rows}

    def _build_toc(self, ws, all_data, module_name, date_str):
        """构建目录 Sheet"""
        ws.sheet_properties.tabColor = "0F766E"

        # 标题
        ws.merge_cells("A1:C1")
        ws["A1"] = f"【{module_name}】周报汇总目录"
        ws["A1"].font = self.TITLE_FONT
        ws["A1"].alignment = Alignment(horizontal="center", vertical="center")

        # 日期
        ws.merge_cells("A2:C2")
        ws["A2"] = f"报告周期: {date_str}"
        ws["A2"].font = Font(name="微软雅黑", size=10, color="666666")
        ws["A2"].alignment = Alignment(horizontal="center")

        # 空行
        ws.append([])

        # 表头
        headers = ["序号", "人员", "数据行数"]
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=4, column=col_idx, value=header)
            cell.font = self.HEADER_FONT
            cell.fill = self.HEADER_FILL
            cell.alignment = self.HEADER_ALIGNMENT
            cell.border = self.THIN_BORDER

        # 数据行
        for idx, person in enumerate(all_data, 1):
            row = idx + 4
            ws.cell(row=row, column=1, value=idx).alignment = Alignment(horizontal="center")
            ws.cell(row=row, column=1).border = self.THIN_BORDER

            # 人名 + 超链接
            name_cell = ws.cell(row=row, column=2, value=person["name"])
            name_cell.font = self.LINK_FONT
            name_cell.border = self.THIN_BORDER
            # 创建内部超链接 (指向同名 Sheet)
            sheet_name = person["name"][:31]
            name_cell.hyperlink = Hyperlink(
                ref=name_cell.coordinate,
                location=f"'{sheet_name}'!A1",
                display=person["name"]
            )

            ws.cell(row=row, column=3, value=len(person["rows"])).alignment = Alignment(horizontal="center")
            ws.cell(row=row, column=3).border = self.THIN_BORDER

        # 列宽
        ws.column_dimensions["A"].width = 8
        ws.column_dimensions["B"].width = 25
        ws.column_dimensions["C"].width = 12

    def _build_analysis(self, ws, all_data, module_name):
        """构建分析 Sheet"""
        ws.sheet_properties.tabColor = "E67E22"

        total_people = len(all_data)
        total_rows = sum(len(p["rows"]) for p in all_data)

        # 收集风险项 (F列)
        risks = []
        projects = []
        for person in all_data:
            for row in person["rows"]:
                if len(row) >= 6 and row[5]:  # F列: 风险及求助
                    risks.append({"person": person["name"], "content": row[5]})
                if len(row) >= 2 and row[1]:  # B列: 重点项目
                    projects.append({"person": person["name"], "content": row[1]})

        # --- 标题 ---
        ws.merge_cells("A1:E1")
        ws["A1"] = f"【{module_name}】本周分析"
        ws["A1"].font = self.TITLE_FONT

        # --- 总览 ---
        row = 3
        ws.cell(row=row, column=1, value="📋 本周总览").font = Font(name="微软雅黑", size=12, bold=True)
        row += 1
        ws.cell(row=row, column=1, value="提交人数").font = Font(bold=True)
        ws.cell(row=row, column=2, value=total_people)
        row += 1
        ws.cell(row=row, column=1, value="工作条目数").font = Font(bold=True)
        ws.cell(row=row, column=2, value=total_rows)
        row += 1
        ws.cell(row=row, column=1, value="风险/求助项").font = Font(bold=True)
        ws.cell(row=row, column=2, value=len(risks))

        # --- 风险汇总 ---
        row += 2
        ws.cell(row=row, column=1, value="⚠️ 风险及求助汇总").font = Font(name="微软雅黑", size=12, bold=True)
        row += 1
        risk_headers = ["人员", "风险/求助内容"]
        for col_idx, header in enumerate(risk_headers, 1):
            cell = ws.cell(row=row, column=col_idx, value=header)
            cell.font = self.HEADER_FONT
            cell.fill = self.HEADER_FILL
            cell.alignment = self.HEADER_ALIGNMENT
            cell.border = self.THIN_BORDER

        if risks:
            row += 1
            for r in risks:
                ws.cell(row=row, column=1, value=r["person"]).border = self.THIN_BORDER
                ws.cell(row=row, column=2, value=r["content"]).border = self.THIN_BORDER
                ws.cell(row=row, column=2).alignment = self.CELL_ALIGNMENT
                row += 1
        else:
            row += 1
            ws.cell(row=row, column=1, value="🎉 本周无风险/求助项")

        # --- 重点项目 ---
        row += 2
        ws.cell(row=row, column=1, value="🎯 重点项目一览").font = Font(name="微软雅黑", size=12, bold=True)
        row += 1
        proj_headers = ["人员", "重点项目"]
        for col_idx, header in enumerate(proj_headers, 1):
            cell = ws.cell(row=row, column=col_idx, value=header)
            cell.font = self.HEADER_FONT
            cell.fill = self.HEADER_FILL
            cell.alignment = self.HEADER_ALIGNMENT
            cell.border = self.THIN_BORDER

        if projects:
            row += 1
            for p in projects:
                ws.cell(row=row, column=1, value=p["person"]).border = self.THIN_BORDER
                ws.cell(row=row, column=2, value=p["content"]).border = self.THIN_BORDER
                ws.cell(row=row, column=2).alignment = self.CELL_ALIGNMENT
                row += 1

        # --- 工作量 ---
        row += 2
        ws.cell(row=row, column=1, value="📊 工作量概况").font = Font(name="微软雅黑", size=12, bold=True)
        row += 1
        work_headers = ["人员", "条目数"]
        for col_idx, header in enumerate(work_headers, 1):
            cell = ws.cell(row=row, column=col_idx, value=header)
            cell.font = self.HEADER_FONT
            cell.fill = self.HEADER_FILL
            cell.alignment = self.HEADER_ALIGNMENT
            cell.border = self.THIN_BORDER

        row += 1
        for person in sorted(all_data, key=lambda x: len(x["rows"]), reverse=True):
            ws.cell(row=row, column=1, value=person["name"]).border = self.THIN_BORDER
            ws.cell(row=row, column=2, value=len(person["rows"])).border = self.THIN_BORDER
            ws.cell(row=row, column=2).alignment = Alignment(horizontal="center")
            row += 1

        # 列宽
        ws.column_dimensions["A"].width = 18
        ws.column_dimensions["B"].width = 50
        ws.column_dimensions["C"].width = 15
        ws.column_dimensions["D"].width = 15
        ws.column_dimensions["E"].width = 15

    def _build_person_sheet(self, ws, person):
        """构建个人数据 Sheet（仅含数据行，无模板空行）"""
        ws.sheet_properties.tabColor = "2E86C1"

        # 表头
        headers = list(self.DOMESTIC_COLUMNS.values())
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = self.HEADER_FONT
            cell.fill = self.HEADER_FILL
            cell.alignment = self.HEADER_ALIGNMENT
            cell.border = self.THIN_BORDER

        # 数据行（仅保留非空行）
        for row_idx, row_data in enumerate(person["rows"], 2):
            for col_idx, value in enumerate(row_data[:6], 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.alignment = self.CELL_ALIGNMENT
                cell.border = self.THIN_BORDER

        # 回到顶部 + 返回目录链接
        row_offset = len(person["rows"]) + 3
        ws.cell(row=row_offset, column=1, value="← 返回目录").font = self.LINK_FONT
        ws.cell(row=row_offset, column=1).hyperlink = Hyperlink(
            ref=ws.cell(row=row_offset, column=1).coordinate,
            location="'📑 目录'!A1",
            display="← 返回目录"
        )

        # 列宽
        col_widths = {"A": 6, "B": 25, "C": 30, "D": 40, "E": 40, "F": 40}
        for col_letter, width in col_widths.items():
            ws.column_dimensions[col_letter].width = width
