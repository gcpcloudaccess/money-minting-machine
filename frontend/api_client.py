import os

import httpx
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")


def _client() -> httpx.Client:
    return httpx.Client(base_url=BACKEND_URL, timeout=120.0)


def get(path: str, **params):
    try:
        with _client() as c:
            resp = c.get(path, params=params or None)
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        st.error(f"Cannot reach backend at {BACKEND_URL}. Is `uvicorn app.main:app` running?")
        st.stop()
    except httpx.HTTPStatusError as e:
        st.error(f"Backend error on {path}: {e.response.status_code} {e.response.text}")
        st.stop()


def post(path: str, **params):
    try:
        with _client() as c:
            resp = c.post(path, params=params or None)
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        st.error(f"Cannot reach backend at {BACKEND_URL}. Is `uvicorn app.main:app` running?")
        st.stop()
    except httpx.HTTPStatusError as e:
        st.error(f"Backend error on {path}: {e.response.status_code} {e.response.text}")
        st.stop()
