import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import qrcode
import base64
from io import BytesIO

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────
DB_PATH = "rcb_inventory.db"

USERS = {
    "admin":    "admin1234",
    "operator": "op1234",
}

PRODUCTS = ["Revolution CB", "Paris CB"]

# ─────────────────────────────────────────────
#  QC REJECTION LIMITS  (set max/min to None to disable)
# ─────────────────────────────────────────────
QC_LIMITS = {
    "moisture":        {"max": 1.0,  "min": None, "label": "Moisture %"},
    "ash_content":     {"max": None, "min": None, "label": "Ash %"},
    "pellet_hardness": {"max": None, "min": None, "label": "Hardness"},
    "toluene":         {"max": None, "min": None, "label": "Toluene"},
}

def qc_check(moist, ash, hard, tol):
    """Returns list of failure strings. Empty = PASS."""
    failures = []
    if QC_LIMITS["moisture"]["max"] is not None and moist > QC_LIMITS["moisture"]["max"]:
        failures.append(f"Moisture {moist:.2f}% exceeds max {QC_LIMITS['moisture']['max']}%")
    if QC_LIMITS["ash_content"]["max"] is not None and ash > QC_LIMITS["ash_content"]["max"]:
        failures.append(f"Ash {ash:.2f}% exceeds max {QC_LIMITS['ash_content']['max']}%")
    if QC_LIMITS["pellet_hardness"]["min"] is not None and hard < QC_LIMITS["pellet_hardness"]["min"]:
        failures.append(f"Hardness {hard} below min {QC_LIMITS['pellet_hardness']['min']}")
    if QC_LIMITS["toluene"]["max"] is not None and tol > QC_LIMITS["toluene"]["max"]:
        failures.append(f"Toluene {tol} exceeds max {QC_LIMITS['toluene']['max']}")
    return failures

