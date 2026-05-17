import streamlit as st
import requests
import yfinance as yf
from google import genai
from supabase import create_client, Client
# ==============================================================================
# 1. CREDENTIAL CONFIGURATION
# ==============================================================================
# Put the LABEL names in the brackets, not the actual long keys!
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
MARKETAUX_API_KEY = st.secrets["MARKETAUX_API_KEY"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

# Initialize Clients
client = genai.Client(api_key=GEMINI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# SYSTEM CONFIGURATION (Put at the top of file)
# ==========================================
system_rules = (
    "You are FinAI, a sharp and direct personal financial advisor for Alex (user ID 1). "
    "Personality: concise, confident, never vague. "
    "Rules: "
    "1. Always use your tools automatically — never ask if you should look something up, just do it. "
    "2. Before giving investment advice, consider Alex’s risk tolerance from their profile. "
    "3. Format numbers clearly (e.g. $1,234.56). "
    "4. End responses with a relevant follow-up question to keep Alex engaged. "
    "5. Always add a one line disclaimer on investment advice. "
    "6. If a question is outside finance, redirect politely."
)
# =====================================================================
# 2. DEFINING THE AI AGENT TOOLS (PYTHON FUNCTIONS)
# =====================================================================

def get_live_stock_price(ticker: str) -> str:
    """Fetches real-time market data, current price, and key ratios for a given stock ticker."""
    try:
        stock = yf.Ticker(ticker)
        history = stock.history(period="1d")
        if history.empty:
            return f"Could not find active trading data for {ticker.upper()}."
        current_price = history['Close'].iloc[-1]
        day_high = history['High'].iloc[-1]
        day_low = history['Low'].iloc[-1]
        return f"{ticker.upper()} Metrics: Current Price: ${current_price:.2f}, Day High: ${day_high:.2f}, Day Low: ${day_low:.2f}"
    except Exception as e:
        return f"Error pulling stock price for {ticker}: {str(e)}"

def get_breaking_financial_news(search_query: str) -> str:
    """Scrapes breaking live global financial news and market updates relative to a keyword."""
    url = f"https://api.marketaux.com/v1/news/all?search={search_query}&language=en&api_token={MARKETAUX_API_KEY}"
    try:
        response = requests.get(url).json()
        articles = response.get("data", [])
        output = ""
        for art in articles[:3]: # Grab top 3 items
            output += f"Headline: {art['title']}\nSummary: {art['description']}\n\n"
        return output if output else "No fresh breaking news found for this topic."
    except Exception as e:
        return f"Could not retrieve news data: {str(e)}"

def view_user_budget(user_id: int = 1) -> str:
    """Reads the private user budget data, limits, and current expenditures from the database."""
    try:
        profile_res = supabase.table("user_profiles").select("*").eq("id", user_id).execute()
        budget_res = supabase.table("budgets").select("*").eq("user_id", user_id).execute()
        
        profile = profile_res.data[0] if profile_res.data else {}
        budgets = budget_res.data if budget_res.data else []
        
        report = f"User Profile: {profile.get('user_name')}. Risk Tolerance: {profile.get('risk_tolerance')}.\n"
        report += "Current Budget Ledger:\n"
        for b in budgets:
            remaining = float(b['limit_amount']) - float(b['spent_amount'])
            report += f"- {b['category']}: Spent ${b['spent_amount']} / Limit ${b['limit_amount']} (Remaining: ${remaining:.2f})\n"
        return report
    except Exception as e:
        return f"Database read error: {str(e)}"

def update_budget_expense(category: str, amount_spent: float, user_id: int = 1) -> str:
    """Adds a new expense or updates money spent inside an existing budget category."""
    try:
        # Fetch current record
        res = supabase.table("budgets").select("spent_amount").eq("user_id", user_id).eq("category", category).execute()
        if not res.data:
            return f"No category named '{category}' found to update."
        
        new_total = float(res.data[0]['spent_amount']) + amount_spent
        supabase.table("budgets").update({"spent_amount": new_total}).eq("user_id", user_id).eq("category", category).execute()
        return f"Successfully added ${amount_spent:.2f} to {category}. New total spent: ${new_total:.2f}."
    except Exception as e:
        return f"Database write error: {str(e)}"

# Pack all modules into a list that Gemini can look at natively
financial_toolkit = [get_live_stock_price, get_breaking_financial_news, view_user_budget, update_budget_expense]

# =====================================================================
# 3. STREAMLIT APPLICATION INTERFACE
# =====================================================================
st.set_page_config(page_title="FinAI Terminal", page_icon="📈", layout="centered")
st.title("📈 Full-Suite FinAI Assistant")
st.caption("Real-Time Tracking, Budgeting, and Portfolio Personalization (Free Tier Beta)")

# Establish chat session container state
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hello! I am your unified tracking and budgeting assistant. Ask me to pull live stock prices, read breaking news, or inspect/update your personal budget dashboard."}]

# Print out conversation history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# Listen for User Prompts
if user_input := st.chat_input("Ex: 'What is Nvidia trading at?' or 'Log a $25 spend to my Entertainment budget'"):
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    # Process via Gemini Agent Engine
# Delete your old line 122 container entirely. 
# Paste this block so it sits flush against the left-hand wall of your file:

if user_input := st.chat_input("Ask FinAI..."):
    
    # Display and append the user's message immediately
    with st.chat_message("user"):
        st.write(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    # Trigger the assistant block
    with st.chat_message("assistant"):
        with st.spinner("Analyzing parameters..."):
            
            # Format the conversation history for Gemini's SDK
            from google.genai import types
            history = []
            for msg in st.session_state.messages:
                role = "model" if msg["role"] == "assistant" else "user"
                history.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=msg["content"])]
                    )
                )

            # Call the model
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=history,
                config=types.GenerateContentConfig(
                    system_instruction=system_rules,
                    tools=financial_toolkit
                )
            )
            
            # Display and save the assistant's response at the very end
            # Display and save the assistant's response at the very end
        output_text = response.text if response.text else "No response text returned."
        st.write(output_text)
        st.session_state.messages.append({"role": "assistant", "content": output_text})
