"""Phase 2 分析引擎测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'weekly-report-system'))
from database_v2 import init_db, seed_data, get_week_risks, get_efficiency_stats
from services.analyzer.risk_extractor import extract_risks_from_excel, _keyword_risk_fallback
from services.analyzer.efficiency import compute_efficiency, _score_timeliness


init_db()
seed_data()


def test_keyword_fallback():
    text = "竞品降价压力大，客户可能流失。\n数据源接入遇到困难，需要IT支持。"
    risks = _keyword_risk_fallback(text)
    assert len(risks) >= 2  # "压力" line + "困难" line
    print(f"Keyword fallback found {len(risks)} risks")


def test_score_timeliness():
    assert _score_timeliness(10) == 100   # 及时
    assert _score_timeliness(60) == 70    # 可接受
    assert _score_timeliness(200) == 30   # 延迟
    assert _score_timeliness(None) == 50  # 无数据


def test_excel_risk_extraction():
    file_path = os.path.join(
        os.path.dirname(__file__), '..',
        'weekly-report-system', 'output', '【国内运营商】周报汇总_20260729.xlsx'
    )
    if not os.path.exists(file_path):
        print("SKIP: test data file not found")
        return
    risks = extract_risks_from_excel(file_path, "周报", 5, 1, "2026-07-27", 1)
    assert len(risks) >= 1  # 至少 "竞品降价压力大"
    assert any("竞品" in r["risk_description"] for r in risks)
    print(f"Excel extraction found {len(risks)} risks: {[r['risk_description'][:30] for r in risks]}")


def test_efficiency_computation():
    result = compute_efficiency(1, "2026-07-27")
    assert isinstance(result, list)
    if result:
        e = result[0]
        assert "timeliness_score" in e
        assert "content_score" in e
        assert "rejection_count" in e
    print(f"Efficiency computed for {len(result)} members")


def test_risk_db_write_and_read():
    from database_v2 import upsert_risk_items, create_submission, add_submission_file
    # 创建真实记录满足 FK 约束
    sub_id = create_submission(5, 1, "2026-07-27", "2026-08-02")
    file_id = add_submission_file(sub_id, "test.xlsx", "/tmp/test.xlsx", "xlsx", 1024)
    upsert_risk_items("2026-07-27", 1, 5, file_id, [
        {"customer": "测试客户", "risk_description": "测试风险描述", "severity": "high", "is_new": 1, "source_column": "风险及求助"},
    ])
    risks = get_week_risks("2026-07-27")
    assert any(r["submission_file_id"] == file_id for r in risks)
    print(f"DB round-trip OK, {len(risks)} risks in week 2026-07-27")
