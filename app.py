import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import hashlib
import os

# --- PATH CONFIGURATION ---
DB_PATH = rcb_tests_v2.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Added ash_content REAL to the table schema
    c.execute('''CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bag_ref TEXT UNIQUE,
                    timestamp DATETIME,
                    operator TEXT,
                    product TEXT,
                    particle_size REAL,
                    pellet_hardness REAL,
                    moisture REAL,
                    toluene REAL,
                    ash_content REAL,
                    weight REAL)''')
    conn.commit()
    conn.close()

def add_test_entry(bag_ref, operator, product, p_size, hardness, moisture, toluene, ash, weight):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''INSERT INTO test_results 
                 (bag_ref, timestamp, operator, product, particle_size, pellet_hardness, moisture, toluene, ash_content, weight)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
              (bag_ref, timestamp, operator, product, p_size, hardness, moisture, toluene, ash, weight))
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

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_login(username, password):
    # Default: admin / admin123
    if username == "admin" and make_hashes(password) == make_hashes("admin123"):
        return True
    return False

# --- UI LAYOUT ---
def main():
    st.set_page_config(page_title="BARC - RCB Quality Control", layout="wide")
    init_db()

    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    if not st.session_state['logged_in']:
        st.title("🔒 BARC QC Portal Login")
        user = st.text_input("Username")
        passwd = st.text_input("Password", type='password')
        if st.button("Login"):
            if check_login(user, passwd):
                st.session_state['logged_in'] = True
                st.session_state['user'] = user
                st.rerun()
            else:
                st.error("Invalid Username/Password")
    else:
        st.sidebar.title(f"User: {st.session_state['user']}")
        if st.sidebar.button("Logout"):
            st.session_state['logged_in'] = False
            st.rerun()

        menu = ["Add New Test", "View Database"]
        choice = st.sidebar.selectbox("Navigation", menu)

        if choice == "Add New Test":
            st.title("🧪 Record New Bag Result")
            bag_id = generate_bag_ref()
            
            with st.form("test_form", clear_on_submit=False):
                st.subheader(f"Bag Reference: {bag_id}")
                
                col1, col2 = st.columns(2)
                with col1:
                    # Updated Product Choices
                    product = st.selectbox("Product", ["Revolution CB", "Paris CB"])
                    p_size = st.number_input("Particle Size (µm)", min_value=0.0, format="%.4f")
                    hardness = st.number_input("Pellet Hardness (N)", min_value=0.0, format="%.2f")
                    weight = st.number_input("Bag Weight (kg)", min_value=0.0, value=25.0)
                
                with col2:
                    moisture = st.number_input("Moisture (%)", min_value=0.0, max_value=100.0, format="%.2f")
                    toluene = st.number_input("Toluene Content (mg/kg)", min_value=0.0, format="%.2f")
                    # New Ash Content Field
                    ash = st.number_input("Ash Content (%)", min_value=0.0, max_value=100.0, format="%.2f")
                
                submitted = st.form_submit_button("Save Test Results")
                
                if submitted:
                    add_test_entry(bag_id, st.session_state['user'], product, p_size, hardness, moisture, toluene, ash, weight)
                    st.success(f"Saved: {bag_id}")
                    st.session_state['last_bag'] = {
                        "id": bag_id, "prod": product, "weight": weight, 
                        "ash": ash, "moist": moisture, "time": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }

            # Label Printing Logic
            if 'last_bag' in st.session_state:
                st.divider()
                label_html = f"""
                <div id="label" style="width:280px; padding:15px; border:3px solid black; font-family:Arial; line-height:1.2;">
                    <div style="font-size:22px; font-weight:bold; text-align:center; border-bottom:2px solid black; margin-bottom:10px;">
                        {st.session_state['last_bag']['prod']}
                    </div>
                    <div style="font-size:18px; text-align:center; margin-bottom:10px;">
                        <strong>BAG ID: {st.session_state['last_bag']['id']}</strong>
                    </div>
                    <div style="font-size:14px;">
                        Weight: {st.session_state['last_bag']['weight']} kg<br>
                        Ash: {st.session_state['last_bag']['ash']}%<br>
                        Moisture: {st.session_state['last_bag']['moist']}%<br>
                        Date: {st.session_state['last_bag']['time']}
                    </div>
                </div>
                <br>
                <button onclick="window.print()" style="padding:10px 20px; background:#007BFF; color:white; border:none; border-radius:4px; cursor:pointer;">
                    🖨️ Print Bag Label
                </button>
                <style>
                    @media print {{
                        body * {{ visibility: hidden; }}
                        #label, #label * {{ visibility: visible; }}
                        #label {{ position: absolute; left: 0; top: 0; border: 2px solid black !important; }}
                    }}
                </style>
                """
                st.components.v1.html(label_html, height=350)

        elif choice == "View Database":
            st.title("📊 Historical Test Records")
            conn = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query("SELECT * FROM test_results ORDER BY timestamp DESC", conn)
            st.dataframe(df, use_container_width=True)
            
            # Export to CSV for Excel
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Database as CSV", data=csv, file_name="rcb_test_history.csv", mime="text/csv")
            conn.close()

if __name__ == '__main__':
    main()



