import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, date
import qrcode
import base64
from io import BytesIO

# --- CONFIGURATION ---
DB_PATH = "rcb_inventory_v14.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 1. Main Production Table
    c.execute('''CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bag_ref TEXT UNIQUE,
                    timestamp DATETIME,
                    operator TEXT,
                    product TEXT,
                    location_id TEXT,
                    status TEXT DEFAULT 'Inventory',
                    customer_name TEXT DEFAULT 'In Inventory',
                    weight_lbs REAL,
                    pellet_hardness INTEGER,
                    moisture REAL,
                    toluene INTEGER,
                    ash_content REAL)''')

    # 2. Location Master Table
    c.execute('''CREATE TABLE IF NOT EXISTS locations (
                    loc_id TEXT PRIMARY KEY,
                    status TEXT DEFAULT 'Available')''')
    
    # Seed 100 Locations
    c.execute("SELECT COUNT(*) FROM locations")
    if c.fetchone()[0] == 0:
        for i in range(1, 101):
            c.execute("INSERT INTO locations (loc_id, status) VALUES (?, 'Available')", (f"WH-{i:03d}",))
    
    c.execute('''CREATE TABLE IF NOT EXISTS process_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME, operator TEXT, toluene_value INTEGER, feed_rate REAL, reactor_1_temp INTEGER, reactor_2_temp INTEGER, reactor_1_hz INTEGER, reactor_2_hz INTEGER)''')
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

def get_next_available_location():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT loc_id FROM locations WHERE status = 'Available' ORDER BY loc_id ASC LIMIT 1")
    res = c.fetchone(); conn.close()
    return res[0] if res else None

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="AI-sistant", layout="wide")
    init_db()

    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

    if not st.session_state['logged_in']:
        st.title("🔒 AI-sistant Login")
        u, p = st.text_input("Username"), st.text_input("Password", type='password')
        if st.button("Login"):
            if (u == "admin" and p == "admin123") or u == "operator":
                st.session_state.update({"logged_in": True, "user_display": u.capitalize()})
                st.rerun()
    else:
        st.sidebar.title("AI-sistant")
        menu = ["Production (Inventory)", "Shipping (FIFO)", "Stock Inquiry (Grid Map)", "View Records"]
        choice = st.sidebar.selectbox("Go to:", menu)

        # --- PRODUCTION ---
        if choice == "Production (Inventory)":
            st.title("🏗️ Bulk Production")
            next_loc = get_next_available_location()
            if not next_loc:
                st.error("🚨 Warehouse Full!")
            else:
                with st.form("prod_form", clear_on_submit=True):
                    st.info(f"📍 Auto-Allocated Location: **{next_loc}**")
                    prod = st.selectbox("Product", ["Revolution CB", "Paris CB"])
                    c1, c2 = st.columns(2)
                    with c1:
                        weight = st.number_input("Weight (lbs)", value=2000.0)
                        hard = st.number_input("Hardness", min_value=0)
                    with c2:
                        moist = st.number_input("Moisture %")
                        tol = st.number_input("Toluene")
                    
                    if st.form_submit_button("Record Bag"):
                        bag_id = f"RCB-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                        c.execute("INSERT INTO test_results (bag_ref, timestamp, operator, product, location_id, weight_lbs, pellet_hardness, moisture, toluene) VALUES (?,?,?,?,?,?,?,?,?)",
                                  (bag_id, datetime.now(), st.session_state['user_display'], prod, next_loc, weight, hard, moist, tol))
                        c.execute("UPDATE locations SET status = 'Occupied' WHERE loc_id = ?", (next_loc,))
                        conn.commit(); conn.close()
                        st.session_state['last_qr'] = {"id": bag_id, "prod": prod, "loc": next_loc}
                        st.success(f"Bag {bag_id} stored in {next_loc}")

                if 'last_qr' in st.session_state:
                    lqr = st.session_state['last_qr']
                    qr_img = generate_qr_base64(lqr['id'])
                    st.image(f"data:image/png;base64,{qr_img}", caption=f"ID: {lqr['id']} | Loc: {lqr['loc']}")

        # --- SHIPPING (FIFO) ---
        elif choice == "Shipping (FIFO)":
            st.title("🚢 Auto-Dispatch (FIFO)")
            st.write("Since products are homogenous, the system will pick the oldest bag for you.")
            ship_prod = st.selectbox("Select Product to Ship", ["Revolution CB", "Paris CB"])
            
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT bag_ref, location_id, timestamp FROM test_results WHERE product = ? AND status = 'Inventory' ORDER BY timestamp ASC LIMIT 1", (ship_prod,))
            oldest_bag = c.fetchone()
            
            if oldest_bag:
                st.success(f"Oldest {ship_prod} found!")
                st.metric("Go to Location", oldest_bag[1])
                st.info(f"Bag ID: {oldest_bag[0]} (Produced: {oldest_bag[2]})")
                
                if st.button(f"Confirm Shipment of {oldest_bag[0]}"):
                    c.execute("UPDATE test_results SET status = 'Shipped', shipped_by = ? WHERE bag_ref = ?", (st.session_state['user_display'], oldest_bag[0]))
                    c.execute("UPDATE locations SET status = 'Available' WHERE loc_id = ?", (oldest_bag[1],))
                    conn.commit(); conn.close()
                    st.balloons()
                    st.success(f"Location {oldest_bag[1]} is now empty and available.")
                    st.rerun()
            else:
                st.warning(f"No {ship_prod} currently in stock.")
                conn.close()

        # --- VISUAL GRID MAP ---
        elif choice == "Stock Inquiry (Grid Map)":
            st.title("🔎 Warehouse Visual Grid")
            conn = sqlite3.connect(DB_PATH)
            loc_query = """
                SELECT l.loc_id, l.status, t.product, t.bag_ref 
                FROM locations l
                LEFT JOIN test_results t ON l.loc_id = t.location_id AND t.status = 'Inventory'
                ORDER BY l.loc_id ASC
            """
            df = pd.read_sql_query(loc_query, conn)
            conn.close()

            # Mapping for Heatmap: 0=Available (Green), 1=Revolution (Black), 2=Paris (Yellow)
            def map_color(row):
                if row['status'] == 'Available': return 0
                return 1 if row['product'] == 'Revolution CB' else 2

            df['color_val'] = df.apply(map_color, axis=1)
            z_data = df['color_val'].values.reshape(10, 10)
            text_data = df.apply(lambda r: f"Loc: {r['loc_id']}<br>Prod: {r['product'] or 'Empty'}<br>ID: {r['bag_ref'] or ''}", axis=1).values.reshape(10, 10)

            fig = go.Figure(data=go.Heatmap(
                z=z_data, text=text_data, hoverinfo="text",
                colorscale=[[0, '#28a745'], [0.5, '#000000'], [1, '#ffc107']],
                showscale=False, xgap=5, ygap=5
            ))
            fig.update_layout(height=600, xaxis_visible=False, yaxis_visible=False, title="100-Slot Warehouse Map")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Available", len(df[df['status'] == 'Available']))
            c2.metric("Revolution (Black)", len(df[df['product'] == 'Revolution CB']))
            c3.metric("Paris (Yellow)", len(df[df['product'] == 'Paris CB']))
            
            st.plotly_chart(fig, use_container_width=True)

        elif choice == "View Records":
            st.title("📊 Master Ledger")
            conn = sqlite3.connect(DB_PATH)
            st.dataframe(pd.read_sql_query("SELECT * FROM test_results ORDER BY timestamp DESC", conn), use_container_width=True)
            conn.close()

if __name__ == '__main__':
    main()



