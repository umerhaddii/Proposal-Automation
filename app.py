from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.runnables import RunnablePassthrough
from langchain_core.chat_history import InMemoryChatMessageHistory
import sqlite3
import os
import logging
import json
from datetime import datetime
from openai import OpenAI
import streamlit as st


# Setup logging and environment
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Replace database path
DATABASE_PATH = "mom_database.db"

def adapt_datetime(ts):
    return ts.isoformat()

def convert_datetime(ts):
    return datetime.fromisoformat(ts)

# Initialize SQLite database
def init_db():
    # Register datetime adapter
    sqlite3.register_adapter(datetime, adapt_datetime)
    sqlite3.register_converter("timestamp", convert_datetime)
    
    conn = sqlite3.connect(DATABASE_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS consultants (
        id INTEGER PRIMARY KEY,
        name TEXT
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY,
        consultant_id INTEGER,
        start_time TIMESTAMP,
        status TEXT,
        FOREIGN KEY (consultant_id) REFERENCES consultants(id)
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS mom_data (
        id INTEGER PRIMARY KEY,
        session_id INTEGER,
        question TEXT,
        answer TEXT,
        timestamp TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS mom_documents (
        id INTEGER PRIMARY KEY,
        session_id INTEGER,
        content TEXT,
        timestamp TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    )
    ''')
    conn.commit()
    conn.close()

# Function to store question and answer
def store_qa(session_id, question, answer):
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO mom_data (session_id, question, answer, timestamp) VALUES (?, ?, ?, ?)",
            (session_id, question, answer, datetime.now())
        )
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()

# Function to create new session
def create_session(consultant_id):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sessions (consultant_id, start_time, status) VALUES (?, ?, ?)",
        (consultant_id, datetime.now(), "active")
    )
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id

# Function to get MoM data for a session
def get_mom_data(session_id):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT question, answer FROM mom_data WHERE session_id = ?",
        (session_id,)
    )
    data = cursor.fetchall()
    conn.close()
    
    mom_dict = {}
    for question, answer in data:
        key = question.lower()
        # More specific check for company name question
        if any(phrase in key for phrase in ["company name", "name of the company", "what is the name"]):
            mom_dict["company_name"] = answer.strip()
        elif "present" in key or "attendees" in key:
            mom_dict["attendees"] = answer
        elif "place" in key or "location" in key:
            mom_dict["location"] = answer
        elif "last" in key or "duration" in key:
            mom_dict["duration"] = answer
        elif "employee" in key:
            mom_dict["employees"] = answer
        elif "management" in key:
            mom_dict["management_levels"] = answer
        else:
            cleaned_key = key.replace("?", "").strip()
            mom_dict[cleaned_key] = answer
    
    # Add debug logging to check the data
    logger.info(f"MoM Data: {mom_dict}")
    return mom_dict

def initialize_llm():
    # Use Streamlit secrets instead of env vars
    api_key = st.secrets["OPENAI_API_KEY"]
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in secrets")
    
    return ChatOpenAI(
        model_name="gpt-4o-mini",
        temperature=0.7,
        api_key=api_key
    )

# Initialize LLM
llm = initialize_llm()

# System prompt for conversation flow
system_prompt = """You are a highly intelligent meeting assistant designed to gather all necessary information for creating accurate and detailed Meeting Minutes (MoM). Your task is to conduct an interview with a consultant by asking questions in a natural, conversational manner. Begin by asking the essential questions below:

*Essential Questions:*
1. What is the name of the company?
2. Who was present at the meeting?
3. Where did the meeting take place?
4. How long did the meeting last?
5. How many employees does the company have?
6. How many levels of management does the company have?

After receiving responses to these, analyze the context of the conversation to determine if additional details are needed. Based on the context, ask any relevant optional questions from the following list to enrich the meeting record:

*Optional Questions (ask if context indicates relevance):*
- What are the company's main strategic goals for this period?
- What is the company's focus when it comes to development?
- Which target groups within the company are prioritized for development?
- What are the main challenges these target groups are currently facing?
- Are there any specific competencies or skills the company wants to prioritize across teams?
- What learning and development programs are currently in place?
- How do you currently measure skill levels and identify training needs?
- Which learning formats do employees prefer (online programs, in-person workshops, blended learning)?
- Is there any specific format desired for the development (trainings, training days, team building, coaching, etc.)?

Once you have gathered all the necessary and contextually relevant responses, also ask:
- What are the key action items from this discussion?
- Who is responsible for following up on these topics?
- When should we check in again on the progress of development initiatives?

Before concluding, confirm with the user if there is any additional information they would like to add. Your goal is to ensure that every piece of relevant data is captured in a structured way to form a complete MoM. Always maintain a conversational tone, adapt your questions based on previous responses, and guide the conversation naturally toward a comprehensive meeting record."""

mom_generation_prompt = """You are a professional meeting assistant tasked with generating comprehensive Meeting Minutes (MoM) that a consultant can immediately use for follow-ups. Based on the structured interview data provided, generate a final MoM document with the following sections and in a clear, business-friendly format:

## Meeting Minutes (MoM)

### 1. Meeting Overview
- *Company Name:* [Extract from data]
- *Meeting Date & Time:* [If available]
- *Location:* [Extract from data]
- *Duration:* [Extract from data]
- *Participants:* [List all names and roles]

### 2. Meeting Objective
- Provide a concise summary of the meeting's purpose (e.g., discussing training needs, leadership development, or strategic planning).

### 3. Discussion Summary
- *Key Topics:*  
  Summarize the main discussion points. Include any specific areas such as:
  - Strategic goals and development focus
  - Target groups for development and current challenges
  - Existing training programs and preferred learning formats
- *Additional Context:*  
  Include any notable insights, pain points, or suggestions mentioned during the discussion.

### 4. Action Items & Follow-Up
- *Action Items:*  
  List each agreed-upon action with a brief description.
- *Responsibilities:*  
  Specify who is responsible for each action.
- *Follow-Up:*  
  Note the agreed timeline or date for checking progress.

### 5. Additional Notes
- Add any extra information or clarifications provided that do not fit in the sections above.

Using the structured interview data below, generate the final Meeting Minutes (MoM) in the above format:

{interview_data}
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{input}")
])

# Chain with history
def create_chain_with_history(llm, prompt):
    chain = (
        RunnablePassthrough.assign(
            history=lambda x: x.get("history", [])
        )
        | prompt
        | llm
    )
    
    chain_with_history = RunnableWithMessageHistory(
        chain,
        lambda session_id: InMemoryChatMessageHistory(),
        input_messages_key="input",
        history_messages_key="history"
    )
    
    return chain_with_history

# Session state tracking with simplified question handling
class SessionState:
    def __init__(self):
        self.active_sessions = {}  # Maps session IDs to current state
    
    def start_session(self, consultant_id):
        session_id = create_session(consultant_id)
        self.active_sessions[session_id] = {
            "essential_complete": False,
            "optional_complete": False,
            "mom_generated": False
        }
        return session_id
    
    def get_state(self, session_id):
        return self.active_sessions.get(session_id, {})

    def mark_essential_complete(self, session_id):
        if session_id in self.active_sessions:
            self.active_sessions[session_id]["essential_complete"] = True

    def mark_optional_complete(self, session_id):
        if session_id in self.active_sessions:
            self.active_sessions[session_id]["optional_complete"] = True

# Initialize components
session_state = SessionState()
chain_with_history = create_chain_with_history(llm, prompt)
init_db()

def format_mom_data(mom_dict):
    """Format the MoM data for the LLM prompt"""
    formatted_data = []
    for key, value in mom_dict.items():
        formatted_data.append(f"{key}: {value}")
    return "\n".join(formatted_data)

# Update generate_mom function to use new OpenAI client
def generate_mom(session_id):
    try:
        mom_data = get_mom_data(session_id)
        interview_data = format_mom_data(mom_data)
        
        # Use new OpenAI client for chat completion
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a professional meeting minutes assistant."},
                {"role": "user", "content": mom_generation_prompt.format(interview_data=interview_data)}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        
        content = response.choices[0].message.content
        
        # Store in database
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO mom_documents (session_id, content, timestamp) VALUES (?, ?, ?)",
            (session_id, content, datetime.now())
        )
        doc_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return content, doc_id
    
    except Exception as e:
        logger.error(f"Error generating MoM: {str(e)}")
        raise

# Main interaction function
def get_bot_response(user_input, session_id=None, consultant_id=1):
    try:
        if not session_id:
            session_id = session_state.start_session(consultant_id)
        
        state = session_state.get_state(session_id)
        
        if "need to make mom" in user_input.lower() or "minutes" in user_input.lower():
            return {
                "response": "Hi! I'll help you create Meeting Minutes. I'll ask you a series of questions to gather all the necessary information. Let's begin with the first question: What is the name of the company?",
                "session_id": session_id
            }
        
        if user_input:
            store_qa(session_id, "user_response", user_input)
            
            try:
                response = chain_with_history.invoke(
                    {"input": user_input},
                    {"session_id": str(session_id)}
                )
                
                return {
                    "response": response.content,
                    "session_id": session_id
                }
            except Exception as e:
                logger.error(f"Error in LLM interaction: {str(e)}")
                return {
                    "response": "I encountered an error processing your request. Please try again.",
                    "session_id": session_id,
                    "error": "llm_error"
                }
    
    except Exception as e:
        logger.error(f"Error processing response: {str(e)}")
        return {
            "response": "I encountered an error. Please try again.",
            "session_id": session_id,
            "error": "general_error"
        }

if __name__ == "__main__":
    print("MoM Bot CLI Demo")
    print("Type 'exit' to quit")
    
    session_id = None
    while True:
        user_input = input("> ")
        if user_input.lower() == 'exit':
            break
        
        response = get_bot_response(user_input, session_id)
        session_id = response.get("session_id")
        print(f"Bot: {response['response']}")

__all__ = ['init_db', 'SessionState', 'get_mom_data', 'generate_mom']