# ─────────────────────────────────────────────
#  DATABASE
# ─────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS test_results (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            bag_ref         TEXT UNIQUE,
            timestamp       DATETIME,
            operator        TEXT,
            product         TEXT,
            location_id     TEXT,
            status          TEXT DEFAULT 'Inventory',
            customer_name   TEXT DEFAULT 'In Inventory',
            shipped_date    TEXT DEFAULT 'Not Shipped',
            shipped_by      TEXT DEFAULT 'N/A',
            weight_lbs      REAL,
            pellet_hardness INTEGER,
            moisture        REAL,
            toluene         INTEGER,
            ash_content     REAL
        )
    """)

    # Self-healing columns (safe to run every time)
    extra_cols = [
        ("customer_name",   "TEXT DEFAULT 'In Inventory'"),
        ("shipped_date",    "TEXT DEFAULT 'Not Shipped'"),
        ("shipped_by",      "TEXT DEFAULT 'N/A'"),
        ("ash_content",     "REAL"),
        ("moisture",        "REAL"),
        ("toluene",         "INTEGER"),
        ("pellet_hardness", "INTEGER"),
    ]
    for col_name, col_def in extra_cols:
        try:
            c.execute(f"ALTER TABLE test_results ADD COLUMN {col_name} {col_def}")
        except sqlite3.OperationalError:
            pass

    # Bagging runs log
    c.execute("""
        CREATE TABLE IF NOT EXISTS bagging_ops (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       DATETIME,
            operator        TEXT,
            source_sack_id  TEXT,
            product         TEXT,
            bag_size_unit   TEXT,
            quantity        INTEGER,
            pallet_id       TEXT
        )
    """)

    # Individual small bags produced from a bagging run
    c.execute("""
        CREATE TABLE IF NOT EXISTS small_bags (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            bag_ref         TEXT UNIQUE,
            timestamp       DATETIME,
            operator        TEXT,
            product         TEXT,
            bag_size_unit   TEXT,
            source_sack_id  TEXT,
            pallet_id       TEXT,
            status          TEXT DEFAULT 'Inventory',
            customer_name   TEXT DEFAULT 'In Inventory',
            shipped_date    TEXT DEFAULT 'Not Shipped',
            shipped_by      TEXT DEFAULT 'N/A'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS locations (
            loc_id TEXT PRIMARY KEY,
            status TEXT DEFAULT 'Available'
        )
    """)

    c.execute("SELECT COUNT(*) FROM locations")
    if c.fetchone()[0] == 0:
        for i in range(1, 101):
            c.execute(
                "INSERT INTO locations (loc_id, status) VALUES (?, 'Available')",
                (f"WH-{i:03d}",)
            )

    conn.commit()
    conn.close()


def get_conn():
    return sqlite3.connect(DB_PATH)


def get_next_loc():
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT loc_id FROM locations WHERE status='Available' ORDER BY loc_id ASC LIMIT 1"
    )
    res = c.fetchone()
    conn.close()
    return res[0] if res else None


# ─────────────────────────────────────────────
#  QR / LABEL HELPER
# ─────────────────────────────────────────────
def generate_qr_b64(data: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def render_label(ls: dict):
    """Render label inline. If ls['rejected']=True, stamps REJECTED in red."""
    qr_b64  = generate_qr_b64(ls["id"])
    ts      = ls.get("ts", "")
    rejected = ls.get("rejected", False)
    reasons  = ls.get("reject_reasons", [])

    border_colour = "#cc0000" if rejected else "black"
    border_width  = "10px"    if rejected else "8px"

    reject_banner = ""
    if rejected:
        reasons_html = "<br>".join(reasons)
        reject_banner = f"""
        <div style="
            position:relative; margin: 10px 0;
            background:#fff0f0; border: 4px solid #cc0000;
            padding: 8px 12px; text-align:center;">
          <div style="font-size:52px; font-weight:900; color:#cc0000;
                      letter-spacing:6px; opacity:0.9; line-height:1;">
            ❌ REJECTED
          </div>
          <div style="font-size:16px; color:#880000; margin-top:4px;">
            {reasons_html}
          </div>
        </div>"""

    btn_colour  = "#cc0000" if rejected else "#28a745"
    btn_hover   = "#aa0000" if rejected else "#218838"
    status_text = "REJECTED — DO NOT SHIP" if rejected else "Revolution Carbon Black — Pyrolysis Facility"
    status_col  = "#cc0000" if rejected else "#666"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #e8e8e8; font-family: Arial, sans-serif; padding: 12px; }}
  .label {{
    width: 100%; max-width: 660px; margin: 0 auto;
    padding: 22px; border: {border_width} solid {border_colour};
    background: white; text-align: center;
  }}
  .product  {{ font-size: 44px; font-weight: 900;
               border-bottom: 5px solid {border_colour}; padding-bottom: 10px; margin-bottom: 10px; }}
  .bagid    {{ font-size: 20px; font-weight: bold; margin-top: 6px; letter-spacing: 1px; }}
  .details  {{ font-size: 19px; text-align: left; border-top: 5px solid {border_colour};
               margin-top: 14px; padding-top: 12px; line-height: 1.9; }}
  .footer   {{ margin-top: 12px; font-size: 13px; color: {status_col}; font-weight: bold; }}
  .printbtn {{
    display: block; width: 100%; margin-top: 14px; padding: 13px;
    background: {btn_colour}; color: white; border: none; font-size: 19px;
    cursor: pointer; border-radius: 6px; font-family: Arial;
  }}
  .printbtn:hover {{ background: {btn_hover}; }}
  @media print {{
    body {{ background: white; padding: 0; }}
    .printbtn {{ display: none; }}
  }}
</style>
</head>
<body>
<div class="label">
  <div class="product">{ls['prod']}</div>
  {reject_banner}
  <img src="data:image/png;base64,{qr_b64}" width="200"><br>
  <div class="bagid">{ls['id']}</div>
  <div class="details">
    <b>Location:</b> {ls['loc']}<br>
    <b>Weight:</b> {ls['weight']:.1f} lbs<br>
    <b>Ash:</b> {ls['ash']:.2f}% &nbsp;|&nbsp; <b>Hardness:</b> {int(ls['hard'])}<br>
    <b>Moisture:</b> {ls['moist']:.2f}% &nbsp;|&nbsp; <b>Toluene:</b> {ls['tol']}<br>
    <b>Operator:</b> {ls['operator']}<br>
    <b>Date/Time:</b> {ts}
  </div>
  <div class="footer">{status_text}</div>
</div>
<button class="printbtn" onclick="window.print()">🖨️ Print Label</button>
</body>
</html>"""

    st.components.v1.html(html, height=760 if rejected else 680, scrolling=False)


# ─────────────────────────────────────────────
#  BOX / PALLET LABEL
# ─────────────────────────────────────────────
def render_box_label(info: dict, copy_num: int = 1, total_copies: int = 1):
    """
    Render a single box/pallet/gaylord label.
    info keys: product, bag_size_unit, qty, total_weight_str,
               pallet_id, source_sack_id, operator, date_str, run_ref
    """
    qr_data = f"{info['run_ref']} | {info['product']} | {info['bag_size_unit']} x {info['qty']} | {info['pallet_id']}"
    qr_b64  = generate_qr_b64(qr_data)

    copy_line = f"Copy {copy_num} of {total_copies}" if total_copies > 1 else ""

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:#d8d8d8; font-family:Arial,sans-serif; padding:14px; }}
  .label {{
    width:100%; max-width:620px; margin:0 auto; padding:26px;
    border:10px solid black; background:white; text-align:center;
  }}
  .product {{
    font-size:54px; font-weight:900; letter-spacing:2px;
    border-bottom:6px solid black; padding-bottom:12px; margin-bottom:14px;
    text-transform:uppercase;
  }}
  .big-row {{
    display:flex; justify-content:space-around; margin:10px 0 14px 0;
  }}
  .big-cell {{
    text-align:center;
  }}
  .big-label {{ font-size:15px; color:#555; text-transform:uppercase; letter-spacing:1px; }}
  .big-value {{ font-size:38px; font-weight:900; line-height:1.1; }}
  .qr-section {{ margin:10px 0; }}
  .run-ref {{ font-size:15px; color:#444; margin-top:4px; letter-spacing:1px; }}
  .divider {{ border-top:5px solid black; margin:14px 0; }}
  .details {{
    font-size:20px; text-align:left; line-height:2.0;
  }}
  .footer {{
    margin-top:14px; font-size:13px; color:#666; border-top:2px solid #ccc; padding-top:8px;
    display:flex; justify-content:space-between;
  }}
  .printbtn {{
    display:block; width:100%; margin-top:14px; padding:13px;
    background:#1a6fba; color:white; border:none; font-size:19px;
    cursor:pointer; border-radius:6px; font-family:Arial;
  }}
  .printbtn:hover {{ background:#155a96; }}
  @media print {{
    body {{ background:white; padding:0; }}
    .printbtn {{ display:none; }}
    .label {{ page-break-inside:avoid; }}
  }}
</style>
</head>
<body>
<div class="label">
  <div class="product">{info["product"]}</div>

  <div class="big-row">
    <div class="big-cell">
      <div class="big-label">Bag Size</div>
      <div class="big-value">{info["bag_size_unit"]}</div>
    </div>
    <div class="big-cell">
      <div class="big-label">No. of Bags</div>
      <div class="big-value">{info["qty"]}</div>
    </div>
    <div class="big-cell">
      <div class="big-label">Total Weight</div>
      <div class="big-value">{info["total_weight_str"]}</div>
    </div>
  </div>

  <div class="qr-section">
    <img src="data:image/png;base64,{qr_b64}" width="180"><br>
    <div class="run-ref">{info["run_ref"]}</div>
  </div>

  <div class="divider"></div>

  <div class="details">
    <b>Pallet / Box ID:</b> {info["pallet_id"]}<br>
    <b>Source Sack:</b> {info["source_sack_id"]}<br>
    <b>Date:</b> {info["date_str"]}&nbsp;&nbsp;&nbsp;<b>Operator:</b> {info["operator"]}
  </div>

  <div class="footer">
    <span>Revolution Carbon Black — Pyrolysis Facility</span>
    <span>{copy_line}</span>
  </div>
</div>
<button class="printbtn" onclick="window.print()">🖨️ Print This Label</button>
</body>
</html>"""
    st.components.v1.html(html, height=720, scrolling=False)


# ─────────────────────────────────────────────
#  BAGGING SECTION
# ─────────────────────────────────────────────
def page_bagging():
    st.title("🛍️ Bagging Operations")
    st.write("Assign a supersack from inventory to a bagging run and print the box/pallet label.")

    # ── Load available supersacks ──
    conn = get_conn()
    sacks_df = pd.read_sql_query(
        """SELECT bag_ref, product, location_id, weight_lbs
           FROM test_results
           WHERE status = 'Inventory'
           ORDER BY timestamp ASC""",
        conn
    )
    conn.close()

    if sacks_df.empty:
        st.warning("No supersacks currently in inventory to process.")
        return

    sack_options = {
        f"{r.bag_ref}  —  {r.product}  @  {r.location_id}  ({r.weight_lbs:.0f} lbs)": r.bag_ref
        for r in sacks_df.itertuples()
    }
    selected_label   = st.selectbox("Select Supersack to Process", list(sack_options.keys()))
    selected_sack_id = sack_options[selected_label]

    st.markdown("---")

    with st.form("bagging_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            bag_size = st.selectbox("Bag Size", ["20kg", "25kg", "50lb", "1000lb", "Other"])
            qty      = st.number_input("Number of bags filled", min_value=1, step=1, value=1)
        with c2:
            pallet      = st.text_input("Pallet / Gaylord Box ID", placeholder="e.g. PAL-001")
            label_copies = st.number_input("Number of label copies to print", min_value=1, max_value=10, step=1, value=1)

        submitted = st.form_submit_button("✅ Complete Bagging Run & Print Label", use_container_width=True)

    if submitted:
        if not pallet.strip():
            st.error("Pallet / Box ID is required.")
            return

        now      = datetime.now()
        operator = st.session_state["user_display"]
        run_ref  = f"BAG-{now.strftime('%Y%m%d-%H%M%S')}"

        # Calculate total weight
        size_to_kg = {"20kg": 20, "25kg": 25, "50lb": 22.68, "1000lb": 453.6}
        if bag_size in size_to_kg:
            total_kg  = size_to_kg[bag_size] * int(qty)
            total_lbs = total_kg * 2.20462
            total_weight_str = f"{total_kg:.0f} kg / {total_lbs:.0f} lbs"
        else:
            total_weight_str = "— see operator"

        # Fetch supersack details
        conn = get_conn()
        c    = conn.cursor()
        c.execute("SELECT product, location_id FROM test_results WHERE bag_ref=?", (selected_sack_id,))
        row  = c.fetchone()
        if not row:
            st.error("Supersack not found — it may have already been processed.")
            conn.close()
            return
        product, loc_to_free = row

        # 1. Log the bagging run (one row, no individual bag records needed)
        c.execute(
            """INSERT INTO bagging_ops
               (timestamp, operator, source_sack_id, product, bag_size_unit, quantity, pallet_id)
               VALUES (?,?,?,?,?,?,?)""",
            (now, operator, selected_sack_id, product, bag_size, int(qty), pallet.strip())
        )

        # 2. Mark supersack consumed and free warehouse slot
        c.execute("UPDATE test_results SET status='Consumed (Bagged)' WHERE bag_ref=?", (selected_sack_id,))
        c.execute("UPDATE locations SET status='Available' WHERE loc_id=?", (loc_to_free,))
        conn.commit()
        conn.close()

        st.success(
            f"✅ Bagging run **{run_ref}** recorded. "
            f"Supersack **{selected_sack_id}** consumed. "
            f"Location **{loc_to_free}** is now free."
        )

        # 3. Store label info in session state for rendering
        st.session_state["box_label"] = {
            "run_ref":          run_ref,
            "product":          product,
            "bag_size_unit":    bag_size,
            "qty":              int(qty),
            "total_weight_str": total_weight_str,
            "pallet_id":        pallet.strip(),
            "source_sack_id":   selected_sack_id,
            "operator":         operator,
            "date_str":         now.strftime("%Y-%m-%d"),
            "label_copies":     int(label_copies),
        }

    # ── Label printing area ──
    if "box_label" in st.session_state:
        info    = st.session_state["box_label"]
        copies  = info["label_copies"]
        st.markdown("---")
        st.subheader(f"🏷️ Box Label — {info['product']}  |  {info['pallet_id']}")

        if copies > 1:
            st.info(f"Showing {copies} label copies — print each one individually or use Ctrl+P / Cmd+P on the page.")

        for i in range(1, copies + 1):
            if copies > 1:
                st.caption(f"Copy {i} of {copies}")
            render_box_label(info, copy_num=i, total_copies=copies)
            if i < copies:
                st.markdown("---")

        if st.button("🗑️ Clear Label", use_container_width=True):
            del st.session_state["box_label"]
            st.rerun()


# ─────────────────────────────────────────────
#  LOGIN PAGE
# ─────────────────────────────────────────────

def login_page():
    st.title("🔒 RCB Inventory – Login")
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Login", use_container_width=True):
            uname = username.strip().lower()
            if uname in USERS and USERS[uname] == password.strip().lower():
                st.session_state["logged_in"]    = True
                st.session_state["user_display"] = uname.capitalize()
                st.session_state["role"]         = "admin" if uname == "admin" else "operator"
                st.rerun()
            else:
                st.error("Invalid username or password.")

    st.caption("Default credentials — admin / admin1234 · operator / op1234")


# ─────────────────────────────────────────────
#  PRODUCTION DASHBOARD
# ─────────────────────────────────────────────
def page_dashboard():
    st.title("📊 Production Dashboard")

    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM test_results", conn)
    conn.close()

    if df.empty:
        st.info("No production records yet.")
        return

    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # ── Top KPIs ──
    inv      = df[df["status"] == "Inventory"]
    ship     = df[df["status"] == "Shipped"]
    rejected = df[df["status"] == "Rejected"]

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Bags Produced",       len(df))
    k2.metric("Currently in Inventory",    len(inv))
    k3.metric("Total Shipped",             len(ship))
    k4.metric("Total Weight in Stock (lbs)", f"{inv['weight_lbs'].sum():,.0f}")
    k5.metric("🚫 Rejected Bags",          len(rejected))

    st.markdown("---")

    # ── Daily Production Chart ──
    st.subheader("Daily Production (last 30 days)")
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=30)
    daily  = (
        df[df["timestamp"] >= cutoff]
        .groupby([df["timestamp"].dt.date, "product"])
        .size()
        .reset_index(name="count")
        .rename(columns={"timestamp": "Date"})
    )
    if not daily.empty:
        pivot = daily.pivot(index="Date", columns="product", values="count").fillna(0)
        st.bar_chart(pivot)
    else:
        st.info("No production in the last 30 days.")

    # ── Product split ──
    st.subheader("Inventory by Product")
    c1, c2 = st.columns(2)
    for prod, col in zip(PRODUCTS, [c1, c2]):
        subset = inv[inv["product"] == prod]
        col.metric(prod, f"{len(subset)} bags / {subset['weight_lbs'].sum():,.0f} lbs")

    # ── Quality averages (inventory) ──
    st.subheader("Average Quality — Current Inventory")
    if not inv.empty:
        qa = inv[["pellet_hardness", "moisture", "toluene", "ash_content"]].mean()
        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Avg Hardness",  f"{qa['pellet_hardness']:.1f}")
        q2.metric("Avg Moisture %", f"{qa['moisture']:.2f}")
        q3.metric("Avg Toluene",    f"{qa['toluene']:.0f}")
        q4.metric("Avg Ash %",      f"{qa['ash_content']:.2f}")

    # ── Small bags summary ──
    st.markdown("---")
    st.subheader("Small Bags Inventory")
    conn2 = get_conn()
    sb_df = pd.read_sql_query("SELECT * FROM small_bags", conn2)
    conn2.close()
    if sb_df.empty:
        st.info("No small bags in system yet.")
    else:
        sb_inv  = sb_df[sb_df["status"] == "Inventory"]
        sb_ship = sb_df[sb_df["status"] == "Shipped"]
        s1, s2, s3 = st.columns(3)
        s1.metric("Small Bags in Stock",   len(sb_inv))
        s2.metric("Small Bags Shipped",    len(sb_ship))
        s3.metric("Total Small Bags Made", len(sb_df))

    # ── Recent activity ──
    st.markdown("---")
    st.subheader("Recent Activity (last 10 records)")
    recent = df.sort_values("timestamp", ascending=False).head(10)[
        ["timestamp", "bag_ref", "product", "location_id", "status", "weight_lbs", "customer_name"]
    ]
    st.dataframe(recent, use_container_width=True)


# ─────────────────────────────────────────────
#  PRODUCTION / INVENTORY
# ─────────────────────────────────────────────
def page_production():
    st.title("🏗️ Bulk Production — Record New Bag")

    loc = get_next_loc()
    if not loc:
        st.error("🚨 Warehouse Full — no available locations!")
        return

    with st.form("prod_form", clear_on_submit=True):
        st.info(f"📍 Auto-Assigned Location: **{loc}**")

        prod = st.selectbox("Product", PRODUCTS)
        c1, c2 = st.columns(2)
        with c1:
            weight = st.number_input("Weight (lbs)", min_value=0.0, value=2000.0, step=10.0)
            hard   = st.number_input("Pellet Hardness", min_value=0, value=0, step=1)
            moist  = st.number_input("Moisture %  ⚠️ max 1.0%", min_value=0.0, value=0.0, format="%.2f")
        with c2:
            tol = st.number_input("Toluene", min_value=0, value=0, step=1)
            ash = st.number_input("Ash %",   min_value=0.0, value=0.0, format="%.2f")

        submitted = st.form_submit_button("✅ Record & Print Label", use_container_width=True)

    if submitted:
        failures = qc_check(moist, ash, hard, tol)
        is_rejected = len(failures) > 0
        now = datetime.now()
        bid = f"RCB-{now.strftime('%Y%m%d-%H%M%S')}"

        # Rejected bags are recorded but NOT assigned a warehouse slot
        bag_status = "Rejected" if is_rejected else "Inventory"
        bag_loc    = "REJECTED"  if is_rejected else loc

        conn = get_conn()
        c = conn.cursor()
        try:
            c.execute(
                """INSERT INTO test_results
                   (bag_ref,timestamp,operator,product,location_id,status,
                    weight_lbs,pellet_hardness,moisture,toluene,ash_content)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (bid, now, st.session_state["user_display"],
                 prod, bag_loc, bag_status, weight, hard, moist, tol, ash),
            )
            if not is_rejected:
                c.execute("UPDATE locations SET status='Occupied' WHERE loc_id=?", (loc,))
            conn.commit()
        except sqlite3.IntegrityError:
            st.error("Duplicate bag ID — please try again.")
            conn.close()
            return
        conn.close()

        if is_rejected:
            st.error(f"🚫 Bag **{bid}** REJECTED — " + " | ".join(failures))
        else:
            st.success(f"✅ Bag **{bid}** recorded at location **{loc}**")

        st.session_state["last_sack"] = {
            "id":             bid,
            "prod":           prod,
            "loc":            bag_loc,
            "weight":         weight,
            "ash":            ash,
            "hard":           hard,
            "moist":          moist,
            "tol":            tol,
            "operator":       st.session_state["user_display"],
            "ts":             now.strftime("%Y-%m-%d %H:%M:%S"),
            "rejected":       is_rejected,
            "reject_reasons": failures,
        }

    if "last_sack" in st.session_state:
        st.markdown("---")
        st.subheader("🏷️ Label for Last Recorded Bag")
        render_label(st.session_state["last_sack"])
        if st.button("Clear Label"):
            del st.session_state["last_sack"]
            st.rerun()


# ─────────────────────────────────────────────
#  SHIPPING — FIFO
# ─────────────────────────────────────────────
def page_shipping():
    st.title("🚢 FIFO Shipping")

    prod = st.selectbox("Select Product", PRODUCTS)

    conn = get_conn()
    fifo_df = pd.read_sql_query(
        """SELECT bag_ref, location_id, timestamp, weight_lbs, ash_content,
                  pellet_hardness, moisture, toluene
           FROM test_results
           WHERE product=? AND status='Inventory'
           ORDER BY timestamp ASC""",
        conn, params=(prod,)
    )
    conn.close()

    if fifo_df.empty:
        st.warning(f"No **{prod}** bags currently in inventory.")
        return

    st.info(f"📦 **{len(fifo_df)} bags** in stock for {prod}. Oldest bag ships first.")
    oldest = fifo_df.iloc[0]
    st.metric("Next Bag to Ship", oldest["bag_ref"])
    st.metric("Location", oldest["location_id"])

    with st.expander("📋 All available bags (oldest first)", expanded=False):
        st.dataframe(fifo_df, use_container_width=True)

    st.markdown("---")
    st.subheader("Ship Bags")

    with st.form("ship_form"):
        cust     = st.text_input("Customer Name *")
        ship_by  = st.text_input("Shipped By (driver / reference) *")
        qty      = st.number_input(
            f"Number of bags to ship (max {len(fifo_df)})",
            min_value=1, max_value=len(fifo_df), value=1, step=1
        )
        note     = st.text_area("Notes (optional)")
        submit   = st.form_submit_button("🚢 Confirm Shipment", use_container_width=True)

    if submit:
        if not cust.strip():
            st.error("Customer name is required.")
            return
        if not ship_by.strip():
            st.error("'Shipped By' is required.")
            return

        bags_to_ship = fifo_df.head(int(qty))["bag_ref"].tolist()
        locs_to_free = fifo_df.head(int(qty))["location_id"].tolist()
        today_str    = str(date.today())

        conn = get_conn()
        c = conn.cursor()
        for bag, loc in zip(bags_to_ship, locs_to_free):
            c.execute(
                """UPDATE test_results
                   SET status='Shipped', customer_name=?, shipped_date=?, shipped_by=?
                   WHERE bag_ref=?""",
                (cust.strip(), today_str, ship_by.strip(), bag),
            )
            c.execute("UPDATE locations SET status='Available' WHERE loc_id=?", (loc,))
        conn.commit()
        conn.close()

        st.success(f"✅ Shipped **{qty} bag(s)** to **{cust}**")
        st.balloons()
        if note.strip():
            st.info(f"Note saved: {note}")


# ─────────────────────────────────────────────
#  LOCATION DIRECTORY
# ─────────────────────────────────────────────
def page_locations():
    st.title("📂 Warehouse Location Directory")

    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT l.loc_id   AS 'Location',
                  l.status   AS 'Status',
                  t.product  AS 'Product',
                  t.bag_ref  AS 'Bag ID',
                  t.weight_lbs AS 'Weight (lbs)',
                  t.ash_content AS 'Ash %',
                  t.timestamp AS 'Recorded'
           FROM locations l
           LEFT JOIN test_results t
             ON l.loc_id = t.location_id AND t.status = 'Inventory'
           ORDER BY l.loc_id ASC""",
        conn,
    )
    conn.close()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Slots",       len(df))
    c2.metric("Available",         len(df[df["Status"] == "Available"]))
    c3.metric("Revolution CB",     len(df[df["Product"] == "Revolution CB"]))
    c4.metric("Paris CB",          len(df[df["Product"] == "Paris CB"]))

    # Filter
    filt = st.selectbox("Filter by Status", ["All", "Available", "Occupied"])
    view = df if filt == "All" else df[df["Status"] == filt]

    st.dataframe(view, use_container_width=True, height=600)


# ─────────────────────────────────────────────
#  VIEW / EXPORT RECORDS
# ─────────────────────────────────────────────
def page_records():
    st.title("📋 Master Records")

    tab1, tab2, tab3 = st.tabs(["📦 Supersacks", "🛍️ Small Bags", "🗂️ Bagging Runs"])

    # ── Tab 1: Supersacks ──
    with tab1:
        conn = get_conn()
        df = pd.read_sql_query("SELECT * FROM test_results ORDER BY timestamp DESC", conn)
        conn.close()

        if df.empty:
            st.info("No supersack records yet.")
        else:
            with st.expander("🔎 Filter", expanded=True):
                f1, f2, f3 = st.columns(3)
                with f1:
                    prod_f = st.selectbox("Product", ["All"] + PRODUCTS, key="rec_prod")
                with f2:
                    stat_f = st.selectbox("Status", ["All", "Inventory", "Shipped", "Rejected", "Consumed (Bagged)"], key="rec_stat")
                with f3:
                    date_from = st.date_input("From", value=date(2020, 1, 1), key="rec_from")
                    date_to   = st.date_input("To",   value=date.today(),     key="rec_to")

            df["timestamp"] = pd.to_datetime(df["timestamp"])
            mask = (df["timestamp"].dt.date >= date_from) & (df["timestamp"].dt.date <= date_to)
            if prod_f != "All": mask &= df["product"] == prod_f
            if stat_f != "All": mask &= df["status"]  == stat_f
            filtered = df[mask]

            st.markdown(f"**{len(filtered)} records** match your filters.")
            st.dataframe(filtered, use_container_width=True, height=450)
            csv = filtered.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Download Supersacks CSV", data=csv,
                               file_name=f"supersacks_{date.today()}.csv", mime="text/csv")

    # ── Tab 2: Small Bags ──
    with tab2:
        conn = get_conn()
        sb_df = pd.read_sql_query("SELECT * FROM small_bags ORDER BY timestamp DESC", conn)
        conn.close()

        if sb_df.empty:
            st.info("No small bag records yet.")
        else:
            with st.expander("🔎 Filter", expanded=True):
                sf1, sf2, sf3 = st.columns(3)
                with sf1:
                    sb_prod = st.selectbox("Product", ["All"] + PRODUCTS, key="sb_prod")
                with sf2:
                    sb_stat = st.selectbox("Status", ["All", "Inventory", "Shipped"], key="sb_stat")
                with sf3:
                    sb_size = st.selectbox("Bag Size", ["All", "20kg", "25kg", "50lb", "1000lb", "Other"], key="sb_size")

            sb_mask = pd.Series([True] * len(sb_df))
            if sb_prod != "All": sb_mask &= sb_df["product"]       == sb_prod
            if sb_stat != "All": sb_mask &= sb_df["status"]        == sb_stat
            if sb_size != "All": sb_mask &= sb_df["bag_size_unit"] == sb_size
            sb_filtered = sb_df[sb_mask]

            st.markdown(f"**{len(sb_filtered)} small bags** match your filters.")
            st.dataframe(sb_filtered, use_container_width=True, height=450)
            csv2 = sb_filtered.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Download Small Bags CSV", data=csv2,
                               file_name=f"small_bags_{date.today()}.csv", mime="text/csv")

    # ── Tab 3: Bagging Runs ──
    with tab3:
        conn = get_conn()
        br_df = pd.read_sql_query("SELECT * FROM bagging_ops ORDER BY timestamp DESC", conn)
        conn.close()

        if br_df.empty:
            st.info("No bagging runs recorded yet.")
        else:
            st.markdown(f"**{len(br_df)} bagging run(s)** on record.")
            st.dataframe(br_df, use_container_width=True, height=450)
            csv3 = br_df.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Download Bagging Runs CSV", data=csv3,
                               file_name=f"bagging_runs_{date.today()}.csv", mime="text/csv")


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    st.set_page_config(page_title="RCB Inventory", page_icon="⚫", layout="wide")
    init_db()

    if not st.session_state.get("logged_in"):
        login_page()
        return

    # ── Sidebar ──
    with st.sidebar:
        st.title("⚫ RCB Inventory")
        st.caption(f"Logged in as: **{st.session_state['user_display']}**")
        st.markdown("---")

        menu = [
            "📊 Dashboard",
            "🏗️ Production",
            "🛍️ Bagging",
            "🚢 Shipping (FIFO)",
            "📂 Location Directory",
            "📋 View / Export Records",
        ]
        choice = st.radio("Navigate", menu, label_visibility="collapsed")

        st.markdown("---")
        if st.button("🔒 Logout", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # ── Page Router ──
    if "Dashboard"   in choice: page_dashboard()
    elif "Production" in choice: page_production()
    elif "Bagging"    in choice: page_bagging()
    elif "Shipping"   in choice: page_shipping()
    elif "Location"   in choice: page_locations()
    elif "Records"    in choice: page_records()


if __name__ == "__main__":
    main()

