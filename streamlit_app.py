import streamlit as st
from app import init_db, generate_mom, get_bot_response
import os
from datetime import datetime
import sqlite3

# Initialize database
try:
    init_db()
except Exception as e:
    st.error(f"Database Initialization Error: {str(e)}")
    st.stop()

st.set_page_config(
    page_title="Meeting Minutes Bot",
    page_icon="📝",
    layout="wide"
)

# Initialize session state variables
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "conversation_started" not in st.session_state:
    st.session_state.conversation_started = False

def create_new_session():
    conn = sqlite3.connect('mom_database.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sessions (consultant_id, start_time, status) VALUES (?, ?, ?)",
        (1, datetime.now(), "active")
    )
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id

def store_qa_local(session_id, question, answer):
    conn = sqlite3.connect('mom_database.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO mom_data (session_id, question, answer, timestamp) VALUES (?, ?, ?, ?)",
        (session_id, question, answer, datetime.now())
    )
    conn.commit()
    conn.close()

st.title("Meeting Minutes Assistant 📝")

with st.sidebar:
    st.header("Session Controls")
    if st.button("Start New Session"):
        st.session_state.session_id = create_new_session()
        st.session_state.chat_history = []
        st.session_state.conversation_started = False
        st.rerun()
    
    if st.session_state.session_id:
        st.success(f"Active Session ID: {st.session_state.session_id}")

if not st.session_state.session_id:
    st.info("👈 Click 'Start New Session' to begin")
else:
    # Start the conversation if not already started
    if not st.session_state.conversation_started:
        response = get_bot_response("need to make mom", st.session_state.session_id)
        st.session_state.chat_history.append({"role": "assistant", "content": response["response"]})
        st.session_state.conversation_started = True
        st.rerun()
    
    # Display chat history
    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.chat_history:
            if msg["role"] == "user":
                st.chat_message("user").write(msg["content"])
            else:
                st.chat_message("assistant").write(msg["content"])
    
    # Handle user input
    user_input = st.chat_input("Your answer:")
    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        response = get_bot_response(user_input, st.session_state.session_id)
        
        if response.get("error"):
            if response["error"] == "api_auth_error":
                st.error("API Authentication Error. Please contact support.")
                st.stop()
            else:
                st.warning("An error occurred. Please try again.")
        else:
            if "Final Meeting Minutes" in response["response"]:
                st.session_state.mom_viewed = True
                parts = response["response"].split("\n\n", 1)
                if len(parts) > 1:
                    mom_content = parts[1]
                else:
                    mom_content = response["response"]
                st.markdown("## Final Meeting Minutes")
                st.markdown(mom_content)
                st.download_button("Download MoM", mom_content, file_name="Meeting_Minutes.txt")
            else:
                st.session_state.chat_history.append({"role": "assistant", "content": response["response"]})
                st.rerun()
