import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import hashlib

# --- PATH CONFIGURATION ---
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
        # Initial Admin User
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
    except: return f"RCB-{datetime.now().year}-0001"

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
    st.set_page_config(page_title="BARC - RCB Inventory & Quality", layout="wide")
    init_db()

    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

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
            
            # Form with clear_on_submit=True to clear inputs after save
            with st.form("prod_form", clear_on_submit=True):
                st.info(f"Assigning Bag ID: **{bag_id}**")
                product = st.selectbox("Product Selection", ["Revolution CB", "Paris CB"]) #
                
                col1, col2 = st.columns(2)
                with col1:
                    p_size = st.number_input("Particle Size (2-digit Integer)", min_value=0, max_value=99, step=1)
                    hardness = st.number_input("Pellet Hardness (2-digit Integer)", min_value=0, max_value=99, step=1)
                    weight = st.number_input("Bag Weight (lbs)", min_value=0.0, value=55.0) #
                
                with col2:
                    moisture = st.number_input("Moisture %", format="%.2f")
                    toluene = st.number_input("Toluene (2-digit Integer)", min_value=0, max_value=99, step=1)
                    ash = st.number_input("Ash Content % (1-decimal)", format="%.1f")
                
                if st.form_submit_button("Record Entry & Add to Inventory"):
                    add_inventory_entry(bag_id, st.session_state['user_display'], product, p_size, hardness, moisture, toluene, ash, weight)
                    st.success(f"Success! {bag_id} is now in Inventory.")
                    
                    # Store data for label printing
                    st.session_state['last_bag'] = {
                        "id": bag_id, "prod": product, "weight": weight, "p_size": p_size,
                        "hardness": hardness, "toluene": toluene, "ash": ash, "moist": moisture,
                        "op": st.session_state['user_display'], "time": datetime.now().strftime("%Y-%m-%d %
