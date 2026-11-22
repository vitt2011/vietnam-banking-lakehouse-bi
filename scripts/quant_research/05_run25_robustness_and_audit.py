"""
RUN 2.5: RESEARCH EVIDENCE AUDIT & ROBUSTNESS TESTING
Location: Stock_Analysis/scripts/quant_research/05_run25_robustness_and_audit.py
Tasks:
  1. Non-Bank Market Benchmark sensitivity for Lead-Lag.
  2. Optimal VAR Lag Selection via AIC/BIC/HQIC.
  3. Benjamini-Hochberg FDR Multiple Testing Correction for Granger tests.
  4. Panel Model Comparison: Pooled OLS vs Entity FE vs Two-way FE.
  5. Overlapping Forward Returns Audit & Sensitivity of Anchor Date (T+30, T+35, T+45).
  6. Multiple Testing Correction (FDR) on Dividend Event Study windows.
  7. Exact Empirical Metrics for MBB, ACB, VCB at 2026Q3 snapshot.
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import statsmodels.api as sm
from statsmodels.tsa.api import VAR
from statsmodels.stats.multitest import multipletests
from scipy import stats

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNTIME_DIR = os.path.join(BASE_DIR, "runtime", "research_snapshots")
OUTPUT_DIR = os.path.join(RUNTIME_DIR, "run25_audit_results")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def load_snapshots():
    ohlcv_path = os.path.join(RUNTIME_DIR, "daily_ohlcv.csv")
    fin_path = os.path.join(RUNTIME_DIR, "quarterly_financials.csv")
    macro_path = os.path.join(RUNTIME_DIR, "macro_indicators.csv")
    events_path = os.path.join(RUNTIME_DIR, "corporate_events.csv")
    
    df_ohlcv = pd.read_csv(ohlcv_path)
    df_fin = pd.read_csv(fin_path)
    df_macro = pd.read_csv(macro_path)
    df_events = pd.read_csv(events_path)
    
    df_ohlcv['date_actual'] = pd.to_datetime(df_ohlcv['date_actual'])
    df_macro['date_actual'] = pd.to_datetime(df_macro['date_actual'])
    df_fin['period_date'] = pd.to_datetime(df_fin['period_date'])
    df_events['public_date'] = pd.to_datetime(df_events['public_date'])
    df_events['exright_date'] = pd.to_datetime(df_events['exright_date'])
    
    return df_ohlcv, df_fin, df_macro, df_events

# ==============================================================================
# 1. NON-BANK BENCHMARK & LEAD-LAG ROBUSTNESS
# ==============================================================================
def audit_lead_lag_sensitivity(df_ohlcv, df_macro):
    print("\n--- [AUDIT 1] Lead-Lag Sensitivity with Alternative Benchmarks & Multiple Testing ---")
    
    # 1. Build log returns
    price_pivot = df_ohlcv[(df_ohlcv['date_actual'] >= '2021-01-01') & (df_ohlcv['date_actual'] <= '2026-11-13')].pivot(
        index='date_actual', columns='ticker', values='close_price'
    )
    log_ret = np.log(price_pivot / price_pivot.shift(1)).dropna(how='all')
    
    # Extract macro series
    vni = df_macro[df_macro['indicator_code'] == 'INDEX_VNINDEX_CLOSE'].set_index('date_actual')['value']
    vni_ret = np.log(vni / vni.shift(1)).rename('VNINDEX')
    
    # Construct Non-Bank Industry Composite Proxy using VNIND (Industrials), VNCONS (Consumer), VNREAL (Real Estate)
    ind_codes = ['INDEX_VNIND_CLOSE', 'INDEX_VNCONS_CLOSE', 'INDEX_VNREAL_CLOSE']
    sub_macro = df_macro[df_macro['indicator_code'].isin(ind_codes)].pivot(index='date_actual', columns='indicator_code', values='value')
    macro_ret = np.log(sub_macro / sub_macro.shift(1))
    non_bank_composite = macro_ret.mean(axis=1).rename('NON_BANK_PROXY')
    
    combined = log_ret.join(vni_ret, how='inner').join(non_bank_composite, how='inner').dropna(subset=['VNINDEX', 'NON_BANK_PROXY'])
    
    state_banks = ['VCB', 'BID', 'CTG']
    tier1_banks = ['ACB', 'MBB', 'TCB', 'VPB', 'HDB', 'STB']
    
    groups_raw = pd.DataFrame(index=combined.index)
    groups_raw['STATE_BIG3'] = combined[state_banks].mean(axis=1)
    groups_raw['PRIVATE_TIER1'] = combined[tier1_banks].mean(axis=1)
    
    # A. Residuals against VNINDEX
    res_vni = pd.DataFrame(index=combined.index)
    X_vni = sm.add_constant(combined['VNINDEX'])
    res_vni['STATE_BIG3'] = sm.OLS(groups_raw['STATE_BIG3'], X_vni).fit().resid
    res_vni['PRIVATE_TIER1'] = sm.OLS(groups_raw['PRIVATE_TIER1'], X_vni).fit().resid
    
    # B. Residuals against Non-Bank Composite Proxy
    res_nonbank = pd.DataFrame(index=combined.index)
    X_nb = sm.add_constant(combined['NON_BANK_PROXY'])
    res_nonbank['STATE_BIG3'] = sm.OLS(groups_raw['STATE_BIG3'], X_nb).fit().resid
    res_nonbank['PRIVATE_TIER1'] = sm.OLS(groups_raw['PRIVATE_TIER1'], X_nb).fit().resid
    
    # VAR lag order selection criteria
    var_raw = VAR(groups_raw.dropna())
    lag_order_raw = var_raw.select_order(maxlags=10)
    
    var_vni = VAR(res_vni.dropna())
    lag_order_vni = var_vni.select_order(maxlags=10)
    
    var_nb = VAR(res_nonbank.dropna())
    lag_order_nb = var_nb.select_order(maxlags=10)
    
    # Granger Causality testing across lags 1, 2, 3, 5
    from statsmodels.tsa.stattools import grangercausalitytests
    
    lags = [1, 2, 3, 5]
    granger_results = []
    
    datasets = {
        "Raw Returns (No Control)": groups_raw,
        "VN-Index Controlled Residuals": res_vni,
        "Non-Bank Benchmark Controlled Residuals": res_nonbank
    }
    
    for d_name, d_df in datasets.items():
        clean_df = d_df.dropna()
        # Test State -> Tier1 (clean_df[['PRIVATE_TIER1', 'STATE_BIG3']])
        gc_s_to_t = grangercausalitytests(clean_df[['PRIVATE_TIER1', 'STATE_BIG3']], maxlag=5)
        # Test Tier1 -> State (clean_df[['STATE_BIG3', 'PRIVATE_TIER1']])
        gc_t_to_s = grangercausalitytests(clean_df[['STATE_BIG3', 'PRIVATE_TIER1']], maxlag=5)
        
        for lag in lags:
            f_s_to_t = gc_s_to_t[lag][0]['ssr_ftest']
            f_t_to_s = gc_t_to_s[lag][0]['ssr_ftest']
            granger_results.append({
                "benchmark": d_name,
                "direction": "State_Big3 -> Private_Tier1",
                "lag": lag,
                "f_stat": float(f_s_to_t[0]),
                "p_value": float(f_s_to_t[1])
            })
            granger_results.append({
                "benchmark": d_name,
                "direction": "Private_Tier1 -> State_Big3",
                "lag": lag,
                "f_stat": float(f_t_to_s[0]),
                "p_value": float(f_t_to_s[1])
            })
            
    df_granger = pd.DataFrame(granger_results)
    
    # Benjamini-Hochberg Multiple Testing Correction
    reject, pvals_corrected, _, _ = multipletests(df_granger['p_value'], alpha=0.05, method='fdr_bh')
    df_granger['p_value_fdr_bh'] = pvals_corrected
    df_granger['significant_after_fdr'] = reject
    
    audit_summary = {
        "observations_count": len(combined),
        "optimal_lag_selection": {
            "raw_aic": int(lag_order_raw.aic),
            "raw_bic": int(lag_order_raw.bic),
            "vni_controlled_aic": int(lag_order_vni.aic),
            "vni_controlled_bic": int(lag_order_vni.bic),
            "nonbank_controlled_aic": int(lag_order_nb.aic),
            "nonbank_controlled_bic": int(lag_order_nb.bic),
        },
        "granger_summary_table": df_granger.to_dict(orient='records')
    }
    
    return audit_summary

# ==============================================================================
# 2. PANEL ECONOMETRIC COMPARISON & OVERLAPPING RETURNS AUDIT
# ==============================================================================
def audit_valuation_panel_models(df_fin, df_ohlcv, df_macro):
    print("\n--- [AUDIT 2] Valuation Panel Models & Overlapping Returns Robustness ---")
    
    # Filter valid P/B
    df = df_fin[(df_fin['pb_ratio'] >= 0.2) & (df_fin['pb_ratio'] <= 5.5)].copy()
    df['log_pb'] = np.log(df['pb_ratio'])
    df['quarter_id'] = df['fiscal_year'].astype(str) + "Q" + df['fiscal_quarter'].astype(str)
    
    features = ['roe', 'nim', 'npl_ratio', 'casa_ratio', 'cir']
    df_clean = df.dropna(subset=['log_pb', 'pb_ratio'] + features).copy()
    
    # 1. Model 1: Pooled OLS (No FE) with Bank Clustered SE
    X_pool = sm.add_constant(df_clean[features])
    y_pool = df_clean['log_pb']
    mod_pool = sm.OLS(y_pool, X_pool).fit(cov_type='cluster', cov_kwds={'groups': df_clean['ticker']})
    
    # 2. Model 2: Entity Fixed Effects (Bank Dummies)
    df_fe_entity = pd.get_dummies(df_clean, columns=['ticker'], drop_first=True, dtype=float)
    bank_dummies = [c for c in df_fe_entity.columns if c.startswith('ticker_')]
    X_fe_entity = sm.add_constant(df_fe_entity[features + bank_dummies])
    mod_fe_entity = sm.OLS(df_fe_entity['log_pb'], X_fe_entity).fit(cov_type='cluster', cov_kwds={'groups': df_clean['ticker']})
    
    # 3. Model 3: Time Fixed Effects (Quarter Dummies)
    df_fe_time = pd.get_dummies(df_clean, columns=['quarter_id'], drop_first=True, dtype=float)
    time_dummies = [c for c in df_fe_time.columns if c.startswith('quarter_id_')]
    X_fe_time = sm.add_constant(df_fe_time[features + time_dummies])
    mod_fe_time = sm.OLS(df_fe_time['log_pb'], X_fe_time).fit(cov_type='cluster', cov_kwds={'groups': df_clean['ticker']})
    
    # 4. Model 4: Two-Way Fixed Effects (Entity + Time Dummies)
    df_twfe = pd.get_dummies(df_clean, columns=['ticker', 'quarter_id'], drop_first=True, dtype=float)
    all_fe_dummies = [c for c in df_twfe.columns if c.startswith('ticker_') or c.startswith('quarter_id_')]
    X_twfe = sm.add_constant(df_twfe[features + all_fe_dummies])
    mod_twfe = sm.OLS(df_twfe['log_pb'], X_twfe).fit()
    
    model_comparison = {
        "pooled_ols": {
            "r2": float(mod_pool.rsquared),
            "adj_r2": float(mod_pool.rsquared_adj),
            "n_obs": int(mod_pool.nobs),
            "coefficients": {k: float(v) for k, v in mod_pool.params.items()},
            "pvalues": {k: float(v) for k, v in mod_pool.pvalues.items()}
        },
        "entity_fixed_effects": {
            "r2": float(mod_fe_entity.rsquared),
            "adj_r2": float(mod_fe_entity.rsquared_adj),
            "n_obs": int(mod_fe_entity.nobs),
            "coefficients": {k: float(v) for k, v in mod_fe_entity.params.items() if not k.startswith('ticker_')},
            "pvalues": {k: float(v) for k, v in mod_fe_entity.pvalues.items() if not k.startswith('ticker_')}
        },
        "time_fixed_effects": {
            "r2": float(mod_fe_time.rsquared),
            "adj_r2": float(mod_fe_time.rsquared_adj),
            "n_obs": int(mod_fe_time.nobs),
            "coefficients": {k: float(v) for k, v in mod_fe_time.params.items() if not k.startswith('quarter_id_')},
            "pvalues": {k: float(v) for k, v in mod_fe_time.pvalues.items() if not k.startswith('quarter_id_')}
        },
        "two_way_fixed_effects": {
            "r2": float(mod_twfe.rsquared),
            "adj_r2": float(mod_twfe.rsquared_adj),
            "n_obs": int(mod_twfe.nobs),
            "coefficients": {k: float(v) for k, v in mod_twfe.params.items() if not (k.startswith('ticker_') or k.startswith('quarter_id_'))},
            "pvalues": {k: float(v) for k, v in mod_twfe.pvalues.items() if not (k.startswith('ticker_') or k.startswith('quarter_id_'))}
        }
    }
    
    # 5. Overlapping Forward Returns & Anchor Date Sensitivity Test
    # Test 3 different publication anchors: T+30 days, T+35 days, T+45 days
    price_pivot = df_ohlcv.pivot(index='date_actual', columns='ticker', values='close_price')
    vni_series = df_macro[df_macro['indicator_code'] == 'INDEX_VNINDEX_CLOSE'].set_index('date_actual')['value']
    all_dates = sorted(price_pivot.index)
    
    def evaluate_anchor_lag(anchor_days=35):
        df_clean['fitted_log_pb'] = mod_pool.predict(X_pool)
        df_clean['fitted_pb'] = np.exp(df_clean['fitted_log_pb'])
        df_clean['res'] = df_clean['pb_ratio'] - df_clean['fitted_pb']
        df_clean['zscore'] = df_clean.groupby('quarter_id')['res'].transform(lambda s: (s - s.mean()) / s.std() if s.std() > 0 else 0)
        
        perf_records = []
        for idx, row in df_clean.iterrows():
            t = row['ticker']
            p_dt = pd.to_datetime(row['quarter_id'][:4] + "-" + ("03-31" if "Q1" in row['quarter_id'] else "06-30" if "Q2" in row['quarter_id'] else "09-30" if "Q3" in row['quarter_id'] else "12-31"))
            t_entry = p_dt + timedelta(days=anchor_days)
            t_1q = t_entry + timedelta(days=90)
            t_2q = t_entry + timedelta(days=180)
            
            sub_d_entry = [d for d in all_dates if d >= t_entry]
            sub_d_1q = [d for d in all_dates if d >= t_1q]
            sub_d_2q = [d for d in all_dates if d >= t_2q]
            
            if not sub_d_entry or not sub_d_1q or not sub_d_2q:
                continue
                
            d_ent, d_1q, d_2q = sub_d_entry[0], sub_d_1q[0], sub_d_2q[0]
            if t not in price_pivot.columns:
                continue
                
            p_ent = price_pivot.loc[d_ent, t]
            p_1q_val = price_pivot.loc[d_1q, t]
            p_2q_val = price_pivot.loc[d_2q, t]
            
            v_ent = vni_series.get(d_ent, np.nan)
            v_1q_val = vni_series.get(d_1q, np.nan)
            v_2q_val = vni_series.get(d_2q, np.nan)
            
            if pd.notnull(p_ent) and pd.notnull(p_1q_val) and p_ent > 0 and pd.notnull(v_ent) and pd.notnull(v_1q_val) and v_ent > 0:
                ret_1q = (p_1q_val / p_ent - 1) - (v_1q_val / v_ent - 1)
            else:
                ret_1q = np.nan
                
            if pd.notnull(p_ent) and pd.notnull(p_2q_val) and p_ent > 0 and pd.notnull(v_ent) and pd.notnull(v_2q_val) and v_ent > 0:
                ret_2q = (p_2q_val / p_ent - 1) - (v_2q_val / v_ent - 1)
            else:
                ret_2q = np.nan
                
            perf_records.append({
                "ticker": t,
                "quarter_id": row['quarter_id'],
                "zscore": row['zscore'],
                "excess_1q": ret_1q,
                "excess_2q": ret_2q
            })
            
        p_df = pd.DataFrame(perf_records)
        u_1q = p_df[p_df['zscore'] <= -0.5]['excess_1q'].dropna()
        o_1q = p_df[p_df['zscore'] >= 0.5]['excess_1q'].dropna()
        u_2q = p_df[p_df['zscore'] <= -0.5]['excess_2q'].dropna()
        o_2q = p_df[p_df['zscore'] >= 0.5]['excess_2q'].dropna()
        
        t1, p1 = stats.ttest_ind(u_1q, o_1q, equal_var=False) if len(u_1q) > 10 and len(o_1q) > 10 else (0, 1)
        t2, p2 = stats.ttest_ind(u_2q, o_2q, equal_var=False) if len(u_2q) > 10 and len(o_2q) > 10 else (0, 1)
        
        return {
            "anchor_days_post_quarter": anchor_days,
            "observations_tested": len(p_df),
            "1q_undervalued_mean_pct": float(u_1q.mean() * 100) if len(u_1q) > 0 else 0,
            "1q_overvalued_mean_pct": float(o_1q.mean() * 100) if len(o_1q) > 0 else 0,
            "1q_spread_pct": float((u_1q.mean() - o_1q.mean()) * 100) if len(u_1q) > 0 and len(o_1q) > 0 else 0,
            "1q_ttest_pvalue": float(p1),
            "1q_statistically_significant_5pct": bool(p1 < 0.05),
            "2q_undervalued_mean_pct": float(u_2q.mean() * 100) if len(u_2q) > 0 else 0,
            "2q_overvalued_mean_pct": float(o_2q.mean() * 100) if len(o_2q) > 0 else 0,
            "2q_spread_pct": float((u_2q.mean() - o_2q.mean()) * 100) if len(u_2q) > 0 and len(o_2q) > 0 else 0,
            "2q_ttest_pvalue": float(p2),
            "2q_statistically_significant_5pct": bool(p2 < 0.05)
        }
        
    anchor_sensitivities = [
        evaluate_anchor_lag(30),
        evaluate_anchor_lag(35),
        evaluate_anchor_lag(45)
    ]
    
    # 6. Extract Exact Metrics for MBB, ACB, VCB at 2026Q3
    latest_q = df_clean[df_clean['quarter_id'] == '2026Q3'].copy()
    latest_q['fitted_log_pb'] = mod_pool.predict(sm.add_constant(latest_q[features]))
    latest_q['fitted_pb'] = np.exp(latest_q['fitted_log_pb'])
    latest_q['residual'] = latest_q['pb_ratio'] - latest_q['fitted_pb']
    latest_q['residual_pct'] = (latest_q['residual'] / latest_q['fitted_pb']) * 100.0
    latest_q['zscore'] = (latest_q['residual'] - latest_q['residual'].mean()) / latest_q['residual'].std()
    
    flagship_empirical_data = {}
    for ticker in ['MBB', 'ACB', 'VCB']:
        row = latest_q[latest_q['ticker'] == ticker]
        if not row.empty:
            r = row.iloc[0]
            flagship_empirical_data[ticker] = {
                "ticker": ticker,
                "quarter": "2026Q3",
                "actual_pb": round(float(r['pb_ratio']), 2),
                "fitted_pb": round(float(r['fitted_pb']), 2),
                "residual": round(float(r['residual']), 4),
                "residual_pct": round(float(r['residual_pct']), 2),
                "zscore": round(float(r['zscore']), 2),
                "roe": round(float(r['roe']) * 100, 2),
                "nim": round(float(r['nim']) * 100, 2),
                "casa": round(float(r['casa_ratio']) * 100, 2),
                "npl": round(float(r['npl_ratio']) * 100, 2),
                "cir": round(float(r['cir']) * 100, 2),
                "classification": "UNDERVALUED" if r['zscore'] <= -0.5 else "OVERVALUED" if r['zscore'] >= 0.5 else "FAIR_VALUED"
            }
            
    return model_comparison, anchor_sensitivities, flagship_empirical_data

# ==============================================================================
# 3. MULTIPLE TESTING CORRECTION ON DIVIDEND EVENT STUDY
# ==============================================================================
def audit_event_study_multiple_testing():
    print("\n--- [AUDIT 3] Event Study Multiple Testing (Benjamini-Hochberg FDR) ---")
    event_report_path = os.path.join(RUNTIME_DIR, "event_study_results", "event_study_empirical_report.json")
    with open(event_report_path, 'r', encoding='utf-8') as f:
        ev_data = json.load(f)
        
    records = []
    for study_key, study_obj in ev_data['results'].items():
        if not study_obj or 'key_subwindows' not in study_obj:
            continue
        for win_name, win_stat in study_obj['key_subwindows'].items():
            records.append({
                "study": study_key,
                "window": win_name,
                "sample_size": study_obj['sample_size'],
                "mean_car_pct": win_stat['mean_car_pct'],
                "t_stat": win_stat['t_statistic'],
                "raw_pvalue": win_stat['p_value'],
                "raw_sig_5pct": win_stat['statistically_significant_5pct']
            })
            
    df_ev = pd.DataFrame(records)
    
    # Benjamini-Hochberg FDR Correction
    reject_bh, pvals_bh, _, _ = multipletests(df_ev['raw_pvalue'], alpha=0.05, method='fdr_bh')
    # Bonferroni Correction (Conservative)
    reject_bonf, pvals_bonf, _, _ = multipletests(df_ev['raw_pvalue'], alpha=0.05, method='bonferroni')
    
    df_ev['fdr_bh_pvalue'] = pvals_bh
    df_ev['sig_after_fdr_bh'] = reject_bh
    df_ev['bonferroni_pvalue'] = pvals_bonf
    df_ev['sig_after_bonferroni'] = reject_bonf
    
    return df_ev.to_dict(orient='records')

def main():
    print("=" * 80)
    print("RUN 2.5: EMPIRICAL EVIDENCE AUDIT & SENSITIVITY SUITE")
    print("=" * 80)
    
    df_ohlcv, df_fin, df_macro, df_events = load_snapshots()
    
    # 1. Lead-Lag Sensitivity
    lead_lag_audit = audit_lead_lag_sensitivity(df_ohlcv, df_macro)
    
    # 2. Valuation Panel Models & Sensitivity
    model_comp, anchor_sens, flagship_data = audit_valuation_panel_models(df_fin, df_ohlcv, df_macro)
    
    # 3. Event Study Multiple Testing
    ev_multitest = audit_event_study_multiple_testing()
    
    # Save Full Audit Results
    consolidated_audit = {
        "audit_timestamp": datetime.now().isoformat(),
        "lead_lag_sensitivity": lead_lag_audit,
        "valuation_panel_comparison": model_comp,
        "valuation_anchor_date_sensitivities": anchor_sens,
        "empirical_metrics_flagship_banks_2026Q3": flagship_data,
        "event_study_multiple_testing_audit": ev_multitest
    }
    
    out_file = os.path.join(OUTPUT_DIR, "run25_consolidated_empirical_audit.json")
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(consolidated_audit, f, indent=2, ensure_ascii=False)
        
    print(f"\nAudit results successfully saved to: {out_file}")
    print("=" * 80)

if __name__ == "__main__":
    main()
