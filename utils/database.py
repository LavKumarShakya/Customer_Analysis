"""
utils/database.py
=================
SQLite database — three-table CRM schema.

Tables
------
  customers     : one row per customer (name, phone, auto-ID)
  transactions  : one row per purchase (many per customer)
  predictions   : one ML inference result per customer per run

Auto Customer ID format:  CUST0001, CUST0002 …
  – Applied ONLY to manually entered customers.
  – CSV-imported customers keep their source IDs (e.g. "12345").
"""

import sqlite3
import os
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "retail.db")


# ── Connection ─────────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ── Schema ─────────────────────────────────────────────────────────────────

def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS customers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT    UNIQUE NOT NULL,
            name        TEXT,
            phone       TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id       TEXT NOT NULL,
            purchase_amount   REAL,
            purchase_date     TEXT,
            product_purchased TEXT,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        );

        CREATE TABLE IF NOT EXISTS predictions (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id       TEXT NOT NULL,
            customer_category TEXT,
            retention_risk    TEXT,
            churn_probability REAL,
            prediction_time   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        );

        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()
    
    # Auto-create demo user
    create_user("testuser", "testpass")


# ── User Auth CRUD ─────────────────────────────────────────────────────────

def create_user(username: str, password: str) -> bool:
    """Create a new user. Returns True if successful, False if username exists."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), datetime.utcnow().isoformat())
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def verify_user(username: str, password: str) -> bool:
    """Verify user credentials. Returns True if valid."""
    conn = get_connection()
    row = conn.execute("SELECT password_hash FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    if row and check_password_hash(row["password_hash"], password):
        return True
    return False


def count_users() -> int:
    """Return total number of registered users."""
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return count


# ── Auto Customer ID ───────────────────────────────────────────────────────

def generate_next_customer_id() -> str:
    """Return the next CUST#### ID based on highest existing CUST ID."""
    conn = get_connection()
    row = conn.execute(
        "SELECT customer_id FROM customers WHERE customer_id LIKE 'CUST%' "
        "ORDER BY CAST(SUBSTR(customer_id,5) AS INTEGER) DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if row:
        n = int(row["customer_id"][4:]) + 1
    else:
        n = 1
    return f"CUST{n:04d}"


def customer_id_exists(customer_id: str) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM customers WHERE customer_id = ?", (customer_id,)
    ).fetchone()
    conn.close()
    return row is not None


# ── Customer CRUD ──────────────────────────────────────────────────────────

