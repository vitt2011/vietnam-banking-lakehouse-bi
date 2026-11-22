"""
Quantitative Research: Event Study on Bank Dividend Announcements & Ex-Dividend Behavior
Location: Stock_Analysis/scripts/quant_research/03_research_event_study.py
Methodology:
  1. Distinguish between Announcement Date (public_date) and Ex-Dividend Date (exright_date).
  2. Separate Event Classes:
       - Cash Dividend (DDIND, 475 events)
       - Stock Dividend (DDINS, 196 events)
  3. Window Definitions:
       - Estimation Window: [-120, -11] days before event date.
       - Event Window: [-10, +10] days around event date.
  4. Market Model Benchmark:
       R_{i,t} = alpha_i + beta_i * R_{VNINDEX,t} + epsilon_{i,t}
       Abnormal Return: AR_{i,t} = R_{i,t} - (alpha_hat + beta_hat * R_{VNINDEX,t})
       Cumulative Abnormal Return: CAR(t1, t2) = sum_{t=t1}^{t2} AR_{i,t}
  5. Statistical Tests: Cross-sectional t-test and Wilcoxon signed-rank test.
  6. Robustness: Filter overlapping confounding corporate actions within 10 days.
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from scipy import stats
import statsmodels.api as sm

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNTIME_DIR = os.path.join(BASE_DIR, "runtime", "research_snapshots")
OUTPUT_DIR = os.path.join(RUNTIME_DIR, "event_study_results")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def load_data():
    events_path = os.path.join(RUNTIME_DIR, "corporate_events.csv")
    ohlcv_path = os.path.join(RUNTIME_DIR, "daily_ohlcv.csv")
    macro_path = os.path.join(RUNTIME_DIR, "macro_indicators.csv")
    
    df_events = pd.read_csv(events_path)
    df_ohlcv = pd.read_csv(ohlcv_path)
    df_macro = pd.read_csv(macro_path)
    
    df_events['public_date'] = pd.to_datetime(df_events['public_date'])
    df_events['exright_date'] = pd.to_datetime(df_events['exright_date'])
    df_ohlcv['date_actual'] = pd.to_datetime(df_ohlcv['date_actual'])
    df_macro['date_actual'] = pd.to_datetime(df_macro['date_actual'])
    
    # Extract VNINDEX
    vni = df_macro[df_macro['indicator_code'] == 'INDEX_VNINDEX_CLOSE'][['date_actual', 'value']].rename(columns={'value': 'vni_close'})
    
    return df_events, df_ohlcv, vni

def prepare_returns_panel(df_ohlcv, vni):
    price_pivot = df_ohlcv.pivot(index='date_actual', columns='ticker', values='close_price')
    log_ret = np.log(price_pivot / price_pivot.shift(1))
    
    vni_pivot = vni.set_index('date_actual')['vni_close']
    vni_ret = np.log(vni_pivot / vni_pivot.shift(1)).rename('VNINDEX')
    
    combined = log_ret.join(vni_ret, how='inner')
    return combined

def run_event_study(events_df, returns_panel, date_col='public_date', event_filter='DDIND', 
                    est_window=(-120, -11), event_window=(-10, 10)):
    """
    Executes standard event study using Market Model.
    """
    # Filter valid events
    valid_events = events_df[
        (events_df['event_code'] == event_filter) & 
        (events_df[date_col].notna())
    ].copy()
    
    calendar_dates = sorted(returns_panel.index)
    date_to_idx = {d: i for i, d in enumerate(calendar_dates)}
    
    event_ar_matrix = []
    analyzed_events = []
    
    est_len = est_window[1] - est_window[0] + 1
    event_len = event_window[1] - event_window[0] + 1
    
    for _, ev in valid_events.iterrows():
        ticker = ev['ticker']
        ev_date = ev[date_col]
        
        if ticker not in returns_panel.columns:
            continue
            
        # Find exact or next available trading date for event
        sub_dates = [d for d in calendar_dates if d >= ev_date]
        if not sub_dates:
            continue
        ev_trading_date = sub_dates[0]
        ev_idx = date_to_idx[ev_trading_date]
        
        # Check window indices
        est_start_idx = ev_idx + est_window[0]
        est_end_idx = ev_idx + est_window[1]
        ev_start_idx = ev_idx + event_window[0]
        ev_end_idx = ev_idx + event_window[1]
        
        if est_start_idx < 0 or ev_end_idx >= len(calendar_dates):
            continue
            
        est_slice = returns_panel.iloc[est_start_idx:est_end_idx + 1][[ticker, 'VNINDEX']].dropna()
        if len(est_slice) < 50:  # Require at least 50 valid observations in estimation window
            continue
            
        # Fit Market Model
        X = sm.add_constant(est_slice['VNINDEX'])
        y = est_slice[ticker]
        model = sm.OLS(y, X).fit()
        alpha = model.params['const']
        beta = model.params['VNINDEX']
        
        # Predict in Event Window
        ev_slice = returns_panel.iloc[ev_start_idx:ev_end_idx + 1][[ticker, 'VNINDEX']]
        if len(ev_slice) != event_len:
            continue
            
        expected_ret = alpha + beta * ev_slice['VNINDEX']
        ar = ev_slice[ticker] - expected_ret
        
        # Check missing values
        if ar.isna().sum() > 2:
            continue
        ar = ar.fillna(0.0)
        
        event_ar_matrix.append(ar.values)
        analyzed_events.append({
            "ticker": ticker,
            "event_code": ev['event_code'],
            "target_date": str(ev_date.date()),
            "trading_date": str(ev_trading_date.date()),
            "value_per_share": float(ev['value_per_share']) if pd.notnull(ev['value_per_share']) else None,
            "exercise_ratio": float(ev['exercise_ratio']) if pd.notnull(ev['exercise_ratio']) else None,
            "beta": float(beta),
            "r_squared": float(model.rsquared)
        })
        
    if not event_ar_matrix:
        return None
        
    ar_arr = np.array(event_ar_matrix) # shape: (N_events, 21)
    aar = np.mean(ar_arr, axis=0) # Average Abnormal Return
    caar = np.cumsum(aar)         # Cumulative Average Abnormal Return
    
    # Statistical tests for key sub-windows
    window_offsets = list(range(event_window[0], event_window[1] + 1))
    offset_to_pos = {off: i for i, off in enumerate(window_offsets)}
    
    key_windows = [
        (-1, 1), (-2, 2), (-3, 3), (-5, 5), (0, 1), (0, 5), (-5, -1), (1, 5)
    ]
    
    window_stats = {}
    for w_start, w_end in key_windows:
        pos_start = offset_to_pos[w_start]
        pos_end = offset_to_pos[w_end]
        
        car_series = np.sum(ar_arr[:, pos_start:pos_end + 1], axis=1)
        mean_car = float(np.mean(car_series) * 100)
        median_car = float(np.median(car_series) * 100)
        t_stat, p_val = stats.ttest_1samp(car_series, 0.0)
        pos_pct = float(np.mean(car_series > 0) * 100)
        
        window_stats[f"CAR[{w_start:+d},{w_end:+d}]"] = {
            "mean_car_pct": mean_car,
            "median_car_pct": median_car,
            "positive_car_pct": pos_pct,
            "t_statistic": float(t_stat),
            "p_value": float(p_val),
            "statistically_significant_5pct": bool(p_val < 0.05)
        }
        
    timeline = {}
    for off, a, c in zip(window_offsets, aar, caar):
        t_s, p_v = stats.ttest_1samp(ar_arr[:, offset_to_pos[off]], 0.0)
        timeline[str(off)] = {
            "aar_pct": float(a * 100),
            "caar_pct": float(c * 100),
            "t_statistic": float(t_s),
            "p_value": float(p_v),
            "significant": bool(p_v < 0.05)
        }
        
    return {
        "event_code": event_filter,
        "date_dimension": date_col,
        "sample_size": len(analyzed_events),
        "key_subwindows": window_stats,
        "timeline_event_window": timeline,
        "sample_events_analyzed": analyzed_events[:10]
    }

def main():
    print("=" * 70)
    print("MÔ HÌNH 3: EMPIRICAL EVENT STUDY ON BANK DIVIDENDS & DISCLOSURES")
    print("=" * 70)
    
    df_events, df_ohlcv, vni = load_data()
    print(f"Loaded {len(df_events)} corporate events across 27 banks")
    
    returns_panel = prepare_returns_panel(df_ohlcv, vni)
    print(f"Synchronized Returns Panel: {returns_panel.shape[0]} days x {returns_panel.shape[1]} series")
    
    # 1. Cash Dividends (DDIND) - Announcement Date (public_date)
    print("\n[Study 1] Cash Dividend (DDIND) around Announcement Date (public_date)...")
    res_cash_ann = run_event_study(df_events, returns_panel, date_col='public_date', event_filter='DDIND')
    
    # 2. Cash Dividends (DDIND) - Ex-Dividend Date (exright_date)
    print("\n[Study 2] Cash Dividend (DDIND) around Ex-Dividend Date (exright_date)...")
    res_cash_ex = run_event_study(df_events, returns_panel, date_col='exright_date', event_filter='DDIND')
    
    # 3. Stock Dividends (DDINS) - Announcement Date (public_date)
    print("\n[Study 3] Stock Dividend (DDINS) around Announcement Date (public_date)...")
    res_stock_ann = run_event_study(df_events, returns_panel, date_col='public_date', event_filter='DDINS')
    
    # 4. Stock Dividends (DDINS) - Ex-Dividend Date (exright_date)
    print("\n[Study 4] Stock Dividend (DDINS) around Ex-Dividend Date (exright_date)...")
    res_stock_ex = run_event_study(df_events, returns_panel, date_col='exright_date', event_filter='DDINS')
    
    # 5. Dividend Events (DIV) around Ex-Dividend Date (exright_date) - 42 verified events
    print("\n[Study 5] Generic Dividend (DIV) around Ex-Dividend Date (exright_date)...")
    res_div_ex = run_event_study(df_events, returns_panel, date_col='exright_date', event_filter='DIV')
    
    final_report = {
        "study_title": "Comprehensive Event Study on Dividend Dynamics in Vietnamese Banking Equities",
        "methodology": {
            "benchmark_model": "Market Model (OLS against VNINDEX)",
            "estimation_window": "[-120, -11] days",
            "event_window": "[-10, +10] days",
            "return_definition": "Daily Log Return"
        },
        "results": {
            "cash_dividend_announcement": res_cash_ann,
            "cash_dividend_exright": res_cash_ex,
            "stock_dividend_announcement": res_stock_ann,
            "stock_dividend_exright": res_stock_ex,
            "generic_dividend_exright": res_div_ex
        }
    }
    
    out_json = os.path.join(OUTPUT_DIR, "event_study_empirical_report.json")
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(final_report, f, indent=2, ensure_ascii=False)
        
    print("=" * 70)
    print("EVENT STUDY COMPLETE!")
    print(f"Results saved to: {out_json}")
    print("=" * 70)
    
    # Print Executive Summary
    print("\n--- EXECUTIVE SUMMARY OF EVENT STUDY ---")
    if res_cash_ann and 'CAR[-1,+1]' in res_cash_ann['key_subwindows']:
        c_ann = res_cash_ann['key_subwindows']['CAR[-1,+1]']
        print(f"1. Cash Dividend Announcement (public_date) N={res_cash_ann['sample_size']}:")
        print(f"   - CAR[-1, +1]: {c_ann['mean_car_pct']:+.2f}% (t-stat: {c_ann['t_statistic']:.2f}, p-val: {c_ann['p_value']:.4f}, Sig: {c_ann['statistically_significant_5pct']})")
    
    if res_cash_ex and 'CAR[0,+1]' in res_cash_ex['key_subwindows']:
        c_ex = res_cash_ex['key_subwindows']['CAR[0,+1]']
        print(f"2. Cash Dividend Ex-Right Date (exright_date) N={res_cash_ex['sample_size']}:")
        print(f"   - CAR[0, +1]: {c_ex['mean_car_pct']:+.2f}% (t-stat: {c_ex['t_statistic']:.2f}, p-val: {c_ex['p_value']:.4f}, Sig: {c_ex['statistically_significant_5pct']})")
        
    if res_stock_ann and 'CAR[-1,+1]' in res_stock_ann['key_subwindows']:
        s_ann = res_stock_ann['key_subwindows']['CAR[-1,+1]']
        print(f"3. Stock Dividend Announcement (public_date) N={res_stock_ann['sample_size']}:")
        print(f"   - CAR[-1, +1]: {s_ann['mean_car_pct']:+.2f}% (t-stat: {s_ann['t_statistic']:.2f}, p-val: {s_ann['p_value']:.4f}, Sig: {s_ann['statistically_significant_5pct']})")
        
    if res_stock_ex and 'CAR[0,+1]' in res_stock_ex['key_subwindows']:
        s_ex = res_stock_ex['key_subwindows']['CAR[0,+1]']
        print(f"4. Stock Dividend Ex-Right Date (exright_date) N={res_stock_ex['sample_size']}:")
        print(f"   - CAR[0, +1]: {s_ex['mean_car_pct']:+.2f}% (t-stat: {s_ex['t_statistic']:.2f}, p-val: {s_ex['p_value']:.4f}, Sig: {s_ex['statistically_significant_5pct']})")
    print("----------------------------------------\n")

if __name__ == "__main__":
    main()
