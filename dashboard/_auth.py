"""Shared password gate. Each page calls ``require_auth()`` before rendering."""

from __future__ import annotations

import streamlit as st


def _password() -> str | None:
    try:
        if "dashboard_password" in st.secrets:
            return str(st.secrets["dashboard_password"])
    except Exception:  # noqa: BLE001 - no secrets file locally
        pass
    return None


def require_auth() -> None:
    pw = _password()
    if not pw:
        st.info("No dashboard_password set — running open. Set one in secrets to lock it down.")
        return
    if st.session_state.get("authed"):
        return
    st.title("🔒 Swing Trading Dashboard")
    with st.form("login"):
        entered = st.text_input("Password", type="password")
        if st.form_submit_button("Enter"):
            if entered == pw:
                st.session_state["authed"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    st.stop()
