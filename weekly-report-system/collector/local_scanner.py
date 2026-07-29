"""
采集模块 - 本地文件模式
扫描指定目录下的 Excel 周报文件
"""

import os
import glob
import yaml
from datetime import datetime


class LocalScanner:
    """扫描本地目录，收集周报 Excel 文件"""

    def __init__(self, config_path="config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

    def scan(self, module_id):
        """
        扫描指定模块的周报文件
        返回: [{"path": ..., "filename": ..., "modified": ...}, ...]
        """
        local_config = self.config.get("local", {})
        scan_dir = local_config.get("scan_dir", f"data/raw/{module_id}")
        pattern = local_config.get("file_pattern", "*.xlsx")

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        scan_dir = os.path.join(project_root, scan_dir)

        if not os.path.exists(scan_dir):
            os.makedirs(scan_dir, exist_ok=True)
            print(f"[提示] 目录不存在，已创建: {scan_dir}")
            print(f"[提示] 请将周报 Excel 文件放入此目录后重新运行")
            return []

        search_pattern = os.path.join(scan_dir, pattern)
        files = glob.glob(search_pattern)
        # 过滤 Excel 临时文件
        files = [f for f in files if not os.path.basename(f).startswith("~$")]

        result = []
        for filepath in files:
            filename = os.path.basename(filepath)
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            result.append({
                "path": filepath,
                "filename": filename,
                "modified": mtime,
            })

        result.sort(key=lambda x: x["modified"])
        return result

    def get_module_members(self, module_id):
        """获取模块成员列表"""
        modules = self.config.get("modules", [])
        for m in modules:
            if m.get("id") == module_id:
                return m.get("members", [])
        return []
