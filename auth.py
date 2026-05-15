"""Simple password authentication for Streamlit apps.

Credentials are stored in .streamlit/secrets.toml (local) or the
Streamlit Cloud Secrets tab.  Format:

    [auth]
    [auth.users]
    [auth.users.admin]
    username = "admin"
    password = "your-password"
    role = "admin"

    [auth.users.viewer1]
    username = "john"
    password = "their-password"
    role = "viewer"
"""
from __future__ import annotations

import streamlit as st


def _get_users() -> dict[str, dict]:
    try:
        return dict(st.secrets["auth"]["users"])
    except (KeyError, FileNotFoundError):
        return {}


def require_login():
    if st.session_state.get("authenticated"):
        return

    users = _get_users()
    if not users:
        st.error("No auth credentials configured. Add [auth.users] to your Streamlit secrets.")
        st.stop()

    st.markdown(
        "<div style='max-width:400px;margin:80px auto;'>",
        unsafe_allow_html=True,
    )
    st.subheader("Sign In")

    username = st.text_input("Username", key="_auth_user")
    password = st.text_input("Password", type="password", key="_auth_pass")

    if st.button("Sign in", type="primary", use_container_width=True):
        for key, creds in users.items():
            if creds["username"] == username and creds["password"] == password:
                st.session_state["authenticated"] = True
                st.session_state["auth_username"] = creds["username"]
                st.session_state["auth_role"] = creds.get("role", "viewer")
                st.rerun()
        st.error("Invalid username or password.")

    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


def logout():
    for key in ["authenticated", "auth_username", "auth_role"]:
        st.session_state.pop(key, None)
    st.rerun()


def current_user() -> str | None:
    return st.session_state.get("auth_username")


def current_role() -> str | None:
    return st.session_state.get("auth_role")


def is_admin() -> bool:
    return st.session_state.get("auth_role") == "admin"
