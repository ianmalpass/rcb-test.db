import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import hashlib
import shutil
import os
import barcode
from barcode.writer import ImageWriter
import base64
from io import BytesIO
import plotly.express as px # NEW: For charts
import plotly.graph_objects as go

# --- CONFIGURATION ---
DB_PATH = "rcb_inventory_v12.db"
BACKUP_DIR = "backups"

# ... [init_db and helper functions remain the same] ...

def main():
    st.set_page_config(page_title="BARC - Plant Management", layout="wide")
    init_db()

    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

    if not st.session_state['logged_in']:
        # --- LOGIN BLOCK ---
        st.title("🔒 BARC Portal Login")
        u = st.text_input("Username")
        p = st.text_input("Password", type='password')
        if st.button("Login"):
            fn = check_login(u, p)
            if fn:
                st.session_state.update({"logged_in": True, "user_display": fn, "username": u})
                st.rerun()
            else: st.error("Invalid credentials.")
    else:
        st.sidebar.title("BARC Navigation")
        # Added 'Analytics Dashboard' to the menu
        menu = ["Production (Inventory)", "Reactor Logs", "Analytics Dashboard", "Shipping", "Stock Inquiry", "View Records"]
        if st.session_state['username'] == 'admin': menu.append("User Management")
        choice = st.sidebar.selectbox("Go to:", menu)
        
        if st.sidebar.button("Logout"):
            st.session_state['logged_in'] = False
            st.rerun()

        # --- NEW: ANALYTICS DASHBOARD ---
        if choice == "Analytics Dashboard":
            st.title("📈 Plant Analytics Dashboard")
            
            conn = sqlite3.connect(DB_PATH)
            process_df = pd.read_sql_query("SELECT * FROM process_logs ORDER BY timestamp ASC", conn)
            quality_df = pd.read_sql_query("SELECT * FROM test_results ORDER BY timestamp ASC", conn)
            conn.close()

            if process_df.empty:
                st.warning("Not enough data to generate reactor charts yet.")
            else:
                # Convert timestamps to datetime objects
                process_df['timestamp'] = pd.to_datetime(process_df['timestamp'])

                # 1. Temperature Trend Chart
                st.subheader("Reactor Temperature Stability (°C)")
                fig_temp = go.Figure()
                fig_temp.add_trace(go.Scatter(x=process_df['timestamp'], y=process_df['reactor_1_temp'], name="Reactor 1 (500°C Target)", line=dict(color='#FF4B4B')))
                fig_temp.add_trace(go.Scatter(x=process_df['timestamp'], y=process_df['reactor_2_temp'], name="Reactor 2 (550°C Target)", line=dict(color='#0068C9')))
                fig_temp.update_layout(xaxis_title="Time", yaxis_title="Temperature °C", legend_orientation="h")
                st.plotly_chart(fig_temp, use_container_width=True)

                col1, col2 = st.columns(2)
                
                # 2. Hz Tracking
                with col1:
                    st.subheader("Motor Frequency (Hz)")
                    fig_hz = px.line(process_df, x='timestamp', y=['reactor_1_hz', 'reactor_2_hz'], 
                                     color_discrete_map={"reactor_1_hz": "#FF4B4B", "reactor_2_hz": "#0068C9"})
                    st.plotly_chart(fig_hz, use_container_width=True)

                # 3. Toluene vs Feed Rate
                with col2:
                    st.subheader("Toluene vs Feed Rate")
                    fig_tol = px.scatter(process_df, x='feed_rate', y='toluene_value', 
                                         color='operator', size='toluene_value', hover_name='timestamp')
                    st.plotly_chart(fig_tol, use_container_width=True)

        # --- REACTOR LOGS SECTION ---
        elif choice == "Reactor Logs":
            st.title("🔥 Reactor Process Parameters")
            # ... (Rest of the Reactor Logs code remains the same as v12) ...
            with st.form("reactor_form", clear_on_submit=True):
                st.write(f"Logging as: **{st.session_state['user_display']}**")
                c1, c2 = st.columns(2)
                with c1:
                    tol_val = st.number_input("Toluene Value", min_value=0, step=1)
                    feed_rate = st.number_input("Feed Rate", min_value=0.0, format="%.2f")
                    r1_hz = st.number_input("Reactor 1 Hz", value=60)
                    r2_hz = st.number_input("Reactor 2 Hz", value=45)
                with c2:
                    r1_temp = st.number_input("Reactor 1 Temp (°C)", value=500)
                    r2_temp = st.number_input("Reactor 2 Temp (°C)", value=550)
                
                if st.form_submit_button("Submit Process Log"):
                    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute('''INSERT INTO process_logs (timestamp, operator, toluene_value, feed_rate, reactor_1_temp, reactor_2_temp, reactor_1_hz, reactor_2_hz)
                                 VALUES (?,?,?,?,?,?,?,?)''', (ts, st.session_state['user_display'], tol_val, feed_rate, r1_temp, r2_temp, r1_hz, r2_hz))
                    conn.commit(); conn.close()
                    st.success("Reactor log saved successfully!")

        # --- ALL OTHER SECTIONS (Production, Shipping, Stock Inquiry, View Records) remain the same ---

if __name__ == '__main__':
    main()
