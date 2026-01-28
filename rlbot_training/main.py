import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from google import genai
import json

# --- 🔒 SECURITY CONFIGURATION (PASTE KEYS HERE) ---
# Keep this file private! Do not share it on GitHub with keys inside.
BALLCHASING_API_KEY = "td4dBE8FuwEQDcPCwvBOvu4Ok5rr1qSWxLiNpNW5"
GEMINI_API_KEY = "AIzaSyAGPcASf7mu3Z_jWrvS14saTLP8wX34Znk"

# --- APP CONFIG ---
st.set_page_config(page_title="Rocket League AI Coach", page_icon="⚽", layout="wide")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


# --- BACKEND FUNCTIONS (CACHED) ---

@st.cache_data(ttl=3600, show_spinner=False)
def upload_replay(file_buffer):
    """Uploads replay to Ballchasing.com using the hardcoded key."""
    if not BALLCHASING_API_KEY or "PASTE" in BALLCHASING_API_KEY:
        return None, "Missing Ballchasing API Key in code."

    url = 'https://ballchasing.com/api/v2/upload'
    headers = {'Authorization': BALLCHASING_API_KEY}

    file_buffer.seek(0)
    files = {'file': ('replay.replay', file_buffer)}
    params = {'visibility': 'public'}  # Must be public/unlisted for others to see, or private for you

    try:
        response = requests.post(url, headers=headers, files=files, params=params)
        if response.status_code == 201:
            return response.json()['id'], None
        elif response.status_code == 409:
            return response.json()['id'], "Duplicate found (using existing stats)"
        else:
            return None, f"Error {response.status_code}: {response.text}"
    except Exception as e:
        return None, f"Connection Error: {e}"


@st.cache_data(show_spinner=False)
def fetch_match_stats(replay_id):
    """Fetches stats using the hardcoded key."""
    url = f"https://ballchasing.com/api/replays/{replay_id}"
    headers = {'Authorization': BALLCHASING_API_KEY}
    try:
        response = requests.get(url, headers=headers)
        return response.json() if response.status_code == 200 else None
    except:
        return None


def process_stats_for_display(data):
    """Flattens JSON for graphs."""
    players_list = []

    def extract_player(p, team_name):
        return {
            "Name": p['name'],
            "Team": team_name,
            "Goals": p['stats']['core']['goals'],
            "Assists": p['stats']['core']['assists'],
            "Saves": p['stats']['core']['saves'],
            "Boost Used": p['stats']['boost'].get('amount_used_while_supersonic', 0) + p['stats']['boost'].get(
                'avg_amount', 0),
            "Boost Collected": p['stats']['boost']['amount_collected'],
            "Boost Stolen": p['stats']['boost']['amount_stolen'],
            "Time Defending": p['stats']['positioning']['time_defensive_third'],
            "Time Attacking": p['stats']['positioning']['time_offensive_third']
        }

    if 'blue' in data and 'players' in data['blue']:
        for p in data['blue']['players']: players_list.append(extract_player(p, "Blue"))
    if 'orange' in data and 'players' in data['orange']:
        for p in data['orange']['players']: players_list.append(extract_player(p, "Orange"))

    return pd.DataFrame(players_list)


@st.cache_data(show_spinner=False)
def get_ai_coaching(stats_json):
    """Sends stats to Gemini."""
    if not GEMINI_API_KEY or "PASTE" in GEMINI_API_KEY:
        return "⚠️ Please add your Gemini API Key in the main.py file."

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model = 'gemini-3-pro-preview',
        contents = f"""
            You are a sarcastic Rocket League Coach (Grand Champion). 
            Analyze this match JSON and report on EACH player.
            MATCH DATA: {json.dumps(stats_json)}

            Format for each player:
            ### 🚗 [Player Name] ([Team])
            * **Archetype:** (Fun nickname e.g. "The Boost Vacuum")
            * **Analysis:** (2 sentences on playstyle)
            * **✅ Strengths:** (1 stat they did well)
            * **⚠️ Weaknesses:** (1 stat to improve + advice)
         """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI Error: {e}"


# --- APP UI ---
st.title("🚀 Rocket League Replay Analyzer")
st.markdown("Upload a `.replay` file to view stats and get AI coaching.")

uploaded_file = st.file_uploader("Drop replay file here", type=['replay'])

if uploaded_file:
    with st.spinner("Processing..."):
        replay_id, error_msg = upload_replay(uploaded_file)

    if replay_id:
        if error_msg: st.info(f"ℹ️ {error_msg}")

        # 🔗 3D Viewer Link
        # Adding #watch attempts to trigger the viewer, though standard link works best
        viewer_link = f"https://ballchasing.com/replay/{replay_id}#watch"
        st.success("Replay Processed!")
        st.markdown(f"""
        <a href="{viewer_link}" target="_blank">
            <button style="width: 100%; padding: 10px; background-color: #FF4B4B; color: white; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">
                📺 Open 3D Replay Viewer (Ballchasing.com)
            </button>
        </a>
        """, unsafe_allow_html=True)

        match_data = fetch_match_stats(replay_id)

        if match_data:
            df = process_stats_for_display(match_data)

            # 1. Scoreboard
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("📊 Scoreboard")
                fig_score = px.bar(df, x="Name", y=["Goals", "Saves", "Assists"], barmode="group",
                                   color_discrete_sequence=["#00CC96", "#EF553B", "#636EFA"])
                st.plotly_chart(fig_score, use_container_width=True)

            # 2. Boost Wars
            with col2:
                st.subheader("⛽ Boost Wars")
                fig_boost = px.bar(df, x="Name", y=["Boost Collected", "Boost Stolen"], title="Collected vs Stolen",
                                   barmode="stack")
                st.plotly_chart(fig_boost, use_container_width=True)

            # 3. Positioning (Fixed Error Here)
            st.subheader("📍 Field Positioning")
            fig_pos = px.bar(
                df,
                y="Name",
                x=["Time Defending", "Time Attacking"],
                orientation='h',
                title="Time in Defensive vs Offensive Thirds",
                barmode="stack"  # Changed from 'fill' to 'stack'
            )
            st.plotly_chart(fig_pos, use_container_width=True)

            # AI Section
            st.divider()
            st.header("🤖 The AI Coach")
            if st.button("Generate Analysis"):
                with st.spinner("Analyzing..."):
                    st.markdown(get_ai_coaching(match_data))
    else:
        st.error(f"Upload failed: {error_msg}")