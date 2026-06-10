"""Diagnose a backtest trade ledger: where does the P&L actually die?

Reads a --dump-trades CSV plus cached OHLCV and reports: exit-reason economics,
per-year split, entry-extension (ATRs above the 20-EMA at signal) vs outcome —
the 'chasing' hypothesis — and the MFE giveback (how far winners ran before
being given back).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from swing_signals.config_loader import load_secrets, load_settings
from swing_signals.data.loader import DataLoader
from swing_signals.factors import indicators as ind


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    args = ap.parse_args()
    t = pd.read_csv(args.csv, parse_dates=["signal_date", "entry_date", "exit_date"])
    if t.empty:
        print("no trades")
        return 0

    settings, secrets = load_settings(), load_secrets()
    loader = DataLoader(settings, secrets)

    print(f"=== {len(t)} trades | total R {t.realized_r.sum():+.1f} | "
          f"mean {t.realized_r.mean():+.3f}R ===\n")

    print("--- by exit reason ---")
    g = t.groupby("exit_reason")["realized_r"].agg(["count", "mean", "sum"])
    print(g.round(3).to_string(), "\n")

    t["year"] = t["signal_date"].dt.year
    print("--- by year ---")
    g = t.groupby("year")["realized_r"].agg(["count", "mean", "sum"])
    print(g.round(3).to_string(), "\n")

    print("--- hold time ---")
    print(t.groupby(pd.cut(t.bars_held, [0, 5, 10, 20, 40, 200]), observed=True)[
        "realized_r"].agg(["count", "mean"]).round(3).to_string(), "\n")

    # Entry extension + MFE/MAE need bars: pull from cache (offline).
    ext, mfe, mae = [], [], []
    for _, r in t.iterrows():
        try:
            df = loader.get_ohlcv(
                r.ticker, str((r.signal_date - pd.Timedelta(days=120)).date()),
                str((r.exit_date + pd.Timedelta(days=3)).date()), offline=True,
            )
        except Exception:  # noqa: BLE001
            df = None
        if df is None or len(df) < 30:
            ext.append(None), mfe.append(None), mae.append(None)
            continue
        upto = df[df.index <= r.signal_date]
        if len(upto) < 25:
            ext.append(None)
        else:
            c = float(upto["close"].iloc[-1])
            e20 = float(ind.ema(upto["close"], 20).iloc[-1])
            a14 = float(ind.atr(upto["high"], upto["low"], upto["close"], 14).iloc[-1])
            ext.append((c - e20) / a14 if a14 > 0 else None)
        win = df[(df.index >= r.entry_date) & (df.index <= r.exit_date)]
        rps = r.risk_per_share
        if len(win) and rps and rps > 0:
            mfe.append((float(win["high"].max()) - r.entry_fill) / rps)
            mae.append((float(win["low"].min()) - r.entry_fill) / rps)
        else:
            mfe.append(None), mae.append(None)
    t["ext_atr"], t["mfe_r"], t["mae_r"] = ext, mfe, mae

    d = t.dropna(subset=["ext_atr"])
    if len(d) > 20:
        print("--- entry extension (ATRs above EMA20 at signal) vs outcome ---")
        d = d.copy()
        d["ext_bucket"] = pd.qcut(d.ext_atr, 4, duplicates="drop")
        print(d.groupby("ext_bucket", observed=True)["realized_r"]
              .agg(["count", "mean", "sum"]).round(3).to_string(), "\n")

    d2 = t.dropna(subset=["mfe_r"])
    if len(d2) > 20:
        ran_1r = d2[d2.mfe_r >= 1.0]
        print(f"--- giveback: {len(ran_1r)}/{len(d2)} trades reached +1R intratrade; "
              f"their realized mean {ran_1r.realized_r.mean():+.3f}R ---")
        ran_15 = d2[d2.mfe_r >= 1.5]
        print(f"    {len(ran_15)} reached +1.5R; realized mean "
              f"{ran_15.realized_r.mean():+.3f}R")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
