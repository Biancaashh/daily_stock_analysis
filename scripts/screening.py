#!/usr/bin/env python3
"""
A 股收盘筛选脚本 — 每日收盘后运行

筛选逻辑：
1. 从东方财富获取全市场 A 股实时行情
2. 过滤条件（按顺序）：
   a) 排除 ST / *ST 股票（名称不含 ST）
   b) 总市值 > 50 亿
   c) 按成交额降序排列，取前 50
   d) 查询质押比例，排除质押总股本比 >= 60% 的股票
3. 输出符合条件股票列表（逗号分隔，每行一个代码）

用法：
    python scripts/screening.py
    python scripts/screening.py --top 30   # 取前30只
    python scripts/screening.py --min-market-cap 30  # 市值门槛30亿
"""
import argparse
import sys
import time

import pandas as pd


def get_all_a_share_quotes() -> pd.DataFrame:
    """获取全市场 A 股实时行情（东方财富）"""
    import akshare as ak

    df = ak.stock_zh_a_spot_em()
    if df is None or df.empty:
        raise RuntimeError("获取 A 股行情失败，返回空数据")
    return df


def get_pledge_ratios() -> dict:
    """
    获取全部 A 股质押比例数据，返回 {股票代码: 质押总股本比例(%)} 的字典。

    使用 akshare 的 stock_gpzy_industry_data_em 接口获取全部质押数据，
    在其中提取 '股票代码' 和 '质押比例(占所持股份)' 或者 '质押总股本比例(%)'。
    """
    import akshare as ak

    try:
        pledge_df = ak.stock_gpzy_industry_data_em()
    except Exception as exc:
        print(f"[WARN] 获取质押数据失败: {exc}，跳过质押过滤", file=sys.stderr)
        return {}

    if pledge_df is None or pledge_df.empty:
        print("[WARN] 质押数据为空，跳过质押过滤", file=sys.stderr)
        return {}

    # 查看列名
    cols = list(pledge_df.columns)
    ratio_col = None
    code_col = "股票代码"

    # 自动识别质押比例列
    for col in cols:
        if "质押" in col and ("比例" in col or "占比" in col or "%" in col):
            ratio_col = col
            break

    if ratio_col is None:
        # 尝试其他列名
        for col in cols:
            if "质押" in col:
                ratio_col = col
                break

    if ratio_col is None:
        print(f"[WARN] 未识别质押比例列，可用列: {cols}，跳过质押过滤", file=sys.stderr)
        return {}

    result = {}
    for _, row in pledge_df.iterrows():
        code = str(row.get(code_col, "")).strip()
        ratio = row.get(ratio_col)
        if code and ratio is not None:
            try:
                result[code] = float(ratio)
            except (ValueError, TypeError):
                pass

    print(f"[INFO] 获取到 {len(result)} 只股票的质押数据", file=sys.stderr)
    return result


