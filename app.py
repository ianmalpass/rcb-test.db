import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
import qrcode
import base64
from io import BytesIO
import random

# --- CONFIGURATION ---
DB_PATH = "rcb_inventory_v14.db"

# --- SELF-HEALING DATABASE ---
def init_db():
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
                    location_id TEXT,
                    status TEXT DEFAULT 'Inventory',
                    customer_name TEXT DEFAULT 'In Inventory',
                    shipped_date TEXT DEFAULT 'Not Shipped',
                    weight_lbs REAL,
                    pellet_hardness INTEGER,
                    moisture REAL,
                    toluene INTEGER,
                    ash_content REAL)''')
    
    # Auto-fix missing columns
    columns = [('customer_name', "TEXT DEFAULT 'In Inventory'"), 
               ('shipped_date', "TEXT DEFAULT 'Not Shipped'"),
               ('shipped_by', "TEXT DEFAULT 'N/A'")]
    for col, definition in columns:
        try: c.execute(f"ALTER TABLE test_results ADD COLUMN {col} {definition}")
        except sqlite3.OperationalError: pass
            
    c.execute('''CREATE TABLE IF NOT EXISTS locations (loc_id TEXT PRIMARY KEY, status TEXT DEFAULT 'Available')''')
    c.execute('''CREATE TABLE IF NOT EXISTS bagging_ops (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME, operator TEXT, product TEXT, bag_size_lbs REAL, quantity INTEGER, pallet_id TEXT)''')
    
    c.execute("SELECT COUNT(*) FROM locations")
    if c.fetchone()[0] == 0:
        for i in range(1, 101):
            c.execute("INSERT INTO locations (loc_id, status) VALUES (?, 'Available')", (f"WH-{i:03d}",))
    conn.commit()
    conn.close()

# --- TEST SIMULATION ENGINE ---
def run_test_simulation():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("DELETE FROM test_results") # Clear for clean test
    c.execute("UPDATE locations SET status = 'Available'")
    
    prods = ["Revolution CB", "Paris CB"]
    # 1. Create 50 Bags
    for i in range(50):
        p = prods[0] if i < 25 else prods[1]
        ts = (datetime.now() - timedelta(days=random.randint(1, 10))).strftime("%Y-%m-%d %H:%M:%S")
        bid = f"TEST-{random.randint(1000,9999)}-{i}"
        loc = f"WH-{(i+1):03d}"
        c.execute("INSERT INTO test_results (bag_ref, timestamp, operator, product, location_id, weight_lbs, status) VALUES (?,?,?,?,?,2000.0,'Inventory')", (bid, ts, "Tester", p, loc))
        c.execute("UPDATE locations SET status = 'Occupied' WHERE loc_id = ?", (loc,))
    
    # 2. Ship 25 of each
    for p in prods:
        c.execute("SELECT bag_ref, location_id FROM test_results WHERE product=? AND status='Inventory' LIMIT 25", (p,))
        rows = c.fetchall()
        for bid, loc in rows:
            c.execute("UPDATE test_results SET status='Shipped', customer_name='Test Client', shipped_date=? WHERE bag_ref=?", (date.today().strftime("%Y-%m-%d"), bid))
            c.execute("UPDATE locations SET status='Available' WHERE loc_id=?", (loc,))
    conn.commit(); conn.close()
    return "Simulation Complete: 50 Created, 50 Shipped (25 each)."

# --- HELPERS ---
def generate_qr_base64(data):
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(data); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO(); img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def get_next_available_location():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT loc_id FROM locations WHERE status = 'Available' ORDER BY loc_id ASC LIMIT 1")
    res = c.fetchone(); conn.close()
    return res[0] if res else None

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="AI-sistant", layout="wide")
    init_db()

    if not st.session_state.get('logged_in'):
        st.title("🔒 Login")
        u = st.text_input("Username")
        if st.button("Login") and u.lower() in ['admin', 'operator']:
            st.session_state.update({'logged_in': True, 'user_display': u.capitalize()})
            st.rerun()
    else:
        # --- SIDEBAR & TEST TRIGGER ---
        st.sidebar.title("AI-sistant")
        if st.sidebar.checkbox("🛠️ Dev Mode"):
            if st.sidebar.button("🧪 Run Test Simulation"):
                msg = run_test_simulation()
                st.sidebar.success(msg); st.rerun()

        menu = ["Production Dashboard", "Production (Inventory)", "Shipping (FIFO)", "Stock Inquiry (Grid Map)", "View Records"]
        choice = st.sidebar.selectbox("Go to:", menu)

        # --- GRID MAP (FIXED CONTRAST) ---
        if choice == "Stock Inquiry (Grid Map)":
            st.title("🔎 Warehouse Visual Grid")
            conn = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query("SELECT l.loc_id, l.status, t.product FROM locations l LEFT JOIN test_results t ON l.loc_id = t.location_id AND t.status = 'Inventory' ORDER BY l.loc_id ASC", conn)
            conn.close()
            df['val'] = df.apply(lambda r: 0 if r['status'] == 'Available' else (1 if r['product'] == 'Revolution CB' else 2), axis=1)
            df['txt'] = df['product'].apply(lambda p: 'black' if p == 'Paris CB' else 'white')
            df['num'] = df['loc_id'].str.extract('(\d+)')
            
            fig = go.Figure(data=go.Heatmap(
                z=df['val'].values.reshape(10,10), text=df['num'].values.reshape(10,10), texttemplate="<b>%{text}</b>",
                textfont={"size": 32, "family": "Arial Black", "color": df['txt'].tolist()},
                colorscale=[[0, '#28a745'], [0.5, '#000000'], [1, '#ffc107']], showscale=False, xgap=8, ygap=8
            ))
            fig.update_layout(height=850, xaxis_visible=False, yaxis_visible=False, scaleanchor="x")
            st.plotly_chart(fig, use_container_width=True)

        # --- PRODUCTION ---
        elif choice == "Production (Inventory)":
            st.title("🏗️ Production")
            loc = get_next_available_location()
            if loc:
                with st.form("p", clear_on_submit=True):
                    st.info(f"Loc: {loc}")
                    p = st.selectbox("Product", ["Revolution CB", "Paris CB"])
                    w = st.number_input("Weight", 2000.0)
                    if st.form_submit_button("Record"):
                        bid = f"RCB-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
                        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                        c.execute("INSERT INTO test_results (bag_ref,timestamp,operator,product,location_id,weight_lbs) VALUES (?,?,?,?,?,?)",(bid,datetime.now(),st.session_state['user_display'],p,loc,w))
                        c.execute("UPDATE locations SET status='Occupied' WHERE loc_id=?",(loc,))
                        conn.commit(); conn.close(); st.success(f"Saved {bid}"); st.rerun()

        # --- SHIPPING ---
        elif choice == "Shipping (FIFO)":
            st.title("🚢 FIFO Shipping")
            p = st.selectbox("Product", ["Revolution CB", "Paris CB"])
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT bag_ref, location_id FROM test_results WHERE product=? AND status='Inventory' ORDER BY timestamp ASC LIMIT 1",(p,))
            res = c.fetchone()
            if res:
                st.metric("Go to Loc", res[1])
                cust = st.text_input("Customer")
                if st.button("Confirm") and cust:
                    c.execute("UPDATE test_results SET status='Shipped', customer_name=?, shipped_date=? WHERE bag_ref=?", (cust, date.today(), res[0]))
                    c.execute("UPDATE locations SET status='Available' WHERE loc_id=?", (res[1],))
                    conn.commit(); conn.close(); st.rerun()
            else: st.warning("No stock"); conn.close()

        # --- DASHBOARD & RECORDS ---
        elif choice == "Production Dashboard":
            st.title("📊 Dashboard")
            conn = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query("SELECT * FROM test_results", conn); conn.close()
            st.metric("Total Made", len(df))
            st.metric("Total Shipped", len(df[df['status'] == 'Shipped']))
            
        elif choice == "View Records":
            st.title("📊 Records")
            conn = sqlite3.connect(DB_PATH)
            st.dataframe(pd.read_sql_query("SELECT * FROM test_results ORDER BY timestamp DESC", conn))
            conn.close()

if __name__ == '__main__':
    main()
