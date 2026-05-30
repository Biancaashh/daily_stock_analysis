#!/usr/bin/env python3
"""
盘中实时筛选脚本 — 下午 14:30-14:50 间运行

筛选逻辑：
1. 从东方财富获取全市场 A 股实时行情
2. 过滤条件：
   a) 排除 ST / *ST 股票
   b) 换手率在 5%～10% 之间
   c) 涨跌幅在 3%～5% 之间
3. 输出符合条件股票列表（JSON 格式，含明细）

用法：
    python scripts/intraday_screening.py
    python scripts/intraday_screening.py --min-turnover 3 --max-turnover 8
    python scripts/intraday_screening.py --min-change 2 --max-change 6

依赖（已包含在 requirements.txt）：
    pip install akshare pandas
"""

from __future__ import annotations

import argparse
import json
import sys

import pandas as pd


def debug(msg: str) -> None:
    """输出调试信息到 stderr"""
    print(f"[intraday] {msg}", file=sys.stderr)


def get_all_a_share_quotes() -> pd.DataFrame:
    """获取全市场 A 股实时行情（东方财富）"""
    import akshare as ak

    df = ak.stock_zh_a_spot_em()
    if df is None or df.empty:
        raise RuntimeError("获取 A 股行情失败，返回空数据")
    return df


def screen_intraday(
    min_turnover: float = 5.0,
    max_turnover: float = 10.0,
    min_change: float = 3.0,
    max_change: float = 5.0,
    exclude_st: bool = True,
) -> pd.DataFrame:
    """
    执行盘中实时筛选，返回符合条件股票的 DataFrame。

    Args:
        min_turnover: 最低换手率（%）
        max_turnover: 最高换手率（%）
        min_change: 最低涨跌幅（%）
        max_change: 最高涨跌幅（%）
        exclude_st: 是否排除 ST 股票
    """
    # ---------- Step 1: 全市场行情 ----------
    debug("[1/3] 获取全市场 A 股行情...")
    df = get_all_a_share_quotes()
    debug(f"     共获取 {len(df)} 只股票")

    # 列名适配（兼容不同 akshare 版本）
    code_col = "代码" if "代码" in df.columns else df.columns[0]
    name_col = "名称" if "名称" in df.columns else df.columns[1]
    change_col = "涨跌幅"
    turnover_col = "换手率"
    price_col = "最新价"
    amount_col = "成交额"
    mv_col = "总市值"

    # 自动识别列名
    for col in df.columns:
        if "涨跌幅" in col or "涨跌" in col:
            change_col = col
        if "换手" in col:
            turnover_col = col
        if "成交额" in col or "金额" in col:
            amount_col = col
        if "总市值" in col:
            mv_col = col
        if "最新" in col or "现价" in col:
            price_col = col

    debug(f"     涨跌幅列={change_col}, 换手率列={turnover_col}")

    # ---------- Step 2: 排除 ST ----------
    if exclude_st:
        before = len(df)
        df = df[~df[name_col].astype(str).str.contains("ST", na=False, case=False)]
        debug(f"[2/3] 排除 ST 股票: {before} → {len(df)} 只")

    # ---------- Step 3: 换手率 + 涨跌幅过滤 ----------
    before = len(df)

    # 确保数值列是数值类型
    if turnover_col in df.columns:
        df[turnover_col] = pd.to_numeric(df[turnover_col], errors="coerce")
        df = df[df[turnover_col].between(min_turnover, max_turnover, inclusive="both")]

    if change_col in df.columns:
        df[change_col] = pd.to_numeric(df[change_col], errors="coerce")
        df = df[df[change_col].between(min_change, max_change, inclusive="both")]

    debug(f"[3/3] 筛选: 换手率{min_turnover}%-{max_turnover}% + "
          f"涨幅{min_change}%-{max_change}%: {before} → {len(df)} 只")

    return df


