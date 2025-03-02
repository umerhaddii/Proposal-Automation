import psycopg2
from psycopg2 import sql
import streamlit as st

def get_db_connection():
    return psycopg2.connect(
        dbname=st.secrets["DB_NAME"],
        user=st.secrets["DB_USER"],
        password=st.secrets["DB_PASSWORD"],
        host=st.secrets["DB_HOST"],
        port=st.secrets["DB_PORT"]
    )

# Add to requirements.txt: psycopg2-binary>=2.9.9
