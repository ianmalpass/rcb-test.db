import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import hashlib
import shutil  # NEW: For file copying
import os      # NEW: For directory management

# --- PATH CONFIGURATION ---
DB_PATH = "rcb_inventory_v10.db"
BACKUP_DIR = "backups"

def init_db():
    # Ensure backup directory exists
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        
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
                    particle_size INTEGER,
                    pellet_hardness INTEGER,
                    moisture REAL,
                    toluene INTEGER,
                    ash_content REAL,
                    weight_lbs REAL)''')
    
    # Users Table
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

# --- BACKUP HELPER ---
def create_backup():
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"inventory_backup_{timestamp}.db"
        backup_path = os.path.join(BACKUP_DIR, backup_file)
        shutil.copy2(DB_PATH, backup_path)
        return backup_path
    except Exception as e:
        return str(e)

# ... [add_inventory_entry, ship_bag, generate_bag_ref, check_login remain the same] ...

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
    st.set_page_config(page_title="BARC - Portal", layout="wide")
    init_db()

    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

    if not st.session_state['logged_in']:
        st.title("🔒 BARC Portal Login")
        u = st.text_input("Username")
        p = st.text_input("Password", type='password')
        if st.button("Login"):
            full_name = check_login(u, p)
            if full_name:
                st.session_state['logged_in'] = True
                st.session_state['user_display'] = full_name
                st.session_state['username'] = u
                st.rerun()
            else: st.error("Invalid credentials.")
    else:
        st.sidebar.title("Navigation")
        st.sidebar.write(f"User: **{st.session_state['user_display']}**")
        
        menu = ["Production (Inventory)", "Shipping (Dispatch)", "Stock Inquiry", "Shipping Report", "View Records"]
        if st.session_state['username'] == 'admin':
            menu.append("User Management")
            
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
                product = st.selectbox("Product", ["Revolution CB", "Paris CB"])
                col1, col2 = st.columns(2)
                with col1:
                    p_size = st.number_input("Particle Size (Integer)", min_value=0, max_value=99, step=1)
                    hardness = st.number_input("Hardness (Integer)", min_value=0, max_value=99, step=1)
                    weight = st.number_input("Weight (lbs)", min_value=0.0, value=55.0)
                with col2:
                    moisture = st.number_input("Moisture %", format="%.2f")
                    toluene = st.number_input("Toluene (Integer)", min_value=0, max_value=99, step=1)
                    ash = st.number_input("Ash Content % (1-decimal)", format="%.1f")
                
                if st.form_submit_button("Record Entry"):
                    add_inventory_entry(bag_id, st.session_state['user_display'], product, p_size, hardness, moisture, toluene, ash, weight)
                    st.session_state['last_bag'] = {
                        "id": bag_id, "prod": product, "weight": weight, "p_size": p_size,
                        "hardness": hardness, "toluene": toluene, "ash": ash, "moist": moisture,
                        "op": st.session_state['user_display'], "time": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }
                    st.success(f"{bag_id} added.")

            if 'last_bag' in st.session_state and st.session_state['last_bag']['id'] == bag_id:
                lb = st.session_state['last_bag']
                st.divider()
                label_html = f"""
                <div id="label" style="width:300px; padding:15px; border:3px solid black; font-family:Arial; line-height:1.4; background:white; color:black;">
                    <div style="font-size:22px; font-weight:bold; text-align:center; border-bottom:2px solid black; margin-bottom:10px;">{lb['prod']}</div>
                    <div style="font-size:16px; text-align:center; margin-bottom:10px;"><strong>BAG ID: {lb['id']}</strong></div>
                    <div style="font-size:14px; border-top:1px solid #000; padding-top:5px;">
                        <strong>Weight:</strong> {lb['weight']:.1f} lbs<br>
                        <strong>P-Size:</strong> {int(lb['p_size'])} | <strong>Hardness:</strong> {int(lb['hardness'])}<br>
                        <strong>Toluene:</strong> {int(lb['toluene'])} | <strong>Ash:</strong> {lb['ash']:.1f}%<br>
                        <strong>Moisture:</strong> {lb['moist']:.2f}%
                    </div>
                    <div style="font-size:10px; margin-top:10px; color:gray;">Operator: {lb['op']} | {lb['time']}</div>
                </div>
                <br><button onclick="window.print()" style="padding:10px; background:#28a745; color:white; border:none; border-radius:4px; width:300px; cursor:pointer; font-weight:bold;">🖨️ Print Label</button>
                <style>@media print {{ body * {{ visibility: hidden; }} #label, #label * {{ visibility: visible; }} #label {{ position: absolute; left: 0; top: 0; }} }}</style>
                """
                st.components.v1.html(label_html, height=400)

        # --- SHIPPING SECTION ---
        elif choice == "Shipping (Dispatch)":
            st.title("🚢 Assign Customer & Ship")
            conn = sqlite3.connect(DB_PATH)
            inv_df = pd.read_sql_query("SELECT bag_ref FROM test_results WHERE status = 'Inventory'", conn)
            if inv_df.empty: st.warning("Inventory empty.")
            else:
                with st.form("ship_form"):
                    sel = st.selectbox("Select Bag", inv_df['bag_ref'])
                    cust = st.text_input("Customer Name")
                    if st.form_submit_button("Ship Bag"):
                        if cust:
                            ship_bag(sel, cust, st.session_state['user_display'])
                            st.success(f"Bag {sel} shipped.")
                            st.rerun()
                        else: st.error("Enter customer name.")
            conn.close()

        # --- STOCK INQUIRY SECTION ---
        elif choice == "Stock Inquiry":
            st.title("🔎 Current Inventory Query")
            conn = sqlite3.connect(DB_PATH)
            inv_df = pd.read_sql_query("SELECT product, weight_lbs, bag_ref, timestamp FROM test_results WHERE status = 'Inventory'", conn)
            conn.close()
            if inv_df.empty: st.info("No stock in inventory.")
            else:
                c1, c2 = st.columns(2)
                for i, prod in enumerate(["Revolution CB", "Paris CB"]):
                    p_data = inv_df[inv_df['product'] == prod]
                    col = c1 if i == 0 else c2
                    col.metric(f"Total {prod}", f"{len(p_data)} Bags", f"{p_data['weight_lbs'].sum():,.1f} lbs")
                st.subheader("Inventory Details")
                st.dataframe(inv_df, use_container_width=True)

        # --- SHIPPING REPORT SECTION ---
        elif choice == "Shipping Report":
            st.title("📦 Outbound Shipping Report")
            c1, c2 = st.columns(2)
            s_date = c1.date_input("Start Date", value=date(2026, 1, 1))
            e_date = c2.date_input("End Date", value=date.today())
            conn = sqlite3.connect(DB_PATH)
            q = "SELECT customer_name, shipped_date, product, weight_lbs, bag_ref FROM test_results WHERE status = 'Shipped' AND shipped_date BETWEEN ? AND ?"
            report_df = pd.read_sql_query(q, conn, params=(str(s_date), str(e_date)))
            conn.close()
            if report_df.empty: st.info("No records found.")
            else:
                st.metric("Total Weight Shipped", f"{report_df['weight_lbs'].sum():,.1f} lbs")
                st.subheader("Summary by Customer")
                st.table(report_df.groupby('customer_name')['weight_lbs'].sum())
                st.dataframe(report_df, use_container_width=True)

        # --- VIEW RECORDS ---
        elif choice == "View Records":
            st.title("📊 Master Ledger")
            
            # Maintenance Section
            with st.expander("🛠️ Database Maintenance"):
                st.write("Create a timestamped backup of the current database.")
                if st.button("🚀 Create Manual Backup"):
                    result = create_backup()
                    if "backup" in result:
                        st.success(f"Backup created: {result}")
                    else:
                        st.error(f"Error: {result}")

            conn = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query("SELECT * FROM test_results ORDER BY timestamp DESC", conn)
            st.dataframe(df, use_container_width=True)
            
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Master CSV", data=csv, file_name=f"BARC_Master_{date.today()}.csv", mime="text/csv")
            conn.close()

        # --- USER MANAGEMENT SECTION ---
        elif choice == "User Management":
            st.title("👤 Staff User Management")
            with st.expander("Add New Staff Member"):
                with st.form("add_user"):
                    un = st.text_input("Username")
                    pw = st.text_input("Password", type='password')
                    fn = st.text_input("Full Name")
                    if st.form_submit_button("Create User"):
                        if un and pw and fn:
                            conn = sqlite3.connect(DB_PATH)
                            c = conn.cursor()
                            hpw = hashlib.sha256(str.encode(pw)).hexdigest()
                            try:
                                c.execute("INSERT INTO users VALUES (?,?,?)", (un, hpw, fn))
                                conn.commit()
                                st.success(f"User {fn} created.")
                            except: st.error("Username exists.")
                            conn.close()
            st.subheader("Current Users")
            conn = sqlite3.connect(DB_PATH)
            u_df = pd.read_sql_query("SELECT username, full_name FROM users", conn)
            st.table(u_df)
            conn.close()

if __name__ == '__main__':
    main()
