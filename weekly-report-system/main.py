"""
营销运作部周报收集系统
======================
采集 → 合并 → 分析 → 投递

用法:
    python main.py collect --module domestic_operator   # 采集
    python main.py merge --module domestic_operator     # 合并
    python main.py analyze --module domestic_operator   # 分析
    python main.py run --module domestic_operator       # 全流程
"""

import argparse
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collector.local_scanner import LocalScanner
from merger.excel_merger import ExcelMerger
from analyzer.domestic_operator import DomesticOperatorAnalyzer


def cmd_collect(args):
    """采集：扫描本地目录，收集周报文件"""
    scanner = LocalScanner(args.config)
    files = scanner.scan(args.module)
    print(f"找到 {len(files)} 个周报文件:")
    for f in files:
        print(f"  {f}")


def cmd_merge(args):
    """合并：将所有周报合并为一个 Excel，含目录超链接"""
    merger = ExcelMerger(args.config)
    output_path = merger.merge(args.module)
    print(f"合并完成: {output_path}")


def cmd_analyze(args):
    """分析：基于合并数据生成分析报告"""
    analyzer = DomesticOperatorAnalyzer(args.config)
    result = analyzer.analyze(args.module, args.input)
    print("分析完成:")
    print(f"  提交率: {result.get('submission_rate', 'N/A')}")
    print(f"  风险项: {len(result.get('risks', []))} 条")


def cmd_run(args):
    """全流程：采集 → 合并 → 分析"""
    print("=" * 50)
    print(f"模块: {args.module}")
    print("=" * 50)
    cmd_collect(args)
    cmd_merge(args)
    # 分析使用合并后的文件
    args.input = None  # 使用默认路径
    cmd_analyze(args)


def main():
    parser = argparse.ArgumentParser(description="营销运作部周报收集系统")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--module", default="domestic_operator", help="业务模块")

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    subparsers.add_parser("collect", help="采集周报")
    subparsers.add_parser("merge", help="合并周报")

    analyze_parser = subparsers.add_parser("analyze", help="分析周报")
    analyze_parser.add_argument("--input", help="合并后的 Excel 路径")

    subparsers.add_parser("run", help="全流程")

    args = parser.parse_args()

    if args.command == "collect":
        cmd_collect(args)
    elif args.command == "merge":
        cmd_merge(args)
    elif args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "run":
        cmd_run(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
