#!/usr/bin/env bash
# ===============================================================================
# CẤU HÌNH CRONTAB TỰ ĐỘNG HÓA TRÊN LINUX SERVER (UBUNTU / DEBIAN / CENTOS)
# Dành cho việc triển khai trên Cloud VPS hoặc Server doanh nghiệp
# ===============================================================================

PROJECT_DIR="/opt/stock_analysis"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"

# 1. Hàng ngày lúc 15:45 (Thứ 2 đến Thứ 6): Cào nến giá, chỉ số sàn, tin tức & Thăm dò BCTC mới
# 45 15 * * 1-5 cd /opt/stock_analysis && .venv/bin/python scripts/03_run_pipeline.py --mode daily >> runtime/logs/cron_daily.log 2>&1

# 2. Hàng tuần vào Chủ nhật lúc 02:00 sáng: Quét lại Vĩ mô và Mạng lưới Quản trị
# 0 2 * * 0 cd /opt/stock_analysis && .venv/bin/python scripts/03_run_pipeline.py --mode quarterly >> runtime/logs/cron_quarterly.log 2>&1

echo "==============================================================================="
echo "   HƯỚNG DẪN CÀI ĐẶT CRON TRÊN LINUX SERVER"
echo "==============================================================================="
echo "1. Chạy lệnh: crontab -e"
echo "2. Dán 2 dòng sau vào cuối file:"
echo ""
echo "45 15 * * 1-5 cd $PROJECT_DIR && $PYTHON_BIN scripts/03_run_pipeline.py --mode daily >> $PROJECT_DIR/runtime/logs/cron_daily.log 2>&1"
echo "0 2 * * 0 cd $PROJECT_DIR && $PYTHON_BIN scripts/03_run_pipeline.py --mode quarterly >> $PROJECT_DIR/runtime/logs/cron_quarterly.log 2>&1"
echo ""
echo "3. Lưu lại (Ctrl+O, Enter, Ctrl+X trong nano). Server sẽ tự động chạy đúng giờ."
echo "==============================================================================="
