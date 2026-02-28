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

# --- 1. THE SELF-HEALING ENGINE ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Create the core table with every field required
    c.execute('''CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bag_ref TEXT UNIQUE,
                    timestamp DATETIME,
                    operator TEXT,
                    product TEXT,
                    location_id TEXT,
                    status TEXT DEFAULT 'Inventory',
                    customer_name TEXT DEFAULT 'In Inventory',
                    shipped_date TEXT DEFAULT 'Not Shipped',
                    shipped_by TEXT DEFAULT 'N/A',
                    weight_lbs REAL,
                    pellet_hardness INTEGER,
                    moisture REAL,
                    toluene INTEGER,
                    ash_content REAL)''')

    # SAFETY CHECK: Add any missing columns if the DB was created in an older version
    cols = [
        ('customer_name', "TEXT DEFAULT 'In Inventory'"),
        ('shipped_date', "TEXT DEFAULT 'Not Shipped'"),
        ('shipped_by', "TEXT DEFAULT 'N/A'"),
        ('ash_content', "REAL"),
        ('moisture', "REAL"),
        ('toluene', "INTEGER"),
        ('pellet_hardness', "INTEGER")
    ]
    for col_name, col_def in cols:
        try:
            c.execute(f"ALTER TABLE test_results ADD COLUMN {col_name} {col_def}")
        except sqlite3.OperationalError:
            pass # Column already exists

    # Location Table
    c.execute('''CREATE TABLE IF NOT EXISTS locations (loc_id TEXT PRIMARY KEY, status TEXT DEFAULT 'Available')''')
    
    # Ensure 100 locations exist
    c.execute("SELECT COUNT(*) FROM locations")
    if c.fetchone()[0] == 0:
        for i in range(1, 101):
            c.execute("INSERT INTO locations (loc_id, status) VALUES (?, 'Available')", (f"WH-{i:03d}",))
    
    conn.commit()
    conn.close()

# --- 2. THE TEST ENGINE ---
def run_full_test():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("DELETE FROM test_results")
    c.execute("UPDATE locations SET status = 'Available'")
    
    prods = ["Revolution CB", "Paris CB"]
    # 50 bags produced
    for i in range(50):
        p = prods[0] if i < 25 else prods[1]
        ts = (datetime.now() - timedelta(days=random.randint(1, 10))).strftime("%Y-%m-%d %H:%M:%S")
        bid = f"TEST-BAG-{random.randint(1000,9999)}-{i}"
        loc = f"WH-{(i+1):03d}"
        c.execute("INSERT INTO test_results (bag_ref, timestamp, operator, product, location_id, weight_lbs, status) VALUES (?,?,?,?,?,2000.0,'Inventory')", (bid, ts, "System", p, loc))
        c.execute("UPDATE locations SET status = 'Occupied' WHERE loc_id = ?", (loc,))
    
    # 25 of each shipped (total 50)
    for p in prods:
        c.execute("SELECT bag_ref, location_id FROM test_results WHERE product=? AND status='Inventory' LIMIT 25", (p,))
        rows = c.fetchall()
        for bid, loc in rows:
            c.execute("UPDATE test_results SET status='Shipped', customer_name='Test Client', shipped_date=? WHERE bag_ref=?", (date.today().strftime("%Y-%m-%d"), bid))
            c.execute("UPDATE locations SET status='Available' WHERE loc_id=?", (loc,))
    conn.commit(); conn.close()
    return "Test Success: 50 Created, 50 Shipped."

# --- 3. HELPERS ---
def generate_qr(data):
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(data); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO(); img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def get_loc():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT loc_id FROM locations WHERE status = 'Available' ORDER BY loc_id ASC LIMIT 1")
    res = c.fetchone(); conn.close()
    return res[0] if res else None

