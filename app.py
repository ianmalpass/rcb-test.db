import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import hashlib

# --- PATH CONFIGURATION ---
# Using v7 to ensure a clean start with all required columns
DB_PATH = "rcb_inventory_v7.db"

def init_db():
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
        # Initial Admin User (admin / admin123)
        admin_pass = hashlib.sha256(str.encode('admin123')).hexdigest()
        c.execute("INSERT INTO users VALUES (?, ?, ?)", ('admin', admin_pass, 'System Admin'))
    conn.commit()
    conn.close()

def add_inventory_entry(bag_ref, operator, product, p_size, hardness, moisture, toluene, ash, weight):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''INSERT INTO test_results 
                 (bag_ref, timestamp, operator, product, particle_size, pellet_hardness, moisture, toluene, ash_content, weight_lbs)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
              (bag_ref, timestamp, operator, product, p_size, hardness, moisture, toluene, ash, weight))
    conn.commit()
    conn.close()

def ship_bag(bag_ref, customer, shipper_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    ship_date = datetime.now().strftime("%Y-%m-%d")
    c.execute('''UPDATE test_results 
                 SET customer_name = ?, shipped_date = ?, status = 'Shipped', shipped_by = ? 
                 WHERE bag_ref = ?''', (customer, ship_date, shipper_name, bag_ref))
    conn.commit()
    conn.close()

def generate_bag_ref():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM test_results")
        count = c.fetchone()[0]
        conn.close()
        return f"RCB-{datetime.now().year}-{(count + 1):04d}"
    except:
        return f"RCB-{datetime.now().year}-0001"

def check_login(username, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    hashed = hashlib.sha256(str.encode(password)).hexdigest()
    c.execute("SELECT full_name FROM users WHERE username = ? AND password = ?", (username, hashed))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

# --- UI LAYOUT ---
def main():
    st.set_page_config(page_title="BARC - RCB Inventory Control", layout="wide")
    init_db()

    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    if not st.session_state['logged_in']:
        st.title("🔒 BARC Portal Login")
        user_input = st.text_input("Username")
        pass_input = st.text_input("Password", type='password')
        if st.button("Login"):
            full_name = check_login(user_input, pass_input)
            if full_name:
                st.session_state['logged_in'] = True
                st.session_state['user_display'] = full_name
                st.rerun()
            else:
                st.error("Invalid credentials.")
    else:
        st.sidebar.title("Navigation")
        st.sidebar.write(f"Logged in as: **{st.session_state['user_display']}**")
        menu = ["Production (Inventory)", "Shipping (Dispatch)", "View Records"]
        choice = st.sidebar.selectbox("Go to:", menu)
        
        if st.sidebar.button("Logout"):
            st.session_state['logged_in'] = False
            st.rerun()

        # --- PRODUCTION SECTION ---
        if choice == "Production (Inventory)":
            st.title("🏗️ New Production Entry")
            bag_id = generate_bag_ref()
            
            with st.form("prod_form", clear_on_submit=True):
                st.info(f"Assigning Bag ID: **{bag_id}**")
                product = st.selectbox("Product Selection", ["Revolution CB", "Paris CB"])
                
                col1, col2 = st.columns(2)
                with col1:
                    p_size = st.number_input("Particle Size (Integer)", min_value=0, max_value=99, step=1)
                    hardness = st.number_input("Pellet Hardness (Integer)", min_value=0, max_value=99, step=1)
                    weight = st.number_input("Bag Weight (lbs)", min_value=0.0, value=55.0)
                
                with col2:
                    moisture = st.number_input("Moisture %", format="%.2f")
                    toluene = st.number_input("Toluene (Integer)", min_value=0, max_value=99, step=1)
                    ash = st.number_input("Ash Content % (1-decimal)", format="%.1f")
                
                submitted = st.form_submit_button("Record Entry & Add to Inventory")
                
                if submitted:
                    add_inventory_entry(bag_id, st.session_state['user_display'], product, p_size, hardness, moisture, toluene, ash, weight)
                    st.success(f"Success! {bag_id} is now in Inventory.")
                    
                    # Store data for label printing
                    st.session_state['last_bag'] = {
                        "id": bag_id, 
                        "prod": product, 
                        "weight": weight, 
                        "p_size": p_size,
                        "hardness": hardness, 
                        "toluene": toluene, 
                        "ash": ash, 
                        "moist": moisture,
                        "op": st.session_state['user_display'], 
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }

            # Print Label Section
            if 'last_bag' in st.session_state:
                lb = st.session_state['last_bag']
                st.divider()
                label_html = f"""
                <div id="label" style="width:300px; padding:15px; border:3px solid black; font-family:Arial; line-height:1.4; background:white; color:black;">
                    <div style="font-size:24px; font-weight:bold; text-align:center; border-bottom:2px solid black; margin-bottom:10px;">{lb['prod']}</div>
                    <div style="font-size:16px; text-align:center; margin-bottom:10px;"><strong>BAG ID: {lb['id']}</strong></div>
                    <div style="font-size:14px; border-top:1px solid #000; padding-top:5px;">
                        <strong>Weight:</strong> {lb['weight']:.1f} lbs<br>
                        <strong>P-Size:</strong> {int(lb['p_size'])} | <strong>Hardness:</strong> {int(lb['hardness'])}<br>
                        <strong>Toluene:</strong> {int(lb['toluene'])} | <strong>Ash:</strong> {lb['ash']:.1f}%<br>
                        <strong>Moisture:</strong> {lb['moist']:.2f}%
                    </div>
                    <div style="font-size:10px; margin-top:10px; color:gray;">Operator: {lb['op']} | {lb['time']}</div>
                </div>
                <br><button onclick="window.print()" style="padding:10px; background:#28a745; color:white; border:none; border-radius:4px; width:300px; cursor:pointer; font-weight:bold;">🖨️ Print Bag Label</button>
                <style>@media print {{ body * {{ visibility: hidden; }} #label, #label * {{ visibility: visible; }} #label {{ position: absolute; left: 0; top: 0; }} }}</style>
                """
                st.components.v1.html(label_html, height=400)

        # --- SHIPPING SECTION ---
        elif choice == "Shipping (Dispatch)":
            st.title("🚢 Assign Customer & Ship")
            conn = sqlite3.connect(DB_PATH)
            inv_df = pd.read_sql_query("SELECT bag_ref FROM test_results WHERE status = 'Inventory'", conn)
            conn.close()

            if inv_df.empty:
                st.warning("No bags currently in inventory.")
            else:
                with st.form("shipping_form"):
                    selected_bag = st.selectbox("Select Bag from Inventory", inv_df['bag_ref'])
                    customer = st.text_input("Customer Name")
                    if st.form_submit_button("Ship Bag"):
                        if customer:
                            ship_bag(selected_bag, customer, st.session_state['user_display'])
                            st.success(f"Bag {selected_bag} dispatched to {customer}!")
                        else:
                            st.error("Please enter a customer name.")

        # --- RECORDS SECTION ---
        elif choice == "View Records":
            st.title("📊 Master Production & Shipping Ledger")
            conn = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query("SELECT * FROM test_results ORDER BY timestamp DESC", conn)
            st.dataframe(df, use_container_width=True)
            
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Database as CSV", data=csv, file_name=f"BARC_Ledger_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")
            conn.close()

if __name__ == '__main__':
    main()
