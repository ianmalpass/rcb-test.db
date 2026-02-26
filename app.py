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
import plotly.express as px
import plotly.graph_objects as go

# --- CONFIGURATION ---
DB_PATH = "rcb_inventory_v12.db"
BACKUP_DIR = "backups"

# --- DATABASE INITIALIZATION ---
def init_db():
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Table 1: Quality & Inventory
    c.execute('''CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bag_ref TEXT UNIQUE,
                    timestamp DATETIME,
                    operator TEXT,
                    shipped_by TEXT,
                    product TEXT,
                    customer_name TEXT DEFAULT 'In Inventory',
                    shipped_date TEXT DEFAULT 'Not Shipped',
                    status TEXT DEFAULT 'Inventory',
                    pellet_hardness INTEGER,
                    moisture REAL,
                    toluene INTEGER,
                    ash_content REAL,
                    weight_lbs REAL)''')
    # Table 2: Reactor Process Logs
    c.execute('''CREATE TABLE IF NOT EXISTS process_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    operator TEXT,
                    toluene_value INTEGER,
                    feed_rate REAL,
                    reactor_1_temp INTEGER,
                    reactor_2_temp INTEGER,
                    reactor_1_hz INTEGER,
                    reactor_2_hz INTEGER)''')
    # Table 3: Users
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY, 
                    password TEXT,
                    full_name TEXT)''')
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        admin_pass = hashlib.sha256(str.encode('admin123')).hexdigest()
        c.execute("INSERT INTO users VALUES (?, ?, ?)", ('admin', admin_pass, 'System Admin'))
    conn.commit()
    conn.close()

# --- HELPERS ---
def generate_barcode_base64(data):
    CODE128 = barcode.get_barcode_class('code128')
    barcode_obj = CODE128(data, writer=ImageWriter())
    buffered = BytesIO()
    barcode_obj.write(buffered)
    return base64.b64encode(buffered.getvalue()).decode()

def check_login(username, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    hashed = hashlib.sha256(str.encode(password)).hexdigest()
    c.execute("SELECT full_name FROM users WHERE username = ? AND password = ?", (username, hashed))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def generate_bag_ref():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM test_results")
    count = c.fetchone()[0]
    conn.close()
    return f"RCB-{datetime.now().year}-{(count + 1):04d}"

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="AI-sistant - Plant Management", layout="wide")
    init_db()

    if 'logged_in' not in st.session_state: 
        st.session_state['logged_in'] = False

    if not st.session_state['logged_in']:
        st.title("🔒 AI-sistant Portal Login")
        u = st.text_input("Username")
        p = st.text_input("Password", type='password')
        if st.button("Login"):
            fn = check_login(u, p)
            if fn:
                st.session_state.update({"logged_in": True, "user_display": fn, "username": u})
                st.rerun()
            else: st.error("Invalid credentials.")
    else:
        st.sidebar.title("AI-sistant")
        st.sidebar.caption(f"DB: {DB_PATH}")
        menu = ["Production (Inventory)", "Reactor Logs", "Analytics Dashboard", "Shipping", "Stock Inquiry", "View Records", "Help & Documentation"]
        if st.session_state['username'] == 'admin': menu.append("User Management")
        choice = st.sidebar.selectbox("Go to:", menu)
        
        if st.sidebar.button("Logout"):
            st.session_state['logged_in'] = False
            st.rerun()

        # --- PRODUCTION ---
        if choice == "Production (Inventory)":
            st.title("🏗️ Bag Production")
            bag_id = generate_bag_ref()
            with st.form("prod_form", clear_on_submit=True):
                st.subheader(f"Bag ID: {bag_id}")
                product = st.selectbox("Product", ["Revolution CB", "Paris CB"])
                c1, c2 = st.columns(2)
                with c1:
                    hardness = st.number_input("Hardness (Int)", min_value=0, max_value=99, step=1)
                    weight = st.number_input("Weight (lbs)", min_value=0.0, value=55.0)
                with c2:
                    moisture = st.number_input("Moisture %", format="%.2f")
                    toluene = st.number_input("Toluene (Int)", min_value=0, max_value=99, step=1)
                    ash = st.number_input("Ash Content % (1-decimal)", format="%.1f")
                if st.form_submit_button("Record Bag"):
                    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute('''INSERT INTO test_results (bag_ref, timestamp, operator, product, pellet_hardness, moisture, toluene, ash_content, weight_lbs)
                                 VALUES (?,?,?,?,?,?,?,?,?)''', (bag_id, ts, st.session_state['user_display'], product, hardness, moisture, toluene, ash, weight))
                    conn.commit(); conn.close()
                    st.session_state['last_bag'] = {"id": bag_id, "prod": product, "weight": weight, "ash": ash, "hardness": hardness, "moist": moisture, "tol": toluene, "op": st.session_state['user_display'], "time": ts}
                    st.success(f"Saved {bag_id}")

            if 'last_bag' in st.session_state:
                lb = st.session_state['last_bag']
                b_code = generate_barcode_base64(lb['id'])
                st.divider()
                st.components.v1.html(f"""<div style="width:320px; padding:15px; border:3px solid black; font-family:Arial; background:white; color:black;">
                    <div style="font-size:20px; font-weight:bold; text-align:center;">{lb['prod']}</div>
                    <div style="text-align:center; padding:5px 0;"><img src="data:image/png;base64,{b_code}" style="width:200px;"><br><b>{lb['id']}</b></div>
                    <div style="font-size:13px; border-top:1px solid #000; padding-top:5px;">
                        <b>Weight:</b> {lb['weight']:.1f} lbs | <b>Ash:</b> {lb['ash']:.1f}% | <b>Hardness:</b> {int(lb['hardness'])}
                    </div></div><br><button onclick="window.print()" style="padding:10px; background:#28a745; color:white; border:none; width:320px; cursor:pointer; font-weight:bold;">Print Label</button>""", height=400)

        # --- REACTOR LOGS ---
        elif choice == "Reactor Logs":
            st.title("🔥 Process Parameters")
            with st.form("reactor_form", clear_on_submit=True):
                c1, c2 = st.columns(2)
                with c1:
                    tol_val = st.number_input("Toluene Value", min_value=0, step=1)
                    feed_rate = st.number_input("Feed Rate", min_value=0.0, format="%.2f")
                    r1_hz, r2_hz = st.number_input("R1 Hz", value=60), st.number_input("R2 Hz", value=45)
                with c2:
                    r1_t, r2_t = st.number_input("R1 Temp", value=500), st.number_input("R2 Temp", value=550)
                if st.form_submit_button("Submit Log"):
                    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute("INSERT INTO process_logs (timestamp, operator, toluene_value, feed_rate, reactor_1_temp, reactor_2_temp, reactor_1_hz, reactor_2_hz) VALUES (?,?,?,?,?,?,?,?)", (ts, st.session_state['user_display'], tol_val, feed_rate, r1_t, r2_t, r1_hz, r2_hz))
                    conn.commit(); conn.close(); st.success("Log saved!")

        # --- STOCK INQUIRY ---
        elif choice == "Stock Inquiry":
            st.title("🔎 Inventory Enquiry")
            conn = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query("SELECT * FROM test_results WHERE status = 'Inventory'", conn)
            conn.close()
            if df.empty: st.info("No stock in inventory.")
            else:
                c1, c2 = st.columns(2)
                for i, p in enumerate(["Revolution CB", "Paris CB"]):
                    d = df[df['product'] == p]
                    c = c1 if i == 0 else c2
                    c.metric(f"Total {p}", f"{len(d)} Bags", f"{d['weight_lbs'].sum():,.1f} lbs Total")
                st.dataframe(df, use_container_width=True)

        # --- ANALYTICS ---
        elif choice == "Analytics Dashboard":
            st.title("📈 Plant Trends")
            conn = sqlite3.connect(DB_PATH)
            p_df = pd.read_sql_query("SELECT * FROM process_logs ORDER BY timestamp ASC", conn)
            conn.close()
            if not p_df.empty:
                p_df['timestamp'] = pd.to_datetime(p_df['timestamp'])
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=p_df['timestamp'], y=p_df['reactor_1_temp'], name="R1 Temp"))
                fig.add_trace(go.Scatter(x=p_df['timestamp'], y=p_df['reactor_2_temp'], name="R2 Temp"))
                fig.add_hline(y=500, line_dash="dash", line_color="red")
                fig.add_hline(y=550, line_dash="dash", line_color="blue")
                st.plotly_chart(fig, use_container_width=True)
            else: st.info("No data yet.")

        # --- SHIPPING ---
        elif choice == "Shipping":
            st.title("🚢 Scan-to-Ship")
            sid = st.text_input("Scan Barcode").upper()
            if sid:
                conn = sqlite3.connect(DB_PATH)
                res = pd.read_sql_query("SELECT * FROM test_results WHERE bag_ref = ? AND status = 'Inventory'", conn, params=(sid,))
                if not res.empty:
                    with st.form("ship"):
                        cust = st.text_input("Customer Name")
                        if st.form_submit_button("Ship"):
                            c = conn.cursor(); sd = date.today().strftime("%Y-%m-%d")
                            c.execute("UPDATE test_results SET customer_name=?, shipped_date=?, status='Shipped', shipped_by=? WHERE bag_ref=?", (cust, sd, st.session_state['user_display'], sid))
                            conn.commit(); conn.close(); st.success("Shipped!"); st.rerun()
                else: st.error("Bag not found."); conn.close()

        # --- VIEW RECORDS ---
        elif choice == "View Records":
            st.title("📊 Master Ledger")
            tab1, tab2 = st.tabs(["Bag Quality", "Reactor Logs"])
            conn = sqlite3.connect(DB_PATH)
            with tab1: st.dataframe(pd.read_sql_query("SELECT * FROM test_results ORDER BY timestamp DESC", conn), use_container_width=True)
            with tab2: st.dataframe(pd.read_sql_query("SELECT * FROM process_logs ORDER BY timestamp DESC", conn), use_container_width=True)
            conn.close()

        # --- HELP SECTION ---
        elif choice == "Help & Documentation":
            st.title("📖 Help Guide")
            with st.expander("🏗️ Production"): st.write("Fill form -> Record -> Print Barcode Label.")
            with st.expander("🚢 Shipping"): st.write("Click box -> Scan bag -> Enter Customer -> Ship.")

if __name__ == '__main__':
    main()

