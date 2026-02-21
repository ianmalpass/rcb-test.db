c.execute('''INSERT INTO test_results (bag_ref, timestamp, operator, product, particle_size, pellet_hardness, moisture, toluene, weight)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
              (bag_ref, timestamp, operator, product, p_size, hardness, moisture, toluene, weight))
    conn.commit()
    conn.close()

def generate_bag_ref():
    conn = sqlite3.connect('rcb_tests.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM test_results")
    count = c.fetchone()[0]
    conn.close()
    return f"RCB-{datetime.now().year}-{(count + 1):04d}"

# --- AUTHENTICATION LOGIC ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_login(username, password):
    # For this demo, we'll use a hardcoded admin/admin123 check
    # In production, you would query the 'users' table
    if username == "admin" and make_hashes(password) == make_hashes("admin123"):
        return True
    return False

# --- UI LAYOUT ---
def main():
    st.set_page_config(page_title="RCB Test Database", layout="wide")
    init_db()

    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    if not st.session_state['logged_in']:
        st.title("🔒 Login Required")
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
            
            # Automated Fields
            bag_id = generate_bag_ref()
            st.info(f"**Auto-Generated Bag Reference:** {bag_id}")

            with st.form("test_form"):
                col1, col2 = st.columns(2)
                with col1:
                    product = st.selectbox("Product Selection", ["Product Alpha", "Product Beta"])
                    p_size = st.number_input("Particle Size (µm)", min_value=0.0)
                    hardness = st.number_input("Pellet Hardness (N)", min_value=0.0)
                with col2:
                    moisture = st.number_input("Moisture (%)", min_value=0.0, max_value=100.0)
                    toluene = st.number_input("Toluene Content (mg/kg)", min_value=0.0)
                    weight = st.number_input("Bag Weight (kg)", min_value=0.0)
                
                if st.form_submit_button("Submit Results"):
                    add_test_entry(bag_id, st.session_state['user'], product, p_size, hardness, moisture, toluene, weight)
                    st.success(f"Successfully recorded test for {bag_id}")

        elif choice == "View Database":
            st.title("📊 Historical Test Records")
            conn = sqlite3.connect('rcb_tests.db')
            df = pd.read_sql_query("SELECT * FROM test_results ORDER BY timestamp DESC", conn)
            st.dataframe(df, use_container_width=True)
            conn.close()

if __name__ == '__main__':
    main()