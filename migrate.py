import sqlite3
import os

OLD_DB = "rcb_inventory_v12.db"
NEW_DB = "rcb_inventory_v13.db"

def migrate():
    if not os.path.exists(OLD_DB):
        print(f"Error: {OLD_DB} not found. Ensure the file is in the same folder.")
        return

    # Connect to both databases
    conn_old = sqlite3.connect(OLD_DB)
    conn_new = sqlite3.connect(NEW_DB)
    
    cursor_old = conn_old.cursor()
    cursor_new = conn_new.cursor()

    print("Migrating Production Records...")
    # Fetch v12 records (v12 had no 'location' column)
    cursor_old.execute("SELECT bag_ref, timestamp, operator, shipped_by, product, customer_name, shipped_date, status, pellet_hardness, moisture, toluene, ash_content, weight_lbs FROM test_results")
    rows = cursor_old.fetchall()

    for row in rows:
        try:
            # Insert into v13 with a default location 'WH-1'
            cursor_new.execute('''INSERT OR IGNORE INTO test_results 
                (bag_ref, timestamp, operator, shipped_by, product, location, customer_name, shipped_date, status, pellet_hardness, moisture, toluene, ash_content, weight_lbs)
                VALUES (?, ?, ?, ?, ?, 'WH-1', ?, ?, ?, ?, ?, ?, ?, ?)''', row)
        except Exception as e:
            print(f"Skipping {row[0]}: {e}")

    print("Migrating Reactor Logs...")
    cursor_old.execute("SELECT timestamp, operator, toluene_value, feed_rate, reactor_1_temp, reactor_2_temp, reactor_1_hz, reactor_2_hz FROM process_logs")
    logs = cursor_old.fetchall()
    for log in logs:
        cursor_new.execute('''INSERT INTO process_logs 
            (timestamp, operator, toluene_value, feed_rate, reactor_1_temp, reactor_2_temp, reactor_1_hz, reactor_2_hz)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', log)

    conn_new.commit()
    conn_old.close()
    conn_new.close()
    print("Migration Complete! You can now delete migrate.py and use v13 in your app.")

if __name__ == "__main__":
    migrate()
