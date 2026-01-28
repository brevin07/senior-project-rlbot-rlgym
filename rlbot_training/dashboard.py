import streamlit as st
import pandas as pd
import plotly.express as px

# --- PAGE CONFIG ---
st.set_page_config(page_title="Replay Analysis", layout="wide")

st.title("Rocket League Replay Analysis")

# --- LOAD DATA ---
DATA_FILE = "match_data.pkl"

try:
    # Load the DataFrame
    df = pd.read_pickle(DATA_FILE)

    # Check if the dataframe is loaded
    if df.empty:
        st.error("Data file is empty.")
        st.stop()

    # --- SIDEBAR CONTROLS ---
    st.sidebar.header("Filter Options")

    # The DataFrame columns are a MultiIndex: (PlayerName, StatName)
    # Level 0 = Player Names, Level 1 = Stats (pos_x, vel_x, boost, etc.)
    all_players = df.columns.levels[0].tolist()

    # Filter out 'game' columns if they exist (ball stats usually under 'ball')
    players = [p for p in all_players if p != 'game' and p != 'ball']

    selected_players = st.sidebar.multiselect(
        "Select Players to Compare",
        players,
        default=players[:2] if len(players) >= 2 else players
    )

    if not selected_players:
        st.warning("Select at least one player on the left.")
        st.stop()

    # --- 1. BOOST OVER TIME ---
    st.subheader("🔥 Boost Usage Over Time")

    # Extract Boost data for selected players
    boost_data = pd.DataFrame()
    for p in selected_players:
        # Check if 'boost' is in the columns for this player
        if 'boost' in df[p].columns:
            boost_data[p] = df[p]['boost']

    if not boost_data.empty:
        # Streamlit handles the line chart automatically
        st.line_chart(boost_data)
    else:
        st.write("No boost data available.")

    # --- 2. SPEED ANALYSIS ---
    st.subheader("🚀 Average Speed")

    speed_stats = []
    for p in selected_players:
        if 'vel_x' in df[p].columns:
            # Calculate speed magnitude: sqrt(vx^2 + vy^2 + vz^2)
            # Carball data is usually scaled, but we can compare relative speed
            vx = df[p]['vel_x']
            vy = df[p]['vel_y']
            vz = df[p]['vel_z']
            speed = (vx ** 2 + vy ** 2 + vz ** 2) ** 0.5

            avg_speed = speed.mean()
            speed_stats.append({"Player": p, "Avg Speed": avg_speed})

    if speed_stats:
        speed_df = pd.DataFrame(speed_stats)
        fig = px.bar(speed_df, x="Player", y="Avg Speed", color="Player", title="Average Speed Comparison")
        st.plotly_chart(fig, use_container_width=True)

except FileNotFoundError:
    st.error(f"Could not find '{DATA_FILE}'. Please run '1_parse_replay.py' first!")
except Exception as e:
    st.error(f"Error loading dashboard: {e}")