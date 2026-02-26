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
DB_PATH = "rcb_inventory_v13.db"
BACKUP_DIR = "backups"

def init_db():
    if not os.path.exists(BACKUP_DIR): os.makedirs(BACKUP_DIR)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Table 1: Quality & Inventory (Added Location)
    c.execute('''CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bag_ref TEXT UNIQUE,
                    timestamp DATETIME,
                    operator TEXT,
                    shipped_by TEXT,
                    product TEXT,
                    location TEXT DEFAULT 'Warehouse',
                    customer_name TEXT DEFAULT 'In Inventory',
                    shipped_date TEXT DEFAULT 'Not Shipped',
                    status TEXT DEFAULT 'Inventory',
                    pellet_hardness INTEGER,
                    moisture REAL,
                    toluene INTEGER,
                    ash_content REAL,
                    weight_lbs REAL)''')
    
    # Table 2: Bagging Operations (New Section)
    c.execute('''CREATE TABLE IF NOT EXISTS bagging_ops (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    operator TEXT,
                    product TEXT,
                    bag_size_lbs REAL,
                    quantity INTEGER,
                    pallet_id TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS process_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME, operator TEXT, toluene_value INTEGER,
                    feed_rate REAL, reactor_1_temp INTEGER, reactor_2_temp INTEGER,
                    reactor_1_hz INTEGER, reactor_2_hz INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, full_name TEXT)''')
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

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="AI-sistant - Plant Management", layout="wide")
    init_db()

    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

    if not st.session_state['logged_in']:
        st.title("🔒 AI-sistant Portal Login")
        u, p = st.text_input("Username"), st.text_input("Password", type='password')
        if st.button("Login"):
            fn = check_login(u, p)
            if fn or (u == "admin" and p == "admin123"):
                st.session_state.update({"logged_in": True, "user_display": fn or "Admin", "username": u})
                st.rerun()
    else:
        st.sidebar.title("AI-sistant")
        menu = ["Production (Inventory)", "Reactor Logs", "Bagging Room", "Shipping", "Analytics Dashboard", "Stock Inquiry", "View Records"]
        if st.session_state['username'] == 'admin': menu.append("User Management")
        choice = st.sidebar.selectbox("Go to:", menu)

        # --- PRODUCTION (Added Location) ---
        if choice == "Production (Inventory)":
            st.title("🏗️ Bulk Production (Supersacks)")
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM test_results"); count = c.fetchone()[0]; conn.close()
            bag_id = f"RCB-{datetime.now().year}-{(count + 1):04d}"
            
            with st.form("prod_form", clear_on_submit=True):
                st.subheader(f"New Supersack ID: {bag_id}")
                product = st.selectbox("Product", ["Revolution CB", "Paris CB"])
                location = st.text_input("Warehouse Location", placeholder="e.g., A-104")
                c1, c2 = st.columns(2)
                with c1:
                    hardness = st.number_input("Hardness", min_value=0, step=1)
                    weight = st.number_input("Bulk Weight (lbs)", value=2000.0)
                with c2:
                    moisture = st.number_input("Moisture %", format="%.2f")
                    toluene = st.number_input("Toluene", step=1)
                    ash = st.number_input("Ash Content %", format="%.1f")
                
                if st.form_submit_button("Record Supersack"):
                    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute('''INSERT INTO test_results (bag_ref, timestamp, operator, product, location, pellet_hardness, moisture, toluene, ash_content, weight_lbs)
                                 VALUES (?,?,?,?,?,?,?,?,?,?)''', (bag_id, ts, st.session_state['user_display'], product, location, hardness, moisture, toluene, ash, weight))
                    conn.commit(); conn.close()
                    st.session_state['last_sack'] = {"id": bag_id, "prod": product, "loc": location, "weight": weight}
                    st.success(f"Recorded Sack {bag_id} at {location}")

        # --- BAGGING ROOM (NEW SECTION) ---
        elif choice == "Bagging Room":
            st.title("🛍️ Small Bagging Operation")
            st.info("Use this page to record small bags filled from bulk supersacks.")
            
            with st.form("bagging_form", clear_on_submit=True):
                prod = st.selectbox("Product Being Bagged", ["Revolution CB", "Paris CB"])
                bag_size = st.number_input("Bag Size (lbs)", min_value=1.0, value=50.0)
                qty = st.number_input("Number of Bags Filled (Qty)", min_value=1, step=1)
                pallet_id = f"PAL-{datetime.now().strftime('%m%d%y-%H%M')}"
                
                if st.form_submit_button("Submit Bagging Run & Print Pallet Label"):
                    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute("INSERT INTO bagging_ops (timestamp, operator, product, bag_size_lbs, quantity, pallet_id) VALUES (?,?,?,?,?,?)",
                              (ts, st.session_state['user_display'], prod, bag_size, qty, pallet_id))
                    conn.commit(); conn.close()
                    
                    st.success(f"Pallet {pallet_id} Recorded!")
                    
                    # Pallet Label HTML
                    st.divider()
                    label_html = f"""
                    <div id="pallet-label" style="width:400px; padding:20px; border:5px solid black; font-family:Arial; background:white; color:black; text-align:center;">
                        <h1 style="margin:0; font-size:40px;">{prod}</h1>
                        <hr style="border:2px solid black;">
                        <h2 style="font-size:30px; margin:10px 0;">PALLET ID: {pallet_id}</h2>
                        <div style="font-size:24px; text-align:left; margin-left:40px;">
                            <strong>Bag Size:</strong> {bag_size} lbs<br>
                            <strong>Quantity:</strong> {qty} Bags<br>
                            <strong>Total Weight:</strong> {bag_size * qty} lbs
                        </div>
                        <div style="margin-top:20px; font-size:12px; color:gray;">Date: {ts} | Operator: {st.session_state['user_display']}</div>
                    </div>
                    <br><button onclick="window.print()" style="padding:15px; background:#007bff; color:white; border:none; width:400px; cursor:pointer; font-weight:bold; font-size:18px;">🖨️ Print Pallet Label</button>
                    <style>@media print {{ body * {{ visibility: hidden; }} #pallet-label, #pallet-label * {{ visibility: visible; }} #pallet-label {{ position: absolute; left: 0; top: 0; }} }}</style>
                    """
                    st.components.v1.html(label_html, height=500)

        # --- SHIPPING (Updated for Location) ---
        elif choice == "Shipping":
            st.title("🚢 Dispatch / Bagging Transfer")
            sid = st.text_input("Scan Supersack Barcode").upper()
            if sid:
                conn = sqlite3.connect(DB_PATH)
                res = pd.read_sql_query("SELECT * FROM test_results WHERE bag_ref = ? AND status = 'Inventory'", conn, params=(sid,))
                if not res.empty:
                    st.warning(f"Sack located at: **{res['location'].values[0]}**")
                    with st.form("ship"):
                        cust = st.text_input("Customer Name", help="Type 'Bagging Operation' if moving to small bags.")
                        if st.form_submit_button("Ship / Move"):
                            c = conn.cursor(); sd = date.today().strftime("%Y-%m-%d")
                            c.execute("UPDATE test_results SET customer_name=?, shipped_date=?, status='Shipped', shipped_by=? WHERE bag_ref=?", (cust, sd, st.session_state['user_display'], sid))
                            conn.commit(); conn.close(); st.success(f"Sack {sid} moved to {cust}"); st.rerun()
                else: st.error("Sack not found."); conn.close()

        # --- STOCK INQUIRY (Updated for Location) ---
        elif choice == "Stock Inquiry":
            st.title("🔎 Inventory Enquiry")
            conn = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query("SELECT bag_ref, product, location, weight_lbs, timestamp FROM test_results WHERE status = 'Inventory'", conn)
            conn.close()
            st.dataframe(df, use_container_width=True)

        # --- VIEW RECORDS ---
        elif choice == "View Records":
            st.title("📊 Plant Archives")
            t1, t2, t3 = st.tabs(["Supersacks", "Small Bagging Runs", "Reactor Logs"])
            conn = sqlite3.connect(DB_PATH)
            with t1: st.dataframe(pd.read_sql_query("SELECT * FROM test_results", conn))
            with t2: st.dataframe(pd.read_sql_query("SELECT * FROM bagging_ops", conn))
            with t3: st.dataframe(pd.read_sql_query("SELECT * FROM process_logs", conn))
            conn.close()

if __name__ == '__main__':
    main()

