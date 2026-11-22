"""
===================================================================================
FEATURE ENGINE: src/transformation/silver_to_gold/feature_governance_analytics.py
CHỨC NĂNG: XÂY DỰNG ĐỒ THỊ MẠNG LƯỚI QUẢN TRỊ & TÍNH CENTRALITY BẰNG NETWORKX
Tuân thủ đặc tả: KIEN_TRUC_DATALAKE_DWH_MDM.md (Phần 2, Mục 116 & Phần 6, Mục 852-857)
Đầu ra: data_lake/03_gold/governance_graph_edges/part-00000.snappy.parquet
===================================================================================
"""

import sys
from pathlib import Path

# Cấu hình UTF-8 cho Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import numpy as np
import networkx as nx

PROJECT_ROOT = Path(__file__).resolve().parents[3]
from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR
SILVER_GOV_PATH = DATA_LAKE_DIR / "02_silver" / "02_structured" / "04_Quan_Tri_So_Huu" / "entity_relationships" / "snapshot_year=2026.snappy.parquet"
GOLD_GOV_DIR = DATA_LAKE_DIR / "03_gold" / "04_Do_Thi_Mang_Luoi_Quan_Tri"
GOLD_GOV_DIR.mkdir(parents=True, exist_ok=True)


def run_feature_governance_analytics():
    print(">>> [GOLD 4/5] Feature Engine: Đồ thị Mạng lưới Quản trị & Tính Degree/Betweenness Centrality...")

    if not SILVER_GOV_PATH.exists():
        print(f"      Không tìm thấy {SILVER_GOV_PATH}!")
        return 0

    df_edges = pd.read_parquet(SILVER_GOV_PATH)
    print(f"      Đã đọc {len(df_edges):,} liên kết từ Silver Governance.")

    # Xây dựng đồ thị có hướng bằng NetworkX
    G = nx.DiGraph()

    for _, r in df_edges.iterrows():
        b_node = r["ticker"]
        s_node = r["stakeholder_name"]
        weight = float(r["ownership_pct"]) if r["ownership_pct"] > 0 else 1.0

        G.add_node(b_node, node_type="BANK")
        G.add_node(s_node, node_type=r["stakeholder_type"])
        G.add_edge(s_node, b_node, relationship=r["relationship_type"], role=r["role_title"], weight=weight)

    # Tính toán Centrality
    deg_centrality = nx.degree_centrality(G)
    bet_centrality = nx.betweenness_centrality(G, weight="weight")

    # Gán điểm Centrality vào từng cạnh
    df_edges["source_degree_centrality"] = df_edges["stakeholder_name"].map(deg_centrality).round(4)
    df_edges["target_degree_centrality"] = df_edges["ticker"].map(deg_centrality).round(4)
    df_edges["source_betweenness_centrality"] = df_edges["stakeholder_name"].map(bet_centrality).round(4)
    df_edges["target_betweenness_centrality"] = df_edges["ticker"].map(bet_centrality).round(4)

    out_file = GOLD_GOV_DIR / "part-00000.snappy.parquet"
    df_edges.to_parquet(out_file, compression="snappy", index=False)
    print(f"      [✓] Hoàn tất xuất bản Gold Governance Network: {len(df_edges):,} cạnh tại {out_file}")
    return len(df_edges)


if __name__ == "__main__":
    run_feature_governance_analytics()
