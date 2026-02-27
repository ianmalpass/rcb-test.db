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
    c.execute('''CREATE TABLE IF NOT EXISTS locations (
                    loc_id TEXT PRIMARY KEY,
                    status TEXT DEFAULT 'Available')''')
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
            if u == "admin" or u == "operator":
                st.session_state.update({"logged_in": True, "user_display": u.capitalize()})
                st.rerun()
    else:
        st.sidebar.title("AI-sistant")
        
        # PERSISTENT REPRINT BUTTON
        if 'last_sack' in st.session_state:
            if st.sidebar.button("🖨️ Reprint Last Label"):
                st.session_state['show_label'] = True

        menu = ["Production (Inventory)", "Shipping (FIFO)", "Stock Inquiry (Grid Map)", "View Records"]
        choice = st.sidebar.selectbox("Go to:", menu)

        if choice == "Production (Inventory)":
            st.title("🏗️ Bulk Production")
            
            # 1. Fetch the absolute latest available location
            next_loc = get_next_available_location()
            
            if not next_loc:
                st.error("🚨 Warehouse Full!")
            else:
                # Use clear_on_submit to reset the fields automatically
                with st.form("prod_form", clear_on_submit=True):
                    st.info(f"📍 Location Assigned for this Bag: **{next_loc}**")
                    prod = st.selectbox("Product", ["Revolution CB", "Paris CB"])
                    c1, c2 = st.columns(2)
                    with c1:
                        weight = st.number_input("Weight (lbs)", value=2000.0)
                        hard = st.number_input("Hardness", min_value=0)
                    with c2:
                        moist = st.number_input("Moisture %", format="%.2f")
                        tol = st.number_input("Toluene", step=1)
                        ash = st.number_input("Ash %", format="%.1f")
                    
                    submit = st.form_submit_button("Record & Generate Label")
                    
                    if submit:
                        bag_id = f"RCB-{datetime.now().strftime('%Y%m%d-%H%M')}"
                        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                        c.execute("INSERT INTO test_results (bag_ref, timestamp, operator, product, location_id, weight_lbs, pellet_hardness, moisture, toluene, ash_content) VALUES (?,?,?,?,?,?,?,?,?,?)",
                                  (bag_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), st.session_state['user_display'], prod, next_loc, weight, hard, moist, tol, ash))
                        c.execute("UPDATE locations SET status = 'Occupied' WHERE loc_id = ?", (next_loc,))
                        conn.commit(); conn.close()
                        
                        # Store in session state for the label display and reprint
                        st.session_state['last_sack'] = {"id": bag_id, "prod": prod, "loc": next_loc, "weight": weight, "ash": ash, "hard": hard, "moist": moist}
                        st.session_state['show_label'] = True
                        st.success(f"Success! {bag_id} saved to {next_loc}. Form Reset.")

            # Display Label (This part stays visible until they navigate away or click a new form)
            if st.session_state.get('show_label') and 'last_sack' in st.session_state:
                ls = st.session_state['last_sack']
                qr_code = generate_qr_base64(ls['id'])
                
                label_html = f"""
                <div id="print-area" style="width: 60%; padding: 30px; border: 10px solid black; font-family: Arial, sans-serif; background: white; color: black; margin: auto; text-align: center;">
                    <div style="font-size: 60px; font-weight: 900; border-bottom: 6px solid black;">{ls['prod']}</div>
                    <div style="padding: 20px 0;">
                        <img src="data:image/png;base64,{qr_code}" style="width: 320px;">
                        <div style="font-size: 40px; font-weight: bold;">{ls['id']}</div>
                    </div>
                    <div style="font-size: 32px; border-top: 6px solid black; padding-top: 15px; text-align: left; line-height: 1.4;">
                        <b>LOCATION:</b> {ls['loc']}<br>
                        <b>WEIGHT:</b> {ls['weight']:.1f} LBS<br>
                        <b>ASH:</b> {ls['ash']:.1f}% | <b>HARDNESS:</b> {int(ls['hard'])}<br>
                        <b>MOISTURE:</b> {ls['moist']:.2f}%
                    </div>
                </div>
                <div style="text-align: center; margin-top: 30px;">
                    <button onclick="window.print()" style="padding: 15px 30px; background: #28a745; color: white; border: none; font-size: 20px; cursor: pointer; border-radius: 8px;">🖨️ PRINT SCALED LABEL</button>
                    <button onclick="window.location.reload()" style="padding: 15px 30px; background: #6c757d; color: white; border: none; font-size: 20px; cursor: pointer; border-radius: 8px; margin-left:10px;">Done / Clear Label</button>
                </div>
                <style>@media print {{ body * {{ visibility: hidden; }} #print-area, #print-area * {{ visibility: visible; }} #print-area {{ position: absolute; left: 20%; top: 5%; width: 60%; }} }}</style>
                """
                st.components.v1.html(label_html, height=950)

        # --- OTHER SECTIONS (Remain the same for FIFO and Grid) ---
        elif choice == "Shipping (FIFO)":
            st.title("🚢 Auto-Dispatch (FIFO)")
            # ... [FIFO Logic]

        elif choice == "Stock Inquiry (Grid Map)":
            st.title("🔎 Warehouse Visual Grid")
            # ... [Grid Map Logic]

if __name__ == '__main__':
    main()


