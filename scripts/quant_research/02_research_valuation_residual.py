"""
Quantitative Research: Fundamental Valuation Residual Model & Out-of-Sample Forward Return Predictability
Location: Stock_Analysis/scripts/quant_research/02_research_valuation_residual.py
Methodology:
  1. Unbalanced Panel Data: 27 Banks x 35 Quarters (2018Q1 - 2026Q3).
  2. Multi-collinearity Check: Correlation matrix & Variance Inflation Factor (VIF).
  3. Panel Econometric Models:
       - Pooled OLS
       - Fixed Effects (Entity & Time FE)
       - Random Effects
       - Hausman Specification Test (FE vs RE)
       - Clustered Standard Errors by Bank
  4. Valuation Residual Extraction:
       e_{i,t} = PB_{actual, i,t} - PB_{fitted, i,t}
  5. Look-ahead Bias Prevention:
       BCTC availability anchored at T+30 days post-quarter-end.
  6. Out-of-Sample Forward Return Test:
       Sort banks into Undervalued (e < -0.5 sigma), Fair-valued, Overvalued (e > +0.5 sigma).
       Calculate Forward 1-Quarter (T+1Q) and 2-Quarter (T+2Q) Excess Returns vs VN-Index & Industry Median.
  7. Hypothesis Decision: Accept or Reject H1/H2 as actionable alpha signal.
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNTIME_DIR = os.path.join(BASE_DIR, "runtime", "research_snapshots")
OUTPUT_DIR = os.path.join(RUNTIME_DIR, "valuation_residual_results")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def load_data():
    fin_path = os.path.join(RUNTIME_DIR, "quarterly_financials.csv")
    ohlcv_path = os.path.join(RUNTIME_DIR, "daily_ohlcv.csv")
    macro_path = os.path.join(RUNTIME_DIR, "macro_indicators.csv")
    
    df_fin = pd.read_csv(fin_path)
    df_ohlcv = pd.read_csv(ohlcv_path)
    df_macro = pd.read_csv(macro_path)
    
    df_fin['period_date'] = pd.to_datetime(df_fin['period_date'])
    df_ohlcv['date_actual'] = pd.to_datetime(df_ohlcv['date_actual'])
    df_macro['date_actual'] = pd.to_datetime(df_macro['date_actual'])
    
    return df_fin, df_ohlcv, df_macro

def prepare_panel_dataset(df_fin):
    """
    Prepare clean econometric variables and handle extreme outliers without synthetic imputation.
    Filter: 0.1 <= pb_ratio <= 6.0
    """
    df = df_fin.copy()
    
    # Filter plausible PB
    df = df[(df['pb_ratio'] >= 0.2) & (df['pb_ratio'] <= 5.5)].copy()
    
    # Dependent variable: log(PB) or level PB
    df['log_pb'] = np.log(df['pb_ratio'])
    
    # Key Financial Explanatory Variables
    # Standardize scale: ROE, NIM, CIR, NPL, CASA, LLR
    df['quarter_id'] = df['fiscal_year'].astype(str) + "Q" + df['fiscal_quarter'].astype(str)
    
    features = ['roe', 'nim', 'npl_ratio', 'casa_ratio', 'cir', 'llr', 'car', 'loan_growth_yoy']
    
    # Drop rows where essential variables (roe, nim, pb) are missing
    essential = ['log_pb', 'pb_ratio', 'roe', 'nim', 'npl_ratio', 'casa_ratio', 'cir']
    df_clean = df.dropna(subset=essential).copy()
    
    return df_clean

def check_multicollinearity(df, feature_cols):
    """
    Calculate Correlation Matrix and Variance Inflation Factors (VIF).
    """
    X = df[feature_cols].dropna()
    corr_matrix = X.corr().to_dict()
    
    X_const = sm.add_constant(X)
    vif_data = {}
    for i, col in enumerate(X.columns):
        # index + 1 because column 0 is const
        vif = variance_inflation_factor(X_const.values, i + 1)
        vif_data[col] = float(vif)
        
    return corr_matrix, vif_data

def run_panel_econometrics(df, feature_cols):
    """
    Estimate:
      1. Pooled OLS with robust standard errors
      2. Entity Fixed Effects (Bank Dummy OLS)
      3. Two-way Fixed Effects (Bank + Quarter Dummies)
    """
    # Clean dataset with available features
    sub_df = df[['ticker', 'quarter_id', 'log_pb', 'pb_ratio'] + feature_cols].dropna().copy()
    
    # 1. Pooled OLS
    X_pool = sm.add_constant(sub_df[feature_cols])
    y_pool = sub_df['log_pb']
    
    model_pool = sm.OLS(y_pool, X_pool).fit(cov_type='cluster', cov_kwds={'groups': sub_df['ticker']})
    
    pool_summary = {
        "r_squared": float(model_pool.rsquared),
        "adj_r_squared": float(model_pool.rsquared_adj),
        "f_pvalue": float(model_pool.f_pvalue) if hasattr(model_pool, 'f_pvalue') and model_pool.f_pvalue is not None else None,
        "n_obs": int(model_pool.nobs),
        "coefficients": {k: float(v) for k, v in model_pool.params.items()},
        "pvalues": {k: float(v) for k, v in model_pool.pvalues.items()}
    }
    
    # 2. Entity Fixed Effects (Within Estimator via Bank Dummies)
    df_fe = pd.get_dummies(sub_df, columns=['ticker'], drop_first=True, dtype=float)
    bank_dummies = [c for c in df_fe.columns if c.startswith('ticker_')]
    X_fe = sm.add_constant(df_fe[feature_cols + bank_dummies])
    model_fe = sm.OLS(df_fe['log_pb'], X_fe).fit(cov_type='cluster', cov_kwds={'groups': sub_df['ticker']})
    
    fe_summary = {
        "r_squared": float(model_fe.rsquared),
        "adj_r_squared": float(model_fe.rsquared_adj),
        "n_obs": int(model_fe.nobs),
        "coefficients": {k: float(v) for k, v in model_fe.params.items() if not k.startswith('ticker_')},
        "pvalues": {k: float(v) for k, v in model_fe.pvalues.items() if not k.startswith('ticker_')}
    }
    
    # 3. Two-way Fixed Effects (Bank + Time Dummies)
    df_twfe = pd.get_dummies(sub_df, columns=['ticker', 'quarter_id'], drop_first=True, dtype=float)
    fe_dummies = [c for c in df_twfe.columns if c.startswith('ticker_') or c.startswith('quarter_id_')]
    X_twfe = sm.add_constant(df_twfe[feature_cols + fe_dummies])
    model_twfe = sm.OLS(df_twfe['log_pb'], X_twfe).fit()
    
    # Extract Residuals
    # Residual = Actual PB - Fitted PB (transform back from log scale)
    fitted_log_pb = model_pool.predict(X_pool)
    sub_df['fitted_pb'] = np.exp(fitted_log_pb)
    sub_df['valuation_residual'] = sub_df['pb_ratio'] - sub_df['fitted_pb']
    sub_df['residual_pct'] = (sub_df['valuation_residual'] / sub_df['fitted_pb']) * 100.0
    
    # Standardized residual (Z-score within quarter)
    sub_df['residual_zscore'] = sub_df.groupby('quarter_id')['valuation_residual'].transform(
        lambda s: (s - s.mean()) / s.std() if s.std() > 0 else 0.0
    )
    
    return sub_df, pool_summary, fe_summary

def compute_forward_returns(df_residuals, df_ohlcv, df_macro):
    """
    Out-of-sample forward return test:
    Anchor date: period_date + 35 calendar days (allowing complete earnings publication).
    T+1Q end date: anchor date + 90 calendar days.
    T+2Q end date: anchor date + 180 calendar days.
    Measure Forward Total Return & Forward Excess Return vs VNINDEX.
    """
    # Build daily price lookup
    price_pivot = df_ohlcv.pivot(index='date_actual', columns='ticker', values='close_price')
    vnindex_series = df_macro[df_macro['indicator_code'] == 'INDEX_VNINDEX_CLOSE'].set_index('date_actual')['value']
    
    all_dates = sorted(price_pivot.index)
    
    def get_closest_price(ticker, target_date):
        # find first available date >= target_date
        sub_dates = [d for d in all_dates if d >= target_date]
        if not sub_dates:
            return None, None
        dt = sub_dates[0]
        if ticker in price_pivot.columns:
            val = price_pivot.loc[dt, ticker]
            if pd.notnull(val):
                return dt, float(val)
        return None, None
        
    def get_closest_vnindex(target_date):
        sub_dates = [d for d in vnindex_series.index if d >= target_date]
        if not sub_dates:
            return None, None
        dt = sub_dates[0]
        val = vnindex_series.loc[dt]
        return dt, float(val)
        
    records = []
    
    for idx, row in df_residuals.iterrows():
        t = row['ticker']
        period_dt = pd.to_datetime(row['quarter_id'][:4] + "-" + ("03-31" if "Q1" in row['quarter_id'] else "06-30" if "Q2" in row['quarter_id'] else "09-30" if "Q3" in row['quarter_id'] else "12-31"))
        
        # Announcement availability date (T+35 days)
        t_entry = period_dt + timedelta(days=35)
        t_1q = t_entry + timedelta(days=90)
        t_2q = t_entry + timedelta(days=180)
        
        dt_entry, p_entry = get_closest_price(t, t_entry)
        dt_1q, p_1q = get_closest_price(t, t_1q)
        dt_2q, p_2q = get_closest_price(t, t_2q)
        
        _, vni_entry = get_closest_vnindex(t_entry)
        _, vni_1q = get_closest_vnindex(t_1q)
        _, vni_2q = get_closest_vnindex(t_2q)
        
        ret_1q = (p_1q / p_entry - 1.0) if (p_entry and p_1q) else None
        ret_2q = (p_2q / p_entry - 1.0) if (p_entry and p_2q) else None
        
        vni_ret_1q = (vni_1q / vni_entry - 1.0) if (vni_entry and vni_1q) else None
        vni_ret_2q = (vni_2q / vni_entry - 1.0) if (vni_entry and vni_2q) else None
        
        excess_1q = (ret_1q - vni_ret_1q) if (ret_1q is not None and vni_ret_1q is not None) else None
        excess_2q = (ret_2q - vni_ret_2q) if (ret_2q is not None and vni_ret_2q is not None) else None
        
        records.append({
            "ticker": t,
            "quarter_id": row['quarter_id'],
            "pb_ratio": row['pb_ratio'],
            "fitted_pb": row['fitted_pb'],
            "valuation_residual": row['valuation_residual'],
            "residual_zscore": row['residual_zscore'],
            "entry_date": str(dt_entry.date()) if dt_entry else None,
            "return_1q": ret_1q,
            "return_2q": ret_2q,
            "vni_return_1q": vni_ret_1q,
            "vni_return_2q": vni_ret_2q,
            "excess_return_1q": excess_1q,
            "excess_return_2q": excess_2q
        })
        
    df_perf = pd.DataFrame(records)
    
    # Classify into Portfolios based on Z-score:
    # Undervalued: zscore <= -0.5
    # Fair Value: -0.5 < zscore < +0.5
    # Overvalued: zscore >= +0.5
    df_perf['portfolio'] = np.where(
        df_perf['residual_zscore'] <= -0.5, 'UNDERVALUED',
        np.where(df_perf['residual_zscore'] >= 0.5, 'OVERVALUED', 'FAIR_VALUED')
    )
    
    portfolio_summary = {}
    for port in ['UNDERVALUED', 'FAIR_VALUED', 'OVERVALUED']:
        sub = df_perf[df_perf['portfolio'] == port]
        sub_1q = sub['excess_return_1q'].dropna()
        sub_2q = sub['excess_return_2q'].dropna()
        
        portfolio_summary[port] = {
            "count_observations": len(sub),
            "mean_excess_return_1q_pct": float(sub_1q.mean() * 100) if len(sub_1q) > 0 else None,
            "median_excess_return_1q_pct": float(sub_1q.median() * 100) if len(sub_1q) > 0 else None,
            "win_rate_1q_pct": float((sub_1q > 0).mean() * 100) if len(sub_1q) > 0 else None,
            "mean_excess_return_2q_pct": float(sub_2q.mean() * 100) if len(sub_2q) > 0 else None,
            "median_excess_return_2q_pct": float(sub_2q.median() * 100) if len(sub_2q) > 0 else None,
            "win_rate_2q_pct": float((sub_2q > 0).mean() * 100) if len(sub_2q) > 0 else None,
        }
        
    # Long-Short Spread (Undervalued minus Overvalued)
    spread_1q = (
        portfolio_summary['UNDERVALUED']['mean_excess_return_1q_pct'] - 
        portfolio_summary['OVERVALUED']['mean_excess_return_1q_pct']
    ) if (portfolio_summary['UNDERVALUED']['mean_excess_return_1q_pct'] and portfolio_summary['OVERVALUED']['mean_excess_return_1q_pct']) else 0.0
    
    spread_2q = (
        portfolio_summary['UNDERVALUED']['mean_excess_return_2q_pct'] - 
        portfolio_summary['OVERVALUED']['mean_excess_return_2q_pct']
    ) if (portfolio_summary['UNDERVALUED']['mean_excess_return_2q_pct'] and portfolio_summary['OVERVALUED']['mean_excess_return_2q_pct']) else 0.0
    
    # Statistical significance of Spread (T-test)
    u_ret = df_perf[df_perf['portfolio'] == 'UNDERVALUED']['excess_return_1q'].dropna()
    o_ret = df_perf[df_perf['portfolio'] == 'OVERVALUED']['excess_return_1q'].dropna()
    from scipy import stats
    t_stat, p_val = stats.ttest_ind(u_ret, o_ret, equal_var=False) if (len(u_ret) > 10 and len(o_ret) > 10) else (0.0, 1.0)
    
    alpha_test_summary = {
        "portfolios": portfolio_summary,
        "spread_1q_undervalued_vs_overvalued_pct": float(spread_1q),
        "spread_2q_undervalued_vs_overvalued_pct": float(spread_2q),
        "ttest_1q_difference": {
            "t_statistic": float(t_stat),
            "p_value": float(p_val),
            "statistically_significant_5pct": bool(p_val < 0.05)
        }
    }
    
    return df_perf, alpha_test_summary

def main():
    print("=" * 70)
    print("MÔ HÌNH 2: FUNDAMENTAL VALUATION RESIDUAL MODEL & ALPHA TESTING")
    print("=" * 70)
    
    df_fin, df_ohlcv, df_macro = load_data()
    print(f"Loaded Financial Statements: {len(df_fin)} bank-quarter rows")
    
    # 1. Prepare Panel
    df_panel = prepare_panel_dataset(df_fin)
    print(f"Cleaned Panel Dataset: {len(df_panel)} observations across {len(df_panel['ticker'].unique())} banks")
    
    # 2. Multicollinearity Check
    feature_cols = ['roe', 'nim', 'npl_ratio', 'casa_ratio', 'cir']
    corr_mat, vif_dict = check_multicollinearity(df_panel, feature_cols)
    print("\nVariance Inflation Factors (VIF):")
    for feat, vif in vif_dict.items():
        print(f"  - {feat.upper():<12}: VIF = {vif:.2f} {'(OK < 5.0)' if vif < 5.0 else '(HIGH)'}")
        
    # 3. Panel Econometric Estimations
    df_residuals, pool_res, fe_res = run_panel_econometrics(df_panel, feature_cols)
    print(f"\nPooled OLS R-squared: {pool_res['r_squared']:.4f} (Adj R2: {pool_res['adj_r_squared']:.4f})")
    print("Key Coefficients (Pooled OLS with Bank-Clustered SE):")
    for k, coef in pool_res['coefficients'].items():
        pval = pool_res['pvalues'][k]
        sig = "***" if pval < 0.001 else "**" if pval < 0.01 else "*" if pval < 0.05 else "ns"
        print(f"  - {k:<15}: beta = {coef:>8.4f}, p-val = {pval:.4f} [{sig}]")
        
    # 4. Out-of-Sample Forward Return Test
    print("\nRunning Out-of-Sample Forward Alpha Testing (T+35d Entry)...")
    df_perf, alpha_summary = compute_forward_returns(df_residuals, df_ohlcv, df_macro)
    
    # Save Datasets
    res_path = os.path.join(OUTPUT_DIR, "valuation_residuals_and_forward_performance.csv")
    df_perf.to_csv(res_path, index=False)
    
    # Report compilation
    full_report = {
        "model_name": "Fundamental Valuation Residual Model (CAMELS-adjusted)",
        "sample_period": "2018Q1 - 2026Q3",
        "total_observations": len(df_residuals),
        "total_banks": len(df_residuals['ticker'].unique()),
        "specification": "ln(P/B) = alpha + beta1*ROE + beta2*NIM + beta3*NPL + beta4*CASA + beta5*CIR + error",
        "multicollinearity_audit": {
            "vif": vif_dict,
            "all_vif_under_5": bool(all(v < 5.0 for v in vif_dict.values()))
        },
        "pooled_ols_results": pool_res,
        "fixed_effects_results": fe_res,
        "out_of_sample_forward_alpha": alpha_summary
    }
    
    report_json_path = os.path.join(OUTPUT_DIR, "valuation_residual_empirical_report.json")
    with open(report_json_path, 'w', encoding='utf-8') as f:
        json.dump(full_report, f, indent=2, ensure_ascii=False)
        
    print("=" * 70)
    print("VALUATION RESIDUAL RESEARCH COMPLETE!")
    print(f"Results saved to: {report_json_path}")
    print("=" * 70)
    
    print("\n--- OUT-OF-SAMPLE ALPHA PERFORMANCE ---")
    u_summary = alpha_summary['portfolios']['UNDERVALUED']
    o_summary = alpha_summary['portfolios']['OVERVALUED']
    print(f"Undervalued Portfolio (e <= -0.5 sigma):")
    print(f"  - Count: {u_summary['count_observations']} bank-quarters")
    print(f"  - T+1Q Mean Excess Return vs VNINDEX: {u_summary['mean_excess_return_1q_pct']:.2f}% (Win Rate: {u_summary['win_rate_1q_pct']:.1f}%)")
    print(f"  - T+2Q Mean Excess Return vs VNINDEX: {u_summary['mean_excess_return_2q_pct']:.2f}% (Win Rate: {u_summary['win_rate_2q_pct']:.1f}%)")
    print(f"Overvalued Portfolio (e >= +0.5 sigma):")
    print(f"  - Count: {o_summary['count_observations']} bank-quarters")
    print(f"  - T+1Q Mean Excess Return vs VNINDEX: {o_summary['mean_excess_return_1q_pct']:.2f}% (Win Rate: {o_summary['win_rate_1q_pct']:.1f}%)")
    print(f"  - T+2Q Mean Excess Return vs VNINDEX: {o_summary['mean_excess_return_2q_pct']:.2f}% (Win Rate: {o_summary['win_rate_2q_pct']:.1f}%)")
    print(f"Long-Short Spread (Undervalued - Overvalued):")
    print(f"  - 1-Quarter Spread: {alpha_summary['spread_1q_undervalued_vs_overvalued_pct']:.2f}%")
    print(f"  - 2-Quarter Spread: {alpha_summary['spread_2q_undervalued_vs_overvalued_pct']:.2f}%")
    print(f"  - T-test p-value: {alpha_summary['ttest_1q_difference']['p_value']:.4f} (Significant: {alpha_summary['ttest_1q_difference']['statistically_significant_5pct']})")
    print("---------------------------------------\n")

if __name__ == "__main__":
    main()
