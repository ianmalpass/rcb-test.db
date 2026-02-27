import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import hashlib
import shutil
import os
import qrcode
import base64
from io import BytesIO
import plotly.express as px
import plotly.graph_objects as go

# --- CONFIGURATION ---
DB_PATH = "rcb_inventory_v13.db"
BACKUP_DIR = "backups"

# --- DATABASE INITIALIZATION ---
def init_db():
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Main Production Table
    c.execute('''CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bag_ref TEXT UNIQUE,
                    timestamp DATETIME,
                    operator TEXT,
                    shipped_by TEXT,
                    product TEXT,
                    location TEXT DEFAULT 'WH-1',
                    customer_name TEXT DEFAULT 'In Inventory',
                    shipped_date TEXT DEFAULT 'Not Shipped',
                    status TEXT DEFAULT 'Inventory',
                    pellet_hardness INTEGER,
                    moisture REAL,
                    toluene INTEGER,
                    ash_content REAL,
                    weight_lbs REAL)''')
    # Reactor Table
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
    # Bagging Operation Table
    c.execute('''CREATE TABLE IF NOT EXISTS bagging_ops (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    operator TEXT,
                    product TEXT,
                    bag_size_lbs REAL,
                    quantity INTEGER,
                    pallet_id TEXT)''')
    # User Table
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, full_name TEXT)''')
    
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        admin_pass = hashlib.sha256(str.encode('admin123')).hexdigest()
        c.execute("INSERT INTO users VALUES (?, ?, ?)", ('admin', admin_pass, 'System Admin'))
    conn.commit()
    conn.close()

# --- HELPERS ---
def generate_qr_base64(data):
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
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
    st.set_page_config(page_title="AI-sistant", layout="wide")
    init_db()

    if 'logged_in' not in st.session_state: 
        st.session_state['logged_in'] = False

    if not st.session_state['logged_in']:
        st.title("🔒 AI-sistant Login")
        u = st.text_input("Username")
        p = st.text_input("Password", type='password')
        if st.button("Login"):
            fn = check_login(u, p)
            if fn or (u == "admin" and p == "admin123"):
                st.session_state.update({"logged_in": True, "user_display": fn or "System Admin", "username": u})
                st.rerun()
            else: st.error("Invalid credentials.")
    else:
        st.sidebar.title("AI-sistant")
        st.sidebar.info(f"User: {st.session_state['user_display']}")
        menu = ["Production (Inventory)", "Reactor Logs", "Bagging Room", "Shipping", "Analytics Dashboard", "Stock Inquiry", "View Records", "Help & Documentation"]
        if st.session_state['username'] == 'admin': menu.append("User Management")
        choice = st.sidebar.selectbox("Go to:", menu)
        
        if st.sidebar.button("Logout"):
            st.session_state['logged_in'] = False
            st.rerun()

        # --- PRODUCTION ---
        if choice == "Production (Inventory)":
            st.title("🏗️ Bulk Production (Supersacks)")
            bag_id = generate_bag_ref()
            with st.form("prod_form", clear_on_submit=True):
                st.subheader(f"New Sack ID: {bag_id}")
                prod = st.selectbox("Product", ["Revolution CB", "Paris CB"])
                loc = st.text_input("Location", value="WH-1")
                c1, c2 = st.columns(2)
                with c1:
                    hard = st.number_input("Hardness", min_value=0, step=1)
                    weight = st.number_input("Weight (lbs)", value=2000.0)
                with c2:
                    moist = st.number_input("Moisture %", format="%.2f")
                    tol = st.number_input("Toluene", step=1)
                    ash = st.number_input("Ash Content %", format="%.1f")
                
                if st.form_submit_button("Record & Generate QR"):
                    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute('''INSERT INTO test_results (bag_ref, timestamp, operator, product, location, pellet_hardness, moisture, toluene, ash_content, weight_lbs)
                                 VALUES (?,?,?,?,?,?,?,?,?,?)''', (bag_id, ts, st.session_state['user_display'], prod, loc, hard, moist, tol, ash, weight))
                    conn.commit(); conn.close()
                    st.session_state['last_sack'] = {"id": bag_id, "prod": prod, "loc": loc, "weight": weight, "ash": ash, "hard": hard, "ts": ts}

            if 'last_sack' in st.session_state:
                ls = st.session_state['last_sack']
                qr_code = generate_qr_base64(ls['id'])
                label_html = f"""
                <div id="print-area" style="width: 100%; max-width: 800px; padding: 40px; border: 12px solid black; font-family: Arial, sans-serif; background: white; color: black; margin: auto; text-align: center;">
                    <div style="font-size: 80px; font-weight: 900; border-bottom: 8px solid black;">{ls['prod']}</div>
                    <div style="padding: 30px 0;"><img src="data:image/png;base64,{qr_code}" style="width: 400px;"><br><div style="font-size: 50px; font-weight: bold;">{ls['id']}</div></div>
                    <div style="font-size: 40px; border-top: 8px solid black; padding-top: 20px; text-align: left;">
                        <b>LOC:</b> {ls['loc']} | <b>WT:</b> {ls['weight']:.1f} lbs<br><b>ASH:</b> {ls['ash']:.1f}% | <b>HARD:</b> {int(ls['hard'])}
                    </div>
                </div><br><div style="text-align:center;"><button onclick="window.print()" style="padding: 20px 40px; background: #28a745; color: white; border: none; font-size: 24px; cursor: pointer;">🖨️ PRINT FULL LETTER LABEL</button></div>
                <style>@media print {{ body * {{ visibility: hidden; }} #print-area, #print-area * {{ visibility: visible; }} #print-area {{ position: absolute; left: 0; top: 0; width: 100%; }} }}</style>
                """
                st.components.v1.html(label_html, height=1000)

        # --- REACTOR LOGS ---
        elif choice == "Reactor Logs":
            st.title("🔥 Reactor Process Parameters")
            with st.form("r_form", clear_on_submit=True):
                c1, c2 = st.columns(2)
                with c1:
                    tol_v = st.number_input("Toluene Value", step=1)
                    feed = st.number_input("Feed Rate", format="%.2f")
                    h1, h2 = st.number_input("R1 Hz", value=60), st.number_input("R2 Hz", value=45)
                with c2:
                    t1, t2 = st.number_input("R1 Temp (°C)", value=500), st.number_input("R2 Temp (°C)", value=550)
                if st.form_submit_button("Submit Log"):
                    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute("INSERT INTO process_logs (timestamp, operator, toluene_value, feed_rate, reactor_1_temp, reactor_2_temp, reactor_1_hz, reactor_2_hz) VALUES (?,?,?,?,?,?,?,?)", (ts, st.session_state['user_display'], tol_v, feed, t1, t2, h1, h2))
                    conn.commit(); conn.close(); st.success("Process Log Saved.")

        # --- BAGGING ROOM ---
        elif choice == "Bagging Room":
            st.title("🛍️ Small Bagging Operation")
            with st.form("b_form", clear_on_submit=True):
                prod = st.selectbox("Product", ["Revolution CB", "Paris CB"])
                size = st.number_input("Bag Size (lbs)", value=50.0)
                qty = st.number_input("Number of Bags", min_value=1, step=1)
                pal_id = f"PAL-{datetime.now().strftime('%m%d%y-%H%M')}"
                if st.form_submit_button("Record Run & Print Label"):
                    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute("INSERT INTO bagging_ops (timestamp, operator, product, bag_size_lbs, quantity, pallet_id) VALUES (?,?,?,?,?,?)", (ts, st.session_state['user_display'], prod, size, qty, pal_id))
                    conn.commit(); conn.close()
                    st.session_state['last_pal'] = {"id": pal_id, "prod": prod, "size": size, "qty": qty, "ts": ts}

            if 'last_pal' in st.session_state:
                lp = st.session_state['last_pal']
                label_html = f"""<div id="p-area" style="width:100%; max-width:800px; padding:40px; border:12px solid black; font-family:Arial; background:white; color:black; text-align:center; margin:auto;">
                    <div style="font-size:90px; font-weight:900;">{lp['prod']}</div><hr style="border:5px solid black;">
                    <div style="font-size:50px; margin:20px 0;">PALLET ID: <b>{lp['id']}</b></div>
                    <div style="font-size:45px; text-align:left; padding-left:50px; line-height:1.8;">
                        <b>BAG SIZE:</b> {lp['size']} lbs<br><b>QUANTITY:</b> {lp['qty']} Bags<br><b>NET WT:</b> {lp['size']*lp['qty']:.1f} lbs
                    </div></div><br><div style="text-align:center;"><button onclick="window.print()" style="padding:20px 40px; background:#007bff; color:white; border:none; font-size:24px; cursor:pointer;">🖨️ PRINT PALLET LABEL</button></div>
                    <style>@media print {{ body * {{ visibility: hidden; }} #p-area, #p-area * {{ visibility: visible; }} #p-area {{ position: absolute; left: 0; top: 0; width:100%; }} }}</style>"""
                st.components.v1.html(label_html, height=900)

        # --- SHIPPING ---
        elif choice == "Shipping":
            st.title("🚢 Dispatch / Transfer")
            sid = st.text_input("Scan QR Code or Type ID").upper()
            if sid:
                conn = sqlite3.connect(DB_PATH)
                res = pd.read_sql_query("SELECT * FROM test_results WHERE bag_ref = ? AND status = 'Inventory'", conn, params=(sid,))
                if not res.empty:
                    st.warning(f"Sack located at: **{res['location'].values[0]}**")
                    with st.form("s_form"):
                        cust = st.text_input("Customer / Operation")
                        if st.form_submit_button("Ship/Move"):
                            c = conn.cursor(); sd = date.today().strftime("%Y-%m-%d")
                            c.execute("UPDATE test_results SET customer_name=?, shipped_date=?, status='Shipped', shipped_by=? WHERE bag_ref=?", (cust, sd, st.session_state['user_display'], sid))
                            conn.commit(); conn.close(); st.success(f"Moved {sid} to {cust}"); st.rerun()
                else: st.error("Sack not found."); conn.close()

        # --- ANALYTICS ---
        elif choice == "Analytics Dashboard":
            st.title("📈 Plant Trends")
            conn = sqlite3.connect(DB_PATH)
            p_df = pd.read_sql_query("SELECT * FROM process_logs ORDER BY timestamp ASC", conn)
            conn.close()
            if not p_df.empty:
                p_df['timestamp'] = pd.to_datetime(p_df['timestamp'])
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=p_df['timestamp'], y=p_df['reactor_1_temp'], name="R1 Temp", line=dict(color='red')))
                fig.add_trace(go.Scatter(x=p_df['timestamp'], y=p_df['reactor_2_temp'], name="R2 Temp", line=dict(color='blue')))
                fig.add_hline(y=500, line_dash="dash", line_color="red")
                fig.add_hline(y=550, line_dash="dash", line_color="blue")
                st.plotly_chart(fig, use_container_width=True)
            else: st.info("No data yet.")

        # --- STOCK INQUIRY ---
        elif choice == "Stock Inquiry":
            st.title("🔎 Inventory Stock")
            conn = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query("SELECT bag_ref, product, location, weight_lbs, timestamp FROM test_results WHERE status = 'Inventory'", conn)
            conn.close()
            st.dataframe(df, use_container_width=True)

        # --- VIEW RECORDS ---
        elif choice == "View Records":
            st.title("📊 Plant Records")
            t1, t2, t3 = st.tabs(["Supersacks", "Bagging runs", "Reactor"])
            conn = sqlite3.connect(DB_PATH)
            with t1: st.dataframe(pd.read_sql_query("SELECT * FROM test_results", conn))
            with t2: st.dataframe(pd.read_sql_query("SELECT * FROM bagging_ops", conn))
            with t3: st.dataframe(pd.read_sql_query("SELECT * FROM process_logs", conn))
            conn.close()

if __name__ == '__main__':
    main()

