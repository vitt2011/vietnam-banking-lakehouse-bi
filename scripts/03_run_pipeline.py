"""
===================================================================================
MASTER ORCHESTRATOR: scripts/03_run_pipeline.py (and src/orchestration/master_orchestrator.py)
CHỨC NĂNG: ĐIỀU PHỐI TOÀN BỘ CÁC ĐƯỜNG ỐNG DỮ LIỆU CHUẨN LAKEHOUSE
===================================================================================
"""

import sys
import argparse
import logging
from pathlib import Path

# Cấu hình UTF-8 cho Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from stock_analysis.pipeline.run_daily_pipeline import run_pipeline as run_daily
from stock_analysis.pipeline.run_quarterly_pipeline import run_pipeline as run_quarterly
from stock_analysis.pipeline.smart_quarterly_sync import run_smart_quarterly_sync
from stock_analysis.sql_serving_loader.publish_to_postgres import publish_all_to_postgres

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("MasterOrchestrator")


def run_status():
    import psycopg2
    from stock_analysis.common.db import get_db_connection
    conn = get_db_connection()
    cur = conn.cursor()
    print("=" * 80)
    print(">>> TRẠNG THÁI NỀN TẢNG DỮ LIỆU & BẢNG OPS <<<")
    print("=" * 80)
    cur.execute("""
        SELECT run_id, job_name, status, records_published, duration_seconds, finished_at 
        FROM ops.pipeline_runs 
        ORDER BY finished_at DESC LIMIT 5;
    """)
    print("\n[5 Phiên chạy gần nhất]")
    for r in cur.fetchall():
        print(f"  * {r[0]} | {r[1]:<25} | {r[2]:<8} | {r[3]:<6} records | {r[4]}s | {r[5]}")

    cur.execute("SELECT dataset_name, latest_record_count, status, last_published_at FROM ops.dataset_publish_state;")
    print("\n[Trạng thái công bố các Dataset]")
    for r in cur.fetchall():
        print(f"  * {r[0]:<25} : {r[1]:<6} records | {r[2]} | {r[3]}")
    conn.close()
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Trạm điều phối Master Pipeline chuẩn Lakehouse")
    parser.add_argument("--mode", type=str, choices=["daily", "quarterly", "auxiliary", "notes", "publish", "all", "status"], default="status", help="Chế độ chạy")
    parser.add_argument("--force", action="store_true", help="Bắt buộc chạy (bỏ qua kiểm tra ngày nghỉ)")
    parser.add_argument("--crawl", action="store_true", help="Cào lại từ nguồn ngoài API")
    args = parser.parse_args()

    if args.mode == "daily":
        run_daily(force=args.force)
    elif args.mode == "auxiliary":
        from stock_analysis.pipeline.daily_auxiliary_sync import run_all_auxiliary_sync
        logger.info(">>> THỰC THI ĐỒNG BỘ CHỈ SỐ THỊ TRƯỜNG, TIN TỨC NLP & SỰ KIỆN DOANH NGHIỆP <<<")
        run_all_auxiliary_sync()
    elif args.mode == "notes":
        from stock_analysis.pipeline.unstructured_notes_etl import run_batch_notes_etl
        logger.info(">>> THỰC THI ĐƯỜNG ỐNG TRÍCH XUẤT THUYẾT MINH BCTC PHI CẤU TRÚC (UNSTRUCTURED NOTES ETL) <<<")
        run_batch_notes_etl(max_banks=10)
    elif args.mode == "quarterly":
        if args.crawl:
            logger.info(">>> THỰC THI ĐỒNG BỘ BCTC QUÝ TOÀN DIỆN (QUÉT 27 NGÂN HÀNG) <<<")
            run_smart_quarterly_sync(force_all=True)
        else:
            logger.info(">>> THỰC THI ĐỒNG BỘ BCTC QUÝ THÔNG MINH (CUỐN CHIẾU) <<<")
            run_smart_quarterly_sync(force_all=False)
    elif args.mode == "publish":
        publish_all_to_postgres()
    elif args.mode == "all":
        logger.info(">>> CHẠY TOÀN BỘ CÁC ĐƯỜNG ỐNG LIÊN HOÀN <<<")
        run_daily(force=True, skip_api=True)
        run_quarterly(skip_crawl=True)
        run_status()
    elif args.mode == "status":
        run_status()


if __name__ == "__main__":
    main()