# --- 4. MAIN APP ---
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
        st.sidebar.title("AI-sistant")
        # DEV TOOLS
        if st.sidebar.checkbox("🛠️ Developer Tools"):
            if st.sidebar.button("🧪 Run 50-Bag Test"):
                st.sidebar.success(run_full_test()); st.rerun()
            if st.sidebar.button("🗑️ Wipe All Data"):
                conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                c.execute("DELETE FROM test_results"); c.execute("UPDATE locations SET status='Available'")
                conn.commit(); conn.close(); st.sidebar.warning("Data Wiped"); st.rerun()

        menu = ["Production Dashboard", "Production (Inventory)", "Shipping (FIFO)", "Stock Inquiry (Grid Map)", "View Records"]
        choice = st.sidebar.selectbox("Go to:", menu)

        # --- GRID VIEW ---
        if choice == "Stock Inquiry (Grid Map)":
            st.title("🔎 Warehouse Visual Grid")
            conn = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query("SELECT l.loc_id, l.status, t.product FROM locations l LEFT JOIN test_results t ON l.loc_id = t.location_id AND t.status = 'Inventory' ORDER BY l.loc_id ASC", conn)
            conn.close()
            df['val'] = df.apply(lambda r: 0 if r['status'] == 'Available' else (1 if r['product'] == 'Revolution CB' else 2), axis=1)
            df['txt_c'] = df['product'].apply(lambda p: 'black' if p == 'Paris CB' else 'white')
            df['num'] = df['loc_id'].str.extract('(\d+)')
            
            fig = go.Figure(data=go.Heatmap(
                z=df['val'].values.reshape(10,10), text=df['num'].values.reshape(10,10), texttemplate="<b>%{text}</b>",
                textfont={"size": 32, "family": "Arial Black", "color": df['txt_c'].tolist()},
                colorscale=[[0, '#28a745'], [0.5, '#000000'], [1, '#ffc107']], showscale=False, xgap=8, ygap=8
            ))
            fig.update_layout(height=850, xaxis_visible=False, yaxis_visible=False, scaleanchor="x")
            st.plotly_chart(fig, use_container_width=True)

        # --- PRODUCTION (ALL FIELDS RESTORED) ---
        elif choice == "Production (Inventory)":
            st.title("🏗️ Bulk Production")
            loc = get_loc()
            if loc:
                with st.form("prod_form", clear_on_submit=True):
                    st.info(f"📍 Location Assigned: **{loc}**")
                    prod = st.selectbox("Product", ["Revolution CB", "Paris CB"])
                    c1, c2 = st.columns(2)
                    with c1:
                        weight = st.number_input("Weight (lbs)", 2000.0)
                        hard = st.number_input("Hardness", 0)
                    with c2:
                        moist = st.number_input("Moisture %", 0.0, format="%.2f")
                        tol = st.number_input("Toluene", 0)
                        ash = st.number_input("Ash %", 0.0)
                    
                    if st.form_submit_button("Record & Print"):
                        bid = f"RCB-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
                        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                        c.execute("INSERT INTO test_results (bag_ref,timestamp,operator,product,location_id,weight_lbs,pellet_hardness,moisture,toluene,ash_content) VALUES (?,?,?,?,?,?,?,?,?,?)",
                                  (bid, datetime.now(), st.session_state['user_display'], prod, loc, weight, hard, moist, tol, ash))
                        c.execute("UPDATE locations SET status='Occupied' WHERE loc_id=?", (loc,))
                        conn.commit(); conn.close()
                        st.session_state['last_sack'] = {"id": bid, "prod": prod, "loc": loc, "weight": weight, "ash": ash, "hard": hard, "moist": moist}
                        st.session_state['show_label'] = True; st.rerun()

                if st.session_state.get('show_label') and 'last_sack' in st.session_state:
                    ls = st.session_state['last_sack']
                    qr_c = generate_qr(ls['id'])
                    label_html = f"""<div id="print-area" style="width:60%; padding:30px; border:10px solid black; font-family:Arial; background:white; color:black; margin:auto; text-align:center;">
                        <div style="font-size:60px; font-weight:900; border-bottom:6px solid black;">{ls['prod']}</div>
                        <div style="padding:20px 0;"><img src="data:image/png;base64,{qr_c}" style="width:320px;"><br><div style="font-size:40px; font-weight:bold;">{ls['id']}</div></div>
                        <div style="font-size:32px; border-top:6px solid black; padding-top:15px; text-align:left; line-height:1.4;">
                            <b>LOC:</b> {ls['loc']} | <b>WT:</b> {ls['weight']:.1f} lbs<br><b>ASH:</b> {ls['ash']:.1f}% | <b>HARD:</b> {int(ls['hard'])}<br><b>MOIST:</b> {ls['moist']:.2f}%
                        </div></div><br><div style="text-align:center;">
                        <button onclick="window.print()" style="padding:15px 30px; background:#28a745; color:white; border:none; font-size:20px; cursor:pointer;">🖨️ PRINT</button>
                        <button onclick="window.location.reload()" style="padding:15px 30px; background:#6c757d; color:white; border:none; font-size:20px; cursor:pointer; margin-left:10px;">Done / Clear</button>
                    </div><style>@media print {{ body * {{ visibility: hidden; }} #print-area, #print-area * {{ visibility: visible; }} #print-area {{ position: absolute; left:20%; top:5%; width:60%; }} }}</style>"""
                    st.components.v1.html(label_html, height=950)

        # --- SHIPPING (FIFO) ---
        elif choice == "Shipping (FIFO)":
            st.title("🚢 FIFO Shipping")
            prod = st.selectbox("Product", ["Revolution CB", "Paris CB"])
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT bag_ref, location_id FROM test_results WHERE product=? AND status='Inventory' ORDER BY timestamp ASC LIMIT 1", (prod,))
            res = c.fetchone()
            if res:
                st.metric("Go to Loc", res[1])
                with st.form("ship_f"):
                    cust = st.text_input("Customer Name")
                    if st.form_submit_button("Ship Oldest Bag") and cust:
                        c.execute("UPDATE test_results SET status='Shipped', customer_name=?, shipped_date=? WHERE bag_ref=?", (cust, date.today(), res[0]))
                        c.execute("UPDATE locations SET status='Available' WHERE loc_id=?", (res[1],))
                        conn.commit(); conn.close(); st.balloons(); st.rerun()
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
