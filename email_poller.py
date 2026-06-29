# email_poller.py
import os
import base64
import pickle
import re
import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# ── config ────────────────────────────────────────────────────────────────────
SCOPES           = ["https://www.googleapis.com/auth/gmail.readonly"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE       = "gmail_token.pkl"
DB_PATH          = "tracker.db"

# Keywords in subject line that identify bank alert emails
BANK_SUBJECT_KEYWORDS = [
    "debit alert", "credit alert", "transaction alert",
    "hdfc bank", "amount debited", "amount credited",
    "upi payment", "bank alert"
]

# ── Gmail auth ────────────────────────────────────────────────────────────────
def get_gmail_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES)
            # Opens browser for one-time login
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return build("gmail", "v1", credentials=creds)


# ── fetch emails ──────────────────────────────────────────────────────────────
def fetch_bank_emails(service, days_back=30):
    since = (datetime.now() - timedelta(days=days_back)).strftime("%Y/%m/%d")
    subject_query = " OR ".join(
        f'subject:"{kw}"' for kw in BANK_SUBJECT_KEYWORDS
    )
    query = f"({subject_query}) after:{since}"

    results = service.users().messages().list(
        userId="me", q=query, maxResults=100
    ).execute()

    messages = results.get("messages", [])
    emails = []
    for msg in messages:
        full = service.users().messages().get(
            userId="me", id=msg["id"], format="full"   # ← 'id' not 'messageId'
        ).execute()
        emails.append(_extract_email(full))
    return emails


def _extract_email(msg):
    headers = {h["name"]: h["value"]
               for h in msg["payload"]["headers"]}
    body = ""
    parts = msg["payload"].get("parts", [msg["payload"]])
    for part in parts:
        if part.get("mimeType") == "text/plain":
            raw = part["body"].get("data", "")
            body = base64.urlsafe_b64decode(
                raw + "==").decode("utf-8", errors="ignore")
            break
    return {
        "id":      msg["id"],
        "from":    headers.get("From", ""),
        "subject": headers.get("Subject", ""),
        "date":    headers.get("Date", ""),
        "body":    body,
    }


# ── parse transaction from email body ─────────────────────────────────────────
PATTERNS = [
    # "Rs. 450 debited from ... at Swiggy on ..."
    re.compile(
        r"Rs\.?\s*([\d,]+\.?\d*)\s+debited\b.*?\bat\s+([A-Za-z0-9 &\-/]+?)(?:\s+on\b|\s+\d)",
        re.IGNORECASE | re.DOTALL
    ),
    # "Rs. 450 debited from ... to Amazon on ..."
    re.compile(
        r"Rs\.?\s*([\d,]+\.?\d*)\s+debited\b.*?\bto\s+([A-Za-z0-9 &\-/]+?)(?:\s+on\b|\s+\d)",
        re.IGNORECASE | re.DOTALL
    ),
    # "Rs. 25000 credited to ... by Salary-Employer on ..."
    re.compile(
        r"Rs\.?\s*([\d,]+\.?\d*)\s+credited\b.*?\bby\s+([A-Za-z0-9 &\-/]+?)(?:\s+on\b|\s+\d)",
        re.IGNORECASE | re.DOTALL
    ),
]

CATEGORY_RULES = {
    "Food & Dining":  ["swiggy", "zomato", "dominos", "mcdonald", "restaurant",
                       "cafe", "hotel", "pizza", "burger"],
    "Groceries":      ["bigbasket", "blinkit", "dmart", "zepto", "grocery",
                       "supermarket", "reliance fresh"],
    "Transportation": ["uber", "ola", "rapido", "metro", "petrol", "fuel",
                       "irctc", "parking", "toll", "bmtc"],
    "Shopping":       ["amazon", "flipkart", "myntra", "ajio", "meesho",
                       "nykaa", "snapdeal"],
    "Healthcare":     ["pharmacy", "apollo", "medplus", "hospital",
                       "clinic", "diagnostic", "lab"],
    "Utilities":      ["electricity", "water", "gas", "airtel", "jio",
                       "bsnl", "broadband", "recharge"],
    "Entertainment":  ["netflix", "prime", "hotstar", "spotify",
                       "bookmyshow", "pvr", "inox"],
    "Salary/Income":  ["salary", "employer", "payroll", "neft", "credited"],
}

