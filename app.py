import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import hashlib

# --- PATH CONFIGURATION ---
DB_PATH = "rcb_inventory_v5.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Main Data Table
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
                    particle_size REAL,
                    pellet_hardness REAL,
                    moisture REAL,
                    toluene REAL,
                    ash_content REAL,
                    weight REAL)''')
    # Users Table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY, 
                    password TEXT,
                    full_name TEXT)''')
    
    # Pre-populate with a few staff members if table is empty
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        users = [
            ('admin', make_hashes('admin123'), 'System Admin'),
            ('staff1', make_hashes('barc2026'), 'Production Lead'),
            ('staff2', make_hashes('ship2026'), 'Logistics Manager')
        ]
        c.executemany("INSERT INTO users VALUES (?, ?, ?)", users)
        
    conn.commit()
    conn.close()

def add_inventory_entry(bag_ref, operator, product, p_size, hardness, moisture, toluene, ash, weight):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''INSERT INTO test_results 
                 (bag_ref, timestamp, operator, product, particle_size, pellet_hardness, moisture, toluene, ash_content, weight)
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

def make_hashes(password): return hashlib.sha256(str.encode(password)).hexdigest()

def check_login(username, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT full_name FROM users WHERE username = ? AND password = ?", (username, make_hashes(password)))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def generate_bag_ref():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM test_results")
        count = c.fetchone()[0]
        conn.close()
        return f"RCB-{datetime.now().year}-{(count + 1):04d}"
    except: return f"RCB-{datetime.now().year}-0001"

def main():
    st.set_page_config(page_title="BARC - Multi-User Portal", layout="wide")
    init_db()

    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

    if not st.session_state['logged_in']:
        st.title("🔒 BARC Security Login")
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
        st.sidebar.success(f"User: {st.session_state['user_display']}")
        menu = ["Production (Inventory)", "Shipping (Assign Customer)", "View Master Records"]
        choice = st.sidebar.selectbox("Navigation", menu)
        
        if st.sidebar.button("Logout"):
            st.session_state['logged_in'] = False
            st.rerun()

        # --- PRODUCTION SECTION ---
        if choice == "Production (Inventory)":
            st.title("🏗️ Production Entry")
            bag_id = generate_bag_ref()
            with st.form("prod_form"):
                st.info(f"Operator: {st.session_state['user_display']}")
                product = st.selectbox("Product", ["Revolution CB", "Paris CB"]) # cite: Interests & Preferences
                # ... [Internal form inputs remain the same as previous v4] ...
                p_size = st.number_input("Particle Size", format="%.4f")
                hardness = st.number_input("Hardness", format="%.2f")
                moisture = st.number_input("Moisture %", format="%.2f")
                toluene = st.number_input("Toluene", format="%.2f")
                ash = st.number_input("Ash %", format="%.2f")
                weight = st.number_input("Weight (kg)", value=25.0)
                
                if st.form_submit_button("Add to Inventory"):
                    add_inventory_entry(bag_id, st.session_state['user_display'], product, p_size, hardness, moisture, toluene, ash, weight)
                    st.success(f"Bag {bag_id} added by {st.session_state['user_display']}")

        # --- SHIPPING SECTION ---
        elif choice == "Shipping (Assign Customer)":
            st.title("🚢 Shipping & Dispatch")
            conn = sqlite3.connect(DB_PATH)
            inventory_df = pd.read_sql_query("SELECT bag_ref FROM test_results WHERE status = 'Inventory'", conn)
            conn.close()

            if inventory_df.empty:
                st.warning("No bags in inventory.")
            else:
                with st.form("ship_form"):
                    selected_bag = st.selectbox("Select Bag ID", inventory_df['bag_ref'])
                    customer = st.text_input("Customer Name")
                    if st.form_submit_button("Confirm Shipment"):
                        if customer:
                            ship_bag(selected_bag, customer, st.session_state['user_display'])
                            st.success(f"Bag {selected_bag} shipped by {st.session_state['user_display']}")
                        else:
                            st.error("Enter customer name.")

        # --- VIEW RECORDS ---
        elif choice == "View Master Records":
            st.title("📊 BARC Master Ledger")
            conn = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query("SELECT * FROM test_results ORDER BY timestamp DESC", conn)
            st.dataframe(df, use_container_width=True)
            conn.close()

if __name__ == '__main__':
    main()
