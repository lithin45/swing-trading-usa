"""Entry flow: submit_entries against a fake broker — idempotency, gating, dry-run."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select

from swing_signals.broker.base import BrokerAccount, BrokerOrder, BrokerPosition
from swing_signals.broker.entries import submit_entries
from swing_signals.config_loader import Secrets, load_settings
from swing_signals.persistence.db import make_engine, session_scope
from swing_signals.persistence.models import Trade
from swing_signals.persistence.repository import create_run, save_signals
from swing_signals.scoring.engine import Signal as EngineSignal

DAY = date(2024, 1, 8)
TS = datetime(2024, 1, 8, 17, 0, 0)


class FakeBroker:
    name = "fake"

    def __init__(self, *, equity=500.0, buying_power=500.0, positions=None, open_orders=None):
        self.enabled = True
        self._account = BrokerAccount(equity=equity, cash=equity, buying_power=buying_power)
        self._positions = positions or []
        self._open_orders = open_orders or []
        self.submitted: list[BrokerOrder] = []
        self._n = 0

    def get_account(self):
        return self._account

    def list_positions(self):
        return list(self._positions)

    def get_position(self, symbol):
        return next((p for p in self._positions if p.symbol == symbol), None)

    def list_open_orders(self):
        return list(self._open_orders)

    def get_order_by_id(self, order_id):
        pool = self.submitted + self._open_orders
        return next((o for o in pool if o.id == order_id), None)

    def _order(self, symbol, side, type_, qty, coid, limit_price=None, stop_price=None):
        self._n += 1
        o = BrokerOrder(
            id=f"ord-{self._n}", client_order_id=coid, symbol=symbol, side=side, type=type_,
            status="accepted", qty=qty, notional=None, limit_price=limit_price,
            stop_price=stop_price, filled_qty=0.0, filled_avg_price=None,
        )
        self.submitted.append(o)
        return o

    def submit_limit_buy(self, symbol, *, qty, limit_price, client_order_id):
        return self._order(symbol, "buy", "limit", qty, client_order_id, limit_price=limit_price)

    def submit_market_buy(self, symbol, *, qty, client_order_id):
        return self._order(symbol, "buy", "market", qty, client_order_id)

    def submit_sell(self, symbol, *, qty, order_type="market", limit_price=None,
                    stop_price=None, client_order_id):
        return self._order(symbol, "sell", order_type, qty, client_order_id,
                           limit_price=limit_price, stop_price=stop_price)

    def cancel_order(self, order_id):
        pass

    def get_latest_price(self, symbol):
        return None


def _sig(symbol, *, score=80.0, rank=1, shares=1.5, risk=0.01) -> EngineSignal:
    return EngineSignal(
        ticker=symbol, signal_date=DAY, direction="LONG", conviction_score=score,
        conviction_tier="High", reference_price=101.0, atr=3.0,
        entry_zone_low=99.0, entry_zone_high=100.0, stop_price=94.0, stop_distance_atr=2.0,
        target_price=112.0, reward_risk=2.0, suggested_risk_pct=risk, suggested_shares=shares,
        chandelier_stop=95.0, regime_state="GREEN", rank=rank,
        factor_contributions={}, agreement_score=1.0, flags=[],
    )


def _settings(tmp_path, **broker_overrides):
    s = load_settings()
    s.run.db_url = f"sqlite:///{tmp_path}/trade.db"
    s.broker.enabled = True
    # These tests exercise the simple (fractional) path sized off the engine's number;
    # the bracket + live-equity path has its own test file.
    s.broker.entry_class = "simple"
    s.broker.size_from_live_equity = False
    for k, v in broker_overrides.items():
        setattr(s.broker, k, v)
    return s


def _secrets(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SWING_DATABASE_URL", raising=False)
    return Secrets(_env_file=None)  # hermetic: ignore the dev's .env


def _seed(db_url, sigs):
    with session_scope(make_engine(db_url)) as s:
        run = create_run(s, run_ts=TS, trading_day=DAY, status="success")
        save_signals(s, run, sigs, created_at=TS)


def _trades(db_url):
    """Read trade rows into plain dicts inside the session (avoid detached ORM access)."""
    with session_scope(make_engine(db_url)) as s:
        return {
            t.symbol: {
                "status": t.status, "limit_price": t.limit_price, "qty": t.qty,
                "entry_client_order_id": t.entry_client_order_id,
                "risk_per_share": t.risk_per_share, "effective_stop": t.effective_stop,
            }
            for t in s.scalars(select(Trade))
        }


def test_submit_entries_creates_pending_trades(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    _seed(s.run.db_url, [_sig("AAPL"), _sig("MSFT", rank=2)])
    fake = FakeBroker()
    report = submit_entries(s, _secrets(monkeypatch), today=DAY, broker=fake)

    assert sorted(report.submitted) == ["AAPL", "MSFT"]
    assert len(fake.submitted) == 2
    trades = _trades(s.run.db_url)
    assert trades["AAPL"]["status"] == "pending_entry"
    assert trades["AAPL"]["limit_price"] == 100.0  # entry_zone_high
    assert trades["AAPL"]["entry_client_order_id"] == "swing-20240108-AAPL-entry"
    assert trades["AAPL"]["risk_per_share"] == 6.0  # 100 - 94


def test_idempotent_rerun_skips_existing(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    _seed(s.run.db_url, [_sig("AAPL")])
    submit_entries(s, _secrets(monkeypatch), today=DAY, broker=FakeBroker())
    second = FakeBroker()
    report = submit_entries(s, _secrets(monkeypatch), today=DAY, broker=second)
    assert report.submitted == []
    assert report.skipped_existing == ["AAPL"]
    assert len(second.submitted) == 0  # never double-submits
    assert len(_trades(s.run.db_url)) == 1


def test_skips_symbol_already_held(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    _seed(s.run.db_url, [_sig("AAPL")])
    pos = BrokerPosition("AAPL", 1.0, 100.0, 100.0, 0.0, 100.0)
    report = submit_entries(s, _secrets(monkeypatch), today=DAY, broker=FakeBroker(positions=[pos]))
    assert report.skipped_position == ["AAPL"]
    assert _trades(s.run.db_url) == {}


def test_max_positions_gate(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    s.risk.max_positions = 1
    _seed(s.run.db_url, [_sig("AAPL", rank=1), _sig("MSFT", rank=2)])
    report = submit_entries(s, _secrets(monkeypatch), today=DAY, broker=FakeBroker())
    assert report.submitted == ["AAPL"]  # ranked first
    assert [sym for sym, _ in report.skipped_gated] == ["MSFT"]


def test_heat_cap_gate(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    s.risk.portfolio_heat_cap = 0.015  # one 1% trade fits, the second pushes to 2%
    _seed(s.run.db_url, [_sig("AAPL", rank=1), _sig("MSFT", rank=2)])
    report = submit_entries(s, _secrets(monkeypatch), today=DAY, broker=FakeBroker())
    assert report.submitted == ["AAPL"]
    assert [sym for sym, _ in report.skipped_gated] == ["MSFT"]


def test_broker_disabled_is_noop(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    s.broker.enabled = False
    _seed(s.run.db_url, [_sig("AAPL")])
    report = submit_entries(s, _secrets(monkeypatch), today=DAY, broker=FakeBroker())
    assert report.submitted == []
    assert _trades(s.run.db_url) == {}


def test_dry_run_submits_and_writes_nothing(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    _seed(s.run.db_url, [_sig("AAPL")])
    fake = FakeBroker()
    report = submit_entries(s, _secrets(monkeypatch), today=DAY, broker=fake, dry_run=True)
    assert report.submitted == ["AAPL"]  # would-submit
    assert len(fake.submitted) == 0      # but nothing actually sent
    assert _trades(s.run.db_url) == {}   # and nothing persisted


def test_size_skip_when_below_min(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    # tiny buying power -> notional below the $1 minimum
    _seed(s.run.db_url, [_sig("AAPL", shares=0.001)])
    report = submit_entries(
        s, _secrets(monkeypatch), today=DAY, broker=FakeBroker(buying_power=500.0)
    )
    assert report.submitted == []
    assert [sym for sym, _ in report.skipped_size] == ["AAPL"]
