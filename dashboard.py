import streamlit as st
import paho.mqtt.client as mqtt
import json
import pandas as pd
import time
import plotly.express as px
import queue 

# ==========================================
#              CONFIGURATION
# ==========================================
BROKER = "127.0.0.1" 
PORT = 1883
TOPIC = "fishhaven/+/stats" 

st.set_page_config(page_title="Vivisystem Dashboard", layout="wide")
st.title("Fish Haven Observability Dashboard")

# ==========================================
#        THREAD-SAFE MQTT SETUP
# ==========================================
@st.cache_resource
def start_mqtt_listener():
    data_queue = queue.Queue()

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            data_queue.put(payload)
        except Exception as e:
            print(f"Error: {e}")

    client = mqtt.Client(client_id=f"dash_{time.time()}")
    client.on_message = on_message
    try:
        client.connect(BROKER, PORT, 60)
        client.subscribe(TOPIC)
        client.loop_start()
        print("Dashboard Connected to MQTT!")
    except Exception as e:
        print(f"Connection Error: {e}")

    return data_queue

msg_queue = start_mqtt_listener()

# ==========================================
#           STREAMLIT STATE SETUP
# ==========================================
if "data" not in st.session_state:
    st.session_state["data"] = pd.DataFrame(columns=["time", "pond", "population"])

placeholder = st.empty()

# ==========================================
#           MAIN DASHBOARD LOOP
# ==========================================
while True:
    # 1. EMPTY THE MAILBOX
    new_rows = []
    while not msg_queue.empty():
        payload = msg_queue.get()
        new_rows.append({
            "time": pd.to_datetime(payload["timestamp"], unit='s'),
            "pond": payload["pond_name"],
            "population": payload["population"],
            "origins": payload.get("origin_breakdown", {})
        })

    # 2. UPDATE SESSION STATE
    if new_rows:
        new_df = pd.DataFrame(new_rows)
        st.session_state["data"] = pd.concat(
            [st.session_state["data"], new_df], 
            ignore_index=True
        )

    # 3. DRAW THE UI
    with placeholder.container():
        df = st.session_state["data"]
        
        # We create a unique ID for this specific second
        # This prevents the "Duplicate Element ID" error
        unique_id = time.time()

        if not df.empty:
            # Metrics
            col1, col2, col3 = st.columns(3)
            latest = df.iloc[-1]
            with col1:
                st.metric("Latest Population", latest["population"])
            with col2:
                st.metric("Reporting Pond", latest["pond"])
            with col3:
                st.metric("Total Data Points", len(df))

            # Line Chart
            # FIX: Added key=... and changed use_container_width to width="stretch"
            fig_line = px.line(df, x="time", y="population", color="pond", title="Population History")
            st.plotly_chart(fig_line, width="stretch", key=f"line_chart_{unique_id}")

            # Pie Chart
            if "origins" in latest and isinstance(latest["origins"], dict):
                origin_data = latest["origins"]
                if origin_data:
                    df_pie = pd.DataFrame(list(origin_data.items()), columns=["Origin", "Count"])
                    fig_pie = px.pie(df_pie, values="Count", names="Origin", title="Current Demographics")
                    # FIX: Added unique key here too
                    st.plotly_chart(fig_pie, width="stretch", key=f"pie_chart_{unique_id}")
        else:
            st.info(f"Connected to {BROKER}. Waiting for stats data...")

    # 4. SLEEP
    time.sleep(1)