#!/usr/bin/env python3
"""
ETF 시그널 & 리밸런싱 대시보드용 시세·히스토리 JSON 생성 스크립트.

안정적인 자산배분용 코어 티커(나스닥·배당성장·커버드콜)를 기본으로 두고,
반도체·레버리지 새틀라이트 티커를 함께 수집해 대시보드 JSON 포맷으로 저장합니다.

사용 예:
    pip install yfinance
    python fetch_etf_signals.py --output data/etf_signals.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yfinance as yf

# 안정적 자산배분 코어 (나스닥 1x · 슈드 배당성장 · S&P500/나스닥 커버드콜)
CORE_TICKERS = ["QQQ", "SCHD", "JEPI", "JEPQ"]

# 성장·레버리지 새틀라이트 (반도체 1x · 나스닥 2x · 반도체 2x/3x)
SATELLITE_TICKERS = ["SMH", "QLD", "USD", "SOXL"]

DEFAULT_TICKERS = CORE_TICKERS + SATELLITE_TICKERS


def fetch_etf_payload(
    tickers: list[str],
    history_points: int = 126,
) -> dict[str, Any]:
    """각 ETF의 최신 시세, 52주 고저점, 최근 종가 히스토리를 수집합니다."""
    etfs: list[dict[str, Any]] = []
    common_dates: list[str] = []
    latest_market_date: str | None = None
    core_set = {t.upper() for t in CORE_TICKERS}

    for raw_symbol in tickers:
        symbol = raw_symbol.strip().upper()
        if not symbol:
            continue

        ticker = yf.Ticker(symbol)
        # 52주 고점/저점 산출을 위해 1년 일봉 조회
        hist = ticker.history(period="1y", interval="1d", auto_adjust=False)
        if hist is None or hist.empty or len(hist) < 2:
            print(f"[WARN] {symbol}: 유효한 시세 데이터를 가져오지 못해 건너뜁니다.", file=sys.stderr)
            continue

        hist = hist.dropna(subset=["Close"])
        if len(hist) < 2:
            print(f"[WARN] {symbol}: 종가 데이터가 부족해 건너뜁니다.", file=sys.stderr)
            continue

        last_price = round(float(hist["Close"].iloc[-1]), 4)
        prev_close = round(float(hist["Close"].iloc[-2]), 4)
        high_52w = round(float(hist["High"].max()), 4)
        low_52w = round(float(hist["Low"].min()), 4)
        volume = int(hist["Volume"].iloc[-1]) if "Volume" in hist.columns else 0

        recent = hist.tail(history_points)
        dates = [idx.strftime("%Y-%m-%d") for idx in recent.index]
        prices = [round(float(val), 2) for val in recent["Close"].tolist()]

        if not common_dates or len(dates) > len(common_dates):
            common_dates = dates
        if dates:
            latest_market_date = dates[-1]

        etfs.append(
            {
                "symbol": symbol,
                "group": "core" if symbol in core_set else "satellite",
                "lastPrice": last_price,
                "prevClose": prev_close,
                "high52w": high_52w,
                "low52w": low_52w,
                "volume": volume,
                "prices": prices,
            }
        )

    if not etfs:
        raise RuntimeError("수집된 ETF 데이터가 없습니다. 티커 목록 또는 네트워크 상태를 확인하세요.")

    updated_at = latest_market_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {
        "updatedAt": updated_at,
        "generatedAtUtc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "coreTickers": CORE_TICKERS,
        "satelliteTickers": SATELLITE_TICKERS,
        "dates": common_dates,
        "etfs": etfs,
    }


def parse_args() -> argparse.Namespace:
    env_tickers = os.getenv("ETF_TICKERS", "")
    default_list = [t.strip() for t in env_tickers.split(",") if t.strip()] or DEFAULT_TICKERS

    parser = argparse.ArgumentParser(
        description="ETF 시그널 대시보드용 yfinance JSON 생성기"
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=default_list,
        help="수집할 ETF 티커 목록 (기본값: 코어 QQQ SCHD JEPI JEPQ + 새틀라이트 SMH QLD USD SOXL)",
    )
    parser.add_argument(
        "--core-only",
        action="store_true",
        help="안정적 코어 티커(QQQ, SCHD, JEPI, JEPQ)만 수집",
    )
    parser.add_argument(
        "--points",
        type=int,
        default=126,
        help="대시보드 차트에 포함할 최근 거래일 수 (기본값: 126, 약 6개월)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/etf_signals.json"),
        help="출력 JSON 파일 경로 (기본값: data/etf_signals.json)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tickers = CORE_TICKERS if args.core_only else args.tickers
    payload = fetch_etf_payload(tickers, history_points=max(20, args.points))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[OK] {len(payload['etfs'])}개 ETF 데이터 저장 완료 -> {args.output} (기준일: {payload['updatedAt']})")


if __name__ == "__main__":
    main()