def format_results(df: pd.DataFrame) -> dict:
    """将筛选结果格式化为可读的 JSON 结构"""
    code_col = "代码" if "代码" in df.columns else df.columns[0]
    name_col = "名称" if "名称" in df.columns else df.columns[1]
    change_col = "涨跌幅"
    turnover_col = "换手率"
    price_col = "最新价"
    amount_col = "成交额"
    mv_col = "总市值"

    # 自动识别列名
    for col in df.columns:
        if "涨跌幅" in col or "涨跌" in col:
            change_col = col
        if "换手" in col:
            turnover_col = col
        if "成交额" in col or "金额" in col:
            amount_col = col
        if "总市值" in col:
            mv_col = col
        if "最新" in col or "现价" in col:
            price_col = col

    stocks = []
    for _, row in df.iterrows():
        stock = {
            "code": str(row.get(code_col, "")).strip(),
            "name": str(row.get(name_col, "")),
        }
        # 添加强制转数值的字段
        for col_key, col_name in [("price", price_col), ("change_pct", change_col),
                                   ("turnover_pct", turnover_col), ("amount", amount_col),
                                   ("market_cap", mv_col)]:
            val = row.get(col_name)
            try:
                stock[col_key] = round(float(val), 2) if val is not None else None
            except (ValueError, TypeError):
                stock[col_key] = None
        stocks.append(stock)

    return {
        "total": len(stocks),
        "time": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "stocks": stocks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="A 股盘中实时筛选（换手率+涨幅）")
    parser.add_argument("--min-turnover", type=float, default=5.0,
                        help="最低换手率 %（默认 5）")
    parser.add_argument("--max-turnover", type=float, default=10.0,
                        help="最高换手率 %（默认 10）")
    parser.add_argument("--min-change", type=float, default=3.0,
                        help="最低涨跌幅 %（默认 3）")
    parser.add_argument("--max-change", type=float, default=5.0,
                        help="最高涨跌幅 %（默认 5）")
    parser.add_argument("--include-st", action="store_true",
                        help="包含 ST 股票（默认排除）")
    parser.add_argument("--json", action="store_true",
                        help="以 JSON 格式输出（默认输出表格）")
    parser.add_argument("--top", type=int, default=0,
                        help="只输出前 N 只（0=全部）")
    args = parser.parse_args()

    debug(f"配置: 换手率[{args.min_turnover}%-{args.max_turnover}%], "
          f"涨幅[{args.min_change}%-{args.max_change}%], "
          f"{'' if args.include_st else '不'}包含ST")

    try:
        df = screen_intraday(
            min_turnover=args.min_turnover,
            max_turnover=args.max_turnover,
            min_change=args.min_change,
            max_change=args.max_change,
            exclude_st=not args.include_st,
        )
    except Exception as exc:
        debug(f"❌ 筛选过程异常: {exc}")
        print("[]" if args.json else "筛选失败")
        sys.exit(1)

    # 限制输出数量
    if args.top > 0 and len(df) > args.top:
        df = df.head(args.top)
        debug(f"限制输出前 {args.top} 只")

    code_col = "代码" if "代码" in df.columns else df.columns[0]
    name_col = "名称" if "名称" in df.columns else df.columns[1]

    if args.json:
        result = format_results(df)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if df.empty:
            print("\n⚠️ 当前无符合条件股票")
            print(f"   换手率: {args.min_turnover}% ~ {args.max_turnover}%")
            print(f"   涨幅: {args.min_change}% ~ {args.max_change}%")
            return

        print(f"\n{'='*70}")
        print(f"📊 盘中筛选结果 — {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}")
        print(f"条件: 换手率 {args.min_turnover}%~{args.max_turnover}% + "
              f"涨幅 {args.min_change}%~{args.max_change}%")
        print(f"共 {len(df)} 只股票")
        print(f"{'─'*70}")
        print(f"{'代码':>8} {'名称':<8} {'最新价':>8} {'涨幅%':>7} {'换手率%':>8} {'成交额':>12} {'总市值(亿)':>10}")
        print(f"{'─'*70}")

        change_col = "涨跌幅"
        turnover_col = "换手率"
        price_col = "最新价"
        amount_col = "成交额"
        mv_col = "总市值"
        for col in df.columns:
            if "涨跌幅" in col or "涨跌" in col:
                change_col = col
            if "换手" in col:
                turnover_col = col
            if "成交额" in col or "金额" in col:
                amount_col = col
            if "总市值" in col:
                mv_col = col
            if "最新" in col or "现价" in col:
                price_col = col

        for _, row in df.iterrows():
            code = str(row.get(code_col, "")).strip()
            name = str(row.get(name_col, ""))
            try:
                price = f"{float(row.get(price_col, 0)):.2f}"
            except (ValueError, TypeError):
                price = "N/A"
            try:
                chg = f"{float(row.get(change_col, 0)):+.2f}"
            except (ValueError, TypeError):
                chg = "N/A"
            try:
                tur = f"{float(row.get(turnover_col, 0)):.2f}"
            except (ValueError, TypeError):
                tur = "N/A"
            try:
                amt_val = float(row.get(amount_col, 0))
                amt = f"{amt_val/1e8:.1f}亿" if amt_val >= 1e8 else f"{amt_val:.0f}"
            except (ValueError, TypeError):
                amt = "N/A"
            try:
                mv_val = float(row.get(mv_col, 0))
                mv = f"{mv_val/1e8:.0f}" if mv_val else "N/A"
            except (ValueError, TypeError):
                mv = "N/A"

            print(f"{code:>8} {name:<8} {price:>8} {chg:>7} {tur:>8} {amt:>12} {mv:>10}")

        print(f"{'─'*70}")


if __name__ == "__main__":
    main()
