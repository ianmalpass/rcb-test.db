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

# --- CONFIGURATION ---
DB_PATH = "rcb_inventory_v11.db"
BACKUP_DIR = "backups"

# --- DATABASE INITIALIZATION ---
def init_db():
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
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
                    particle_size INTEGER,
                    pellet_hardness INTEGER,
                    moisture REAL,
                    toluene INTEGER,
                    ash_content REAL,
                    weight_lbs REAL)''')
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

def create_backup():
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"inventory_backup_{timestamp}.db")
        shutil.copy2(DB_PATH, backup_path)
        return backup_path
    except Exception as e: return str(e)

def add_inventory_entry(bag_ref, operator, product, p_size, hardness, moisture, toluene, ash, weight):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''INSERT INTO test_results 
                 (bag_ref, timestamp, operator, product, particle_size, pellet_hardness, moisture, toluene, ash_content, weight_lbs)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
              (bag_ref, ts, operator, product, p_size, hardness, moisture, toluene, ash, weight))
    conn.commit()
    conn.close()

def ship_bag(bag_ref, customer, shipper_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    ship_date = datetime.now().strftime("%Y-%m-%d")
    c.execute('''UPDATE test_results SET customer_name = ?, shipped_date = ?, status = 'Shipped', shipped_by = ? 
                 WHERE bag_ref = ?''', (customer, ship_date, shipper_name, bag_ref))
    conn.commit()
    conn.close()

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
    st.set_page_config(page_title="BARC - Inventory & QC", layout="wide")
    init_db()

    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

    if not st.session_state['logged_in']:
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
        st.sidebar.title("Navigation")
        st.sidebar.info(f"User: {st.session_state['user_display']}")
        menu = ["Production", "Shipping", "Stock Inquiry", "Shipping Report", "View Records"]
        if st.session_state['username'] == 'admin': menu.append("User Management")
        choice = st.sidebar.selectbox("Go to:", menu)
        if st.sidebar.button("Logout"):
            st.session_state['logged_in'] = False
            st.rerun()

        # --- PRODUCTION ---
        if choice == "Production":
            st.title("🏗️ New Production Entry")
            bag_id = generate_bag_ref()
            with st.form("prod_form", clear_on_submit=True):
                st.subheader(f"Bag ID: {bag_id}")
                product = st.selectbox("Product", ["Revolution CB", "Paris CB"])
                c1, c2 = st.columns(2)
                with c1:
                    p_size = st.number_input("Particle Size (Integer)", min_value=0, max_value=99, step=1)
                    hardness = st.number_input("Hardness (Integer)", min_value=0, max_value=99, step=1)
                    weight = st.number_input("Weight (lbs)", min_value=0.0, value=55.0)
                with c2:
                    moisture = st.number_input("Moisture %", format="%.2f")
                    toluene = st.number_input("Toluene (Integer)", min_value=0, max_value=99, step=1)
                    ash = st.number_input("Ash Content %", format="%.1f")
                
                if st.form_submit_button("Save & Generate Barcode"):
                    add_inventory_entry(bag_id, st.session_state['user_display'], product, p_size, hardness, moisture, toluene, ash, weight)
                    st.session_state['last_bag'] = {
                        "id": bag_id, "prod": product, "weight": weight, "p_size": p_size,
                        "hardness": hardness, "toluene": toluene, "ash": ash, "moist": moisture,
                        "op": st.session_state['user_display'], "time": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }
                    st.success(f"Recorded {bag_id}")

            if 'last_bag' in st.session_state and st.session_state['last_bag']['id'] == bag_id:
                lb = st.session_state['last_bag']
                b_code = generate_barcode_base64(lb['id'])
                st.divider()
                label_html = f"""
                <div id="label" style="width:320px; padding:15px; border:3px solid black; font-family:Arial; background:white; color:black;">
                    <div style="font-size:22px; font-weight:bold; text-align:center; border-bottom:2px solid black;">{lb['prod']}</div>
                    <div style="text-align:center; padding:10px 0;">
                        <img src="data:image/png;base64,{b_code}" style="width:240px;">
                        <br><span style="font-size:18px; font-weight:bold;">{lb['id']}</span>
                    </div>
                    <div style="font-size:14px; border-top:1px solid #000; padding-top:8px;">
                        <strong>Weight:</strong> {lb['weight']:.1f} lbs | <strong>Ash:</strong> {lb['ash']:.1f}%<br>
                        <strong>P-Size:</strong> {int(lb['p_size'])} | <strong>Hardness:</strong> {int(lb['hardness'])}<br>
                        <span style="font-size:10px; color:gray;">Op: {lb['op']} | {lb['time']}</span>
                    </div>
                </div>
                <br><button onclick="window.print()" style="padding:10px; background:#28a745; color:white; border:none; border-radius:4px; width:320px; cursor:pointer; font-weight:bold;">🖨️ Print Label</button>
                <style>@media print {{ body * {{ visibility: hidden; }} #label, #label * {{ visibility: visible; }} #label {{ position: absolute; left: 0; top: 0; }} }}</style>
                """
                st.components.v1.html(label_html, height=500)

        # --- SHIPPING (SCAN TO SHIP) ---
        elif choice == "Shipping":
            st.title("🚢 Scan-to-Ship")
            scan_id = st.text_input("🔍 Scan Barcode or Type Bag ID").upper()
            if scan_id:
                conn = sqlite3.connect(DB_PATH)
                res = pd.read_sql_query("SELECT * FROM test_results WHERE bag_ref = ? AND status = 'Inventory'", conn, params=(scan_id,))
                conn.close()
                if not res.empty:
                    st.success(f"Found: {scan_id} ({res['product'].values[0]})")
                    with st.form("ship_confirm"):
                        cust = st.text_input("Customer Name")
                        if st.form_submit_button("Ship Bag"):
                            if cust:
                                ship_bag(scan_id, cust, st.session_state['user_display'])
                                st.success(f"Dispatched {scan_id} to {cust}")
                                st.rerun()
                else: st.error("Bag not found or already shipped.")

        # --- STOCK INQUIRY ---
        elif choice == "Stock Inquiry":
            st.title("🔎 Inventory Status")
            conn = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query("SELECT product, weight_lbs, bag_ref, timestamp FROM test_results WHERE status = 'Inventory'", conn)
            conn.close()
            if df.empty: st.info("Inventory Empty")
            else:
                c1, c2 = st.columns(2)
                for i, p in enumerate(["Revolution CB", "Paris CB"]):
                    d = df[df['product'] == p]
                    col = c1 if i == 0 else c2
                    col.metric(f"Stock: {p}", f"{len(d)} Bags", f"{d['weight_lbs'].sum():,.1f} lbs")
                st.dataframe(df, use_container_width=True)

        # --- SHIPPING REPORT ---
        elif choice == "Shipping Report":
            st.title("📦 Outbound Report")
            c1, c2 = st.columns(2)
            sd = c1.date_input("From", value=date(2026, 1, 1))
            ed = c2.date_input("To", value=date.today())
            conn = sqlite3.connect(DB_PATH)
            rdf = pd.read_sql_query("SELECT customer_name, shipped_date, product, weight_lbs, bag_ref FROM test_results WHERE status = 'Shipped' AND shipped_date BETWEEN ? AND ?", conn, params=(str(sd), str(ed)))
            conn.close()
            if not rdf.empty:
                st.metric("Total Weight Shipped", f"{rdf['weight_lbs'].sum():,.1f} lbs")
                st.table(rdf.groupby('customer_name')['weight_lbs'].sum())
                st.dataframe(rdf)

        # --- VIEW RECORDS & BACKUP ---
        elif choice == "View Records":
            st.title("📊 Master Records")
            if st.button("🛠️ Create Database Backup"):
                st.success(f"Backup saved: {create_backup()}")
            conn = sqlite3.connect(DB_PATH)
            st.dataframe(pd.read_sql_query("SELECT * FROM test_results ORDER BY timestamp DESC", conn))
            conn.close()

        # --- USER MANAGEMENT ---
        elif choice == "User Management":
            st.title("👤 User Admin")
            with st.expander("Add Staff"):
                with st.form("u_add"):
                    un, pw, fn = st.text_input("User"), st.text_input("Pass", type='password'), st.text_input("Name")
                    if st.form_submit_button("Add"):
                        conn = sqlite3.connect(DB_PATH)
                        try:
                            conn.execute("INSERT INTO users VALUES (?,?,?)", (un, hashlib.sha256(str.encode(pw)).hexdigest(), fn))
                            conn.commit()
                            st.success("User Added")
                        except: st.error("Error")
                        conn.close()
            conn = sqlite3.connect(DB_PATH)
            st.table(pd.read_sql_query("SELECT username, full_name FROM users", conn))
            conn.close()

if __name__ == '__main__':
    main()