def screen_stocks(
    top_n: int = 50,
    min_market_cap_yi: float = 50.0,
    exclude_st: bool = True,
    max_pledge_ratio: float = 60.0,
) -> list:
    """
    执行 A 股筛选，返回符合条件股票代码列表。

    Args:
        top_n: 取成交量（成交额）前 N 名
        min_market_cap_yi: 最小总市值（亿）
        exclude_st: 是否排除 ST 股票
        max_pledge_ratio: 最大允许质押总股本比例（%）
    """
    print("[STEP 1/4] 获取全市场 A 股行情...", file=sys.stderr)
    df = get_all_a_share_quotes()
    print(f"  共获取 {len(df)} 只股票", file=sys.stderr)

    # 识别列名（兼容不同版本）
    col_code = "代码" if "代码" in df.columns else df.columns[0]
    col_name = "名称" if "名称" in df.columns else df.columns[1]
    col_amount = "成交额" if "成交额" in df.columns else "金额"
    col_mv = "总市值" if "总市值" in df.columns else None

    print(f"  代码列: {col_code}, 名称列: {col_name}", file=sys.stderr)

    # Step 2: 排除 ST
    if exclude_st:
        before = len(df)
        df = df[~df[col_name].str.contains("ST", na=False, case=False)]
        print(f"[STEP 2/4] 排除 ST 股票: {before} → {len(df)} 只", file=sys.stderr)

    # Step 3: 市值过滤
    if col_mv and col_mv in df.columns:
        before = len(df)
        min_mv = min_market_cap_yi * 1e8  # 亿 → 元
        df = df[df[col_mv] >= min_mv]
        print(f"[STEP 3/4] 市值 > {min_market_cap_yi}亿: {before} → {len(df)} 只", file=sys.stderr)
    else:
        print(f"[STEP 3/4] 跳过市值过滤（无总市值列）", file=sys.stderr)

    # Step 4: 按成交额排序取前 N
    if col_amount in df.columns:
        df = df.sort_values(by=col_amount, ascending=False)
    df_top = df.head(top_n).copy()
    print(f"[STEP 4/4] 成交额前 {top_n}: 取 {len(df_top)} 只", file=sys.stderr)

    # 获取质押比例
    pledge_map = get_pledge_ratios()
    if pledge_map:
        before = len(df_top)
        df_top = df_top[~df_top[col_code].astype(str).map(
            lambda x: pledge_map.get(x, 0) >= max_pledge_ratio
        )]
        print(f"[质押过滤] 排除质押比 >= {max_pledge_ratio}%: {before} → {len(df_top)} 只", file=sys.stderr)

    # 输出
    codes = df_top[col_code].astype(str).str.strip().tolist()
    print(f"\n✅ 最终筛选结果: {len(codes)} 只股票", file=sys.stderr)
    for i, (_, row) in enumerate(df_top.iterrows(), 1):
        pledge_info = ""
        code = str(row[col_code]).strip()
        if pledge_map and code in pledge_map:
            pledge_info = f" [质押: {pledge_map[code]:.1f}%]"
        mv_str = ""
        if col_mv and col_mv in df.columns:
            mv = row.get(col_mv, 0)
            mv_str = f" 市值: {mv/1e8:.1f}亿" if mv else ""
        print(f"  {i:2d}. {code} {row.get(col_name, '')} 成交额: {row.get(col_amount, 0):.0f}{mv_str}{pledge_info}", file=sys.stderr)

    return codes


def main():
    parser = argparse.ArgumentParser(description="A 股收盘筛选")
    parser.add_argument("--top", type=int, default=50, help="取成交量前 N 名（默认 50）")
    parser.add_argument("--min-market-cap", type=float, default=50.0, help="最低总市值，单位亿（默认 50）")
    parser.add_argument("--max-pledge-ratio", type=float, default=60.0, help="最大质押总股本比例 %（默认 60）")
    parser.add_argument("--include-st", action="store_true", help="包含 ST 股票（默认排除）")
    parser.add_argument("--skip-pledge", action="store_true", help="跳过质押比例过滤")
    parser.add_argument("--csv", type=str, help="输出到 CSV 文件（调试用）")
    parser.add_argument("--debug", action="store_true", help="打印更多调试信息")
    args = parser.parse_args()

    print(f"[配置] top={args.top}, 最小市值={args.min_market_cap}亿, "
          f"{'' if args.include_st else '不'}包含ST, "
          f"{'跳过质押' if args.skip_pledge else f'最大质押比={args.max_pledge_ratio}%'}",
          file=sys.stderr)

    codes = screen_stocks(
        top_n=args.top,
        min_market_cap_yi=args.min_market_cap,
        exclude_st=not args.include_st,
        max_pledge_ratio=args.max_pledge_ratio if not args.skip_pledge else 999,
    )

    # 以逗号分隔输出到 stdout（供 workflow 捕获）
    print(",".join(codes))


if __name__ == "__main__":
    main()
