from __future__ import annotations

import strategy_layer.portfolio_alpha.risk.barra_model.barra_data as barra_data
import strategy_layer.portfolio_alpha.risk.barra_model.barra_risk as barra_risk


DEFAULT_CAP_PATH = r"C:\Users\yixuanwang2\Desktop\to_wyx\to_wyx\market_cap\market_cap_weights.parquet"


def start_to_finish(f_raw, m_raw, c_raw, out_dir):
    print("进行数据对齐")
    clean_f, clean_r, clean_c = barra_data.generate_aligned_datasets(
        factor_path=f_raw,
        market_path=m_raw,
        cap_path=c_raw,
        output_dir=out_dir,
    )

    if clean_c is None:
        raise ValueError("Market cap alignment output was not generated.")

    print("启动风险引擎")
    engine = barra_risk.BarraRiskEngine(
        factor_path=clean_f,
        return_path=clean_r,
        cap_path=clean_c,
    )
    engine.run_full_pipeline()
    engine.save_outputs(out_dir)

    print(f"--- 最新截面风险参数已存入 {out_dir} ---")
    return engine.factor_covariance


if __name__ == "__main__":
    F_PATH = r"C:\Users\yixuanwang2\Desktop\to_wyx\to_wyx\generated_factor\mock_barra_10_factors.parquet"
    M_PATH = r"C:\Users\yixuanwang2\Desktop\to_wyx\to_wyx\daily_market_summary\daily_market_summary_2025.parquet"
    C_PATH = DEFAULT_CAP_PATH
    OUT = r"C:\Users\yixuanwang2\Desktop\to_wyx\to_wyx"

    final_cov = start_to_finish(F_PATH, M_PATH, C_PATH, OUT)
