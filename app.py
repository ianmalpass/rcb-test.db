import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import hashlib

# --- PATH CONFIGURATION ---
DB_PATH = "rcb_inventory_v4.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bag_ref TEXT UNIQUE,
                    timestamp DATETIME,
                    operator TEXT,
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

def ship_bag(bag_ref, customer):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    ship_date = datetime.now().strftime("%Y-%m-%d")
    c.execute('''UPDATE test_results 
                 SET customer_name = ?, shipped_date = ?, status = 'Shipped' 
                 WHERE bag_ref = ?''', (customer, ship_date, bag_ref))
    conn.commit()
    conn.close()

# ... (Helper functions generate_bag_ref, make_hashes, check_login stay the same) ...
def generate_bag_ref():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM test_results")
        count = c.fetchone()[0]
        conn.close()
        return f"RCB-{datetime.now().year}-{(count + 1):04d}"
    except: return f"RCB-{datetime.now().year}-0001"

def make_hashes(password): return hashlib.sha256(str.encode(password)).hexdigest()

def check_login(username, password):
    if username == "admin" and make_hashes(password) == make_hashes("admin123"): return True
    return False

def main():
    st.set_page_config(page_title="BARC - Inventory & Shipping", layout="wide")
    init_db()

    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

    if not st.session_state['logged_in']:
        st.title("🔒 BARC Portal Login")
        user = st.text_input("Username")
        passwd = st.text_input("Password", type='password')
        if st.button("Login"):
            if check_login(user, passwd):
                st.session_state['logged_in'] = True
                st.session_state['user'] = user
                st.rerun()
    else:
        menu = ["Production (Inventory)", "Shipping (Assign Customer)", "View Records"]
        choice = st.sidebar.selectbox("Navigation", menu)

        # --- PRODUCTION SECTION ---
        if choice == "Production (Inventory)":
            st.title("🏗️ New Production Entry")
            bag_id = generate_bag_ref()
            with st.form("prod_form"):
                st.subheader(f"Bag ID: {bag_id}")
                col1, col2 = st.columns(2)
                with col1:
                    product = st.selectbox("Product", ["Revolution CB", "Paris CB"])
                    p_size = st.number_input("Particle Size", format="%.4f")
                    hardness = st.number_input("Hardness", format="%.2f")
                with col2:
                    moisture = st.number_input("Moisture %", format="%.2f")
                    toluene = st.number_input("Toluene", format="%.2f")
                    ash = st.number_input("Ash %", format="%.2f")
                    weight = st.number_input("Weight (kg)", value=25.0)
                
                if st.form_submit_button("Add to Inventory"):
                    add_inventory_entry(bag_id, st.session_state['user'], product, p_size, hardness, moisture, toluene, ash, weight)
                    st.success(f"Bag {bag_id} added to Inventory.")

        # --- SHIPPING SECTION ---
        elif choice == "Shipping (Assign Customer)":
            st.title("🚢 Ship a Bag")
            conn = sqlite3.connect(DB_PATH)
            # Only show bags that are currently in inventory
            inventory_df = pd.read_sql_query("SELECT bag_ref FROM test_results WHERE status = 'Inventory'", conn)
            conn.close()

            if inventory_df.empty:
                st.warning("No bags currently in inventory.")
            else:
                with st.form("ship_form"):
                    selected_bag = st.selectbox("Select Bag ID from Inventory", inventory_df['bag_ref'])
                    customer = st.text_input("Customer Name")
                    st.info("Note: Shipped Date will be set to Today automatically.")
                    
                    if st.form_submit_button("Confirm Shipment"):
                        if customer:
                            ship_bag(selected_bag, customer)
                            st.success(f"Bag {selected_bag} shipped to {customer}!")
                        else:
                            st.error("Please enter a customer name.")

        # --- VIEW RECORDS ---
        elif choice == "View Records":
            st.title("📊 Master Ledger")
            conn = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query("SELECT * FROM test_results ORDER BY timestamp DESC", conn)
            st.dataframe(df, use_container_width=True)
            conn.close()

if __name__ == '__main__':
    main()



