import streamlit as st


@st.cache_resource
def get_supabase_client():
    try:
        from supabase import create_client
    except ModuleNotFoundError as exc:
        if exc.name != "supabase":
            raise
        raise RuntimeError(
            "The Supabase Python package is missing. Install project dependencies "
            "with: python -m pip install -r requirements.txt"
        ) from exc

    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SECRET_KEY"],
    )
