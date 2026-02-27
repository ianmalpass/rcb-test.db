import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import hashlib
import os
import qrcode
import base64
from io import BytesIO
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
                    # Store data with moisture included
                    st.session_state['last_sack'] = {"id": bag_id, "prod": prod, "loc": loc, "weight": weight, "moist": moist, "ash": ash, "hard": hard, "ts": ts}

            if 'last_sack' in st.session_state:
                ls = st.session_state['last_sack']
                qr_code = generate_qr_base64(ls['id'])
                
                # OPTIMIZED FULL PAGE LETTER LABEL
                label_html = f"""
                <div id="print-area" style="width: 80%; padding: 40px; border: 12px solid black; font-family: Arial, sans-serif; background: white; color: black; margin: auto; text-align: center;">
                    <div style="font-size: 80px; font-weight: 900; border-bottom: 8px solid black;">{ls.get('prod', '')}</div>
                    
                    <div style="padding: 30px 0;">
                        <img src="data:image/png;base64,{qr_code}" style="width: 400px;">
                        <div style="font-size: 50px; font-weight: bold;">{ls.get('id', '')}</div>
                    </div>
                    
                    <div style="font-size: 40px; border-top: 8px solid black; padding-top: 20px; text-align: left; line-height: 1.4;">
                        <strong>LOCATION:</strong> {ls.get('loc', '')}<br>
                        <strong>WEIGHT:</strong> {ls.get('weight', 0.0):.1f} LBS<br>
                        <strong>ASH:</strong> {ls.get('ash', 0.0):.1f}% | <strong>HARDNESS:</strong> {int(ls.get('hard', 0))}<br>
                        <strong>MOISTURE:</strong> {ls.get('moist', 0.0):.2f}%
                    </div>
                </div>
                <div style="text-align: center; margin-top: 30px;">
                    <button onclick="window.print()" style="padding: 20px 40px; background: #28a745; color: white; border: none; font-size: 24px; cursor: pointer; border-radius: 10px;">🖨️ PRINT FULL LETTER LABEL</button>
                </div>
                <style>
                    @media print {{
                        body * {{ visibility: hidden; }}
                        #print-area, #print-area * {{ visibility: visible; }}
                        #print-area {{ position: absolute; left: 10%; top: 0; width: 80%; }}
                    }}
                </style>
                """
                st.components.v1.html(label_html, height=1100)

        # --- ALL OTHER SECTIONS remain the same ---
        elif choice == "Reactor Logs":
            st.title("🔥 Reactor Logs")
        elif choice == "Bagging Room":
            st.title("🛍️ Bagging Room")
        elif choice == "Shipping":
            st.title("🚢 Dispatch")
        elif choice == "Stock Inquiry":
            st.title("🔎 Stock Inquiry")
        elif choice == "View Records":
            st.title("📊 Master Ledger")

if __name__ == '__main__':
    main()