def _categorize(merchant: str) -> str:
    m = merchant.lower()
    for category, keywords in CATEGORY_RULES.items():
        if any(kw in m for kw in keywords):
            return category
    return "Uncategorized"

def parse_transaction(email: dict):
    body = email["body"]
    subject = email["subject"].lower()

    # Determine type from subject/body
    is_credit = "credit" in subject or "credited" in body.lower()

    for pattern in PATTERNS:
        match = pattern.search(body)
        if match:
            amount_str = match.group(1).replace(",", "")
            merchant   = match.group(2).strip().title()
            return {
                "email_id":  email["id"],
                "date":      _parse_date(email["date"]),
                "amount":    float(amount_str),
                "type":      "Income" if is_credit else "Expense",
                "merchant":  merchant,
                "category":  _categorize(merchant),
            }
    return None

def _parse_date(date_str: str) -> str:
    """Convert email date header to YYYY-MM-DD."""
    for fmt in ["%a, %d %b %Y", "%d %b %Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(date_str[:16].strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return datetime.now().strftime("%Y-%m-%d")


# ── save to tracker.db ────────────────────────────────────────────────────────
@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def save_transaction(txn: dict, username: str,
                     account_type: str, personal_type: str):
    pt = personal_type if personal_type else "__none__"

    with _db() as conn:
        # Duplicate check by Gmail message ID
        existing = conn.execute(
            "SELECT 1 FROM records WHERE email_id = ?",
            (txn["email_id"],)
        ).fetchone()
        if existing:
            return False   # already imported

        # Ensure category exists
        conn.execute(
            """INSERT OR IGNORE INTO categories
               (username, account_type, personal_type, name)
               VALUES (?, ?, ?, ?)""",
            (username, account_type, pt, txn["category"])
        )

        # Insert record
        conn.execute(
            """INSERT INTO records
               (username, account_type, personal_type, date,
                description, amount, txn_type, account_label,
                category, source, email_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'email', ?)""",
            (username, account_type, pt,
             txn["date"], txn["merchant"], txn["amount"],
             txn["type"], username,
             txn["category"], txn["email_id"])
        )
    return True


# ── main sync function (called from UI or scheduler) ─────────────────────────
def sync_emails(username: str, account_type: str,
                personal_type: str, days_back: int = 30):
    """
    Full sync: authenticate → fetch → parse → save.
    Returns a summary dict.
    """
    print(f"Connecting to Gmail for '{username}' ...")
    service  = get_gmail_service()
    emails   = fetch_bank_emails(service, days_back=days_back)
    print(f"Found {len(emails)} bank-related email(s).")

    imported = skipped = failed = 0
    for email in emails:
        txn = parse_transaction(email)
        if txn:
            saved = save_transaction(txn, username, account_type, personal_type)
            if saved:
                imported += 1
                print(f"  ✓  {txn['type']:7s}  ₹{txn['amount']:>10,.2f}"
                      f"  {txn['merchant']:<20}  [{txn['category']}]")
            else:
                skipped += 1
        else:
            failed += 1

    print(f"\nSync complete — {imported} imported, "
          f"{skipped} duplicate(s) skipped, "
          f"{failed} email(s) could not be parsed.")
    return {"imported": imported, "skipped": skipped, "failed": failed}


if __name__ == "__main__":
    # Quick test — run this file directly to verify the pipeline
    result = sync_emails(
        username     = "your_tracker_username",
        account_type = "Personal",
        personal_type= "Student",
        days_back    = 30,
    )