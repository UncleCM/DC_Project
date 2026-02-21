import streamlit as st
import paho.mqtt.client as mqtt
import json
import pandas as pd
import time
import plotly.express as px

# CONFIG
BROKER = "127.0.0.1" # Same as your pond
PORT = 1883
TOPIC = "fishhaven/+/stats" # Listen to EVERYONE'S stats

st.set_page_config(page_title="Vivisystem Dashboard", layout="wide")
st.title("Fish Haven Observability Dashboard")

# Initialize Session State to hold data history
if "data" not in st.session_state:
    st.session_state["data"] = pd.DataFrame(columns=["time", "pond", "population"])

# MQTT Setup in a separate thread/process is tricky with Streamlit.
# We will use a placeholder approach for the UI updates.
placeholder = st.empty()

# Define MQTT Client
client = mqtt.Client()

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        
        # Append new data to session state
        new_row = {
            "time": pd.to_datetime(payload["timestamp"], unit='s'),
            "pond": payload["pond_name"],
            "population": payload["population"],
            "origins": payload["origin_breakdown"] # Complex data for drill-down
        }
        
        # Add to dataframe
        st.session_state["data"] = pd.concat([
            st.session_state["data"], 
            pd.DataFrame([new_row])
        ], ignore_index=True)
        
    except Exception as e:
        print(e)

client.on_message = on_message
client.connect(BROKER, PORT, 60)
client.subscribe(TOPIC)
client.loop_start()

# STREAMLIT REFRESH LOOP
# This loop updates the charts every second
while True:
    with placeholder.container():
        # Get Data
        df = st.session_state["data"]
        
        if not df.empty:
            # METRICS ROW
            col1, col2, col3 = st.columns(3)
            latest = df.iloc[-1]
            with col1:
                st.metric("Latest Population", latest["population"])
            with col2:
                st.metric("Reporting Pond", latest["pond"])
            with col3:
                st.metric("Total Data Points", len(df))

            # CHART 1: Population over Time (Line Chart)
            fig_line = px.line(df, x="time", y="population", color="pond", title="Real-Time Population Health")
            st.plotly_chart(fig_line, use_container_width=True)

            # CHART 2: Origin Analytics (Pie Chart of latest state)
            # We look at the 'origins' dict of the most recent packet
            if "origins" in latest and latest["origins"]:
                origin_data = latest["origins"]
                df_pie = pd.DataFrame(list(origin_data.items()), columns=["Origin", "Count"])
                fig_pie = px.pie(df_pie, values="Count", names="Origin", title="Current Fish Demographics (Where are they from?)")
                st.plotly_chart(fig_pie, use_container_width=True)

        else:
            st.warning("Waiting for telemetry data...")
            
    time.sleep(1)