"""Shared password gate. Each page calls ``require_auth()`` before rendering.

Fail-closed by design: if ``dashboard_password`` is missing from the Streamlit
secrets (typo, secrets box wiped on a redeploy), the dashboard refuses to render
rather than silently publishing the account's equity, positions, and trades on a
public URL. Local development / tests can opt into an open dashboard explicitly
with ``SWING_DASHBOARD_ALLOW_OPEN=1`` — an env var a cloud deploy never sets by
accident.
"""

from __future__ import annotations

import hmac
import os
import time

import streamlit as st


def _password() -> str | None:
    try:
        if "dashboard_password" in st.secrets:
            return str(st.secrets["dashboard_password"]) or None  # blank == unset
    except Exception:  # noqa: BLE001 - no secrets file locally
        pass
    return None


def require_auth() -> None:
    pw = _password()
    if not pw:
        if os.environ.get("SWING_DASHBOARD_ALLOW_OPEN") == "1":
            st.warning("⚠ Dashboard running OPEN (SWING_DASHBOARD_ALLOW_OPEN=1) — dev only.")
            return
        st.error(
            "🔒 `dashboard_password` is not configured — refusing to serve. "
            "Set it in the Streamlit secrets (or export SWING_DASHBOARD_ALLOW_OPEN=1 "
            "for local development)."
        )
        st.stop()
        return
    if st.session_state.get("authed"):
        return
    st.title("🔒 Swing Trading Dashboard")
    with st.form("login"):
        entered = st.text_input("Password", type="password")
        if st.form_submit_button("Enter"):
            # Exponential per-session delay blunts scripted brute force; the
            # constant-time compare avoids the (mostly theoretical) timing oracle.
            attempts = int(st.session_state.get("auth_attempts", 0))
            if attempts:
                time.sleep(min(2 ** attempts, 30))
            if hmac.compare_digest(entered.encode(), pw.encode()):
                st.session_state["authed"] = True
                st.session_state["auth_attempts"] = 0
                st.rerun()
            else:
                st.session_state["auth_attempts"] = attempts + 1
                st.error("Incorrect password.")
    st.stop()
