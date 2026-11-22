"""
Quantitative Research: Lead-Lag Dynamics & Temporal Predictability in Vietnam Banking Stocks
Location: Stock_Analysis/scripts/quant_research/01_research_lead_lag.py
Methodology:
  1. Synchronized Daily Log Returns (2021-01-01 to 2026-11-13 for full sample, 2012-2026 for long sample).
  2. Market Control: Residual returns from Market Model against VN-Index:
       R_{i,t} = alpha_i + beta_i * R_{VNINDEX,t} + epsilon_{i,t}
  3. Portfolio Indices:
       - State-Owned Listed Group (VCB, BID, CTG)
       - Private Tier 1 Group (ACB, MBB, TCB, VPB, HDB, STB)
       - Mid/Small Banking Group (Remaining Banks)
  4. Stationarity: Augmented Dickey-Fuller (ADF) tests.
  5. Cross-Correlation Function (CCF) at lag k in [-20, +20].
  6. Vector Autoregression (VAR) & Granger Causality Tests (lags 1, 2, 3, 5).
  7. Pairwise Lead-Lag Matrix for Key Banking Pairs.
  8. Sub-period Robustness & Regime Stability (2021-2022 vs 2023-2024 vs 2025-2026).
  9. Economic Exploitation Potential (Transaction Cost Friction Analysis).
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from datetime import datetime
from statsmodels.tsa.stattools import adfuller, grangercausalitytests
from statsmodels.tsa.api import VAR
import statsmodels.api as sm

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNTIME_DIR = os.path.join(BASE_DIR, "runtime", "research_snapshots")
OUTPUT_DIR = os.path.join(RUNTIME_DIR, "lead_lag_results")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def load_data():
    ohlcv_path = os.path.join(RUNTIME_DIR, "daily_ohlcv.csv")
    macro_path = os.path.join(RUNTIME_DIR, "macro_indicators.csv")
    
    df_ohlcv = pd.read_csv(ohlcv_path)
    df_macro = pd.read_csv(macro_path)
    
    df_ohlcv['date_actual'] = pd.to_datetime(df_ohlcv['date_actual'])
    df_macro['date_actual'] = pd.to_datetime(df_macro['date_actual'])
    
    # Extract VNINDEX
    vnindex = df_macro[df_macro['indicator_code'] == 'INDEX_VNINDEX_CLOSE'][['date_actual', 'value']].rename(columns={'value': 'close_price'})
    vnindex['ticker'] = 'VNINDEX'
    vnindex['tier_group'] = 'INDEX'
    vnindex['listing_exchange'] = 'HOSE'
    vnindex['open_price'] = vnindex['close_price']
    vnindex['high_price'] = vnindex['close_price']
    vnindex['low_price'] = vnindex['close_price']
    vnindex['volume'] = 0
    vnindex['turnover_vnd'] = 0
    vnindex['return_daily_pct'] = 0.0
    
    # Extract VNFINLEAD if available
    vnfinlead = df_macro[df_macro['indicator_code'] == 'INDEX_VNFINLEAD_CLOSE'][['date_actual', 'value']].rename(columns={'value': 'close_price'})
    vnfinlead['ticker'] = 'VNFINLEAD'
    vnfinlead['tier_group'] = 'INDEX'
    vnfinlead['listing_exchange'] = 'HOSE'
    vnfinlead['open_price'] = vnfinlead['close_price']
    vnfinlead['high_price'] = vnfinlead['close_price']
    vnfinlead['low_price'] = vnfinlead['close_price']
    vnfinlead['volume'] = 0
    vnfinlead['turnover_vnd'] = 0
    vnfinlead['return_daily_pct'] = 0.0
    
    combined = pd.concat([df_ohlcv, vnindex, vnfinlead], ignore_index=True)
    return combined

def prepare_pivot_returns(df, start_date='2021-01-01', end_date='2026-11-13'):
    """
    Pivot close prices and calculate synchronized log returns.
    No forward filling to invent fake trades!
    """
    df_filtered = df[(df['date_actual'] >= start_date) & (df['date_actual'] <= end_date)]
    price_pivot = df_filtered.pivot(index='date_actual', columns='ticker', values='close_price')
    
    # Calculate Log Returns
    log_returns = np.log(price_pivot / price_pivot.shift(1)).dropna(how='all')
    return log_returns

def compute_market_residuals(returns_df):
    """
    Run OLS Market Model: R_{i,t} = alpha_i + beta_i * R_{VNINDEX,t} + epsilon_{i,t}
    Return residuals and beta summary.
    """
    residuals = pd.DataFrame(index=returns_df.index)
    beta_summary = {}
    
    r_m = returns_df['VNINDEX']
    
    for col in returns_df.columns:
        if col in ['VNINDEX', 'VNFINLEAD']:
            continue
        series = pd.concat([returns_df[col], r_m], axis=1).dropna()
        if len(series) < 100:
            continue
        X = sm.add_constant(series['VNINDEX'])
        y = series[col]
        model = sm.OLS(y, X).fit()
        
        residuals[col] = model.resid
        beta_summary[col] = {
            "alpha": float(model.params['const']),
            "beta": float(model.params['VNINDEX']),
            "pvalue_beta": float(model.pvalues['VNINDEX']),
            "r_squared": float(model.rsquared),
            "obs": int(model.nobs)
        }
        
    return residuals, beta_summary

def build_group_indices(returns_df, residuals_df):
    """
    Build Equal-Weighted Indices for:
      - State-Owned Listed Group (VCB, BID, CTG)
      - Private Tier 1 Group (ACB, MBB, TCB, VPB, HDB, STB)
      - Mid/Small Group (remaining banks)
    """
    state_banks = [c for c in ['VCB', 'BID', 'CTG'] if c in returns_df.columns]
    tier1_banks = [c for c in ['ACB', 'MBB', 'TCB', 'VPB', 'HDB', 'STB'] if c in returns_df.columns]
    midsmall_banks = [c for c in returns_df.columns if c not in state_banks + tier1_banks + ['VNINDEX', 'VNFINLEAD']]
    
    groups_raw = pd.DataFrame(index=returns_df.index)
    groups_raw['STATE_BIG3'] = returns_df[state_banks].mean(axis=1)
    groups_raw['PRIVATE_TIER1'] = returns_df[tier1_banks].mean(axis=1)
    groups_raw['MID_SMALL'] = returns_df[midsmall_banks].mean(axis=1)
    if 'VNINDEX' in returns_df.columns:
        groups_raw['VNINDEX'] = returns_df['VNINDEX']
        
    groups_res = pd.DataFrame(index=residuals_df.index)
    groups_res['STATE_BIG3'] = residuals_df[state_banks].mean(axis=1)
    groups_res['PRIVATE_TIER1'] = residuals_df[tier1_banks].mean(axis=1)
    groups_res['MID_SMALL'] = residuals_df[midsmall_banks].mean(axis=1)
    
    return groups_raw.dropna(), groups_res.dropna()

def test_stationarity(series, name):
    clean = series.dropna()
    res = adfuller(clean, autolag='AIC')
    return {
        "series": name,
        "adf_stat": float(res[0]),
        "p_value": float(res[1]),
        "used_lag": int(res[2]),
        "n_obs": int(res[3]),
        "critical_values": {k: float(v) for k, v in res[4].items()},
        "is_stationary_5pct": bool(res[1] < 0.05)
    }

def compute_cross_correlation(series_x, series_y, max_lag=20):
    """
    Cross correlation between X and Y at lag k in [-max_lag, +max_lag].
    Lag k > 0 means X leads Y by k days (X_{t-k} corr with Y_t).
    Lag k < 0 means Y leads X by |k| days.
    """
    df = pd.concat([series_x, series_y], axis=1).dropna()
    x = df.iloc[:, 0]
    y = df.iloc[:, 1]
    
    ccf = {}
    for k in range(-max_lag, max_lag + 1):
        if k > 0:
            # X leads Y: x_{t-k} vs y_t
            r = np.corrcoef(x.shift(k).dropna(), y.iloc[k:])[0, 1]
        elif k < 0:
            # Y leads X: x_t vs y_{t-|k|}
            pos_k = abs(k)
            r = np.corrcoef(x.iloc[pos_k:], y.shift(pos_k).dropna())[0, 1]
        else:
            r = np.corrcoef(x, y)[0, 1]
        ccf[k] = float(r)
        
    max_k = max(ccf.keys(), key=lambda k: ccf[k])
    return ccf, max_k, ccf[max_k]

def run_var_granger(data_df, var_x, var_y, max_lags=[1, 2, 3, 5]):
    """
    Run Granger Causality test: Does var_x Granger-cause var_y? And vice versa.
    """
    clean_df = data_df[[var_y, var_x]].dropna()
    
    results = {
        "x_causes_y": {},
        "y_causes_x": {}
    }
    
    # Test 1: X causes Y (data is [Y, X])
    gc_x_to_y = grangercausalitytests(clean_df, maxlag=max(max_lags))
    for lag in max_lags:
        f_test = gc_x_to_y[lag][0]['ssr_ftest']
        chi2_test = gc_x_to_y[lag][0]['ssr_chi2test']
        results["x_causes_y"][f"lag_{lag}"] = {
            "f_stat": float(f_test[0]),
            "f_pvalue": float(f_test[1]),
            "chi2_stat": float(chi2_test[0]),
            "chi2_pvalue": float(chi2_test[1]),
            "significant_5pct": bool(f_test[1] < 0.05)
        }
        
    # Test 2: Y causes X (data is [X, Y])
    clean_df_rev = data_df[[var_x, var_y]].dropna()
    gc_y_to_x = grangercausalitytests(clean_df_rev, maxlag=max(max_lags))
    for lag in max_lags:
        f_test = gc_y_to_x[lag][0]['ssr_ftest']
        chi2_test = gc_y_to_x[lag][0]['ssr_chi2test']
        results["y_causes_x"][f"lag_{lag}"] = {
            "f_stat": float(f_test[0]),
            "f_pvalue": float(f_test[1]),
            "chi2_stat": float(chi2_test[0]),
            "chi2_pvalue": float(chi2_test[1]),
            "significant_5pct": bool(f_test[1] < 0.05)
        }
        
    return results

def run_regime_stability(df, regimes):
    """
    Check if Lead-Lag relationship holds across different market regimes.
    """
    stability = {}
    for name, (start, end) in regimes.items():
        sub_df = df[(df.index >= start) & (df.index <= end)]
        if len(sub_df) < 60:
            continue
        
        # Test Big3 vs Tier1
        corr_0 = float(sub_df['STATE_BIG3'].corr(sub_df['PRIVATE_TIER1']))
        corr_lead1 = float(sub_df['STATE_BIG3'].shift(1).corr(sub_df['PRIVATE_TIER1']))
        corr_lag1 = float(sub_df['PRIVATE_TIER1'].shift(1).corr(sub_df['STATE_BIG3']))
        
        # Granger at lag 1
        gc = run_var_granger(sub_df, 'STATE_BIG3', 'PRIVATE_TIER1', max_lags=[1, 2])
        
        stability[name] = {
            "period": f"{start} to {end}",
            "observations": len(sub_df),
            "contemporaneous_corr": corr_0,
            "state_leads_tier1_lag1_corr": corr_lead1,
            "tier1_leads_state_lag1_corr": corr_lag1,
            "granger_state_to_tier1_lag1_pvalue": gc["x_causes_y"]["lag_1"]["f_pvalue"],
            "granger_tier1_to_state_lag1_pvalue": gc["y_causes_x"]["lag_1"]["f_pvalue"],
            "state_leads_significant": gc["x_causes_y"]["lag_1"]["significant_5pct"],
            "tier1_leads_significant": gc["y_causes_x"]["lag_1"]["significant_5pct"]
        }
    return stability

def run_pairwise_lead_lag(residuals_df, pairs):
    """
    Pairwise Lead-Lag analysis for specific flagship banking pairs.
    """
    pairwise_results = {}
    for p1, p2 in pairs:
        pair_key = f"{p1}_vs_{p2}"
        if p1 not in residuals_df.columns or p2 not in residuals_df.columns:
            continue
        sub = residuals_df[[p1, p2]].dropna()
        if len(sub) < 100:
            continue
            
        ccf, max_k, max_r = compute_cross_correlation(sub[p1], sub[p2], max_lag=5)
        gc = run_var_granger(sub, p1, p2, max_lags=[1, 2, 3])
        
        pairwise_results[pair_key] = {
            "stock_1": p1,
            "stock_2": p2,
            "contemporaneous_corr": ccf[0],
            "optimal_lag": max_k,
            "max_correlation": max_r,
            "interpretation": (
                f"{p1} leads {p2} by {max_k} days" if max_k > 0 
                else f"{p2} leads {p1} by {-max_k} days" if max_k < 0 
                else "Synchronous"
            ),
            "granger_p1_causes_p2_lag1": gc["x_causes_y"]["lag_1"]["f_pvalue"],
            "granger_p2_causes_p1_lag1": gc["y_causes_x"]["lag_1"]["f_pvalue"],
            "p1_predicts_p2": gc["x_causes_y"]["lag_1"]["significant_5pct"],
            "p2_predicts_p1": gc["y_causes_x"]["lag_1"]["significant_5pct"]
        }
    return pairwise_results

def evaluate_economic_magnitude(df_groups, transaction_fee_bps=15.0):
    """
    Examine if lag-1 predictability can cover bid-ask spread and transaction tax (approx 15 bps each way).
    Strategy: If State Big 3 return at t-1 > 0, long Private Tier 1 at t; else cash/short.
    """
    df = df_groups[['STATE_BIG3', 'PRIVATE_TIER1']].dropna().copy()
    
    # Signal: sign of Big 3 at t-1
    df['signal'] = np.sign(df['STATE_BIG3'].shift(1))
    df['strat_return_raw'] = df['signal'] * df['PRIVATE_TIER1']
    
    # Apply transaction cost whenever signal changes
    df['trade_occurred'] = (df['signal'] != df['signal'].shift(1)).astype(int)
    cost = (transaction_fee_bps / 10000.0)
    df['strat_return_net'] = df['strat_return_raw'] - (df['trade_occurred'] * cost)
    
    annual_factor = 252
    
    buy_hold_ret = df['PRIVATE_TIER1'].mean() * annual_factor
    buy_hold_vol = df['PRIVATE_TIER1'].std() * np.sqrt(annual_factor)
    buy_hold_sharpe = buy_hold_ret / buy_hold_vol if buy_hold_vol > 0 else 0
    
    strat_raw_ret = df['strat_return_raw'].mean() * annual_factor
    strat_raw_vol = df['strat_return_raw'].std() * np.sqrt(annual_factor)
    strat_raw_sharpe = strat_raw_ret / strat_raw_vol if strat_raw_vol > 0 else 0
    
    strat_net_ret = df['strat_return_net'].mean() * annual_factor
    strat_net_vol = df['strat_return_net'].std() * np.sqrt(annual_factor)
    strat_net_sharpe = strat_net_ret / strat_net_vol if strat_net_vol > 0 else 0
    
    total_trades = int(df['trade_occurred'].sum())
    
    return {
        "benchmark_buy_hold": {
            "annualized_return_pct": float(buy_hold_ret * 100),
            "annualized_volatility_pct": float(buy_hold_vol * 100),
            "sharpe_ratio": float(buy_hold_sharpe)
        },
        "naive_lead_lag_strategy_gross": {
            "annualized_return_pct": float(strat_raw_ret * 100),
            "annualized_volatility_pct": float(strat_raw_vol * 100),
            "sharpe_ratio": float(strat_raw_sharpe)
        },
        "lead_lag_strategy_net_of_fees": {
            "fee_per_trade_bps": transaction_fee_bps,
            "total_turnover_trades": total_trades,
            "annualized_return_pct": float(strat_net_ret * 100),
            "annualized_volatility_pct": float(strat_net_vol * 100),
            "sharpe_ratio": float(strat_net_sharpe),
            "is_economically_viable": bool(strat_net_sharpe > buy_hold_sharpe and strat_net_ret > 0)
        }
    }

def main():
    print("=" * 70)
    print("MÔ HÌNH 1: EMPIRICAL RESEARCH ON BANKING LEAD-LAG DYNAMICS")
    print("=" * 70)
    
    df_raw = load_data()
    print(f"Loaded raw data: {len(df_raw):,} records")
    
    # 1. Pivot Log Returns
    log_ret = prepare_pivot_returns(df_raw, start_date='2021-01-01', end_date='2026-11-13')
    print(f"Calculated log returns matrix: {log_ret.shape[0]} trading days x {log_ret.shape[1]} series")
    
    # 2. Market Model Residuals
    residuals, beta_summary = compute_market_residuals(log_ret)
    print(f"Extracted Market Model residuals for {len(beta_summary)} banks (controlled for VN-Index)")
    
    # Save Betas
    df_betas = pd.DataFrame.from_dict(beta_summary, orient='index')
    df_betas.to_csv(os.path.join(OUTPUT_DIR, "bank_market_betas.csv"))
    
    # 3. Build Group Indices
    groups_raw, groups_res = build_group_indices(log_ret, residuals)
    groups_raw.to_csv(os.path.join(OUTPUT_DIR, "group_indices_raw_returns.csv"))
    groups_res.to_csv(os.path.join(OUTPUT_DIR, "group_indices_market_residuals.csv"))
    
    # 4. Stationarity Tests
    stationarity_results = {}
    for col in groups_raw.columns:
        stationarity_results[f"raw_{col}"] = test_stationarity(groups_raw[col], f"raw_{col}")
    for col in groups_res.columns:
        stationarity_results[f"residual_{col}"] = test_stationarity(groups_res[col], f"residual_{col}")
        
    # 5. Cross-Correlation Function (CCF)
    # A. Raw Returns: State Big 3 vs Private Tier 1
    ccf_raw, max_k_raw, max_r_raw = compute_cross_correlation(groups_raw['STATE_BIG3'], groups_raw['PRIVATE_TIER1'], max_lag=10)
    # B. Market Controlled Residuals: State Big 3 vs Private Tier 1
    ccf_res, max_k_res, max_r_res = compute_cross_correlation(groups_res['STATE_BIG3'], groups_res['PRIVATE_TIER1'], max_lag=10)
    # C. State Big 3 vs Mid/Small Residuals
    ccf_midsmall, max_k_ms, max_r_ms = compute_cross_correlation(groups_res['STATE_BIG3'], groups_res['MID_SMALL'], max_lag=10)
    
    # 6. Granger Causality & VAR Analysis
    granger_raw = run_var_granger(groups_raw, 'STATE_BIG3', 'PRIVATE_TIER1', max_lags=[1, 2, 3, 5])
    granger_res = run_var_granger(groups_res, 'STATE_BIG3', 'PRIVATE_TIER1', max_lags=[1, 2, 3, 5])
    granger_res_ms = run_var_granger(groups_res, 'STATE_BIG3', 'MID_SMALL', max_lags=[1, 2, 3, 5])
    
    # 7. Regime Stability
    regimes = {
        "regime_1_liquidity_boom_2021": ('2021-01-01', '2021-12-31'),
        "regime_2_rate_hike_bear_2022": ('2022-01-01', '2022-12-31'),
        "regime_3_rate_cut_sideway_2023": ('2023-01-01', '2023-12-31'),
        "regime_4_differentiation_2024_2026": ('2024-01-01', '2026-11-13')
    }
    stability_res = run_regime_stability(groups_res, regimes)
    
    # 8. Pairwise Lead-Lag for Key Flagship Pairs
    flagship_pairs = [
        ('VCB', 'BID'), ('VCB', 'CTG'), ('VCB', 'ACB'), ('VCB', 'TCB'),
        ('BID', 'CTG'), ('BID', 'ACB'), ('CTG', 'MBB'), ('TCB', 'VPB'),
        ('ACB', 'MBB'), ('STB', 'EIB'), ('VCB', 'STB'), ('MBB', 'LPB')
    ]
    pairwise_analysis = run_pairwise_lead_lag(residuals, flagship_pairs)
    
    # 9. Economic Friction & Strategy Simulation
    economic_eval = evaluate_economic_magnitude(groups_res, transaction_fee_bps=15.0)
    
    # Consolidate Full Findings
    report = {
        "research_title": "Empirical Lead-Lag Dynamics & Temporal Predictability in Vietnamese Banking Stocks",
        "sample_period": "2021-01-04 to 2026-11-13",
        "observations_trading_days": len(groups_raw),
        "methodology_safeguards": {
            "market_controlled": True,
            "market_benchmark": "VNINDEX (HOSE)",
            "return_definition": "Daily Log Return",
            "cross_correlation_range": "[-10, +10]",
            "granger_lags_tested": [1, 2, 3, 5],
            "state_group_definition": "State-Owned Listed Banks in sample: VCB, BID, CTG",
            "private_tier1_definition": "ACB, MBB, TCB, VPB, HDB, STB"
        },
        "stationarity_tests": stationarity_results,
        "cross_correlation": {
            "raw_state_vs_tier1": {
                "contemporaneous_corr_lag0": ccf_raw[0],
                "optimal_lag": max_k_raw,
                "optimal_corr": max_r_raw,
                "ccf_curve": ccf_raw
            },
            "market_controlled_state_vs_tier1": {
                "contemporaneous_corr_lag0": ccf_res[0],
                "optimal_lag": max_k_res,
                "optimal_corr": max_r_res,
                "ccf_curve": ccf_res
            },
            "market_controlled_state_vs_midsmall": {
                "contemporaneous_corr_lag0": ccf_midsmall[0],
                "optimal_lag": max_k_ms,
                "optimal_corr": max_r_ms,
                "ccf_curve": ccf_midsmall
            }
        },
        "granger_causality_tests": {
            "raw_returns_state_vs_tier1": granger_raw,
            "market_controlled_residuals_state_vs_tier1": granger_res,
            "market_controlled_residuals_state_vs_midsmall": granger_res_ms
        },
        "regime_stability_analysis": stability_res,
        "pairwise_lead_lag_matrix": pairwise_analysis,
        "economic_friction_and_viability": economic_eval
    }
    
    report_path = os.path.join(OUTPUT_DIR, "lead_lag_empirical_report.json")
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        
    print("=" * 70)
    print("LEAD-LAG RESEARCH COMPLETE!")
    print(f"Results saved to: {report_path}")
    print("=" * 70)
    
    # Print Executive Summary to Console
    print("\n--- EXECUTIVE SUMMARY OF FINDINGS ---")
    print(f"1. Contemporaneous Correlation (Lag 0):")
    print(f"   - Raw Returns: {ccf_raw[0]:.4f}")
    print(f"   - Market-Controlled Residuals: {ccf_res[0]:.4f}")
    print(f"2. Optimal Lead-Lag Peak:")
    print(f"   - Raw: Lag {max_k_raw} (Corr: {max_r_raw:.4f})")
    print(f"   - Market-Controlled: Lag {max_k_res} (Corr: {max_r_res:.4f})")
    print(f"3. Granger Causality (Lag 1, Market Controlled):")
    print(f"   - State Big3 -> Private Tier 1: p-value = {granger_res['x_causes_y']['lag_1']['f_pvalue']:.4f} (Significant: {granger_res['x_causes_y']['lag_1']['significant_5pct']})")
    print(f"   - Private Tier 1 -> State Big3: p-value = {granger_res['y_causes_x']['lag_1']['f_pvalue']:.4f} (Significant: {granger_res['y_causes_x']['lag_1']['significant_5pct']})")
    print(f"4. Economic Viability after 15 bps Transaction Fees:")
    print(f"   - Benchmark Buy & Hold Sharpe: {economic_eval['benchmark_buy_hold']['sharpe_ratio']:.2f}")
    print(f"   - Lead-Lag Strategy Net Sharpe: {economic_eval['lead_lag_strategy_net_of_fees']['sharpe_ratio']:.2f}")
    print(f"   - Viable after fees: {economic_eval['lead_lag_strategy_net_of_fees']['is_economically_viable']}")
    print("-------------------------------------\n")

if __name__ == "__main__":
    main()
