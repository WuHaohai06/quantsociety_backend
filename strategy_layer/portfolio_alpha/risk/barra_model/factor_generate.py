import pandas as pd
import numpy as np
from pathlib import Path


def generate_barra_and_market_caps(market_path: str, factor_output: str, cap_output: str):
    """
    生成模拟的 Barra 因子表和配套的市值表。
    1. Size 因子由 Market Cap 的对数标准化得到。
    2. 其他 9 个因子维持正态分布。
    3. 生成独立的市值表用于 WLS 回归权重。
    """
    print(f"🚀 正在读取行情基准: {market_path}")
    df_market = pd.read_parquet(market_path)

    # --- 1. 坐标对齐 ---
    # 自动识别日期和代码列
    possible_date_cols = ['trade_date', 'date', 'Date', 't', 'datetime']
    date_col = next((c for c in possible_date_cols if c in df_market.columns), None)

    possible_ticker_cols = ['ticker', 'Ticker', 'asset', 'code']
    ticker_col = next((c for c in possible_ticker_cols if c in df_market.columns), None)

    if not date_col or not ticker_col:
        raise KeyError(f"找不到日期或代码列！当前列名: {df_market.columns.tolist()}")

    coords = df_market[[date_col, ticker_col]].drop_duplicates()
    coords = coords.rename(columns={date_col: 'datetime', ticker_col: 'asset'})
    coords['datetime'] = pd.to_datetime(coords['datetime'])
    num_rows = len(coords)
    print(f"📈 提取到 {num_rows} 条坐标点。")

    # --- 2. 模拟市值 (Market Cap) ---
    # 使用对数正态分布模拟真实市场：少数巨头，多数小票
    # mean=10, sigma=2 对应中等市值的 ln 规模
    mock_caps = np.random.lognormal(mean=10.0, sigma=2.0, size=num_rows).astype(np.float32)

    df_caps = pd.concat([
        coords.reset_index(drop=True),
        pd.DataFrame({'market_cap': mock_caps})
    ], axis=1)

    # --- 3. 生成因子表 (以 Size 为核心) ---
    # Size 因子 = ln(Market Cap) 的截面标准化
    ln_cap = np.log(mock_caps)
    # 按截面（每一天）做标准化更专业，这里简化处理：
    size_factor = (ln_cap - ln_cap.mean()) / ln_cap.std()

    # 其他 9 个因子
    style_factors = ['Value', 'Momentum', 'Volatility', 'Liquidity',
                     'Quality', 'Growth', 'DividendYield', 'Leverage', 'Sentiment']
    mock_others = np.random.randn(num_rows, len(style_factors)).astype(np.float32)

    df_factors = pd.concat([
        coords.reset_index(drop=True),
        pd.DataFrame({'Size': size_factor.astype(np.float32)}),
        pd.DataFrame(mock_others, columns=style_factors)
    ], axis=1)

    # --- 4. 排序与保存 ---
    df_factors = df_factors.sort_values(['datetime', 'asset']).reset_index(drop=True)
    df_caps = df_caps.sort_values(['datetime', 'asset']).reset_index(drop=True)

    df_factors.to_parquet(factor_output, index=False)
    df_caps.to_parquet(cap_output, index=False)

    print(f"📁 因子大表已保存: {factor_output}")
    print(f"📁 市值权重已保存: {cap_output}")
    return df_factors, df_caps


# ==========================================
#              🚀 执行/调用区域
# ==========================================
if __name__ == "__main__":
    # 配置基础路径
    BASE_DIR = r'C:\Users\yixuanwang2\Desktop\to_wyx\to_wyx'
    # 输入：行情表
    M_PATH = BASE_DIR + r'\daily_market_summary\daily_market_summary_2025.parquet'
    # 输出：因子表 和 市值表
    F_OUT = BASE_DIR + r'\generated_factor\mock_barra_10_factors.parquet'
    C_OUT = BASE_DIR + r'\market_cap\market_cap_weights.parquet'

    # 确保文件夹存在 (如果需要的话)
    # Path(BASE_DIR).mkdir(parents=True, exist_ok=True)

    # 调用生成函数
    try:
        df_f, df_c = generate_barra_and_market_caps(
            market_path=M_PATH,
            factor_output=F_OUT,
            cap_output=C_OUT
        )
        print("\n文件已生成")
    except Exception as e:
        print(f"\n生成出错{e}")