import sqlite3
import random
from datetime import datetime, timedelta

DB_PATH = "rcb_inventory_v14.db"

def run_simulation():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 1. Clear existing data for a clean test
    c.execute("DELETE FROM test_results")
    c.execute("UPDATE locations SET status = 'Available'")
    
    products = ["Revolution CB", "Paris CB"]
    operators = ["System Test", "Auto-Bot"]
    
    print("Step 1: Creating 50 initial Supersacks...")
    # Create 25 of each product to total 50
    for i in range(50):
        prod = products[0] if i < 25 else products[1]
        # Spread timestamps over the last 5 days to test FIFO
        ts = (datetime.now() - timedelta(days=random.randint(1, 5))).strftime("%Y-%m-%d %H:%M:%S")
        bag_id = f"TEST-BAG-{i:04d}-{random.randint(100,999)}"
        loc_id = f"WH-{(i+1):03d}"
        
        c.execute('''INSERT INTO test_results 
            (bag_ref, timestamp, operator, product, location_id, weight_lbs, pellet_hardness, moisture, toluene, ash_content, status)
            VALUES (?, ?, ?, ?, ?, 2000.0, 45, 1.2, 15, 12.0, 'Inventory')''',
            (bag_id, ts, random.choice(operators), prod, loc_id))
        
        c.execute("UPDATE locations SET status = 'Occupied' WHERE loc_id = ?", (loc_id,))

    print("Step 2: Shipping 25 of each (50 total)...")
    # This leaves the warehouse empty to test the 'Available' reset
    c.execute("SELECT bag_ref, location_id FROM test_results WHERE status = 'Inventory'")
    to_ship = c.fetchall()
    for bag_ref, loc_id in to_ship:
        ship_ts = datetime.now().strftime("%Y-%m-%d")
        c.execute('''UPDATE test_results SET 
            status = 'Shipped', 
            customer_name = 'Test Customer Export', 
            shipped_date = ?, 
            shipped_by = 'Test Script' 
            WHERE bag_ref = ?''', (ship_ts, bag_ref))
        c.execute("UPDATE locations SET status = 'Available' WHERE loc_id = ?", (loc_id,))

    print("Step 3: Creating 20 new bags for Bagging Section...")
    # 10 of each to be moved to the new bagging section
    for i in range(20):
        prod = products[0] if i < 10 else products[1]
        bag_id = f"BAGGING-TEST-{i:02d}"
        loc_id = f"WH-{(i+1):03d}"
        
        c.execute('''INSERT INTO test_results 
            (bag_ref, timestamp, operator, product, location_id, weight_lbs, status)
            VALUES (?, ?, ?, ?, ?, 2000.0, 'Inventory')''',
            (bag_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Bagging-Op", prod, loc_id))
        
        c.execute("UPDATE locations SET status = 'Occupied' WHERE loc_id = ?", (loc_id,))

    conn.commit()
    conn.close()
    return "Test Simulation Successful! 50 created, 50 shipped, 20 currently in stock for bagging."

if __name__ == "__main__":
    run_simulation()
