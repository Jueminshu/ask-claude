"""
销售部合并器
处理销售部 Excel 周报模板，合并多人周报为一份汇总文件
使用 config.yaml 中的 module_columns.sales 配置
"""
import os
import glob
import yaml
from datetime import datetime
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.worksheet.hyperlink import Hyperlink


class SalesMerger:
    """销售部 Excel 合并器"""

    HEADER_FONT = Font(name="微软雅黑", size=11, bold=True, color="FFFFFF")
    HEADER_FILL = PatternFill(start_color="2B579A", end_color="2B579A", fill_type="solid")
    HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=True)
    CELL_ALIGNMENT = Alignment(vertical="top", wrap_text=True)
    LINK_FONT = Font(name="微软雅黑", size=11, color="2B579A", underline="single")
    TITLE_FONT = Font(name="微软雅黑", size=14, bold=True)
    THIN_BORDER = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin")
    )

    def __init__(self, config_path="config.yaml"):
        """初始化销售部合并器"""
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_full_path = os.path.join(project_root, config_path)
        if not os.path.exists(config_full_path):
            config_full_path = config_path
        with open(config_full_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        module_config = self.config.get("module_columns", {}).get("sales", {})
        self.columns = module_config.get("columns", {})
        self.data_start_row = module_config.get("data_start_row", 3)
        self.risk_column_letter = module_config.get("risk_column", "F")
        self.module_name = "销售部"

        if not self.columns:
            raise ValueError("销售部模块未配置列映射")

    def merge(self, upload_dir, output_dir, week_start, week_end):
        """
        扫描 upload_dir 中的 .xlsx 文件，合并为一份销售部汇总。

        参数:
            upload_dir: 上传文件目录
            output_dir: 输出目录
            week_start: 周起始日期 (YYYY-MM-DD)
            week_end:   周结束日期 (YYYY-MM-DD)

        返回:
            dict: 标准化摘要，或 None（无文件时）
        """
        if not os.path.isdir(upload_dir):
            return None

        pattern = os.path.join(upload_dir, "*.xlsx")
        files = [f for f in glob.glob(pattern) if not os.path.basename(f).startswith("~$")]

        if not files:
            return None

        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"销售部_周报汇总_{week_end}.xlsx")

        # 提取所有人员数据
        all_data = []
        for filepath in files:
            person_name = self._extract_name(os.path.basename(filepath))
            person_data = self._extract_data(filepath, person_name)
            all_data.append(person_data)

        all_data.sort(key=lambda x: x["name"])

        # 构建合并工作簿
        self._build_merged_workbook(all_data, output_path)

        # 返回摘要
        return self._build_summary(output_path, all_data, week_start, week_end)

    def _extract_name(self, filename):
        """从文件名提取姓名"""
        name = os.path.splitext(filename)[0]
        for prefix in ["周报_", "周报-", "weekly_", "weekly-"]:
            if name.lower().startswith(prefix):
                name = name[len(prefix):]
        for suffix in ["_周报", "-周报", "_weekly", "-weekly"]:
            if name.lower().endswith(suffix):
                name = name[:-len(suffix)]
        return name.strip()

    def _extract_data(self, filepath, person_name):
        """从 Excel 文件提取数据，跳过空行"""
        wb = load_workbook(filepath, data_only=True)
        rows = []

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            for row in ws.iter_rows(min_row=self.data_start_row, values_only=True):
                if all(c is None or str(c).strip() == "" for c in row):
                    continue
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

    def _build_merged_workbook(self, all_data, output_path):
        """构建合并工作簿"""
        wb = Workbook()
        wb.remove(wb.active)

        # 目录 Sheet
        toc = wb.create_sheet("📑 目录", 0)
        self._build_toc(toc, all_data)

        # 分析 Sheet
        analysis = wb.create_sheet("📊 本周分析")
        self._build_analysis(analysis, all_data)

        # 个人 Sheet
        for person in all_data:
            sheet_name = person["name"][:31]
            ws = wb.create_sheet(sheet_name)
            self._build_person_sheet(ws, person)

        wb.save(output_path)

    def _build_toc(self, ws, all_data):
        """目录 Sheet"""
        ws.sheet_properties.tabColor = "2B579A"
        ws.merge_cells("A1:C1")
        ws["A1"] = f"【{self.module_name}】周报汇总目录"
        ws["A1"].font = self.TITLE_FONT
        ws["A1"].alignment = Alignment(horizontal="center", vertical="center")

        ws.append([])
        headers = ["序号", "人员", "数据行数"]
        for ci, h in enumerate(headers, 1):
            cell = ws.cell(row=4, column=ci, value=h)
            cell.font = self.HEADER_FONT
            cell.fill = self.HEADER_FILL
            cell.alignment = self.HEADER_ALIGNMENT
            cell.border = self.THIN_BORDER

        for idx, person in enumerate(all_data, 1):
            row = idx + 4
            ws.cell(row=row, column=1, value=idx).alignment = Alignment(horizontal="center")
            ws.cell(row=row, column=1).border = self.THIN_BORDER

            name_cell = ws.cell(row=row, column=2, value=person["name"])
            name_cell.font = self.LINK_FONT
            name_cell.border = self.THIN_BORDER
            sheet_name = person["name"][:31]
            name_cell.hyperlink = Hyperlink(
                ref=name_cell.coordinate,
                location=f"'{sheet_name}'!A1",
                display=person["name"]
            )

            ws.cell(row=row, column=3, value=len(person["rows"])).alignment = Alignment(horizontal="center")
            ws.cell(row=row, column=3).border = self.THIN_BORDER

        ws.column_dimensions["A"].width = 8
        ws.column_dimensions["B"].width = 25
        ws.column_dimensions["C"].width = 12

    def _build_analysis(self, ws, all_data):
        """分析 Sheet"""
        ws.sheet_properties.tabColor = "E67E22"

        total_people = len(all_data)
        total_rows = sum(len(p["rows"]) for p in all_data)

        risk_col = ord(self.risk_column_letter.upper()) - ord('A')

        risks = []
        projects = []
        for person in all_data:
            for row in person["rows"]:
                if len(row) > risk_col and row[risk_col]:
                    risks.append({"person": person["name"], "content": row[risk_col]})
                if len(row) >= 2 and row[1]:
                    projects.append({"person": person["name"], "content": row[1]})

        ws.merge_cells("A1:E1")
        ws["A1"] = f"【{self.module_name}】本周分析"
        ws["A1"].font = self.TITLE_FONT

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

        row += 2
        ws.cell(row=row, column=1, value="⚠️ 风险及求助汇总").font = Font(name="微软雅黑", size=12, bold=True)
        row += 1
        for ci, h in enumerate(["人员", "风险/求助内容"], 1):
            cell = ws.cell(row=row, column=ci, value=h)
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

        row += 2
        ws.cell(row=row, column=1, value="🎯 重点项目一览").font = Font(name="微软雅黑", size=12, bold=True)
        row += 1
        for ci, h in enumerate(["人员", "重点项目"], 1):
            cell = ws.cell(row=row, column=ci, value=h)
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

        row += 2
        ws.cell(row=row, column=1, value="📊 工作量概况").font = Font(name="微软雅黑", size=12, bold=True)
        row += 1
        for ci, h in enumerate(["人员", "条目数"], 1):
            cell = ws.cell(row=row, column=ci, value=h)
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

        ws.column_dimensions["A"].width = 18
        ws.column_dimensions["B"].width = 50

    def _build_person_sheet(self, ws, person):
        """个人数据 Sheet"""
        ws.sheet_properties.tabColor = "2E86C1"

        headers = list(self.columns.values())
        num_cols = len(headers)
        for ci, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=ci, value=h)
            cell.font = self.HEADER_FONT
            cell.fill = self.HEADER_FILL
            cell.alignment = self.HEADER_ALIGNMENT
            cell.border = self.THIN_BORDER

        for ri, row_data in enumerate(person["rows"], 2):
            for ci, value in enumerate(row_data[:num_cols], 1):
                cell = ws.cell(row=ri, column=ci, value=value)
                cell.alignment = self.CELL_ALIGNMENT
                cell.border = self.THIN_BORDER

        row_offset = len(person["rows"]) + 3
        ws.cell(row=row_offset, column=1, value="← 返回目录").font = self.LINK_FONT
        ws.cell(row=row_offset, column=1).hyperlink = Hyperlink(
            ref=ws.cell(row=row_offset, column=1).coordinate,
            location="'📑 目录'!A1",
            display="← 返回目录"
        )

        default_widths = [6, 25, 30, 40, 40, 40]
        col_keys = list(self.columns.keys())
        for i, col_letter in enumerate(col_keys):
            width = default_widths[i] if i < len(default_widths) else 40
            ws.column_dimensions[col_letter].width = width

    def _build_summary(self, output_path, all_data, week_start, week_end):
        """构建标准化摘要"""
        submitted = len(all_data)
        total = submitted  # 以实际提交人数为准

        risk_items = []
        risk_col = ord(self.risk_column_letter.upper()) - ord('A')
        for person in all_data:
            for row in person.get("rows", []):
                if len(row) > risk_col and row[risk_col]:
                    risk_text = str(row[risk_col]).strip()
                    if risk_text and risk_text != "None":
                        risk_items.append(f"{person['name']}: {risk_text[:80]}")

        key_projects = []
        for person in all_data:
            for row in person.get("rows", []):
                if len(row) >= 2 and row[1]:
                    proj_text = str(row[1]).strip()
                    if proj_text:
                        key_projects.append(f"{person['name']}: {proj_text}")

        return {
            "module_name": self.module_name,
            "total_people": total,
            "submitted_count": submitted,
            "submission_rate": f"{round(submitted / max(total, 1) * 100)}%",
            "risk_items": risk_items,
            "key_projects": key_projects,
            "output_file": output_path,
            "deadline_passed": False,
        }
