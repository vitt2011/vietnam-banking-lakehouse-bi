"""
Script tiện ích hỗ trợ xem nhanh cấu trúc và nội dung file Parquet.
Cách dùng:
    python preview_parquet.py <đường_dẫn_file_parquet> [--rows 10] [--export-csv] [--export-html]
"""

import sys
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Xem nhanh nội dung file Parquet")
    parser.add_argument("file_path", help="Đường dẫn tới file .parquet cần xem")
    parser.add_argument("--rows", "-n", type=int, default=5, help="Số dòng hiển thị mẫu (mặc định: 5)")
    parser.add_argument("--export-csv", action="store_true", help="Xuất ra file CSV cùng tên để mở bằng Excel")
    parser.add_argument("--export-html", action="store_true", help="Xuất ra file HTML và mở bằng trình duyệt")

    args = parser.parse_args()

    file_path = Path(args.file_path)
    if not file_path.exists():
        print(f"[ERROR] Không tìm thấy file: {file_path}")
        sys.exit(1)

    try:
        import pandas as pd
    except ImportError:
        print("[ERROR] Cần cài đặt pandas. Hãy chạy: pip install pandas")
        sys.exit(1)

    try:
        df = pd.read_parquet(file_path)
    except Exception as e:
        print(f"[ERROR] Không thể đọc file Parquet: {e}")
        print("\n[GỢI Ý] Máy bạn có thể đang thiếu engine 'pyarrow'. Hãy chạy lệnh sau:")
        print("    pip install pyarrow")
        sys.exit(1)

    print("=" * 80)
    print(f"THÔNG TIN FILE: {file_path.name}")
    print(f"Đường dẫn: {file_path.resolve()}")
    print(f"Kích thước file: {file_path.stat().st_size / 1024:.2f} KB")
    print(f"Kích thước dữ liệu: {df.shape[0]} dòng x {df.shape[1]} cột")
    print("=" * 80)
    print("\n[DANH SÁCH CÁC CỘT & KIỂU DỮ LIỆU]")
    for col, dtype in zip(df.columns, df.dtypes):
        print(f" - {col:<30} : {dtype}")

    print(f"\n[DỮ LIỆU {min(args.rows, len(df))} DÒNG ĐẦU TIÊN]")
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(df.head(args.rows))

    if args.export_csv:
        csv_out = file_path.with_suffix('.csv')
        df.to_csv(csv_out, index=False, encoding='utf-8-sig')
        print(f"\n-> Đã xuất sang CSV: {csv_out} (bạn có thể mở bằng Excel)")

    if args.export_html:
        html_out = file_path.with_suffix('.html')
        df.head(100).to_html(html_out, index=False)
        print(f"\n-> Đã xuất 100 dòng sang HTML: {html_out} (bấm đúp để xem trên trình duyệt)")

if __name__ == "__main__":
    main()