def save_customer_record(data: dict) -> None:
    """Insert a new customer (or ignore if customer_id already exists)."""
    conn = get_connection()
    conn.execute(
        """
        INSERT OR IGNORE INTO customers (customer_id, name, phone, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            str(data["customer_id"]),
            data.get("name", ""),
            data.get("phone", ""),
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_customer_by_id(customer_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM customers WHERE customer_id = ?", (customer_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_customer_stats() -> dict:
    """Return total count, first and last CUST#### ID."""
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    first = conn.execute(
        "SELECT customer_id FROM customers WHERE customer_id LIKE 'CUST%' "
        "ORDER BY CAST(SUBSTR(customer_id,5) AS INTEGER) ASC LIMIT 1"
    ).fetchone()
    last = conn.execute(
        "SELECT customer_id FROM customers WHERE customer_id LIKE 'CUST%' "
        "ORDER BY CAST(SUBSTR(customer_id,5) AS INTEGER) DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return {
        "total":   total,
        "first_id": first["customer_id"] if first else "—",
        "last_id":  last["customer_id"]  if last  else "—",
    }


def search_customers_autocomplete(q: str, limit: int = 8) -> list[dict]:
    """Search by customer_id or name for autocomplete suggestions."""
    conn = get_connection()
    like = f"%{q}%"
    rows = conn.execute(
        """
        SELECT customer_id, name, phone FROM customers
        WHERE customer_id LIKE ? OR name LIKE ?
        ORDER BY customer_id LIMIT ?
        """,
        (like, like, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Transaction CRUD ───────────────────────────────────────────────────────

def save_transaction(data: dict) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO transactions
            (customer_id, purchase_amount, purchase_date, product_purchased, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            str(data["customer_id"]),
            float(data["purchase_amount"]),
            str(data["purchase_date"]),
            data.get("product_purchased", ""),
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_customer_transactions(customer_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM transactions WHERE customer_id = ? ORDER BY purchase_date DESC",
        (customer_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def compute_customer_rfm(customer_id: str) -> dict:
    """
    Derive RFM + CLV metrics from the transactions table.

    Returns dict with:
      recency, frequency, monetary, total_revenue,
      total_quantity, unique_products, clv,
      avg_order_value, last_purchase_date
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT purchase_amount, purchase_date, product_purchased "
        "FROM transactions WHERE customer_id = ? ORDER BY purchase_date DESC",
        (customer_id,),
    ).fetchall()
    conn.close()

    if not rows:
        return {
            "recency": 365, "frequency": 1, "monetary": 0,
            "total_revenue": 0, "total_quantity": 1, "unique_products": 1,
            "clv": 0, "avg_order_value": 0, "last_purchase_date": "—",
        }

    amounts   = [r["purchase_amount"] for r in rows]
    products  = [r["product_purchased"] for r in rows if r["product_purchased"]]
    dates     = [r["purchase_date"]     for r in rows if r["purchase_date"]]

    total_spending = sum(amounts)
    frequency      = len(rows)

    # Recency
    last_date = None
    if dates:
        try:
            last_date = max(
                datetime.strptime(d, "%Y-%m-%d").date() if len(d) == 10
                else datetime.fromisoformat(d).date()
                for d in dates
            )
            recency = (date.today() - last_date).days
        except Exception:
            recency = 365
    else:
        recency = 365

    unique_prods = len(set(p for p in products if p))

    clv = round(total_spending * frequency, 2)
    avg_order = round(total_spending / frequency, 2) if frequency else 0

    return {
        "recency":          recency,
        "frequency":        frequency,
        "monetary":         round(total_spending, 2),
        "total_revenue":    round(total_spending, 2),
        "total_quantity":   frequency,
        "unique_products":  max(unique_prods, 1),
        "clv":              clv,
        "avg_order_value":  avg_order,
        "last_purchase_date": last_date.isoformat() if last_date else "—",
    }


# ── Prediction CRUD ────────────────────────────────────────────────────────

def save_prediction(data: dict) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO predictions
            (customer_id, customer_category, retention_risk, churn_probability, prediction_time)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            str(data["customer_id"]),
            data.get("customer_category", data.get("segment", "")),
            data.get("retention_risk",   data.get("churn_risk", "")),
            float(data.get("churn_probability", 0)),
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_customer_predictions(customer_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM predictions WHERE customer_id = ? ORDER BY prediction_time DESC",
        (customer_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_prediction(customer_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM predictions WHERE customer_id = ? "
        "ORDER BY prediction_time DESC LIMIT 1",
        (customer_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_predictions() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM predictions ORDER BY prediction_time DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Customer Directory ─────────────────────────────────────────────────────

def get_all_customers_with_stats(
    search: str = "",
    category: str = "",
    risk: str = "",
    sort_by: str = "total_spending",
    sort_dir: str = "desc",
    page: int = 1,
    per_page: int = 25,
) -> dict:
    """
    Return paginated customer list with aggregated transaction + prediction data.
    """
    conn = get_connection()

    # Build WHERE clause
    conditions = []
    params: list = []
    if search:
        conditions.append("(c.customer_id LIKE ? OR c.name LIKE ? OR c.phone LIKE ?)")
        like = f"%{search}%"
        params += [like, like, like]
    if category:
        conditions.append("p.customer_category = ?")
        params.append(category)
    if risk:
        conditions.append("p.retention_risk = ?")
        params.append(risk)

    where_sql = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # Allowed sort columns (whitelist to prevent injection)
    allowed_sorts = {
        "total_spending":    "total_spending",
        "order_count":       "order_count",
        "clv":               "clv",
        "customer_id":       "c.customer_id",
        "name":              "c.name",
        "last_purchase":     "last_purchase",
        "customer_category": "p.customer_category",
    }
    sort_col = allowed_sorts.get(sort_by, "total_spending")
    direction = "DESC" if sort_dir.lower() == "desc" else "ASC"

    base_query = f"""
        SELECT
            c.customer_id,
            c.name,
            c.phone,
            c.created_at,
            COALESCE(t.total_spending, 0)  AS total_spending,
            COALESCE(t.order_count, 0)     AS order_count,
            COALESCE(t.total_spending, 0) * COALESCE(t.order_count, 0) AS clv,
            COALESCE(t.avg_order, 0)       AS avg_order_value,
            t.last_purchase,
            p.customer_category,
            p.retention_risk,
            p.churn_probability,
            p.prediction_time
        FROM customers c
        LEFT JOIN (
            SELECT customer_id,
                   SUM(purchase_amount)  AS total_spending,
                   COUNT(*)              AS order_count,
                   AVG(purchase_amount)  AS avg_order,
                   MAX(purchase_date)    AS last_purchase
            FROM transactions
            GROUP BY customer_id
        ) t ON c.customer_id = t.customer_id
        LEFT JOIN (
            SELECT customer_id, customer_category, retention_risk,
                   churn_probability, prediction_time
            FROM predictions
            WHERE id IN (
                SELECT MAX(id) FROM predictions GROUP BY customer_id
            )
        ) p ON c.customer_id = p.customer_id
        {where_sql}
    """

    total = conn.execute(
        f"SELECT COUNT(*) FROM ({base_query})", params
    ).fetchone()[0]

    offset = (page - 1) * per_page
    rows = conn.execute(
        f"{base_query} ORDER BY {sort_col} {direction} LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()
    conn.close()

    return {
        "rows":       [dict(r) for r in rows],
        "total":      total,
        "page":       page,
        "per_page":   per_page,
        "total_pages":((total - 1) // per_page + 1) if total else 1,
    }


def get_top_customers(n: int = 25, sort_by: str = "total_spending") -> list[dict]:
    """Return top N customers by total_spending, order_count, or clv."""
    allowed = {"total_spending", "order_count", "clv"}
    col = sort_by if sort_by in allowed else "total_spending"

    conn = get_connection()
    rows = conn.execute(
        f"""
        SELECT
            c.customer_id, c.name,
            COALESCE(t.total_spending, 0)  AS total_spending,
            COALESCE(t.order_count, 0)     AS order_count,
            COALESCE(t.total_spending, 0) * COALESCE(t.order_count, 0) AS clv,
            COALESCE(t.avg_order, 0)       AS avg_order_value,
            t.last_purchase,
            p.customer_category,
            p.retention_risk,
            p.churn_probability
        FROM customers c
        LEFT JOIN (
            SELECT customer_id,
                   SUM(purchase_amount) AS total_spending,
                   COUNT(*)             AS order_count,
                   AVG(purchase_amount) AS avg_order,
                   MAX(purchase_date)   AS last_purchase
            FROM transactions GROUP BY customer_id
        ) t ON c.customer_id = t.customer_id
        LEFT JOIN (
            SELECT customer_id, customer_category, retention_risk, churn_probability
            FROM predictions
            WHERE id IN (SELECT MAX(id) FROM predictions GROUP BY customer_id)
        ) p ON c.customer_id = p.customer_id
        ORDER BY {col} DESC
        LIMIT ?
        """,
        (n,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Live Dashboard Stats (from DB, always up-to-date) ─────────────────────

def get_live_dashboard_stats() -> dict:
    """
    Return live KPIs sourced directly from the SQLite database.
    These values update immediately whenever a new customer or
    transaction is added — unlike the static CSV/JSON summary.

    Returns dict with:
      total_customers (int)
      total_revenue   (float)
      total_orders    (int)
      avg_order_value (float)
      latest_customer (str | None)
    """
    conn = get_connection()

    total_customers = conn.execute(
        "SELECT COUNT(*) FROM customers"
    ).fetchone()[0]

    rev_row = conn.execute(
        "SELECT COALESCE(SUM(purchase_amount), 0), COALESCE(COUNT(*), 0) FROM transactions"
    ).fetchone()
    total_revenue = round(float(rev_row[0]), 2)
    total_orders  = int(rev_row[1])
    avg_order     = round(total_revenue / total_orders, 2) if total_orders else 0

    latest_row = conn.execute(
        "SELECT customer_id FROM customers ORDER BY id DESC LIMIT 1"
    ).fetchone()
    latest_customer = latest_row["customer_id"] if latest_row else None

    conn.close()
    return {
        "total_customers":  total_customers,
        "total_revenue":    total_revenue,
        "total_orders":     total_orders,
        "avg_order_value":  avg_order,
        "latest_customer":  latest_customer,
    }


# ── Live Segment / Category Stats (from DB, always up-to-date) ────────────

_FRIENDLY_TO_ML: dict[str, str] = {
    "Best Customers":        "VIP",
    "Repeat Customers":      "Loyal",
    "Standard Customers":    "Regular",
    "Customers You May Lose":"At Risk",
}

_SEG_COLORS_DB: dict[str, str] = {
    "Best Customers":        "#10b981",
    "Repeat Customers":      "#3b82f6",
    "Standard Customers":    "#64748b",
    "Customers You May Lose":"#ef4444",
}

_SEG_ACTIONS_DB: dict[str, list] = {
    "Best Customers":        ["Send VIP loyalty rewards", "Offer early access to new products", "Request testimonials or referrals"],
    "Repeat Customers":      ["Offer a subscription or bundle deal", "Send personalised thank-you messages", "Provide exclusive member discounts"],
    "Standard Customers":    ["Send product recommendations", "Run promotional campaigns", "Invite to loyalty programme"],
    "Customers You May Lose":["Send re-engagement offers", "Follow up with a personal call", "Provide a win-back discount"],
}

_CATEGORY_ORDER = ["Best Customers", "Repeat Customers", "Standard Customers", "Customers You May Lose"]


def get_live_segment_stats() -> dict:
    """
    Derive live category breakdown and retention stats directly from SQLite.
    Uses the LATEST prediction per customer + the transactions table for
    revenue, so every new customer entry is immediately reflected in
    the dashboard, sidebar, and all other UI sections.

    Returns dict with:
      seg_breakdown    list[dict]
      rev_by_segment   list[dict]
      at_risk_count    int
      retention_rate   float
      sb_total / sb_best / sb_repeat / sb_standard / sb_losing  str
    """
    from collections import defaultdict

    conn = get_connection()

    # Latest prediction per customer
    pred_rows = conn.execute("""
        SELECT p.customer_id, p.customer_category, p.retention_risk
        FROM predictions p
        WHERE p.id IN (
            SELECT MAX(id) FROM predictions GROUP BY customer_id
        )
    """).fetchall()

    # Total revenue per customer
    rev_rows = conn.execute("""
        SELECT customer_id, COALESCE(SUM(purchase_amount), 0) AS revenue
        FROM transactions
        GROUP BY customer_id
    """).fetchall()
    conn.close()

    rev_map: dict[str, float] = {r["customer_id"]: float(r["revenue"]) for r in rev_rows}

    cat_counts:  dict[str, int]   = defaultdict(int)
    cat_revenue: dict[str, float] = defaultdict(float)
    risk_counts: dict[str, int]   = defaultdict(int)
    total = 0

    # ML label → friendly label (handles both old ML-label and new friendly-label rows)
    _ML_TO_FRIENDLY_LOCAL = {
        "VIP":     "Best Customers",
        "Loyal":   "Repeat Customers",
        "Regular": "Standard Customers",
        "At Risk": "Customers You May Lose",
    }

    for row in pred_rows:
        raw_cat = row["customer_category"] or "Standard Customers"
        # Normalize: if it's a raw ML label, convert it; otherwise keep as-is
        cat  = _ML_TO_FRIENDLY_LOCAL.get(raw_cat, raw_cat)
        risk = row["retention_risk"] or ""
        cid  = row["customer_id"]
        cat_counts[cat]  += 1
        cat_revenue[cat] += rev_map.get(cid, 0.0)
        risk_counts[risk] += 1
        total += 1

    seg_breakdown = []
    for cat in _CATEGORY_ORDER:
        cnt    = cat_counts.get(cat, 0)
        ml_seg = _FRIENDLY_TO_ML.get(cat, cat)
        seg_breakdown.append({
            "segment":  ml_seg,
            "category": cat,
            "count":    cnt,
            "pct":      round(cnt / total * 100, 1) if total else 0,
            "color":    _SEG_COLORS_DB.get(cat, "#64748b"),
            "actions":  _SEG_ACTIONS_DB.get(cat, []),
        })

    rev_by_segment = [
        {
            "category": cat,
            "Revenue":  round(cat_revenue.get(cat, 0.0), 2),
            "color":    _SEG_COLORS_DB.get(cat, "#64748b"),
        }
        for cat in _CATEGORY_ORDER
    ]

    at_risk_count  = risk_counts.get("High Retention Risk", 0)
    retention_rate = round((total - at_risk_count) / total * 100, 1) if total else 0

    return {
        "seg_breakdown":   seg_breakdown,
        "rev_by_segment":  rev_by_segment,
        "at_risk_count":   at_risk_count,
        "retention_rate":  retention_rate,
        "sb_total":    f"{total:,}" if total else "—",
        "sb_best":     f"{cat_counts.get('Best Customers', 0):,}",
        "sb_repeat":   f"{cat_counts.get('Repeat Customers', 0):,}",
        "sb_standard": f"{cat_counts.get('Standard Customers', 0):,}",
        "sb_losing":   f"{cat_counts.get('Customers You May Lose', 0):,}",
    }
