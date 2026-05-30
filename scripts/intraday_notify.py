#!/usr/bin/env python3
"""
盘中扫描通知格式化脚本 — 将筛选结果 JSON 转为飞书消息卡片 或 表格展示

用法:
    cat result.json | python scripts/intraday_notify.py          # 飞书卡片 (stdout)
    cat result.json | python scripts/intraday_notify.py --table  # 终端表格 (stderr)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta


def build_feishu_card(data: dict) -> dict:
    """构建飞书消息卡片"""
    stocks = data.get("stocks", [])
    total = data.get("total", len(stocks))

    bj_tz = timezone(timedelta(hours=8))
    time_str = datetime.now(bj_tz).strftime("%Y-%m-%d %H:%M:%S")

    lines = [f"📊 A股尾盘异动扫描 — {time_str}"]
    lines.append("")
    lines.append("条件: 换手率 5%-10% + 涨幅 3%-5%")
    lines.append(f"命中: {total} 只")
    lines.append("")

    if stocks:
        for s in stocks[:20]:
            chg = f"{s['change_pct']:+.2f}%" if s.get("change_pct") is not None else "N/A"
            tur = f"{s['turnover_pct']:.2f}%" if s.get("turnover_pct") is not None else "N/A"
            lines.append(f"· {s['name']}({s['code']}) 涨幅{chg} 换手率{tur}")

        if len(stocks) > 20:
            lines.append(f"... 还有 {len(stocks) - 20} 只")
    else:
        lines.append("✅ 当前无符合条件股票")

    lines.append("")
    lines.append("⚠️ 仅为技术面筛选，不构成投资建议")

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "📊 A股尾盘异动扫描"},
                "template": "orange" if total > 0 else "green",
            },
            "elements": [
                {"tag": "markdown", "content": "\n".join(lines)},
            ],
        },
    }


def print_table(data: dict) -> None:
    """在终端打印表格"""
    stocks = data.get("stocks", [])
    total = data.get("total", len(stocks))

    print("=" * 70, file=sys.stderr)
    print(f"{'代码':>8} {'名称':<8} {'最新价':>8} {'涨幅%':>7} {'换手率%':>8}", file=sys.stderr)
    print("-" * 45, file=sys.stderr)

    if stocks:
        for s in stocks:
            chg = f"{s['change_pct']:+.2f}" if s.get("change_pct") is not None else "N/A"
            tur = f"{s['turnover_pct']:.2f}" if s.get("turnover_pct") is not None else "N/A"
            prc = f"{s['price']:.2f}" if s.get("price") is not None else "N/A"
            print(f"{s['code']:>8} {s['name']:<8} {prc:>8} {chg:>7} {tur:>8}", file=sys.stderr)
    else:
        print("当前无符合条件股票", file=sys.stderr)

    print("=" * 70, file=sys.stderr)
    print(f"✅ 共 {total} 只", file=sys.stderr)


def main() -> None:
    raw = sys.stdin.read().strip()
    if not raw:
        data = {"total": 0, "stocks": []}
    else:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            print("错误: 无法解析 JSON", file=sys.stderr)
            sys.exit(1)

    if "--table" in sys.argv:
        print_table(data)
    else:
        card = build_feishu_card(data)
        sys.stdout.write(json.dumps(card, ensure_ascii=False))


if __name__ == "__main__":
    main()
