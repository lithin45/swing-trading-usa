"""Live-vs-shadow reconciliation + the broker-gate rejection audit trail."""

from __future__ import annotations

import json
from datetime import date, datetime

from swing_signals.persistence.db import make_engine, session_scope
from swing_signals.persistence.models import Outcome, Run, Signal, Trade
from swing_signals.persistence.repository import save_broker_rejections
from swing_signals.tracking.reconcile import reconcile

DAY = date(2024, 2, 20)
NOW = datetime(2024, 2, 20, 17, 0, 0)


def _seed(session):
    run = Run(run_ts=NOW, trading_day=DAY, status="success", n_signals=1)
    session.add(run)
    session.flush()
    sig = Signal(
        run_id=run.id, signal_date=DAY, symbol="AAPL", composite_score=80.0,
        stop_price=94.0, target_price=112.0, created_at=NOW,
    )
    session.add(sig)
    session.flush()
    # Theoretical grade: market-at-next-open reference model said +1.5R.
    session.add(Outcome(
        signal_id=sig.id, status="target_hit", actual_entry=100.5, exit_price=112.0,
        exit_date=date(2024, 3, 1), bars_held=8, realized_r=1.5, pct_return=0.115,
        slippage=0.0050, updated_at=NOW,
    ))
    # The real paper trade: limit at 100, filled at 100.2, stopped at 93.8.
    session.add(Trade(
        signal_id=sig.id, signal_date=DAY, symbol="AAPL", status="closed",
        order_class="simple", entry_order_type="limit", limit_price=100.0,
        actual_entry=100.2, entry_fill_date=DAY, qty=1.5, stop_price=94.0,
        target_price=112.0, effective_stop=94.0, risk_per_share=6.2,
        exit_reason="stopped", exit_price=93.8, exit_date=date(2024, 3, 1),
        realized_r=-1.03, pnl=-9.6, pct_return=-0.0639,
        created_at=NOW, updated_at=NOW,
    ))
    # A second submission that fell back to market (counts against the fill rate).
    session.add(Trade(
        signal_date=DAY, symbol="MSFT", status="canceled", order_class="simple",
        entry_order_type="market", entry_client_order_id="swing-x-MSFT-mktfallback",
        limit_price=400.0, exit_reason="unfilled", created_at=NOW, updated_at=NOW,
    ))


def test_reconcile_joins_trades_to_outcomes(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/rec.db")
    with session_scope(engine) as session:
        _seed(session)
        report = reconcile(session)

    assert report.n_closed == 1
    row = report.rows[0]
    assert row.symbol == "AAPL"
    # entry slippage: 100.2 vs limit 100.0 = +20 bps; +10 bps over the model
    assert row.entry_slippage_bps == 20.0
    assert row.entry_excess_vs_model_bps == 10.0
    # exit slippage: stopped at 93.8 vs planned 94.0
    assert row.exit_slippage_bps == round((93.8 / 94.0 - 1.0) * 1e4, 2)
    assert row.shadow_r == 1.5 and row.live_r == -1.03
    assert row.r_delta == round(-1.03 - 1.5, 4)
    # fill rate: AAPL filled at the limit; MSFT began as a limit but fell back
    assert report.n_limit_submitted == 2
    assert report.n_limit_filled == 1
    assert report.limit_fill_rate == 0.5
    assert report.monthly_entries == {"2024-02": 2}


def test_broker_rejections_idempotent(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/rej.db")
    decision = {
        "signal_date": DAY, "symbol": "NVDA", "gate": "heat_cap",
        "reason": "portfolio heat cap reached (10%)",
        "details": {"open_heat_pct": 0.095, "portfolio_heat_cap": 0.10},
    }
    with session_scope(engine) as session:
        assert save_broker_rejections(session, [decision], created_at=NOW) == 1
        # same-day re-run of the trade job: same gate decision inserts nothing new
        assert save_broker_rejections(session, [decision], created_at=NOW) == 0
    with session_scope(engine) as session:
        from sqlalchemy import select

        from swing_signals.persistence.models import BrokerRejection

        rows = list(session.scalars(select(BrokerRejection)))
        assert len(rows) == 1
        assert rows[0].gate == "heat_cap"
        assert json.loads(rows[0].details)["portfolio_heat_cap"] == 0.10
