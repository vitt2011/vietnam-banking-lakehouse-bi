"""
===================================================================================
MODULE: src/governance/lineage_tracker.py
CHỨC NĂNG: GHI NHẬN RUN_ID, LINEAGE MANIFEST & AUDIT LOGS TRÊN POSTGRESQL OPS
===================================================================================
"""

import os
import sys
import json
import uuid
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

import psycopg2

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR, MANIFESTS_DIR

logger = logging.getLogger("LineageTracker")

# DB credentials
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "Stock_Warehouse")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "")


class PipelineRunContext:
    def __init__(self, job_name: str, trigger_type: str = "MANUAL"):
        self.job_name = job_name
        self.trigger_type = trigger_type
        self.run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.source_dataset = ""
        self.target_datasets: List[str] = []
        self.records_ingested = 0
        self.records_validated = 0
        self.records_published = 0
        self.validation_status = "PENDING"
        self.status = "RUNNING"
        self.error_message: Optional[str] = None
        self.started_at = datetime.now(timezone.utc)
        self.start_time = time.time()
        self.manifest_path = ""

    def add_target(self, target: str):
        if target not in self.target_datasets:
            self.target_datasets.append(target)

    def complete(self, status: str = "SUCCESS", error_msg: Optional[str] = None):
        self.status = status
        self.error_message = error_msg
        self.finished_at = datetime.now(timezone.utc)
        self.duration_seconds = round(time.time() - self.start_time, 2)
        
        # 1. Write Manifest JSON file to runtime/manifests
        manifest_filename = f"{self.run_id}.json"
        manifest_file = MANIFESTS_DIR / manifest_filename
        self.manifest_path = str(manifest_file)
        
        manifest_data = {
            "run_id": self.run_id,
            "job_name": self.job_name,
            "trigger_type": self.trigger_type,
            "source_dataset": self.source_dataset,
            "target_datasets": self.target_datasets,
            "records_ingested": self.records_ingested,
            "records_validated": self.records_validated,
            "records_published": self.records_published,
            "validation_status": self.validation_status,
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "error_message": self.error_message,
        }
        
        try:
            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump(manifest_data, f, indent=2, ensure_ascii=False)
            logger.info("Saved lineage manifest to: %s", manifest_file)
        except Exception as e:
            logger.error("Failed to write manifest file: %s", e)

        # 2. Write record into PostgreSQL ops.pipeline_runs
        self._record_to_postgres()

    def _record_to_postgres(self):
        try:
            conn = psycopg2.connect(
                dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT
            )
            conn.autocommit = True
            cur = conn.cursor()
            
            sql = """
            INSERT INTO ops.pipeline_runs (
                run_id, job_name, trigger_type, source_dataset, target_datasets,
                records_ingested, records_validated, records_published,
                validation_status, status, duration_seconds, started_at, finished_at,
                error_message, manifest_path
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s
            ) ON CONFLICT (run_id) DO UPDATE SET
                status = EXCLUDED.status,
                records_published = EXCLUDED.records_published,
                duration_seconds = EXCLUDED.duration_seconds,
                finished_at = EXCLUDED.finished_at,
                error_message = EXCLUDED.error_message;
            """
            cur.execute(sql, (
                self.run_id, self.job_name, self.trigger_type, self.source_dataset, self.target_datasets,
                self.records_ingested, self.records_validated, self.records_published,
                self.validation_status, self.status, self.duration_seconds, self.started_at, self.finished_at,
                self.error_message, self.manifest_path
            ))
            conn.close()
            logger.info("Recorded pipeline run in ops.pipeline_runs: %s (%s)", self.run_id, self.status)
        except Exception as e:
            logger.warning("Could not record pipeline run to ops.pipeline_runs: %s", e)


def update_dataset_state(dataset_name: str, target_table: str, run_id: str, record_count: int, snapshot_date: Optional[str] = None):
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT
        )
        conn.autocommit = True
        cur = conn.cursor()
        
        # Đảm bảo run_id tồn tại trong ops.pipeline_runs để thỏa mãn Foreign Key
        cur.execute("SELECT 1 FROM ops.pipeline_runs WHERE run_id = %s;", (run_id,))
        if not cur.fetchone():
            cur.execute(
                """
                INSERT INTO ops.pipeline_runs (run_id, job_name, trigger_type, status, records_published, finished_at)
                VALUES (%s, %s, 'SYNC', 'SUCCESS', %s, NOW())
                ON CONFLICT (run_id) DO NOTHING;
                """,
                (run_id, f"publish_{dataset_name}", record_count),
            )

        sql = """
        INSERT INTO ops.dataset_publish_state (
            dataset_name, target_table, latest_run_id, latest_record_count, latest_snapshot_date, status, last_published_at
        ) VALUES (
            %s, %s, %s, %s, %s, 'CURRENT', NOW()
        ) ON CONFLICT (dataset_name) DO UPDATE SET
            latest_run_id = EXCLUDED.latest_run_id,
            latest_record_count = EXCLUDED.latest_record_count,
            latest_snapshot_date = COALESCE(EXCLUDED.latest_snapshot_date, ops.dataset_publish_state.latest_snapshot_date),
            status = 'CURRENT',
            last_published_at = NOW();
        """
        cur.execute(sql, (dataset_name, target_table, run_id, record_count, snapshot_date))
        conn.close()
    except Exception as e:
        logger.warning("Could not update dataset state for %s: %s", dataset_name, e)
