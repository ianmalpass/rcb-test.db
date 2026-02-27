import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
import qrcode
import base64
from io import BytesIO

# --- CONFIGURATION ---
DB_PATH = "rcb_inventory_v14.db"

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
    # Location Master
    c.execute('''CREATE TABLE IF NOT EXISTS locations (
                    loc_id TEXT PRIMARY KEY,
                    status TEXT DEFAULT 'Available')''')
    # Small Bagging Operations
    c.execute('''CREATE TABLE IF NOT EXISTS bagging_ops (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    operator TEXT,
                    product TEXT,
                    bag_size_lbs REAL,
                    quantity INTEGER,
                    pallet_id TEXT)''')
    # Seed 100 Locations
    c.execute("SELECT COUNT(*) FROM locations")
    if c.fetchone()[0] == 0:
        for i in range(1, 101):
            c.execute("INSERT INTO locations (loc_id, status) VALUES (?, 'Available')", (f"WH-{i:03d}",))
    conn.commit()
    conn.close()

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

def main():
    st.set_page_config(page_title="AI-sistant", layout="wide")
    init_db()

    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

    if not st.session_state['logged_in']:
        st.title("🔒 AI-sistant Login")
        u, p = st.text_input("Username"), st.text_input("Password", type='password')
        if st.button("Login"):
            if u.lower() in ["admin", "operator"]:
                st.session_state.update({"logged_in": True, "user_display": u.capitalize()})
                st.rerun()
    else:
        st.sidebar.title("AI-sistant")
        if 'last_sack' in st.session_state:
            if st.sidebar.button("🖨️ Reprint Last Label"):
                st.session_state['show_label'] = True

        menu = ["Production Dashboard", "Production (Inventory)", "Shipping (FIFO)", "Stock Inquiry (Grid Map)", "View Records"]
        choice = st.sidebar.selectbox("Go to:", menu)

        # --- 1. DASHBOARD ---
        if choice == "Production Dashboard":
            st.title("📊 Production & Shipping Dashboard")
            d_start = st.sidebar.date_input("Start Date", value=date.today() - timedelta(days=30))
            d_end = st.sidebar.date_input("End Date", value=date.today())
            s_date, e_date = d_start.strftime("%Y-%m-%d 00:00:00"), d_end.strftime("%Y-%m-%d 23:59:59")
            conn = sqlite3.connect(DB_PATH)
            bulk_df = pd.read_sql_query(f"SELECT * FROM test_results WHERE timestamp BETWEEN '{s_date}' AND '{e_date}'", conn)
            bag_df = pd.read_sql_query(f"SELECT * FROM bagging_ops WHERE timestamp BETWEEN '{s_date}' AND '{e_date}'", conn)
            ship_df = pd.read_sql_query(f"SELECT * FROM test_results WHERE status = 'Shipped' AND timestamp BETWEEN '{s_date}' AND '{e_date}'", conn)
            conn.close()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Rev Sacks Made", len(bulk_df[bulk_df['product'] == 'Revolution CB']))
            c2.metric("Par Sacks Made", len(bulk_df[bulk_df['product'] == 'Paris CB']))
            c3.metric("Total Shipped", len(ship_df))
            c4.metric("Small Bags Produced", int(bag_df['quantity'].sum()) if not bag_df.empty else 0)

        # --- 2. PRODUCTION ---
        elif choice == "Production (Inventory)":
            st.title("🏗️ Bulk Production")
            next_loc = get_next_available_location()
            if not next_loc:
                st.error("🚨 Warehouse Full!")
            else:
                with st.form("prod_form", clear_on_submit=True):
                    st.info(f"📍 Location Assigned: **{next_loc}**")
                    prod = st.selectbox("Product", ["Revolution CB", "Paris CB"])
                    c1, c2 = st.columns(2)
                    with c1:
                        weight = st.number_input("Weight (lbs)", value=2000.0)
                        hard = st.number_input("Hardness", min_value=0)
                    with c2:
                        moist = st.number_input("Moisture %", format="%.2f")
                        tol = st.number_input("Toluene", step=1)
                        ash = st.number_input("Ash %", format="%.1f")
                    
                    if st.form_submit_button("Record & Generate Label"):
                        bag_id = f"RCB-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                        try:
                            c.execute("INSERT INTO test_results (bag_ref, timestamp, operator, product, location_id, weight_lbs, pellet_hardness, moisture, toluene, ash_content) VALUES (?,?,?,?,?,?,?,?,?,?)",
                                      (bag_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), st.session_state['user_display'], prod, next_loc, weight, hard, moist, tol, ash))
                            c.execute("UPDATE locations SET status = 'Occupied' WHERE loc_id = ?", (next_loc,))
                            conn.commit()
                            st.session_state['last_sack'] = {"id": bag_id, "prod": prod, "loc": next_loc, "weight": weight, "ash": ash, "hard": hard, "moist": moist}
                            st.session_state['show_label'] = True
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("Submission conflict. Please wait 1 second and try again.")
                        finally:
                            conn.close()

            if st.session_state.get('show_label') and 'last_sack' in st.session_state:
                ls = st.session_state['last_sack']
                qr_code = generate_qr_base64(ls['id'])
                label_html = f"""
                <div id="print-area" style="width: 60%; padding: 30px; border: 10px solid black; font-family: Arial, sans-serif; background: white; color: black; margin: auto; text-align: center;">
                    <div style="font-size: 60px; font-weight: 900; border-bottom: 6px solid black;">{ls['prod']}</div>
                    <div style="padding: 20px 0;"><img src="data:image/png;base64,{qr_code}" style="width: 320px;"><br><div style="font-size: 40px; font-weight: bold;">{ls['id']}</div></div>
                    <div style="font-size: 32px; border-top: 6px solid black; padding-top: 15px; text-align: left; line-height: 1.4;">
                        <b>LOC:</b> {ls['loc']} | <b>WT:</b> {ls['weight']:.1f} lbs<br><b>ASH:</b> {ls['ash']:.1f}% | <b>HARD:</b> {int(ls['hard'])}<br><b>MOIST:</b> {ls['moist']:.2f}%
                    </div>
                </div><br><div style="text-align: center;">
                    <button onclick="window.print()" style="padding: 15px 30px; background: #28a745; color: white; border: none; font-size: 20px; cursor: pointer;">🖨️ PRINT LABEL</button>
                    <button onclick="window.location.reload()" style="padding: 15px 30px; background: #6c757d; color: white; border: none; font-size: 20px; cursor: pointer; margin-left:10px;">Done / Clear</button>
                </div>
                <style>@media print {{ body * {{ visibility: hidden; }} #print-area, #print-area * {{ visibility: visible; }} #print-area {{ position: absolute; left: 20%; top: 5%; width: 60%; }} }}</style>
                """
                st.components.v1.html(label_html, height=950)

        # --- 3. SHIPPING (FIFO) ---
        elif choice == "Shipping (FIFO)":
            st.title("🚢 Auto-Dispatch (FIFO)")
            ship_prod = st.selectbox("Select Product to Ship", ["Revolution CB", "Paris CB"])
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT bag_ref, location_id, timestamp FROM test_results WHERE product = ? AND status = 'Inventory' ORDER BY timestamp ASC LIMIT 1", (ship_prod,))
            oldest = c.fetchone()
            if oldest:
                st.metric("Go to Location", oldest[1])
                st.write(f"**Oldest Bag ID:** {oldest[0]} | **Produced:** {oldest[2]}")
                with st.form("ship_confirm"):
                    cust_name = st.text_input("Customer Name / Destination")
                    if st.form_submit_button(f"Confirm Shipment of {oldest[0]}"):
                        if not cust_name:
                            st.error("Please enter a customer name.")
                        else:
                            ship_ts = datetime.now().strftime("%Y-%m-%d")
                            c.execute("UPDATE test_results SET status = 'Shipped', customer_name = ?, shipped_date = ?, shipped_by = ? WHERE bag_ref = ?", 
                                      (cust_name, ship_ts, st.session_state['user_display'], oldest[0]))
                            c.execute("UPDATE locations SET status = 'Available' WHERE loc_id = ?", (oldest[1],))
                            conn.commit(); st.balloons(); st.rerun()
                conn.close()
            else:
                st.warning("No stock available."); conn.close()

        # --- 4. GRID MAP (FIXED CONTRAST ERROR) ---
        elif choice == "Stock Inquiry (Grid Map)":
            st.title("🔎 Warehouse Visual Grid")
            conn = sqlite3.connect(DB_PATH)
            loc_query = "SELECT l.loc_id, l.status, t.product FROM locations l LEFT JOIN test_results t ON l.loc_id = t.location_id AND t.status = 'Inventory' ORDER BY l.loc_id ASC"
            df = pd.read_sql_query(loc_query, conn); conn.close()
            
            # Map values and colors correctly
            df['color_val'] = df.apply(lambda r: 0 if r['status'] == 'Available' else (1 if r['product'] == 'Revolution CB' else 2), axis=1)
            df['t_color'] = df['product'].apply(lambda p: 'black' if p == 'Paris CB' else 'white')
            df['display_num'] = df['loc_id'].str.extract('(\d+)')
            
            z_data = df['color_val'].values.reshape(10, 10)
            number_labels = df['display_num'].values.reshape(10, 10)
            text_colors = df['t_color'].values.reshape(10, 10)

            fig = go.Figure(data=go.Heatmap(
                z=z_data, text=number_labels, texttemplate="<b>%{text}</b>",
                textfont={"size": 32, "family": "Arial Black", "color": text_colors.flatten().tolist()},
                colorscale=[[0, '#28a745'], [0.5, '#000000'], [1, '#ffc107']],
                showscale=False, xgap=8, ygap=8
            ))
            fig.update_layout(height=900, xaxis_visible=False, yaxis_visible=False, scaleanchor="x")
            st.plotly_chart(fig, use_container_width=True)

        # --- 5. VIEW RECORDS ---
        elif choice == "View Records":
            st.title("📊 Master Ledger")
            conn = sqlite3.connect(DB_PATH)
            st.dataframe(pd.read_sql_query("SELECT * FROM test_results ORDER BY timestamp DESC", conn), use_container_width=True)
            conn.close()

if __name__ == '__main__':
    main()
