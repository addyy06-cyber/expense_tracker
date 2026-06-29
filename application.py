import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import json
import os
import sqlite3
import hashlib
import secrets
from contextlib import contextmanager
from datetime import datetime
from collections import defaultdict
from PIL import Image, ImageTk, ImageDraw, ImageFont

# ── paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH  = os.path.join(SCRIPT_DIR, "IMG_0023.GIF")
DB_PATH    = os.path.join(SCRIPT_DIR, "tracker.db")

# Legacy paths — only used during one-time migration
_LEGACY_USERS_FILE = os.path.join(SCRIPT_DIR, "users.json")
_LEGACY_DATA_DIR   = os.path.join(SCRIPT_DIR, "data")
_LEGACY_PROFILE_FILES = {
    ("Family",   None)       : "data_family.json",
    ("Business", None)       : "data_business.json",
    ("Personal", "Student")  : "data_personal_student.json",
    ("Personal", "Employee") : "data_personal_employee.json",
}

GRAD_START = (61,  214, 140)   # #3dd68c teal-green
GRAD_END   = (66,  165, 245)   # #42a5f5 blue
BG_RGB     = (26,  26,  26)    # #1a1a1a dark background

# ── SQLite database layer ──────────────────────────────────────────────────────
_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    balance       REAL NOT NULL DEFAULT 0.0,
    account_type  TEXT,
    personal_type TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL,
    account_type  TEXT NOT NULL,
    personal_type TEXT NOT NULL,
    name          TEXT NOT NULL,
    UNIQUE (username, account_type, personal_type, name),
    FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS records (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL,
    account_type  TEXT NOT NULL,
    personal_type TEXT NOT NULL,
    date          TEXT NOT NULL,
    description   TEXT NOT NULL,
    amount        REAL NOT NULL,
    txn_type      TEXT NOT NULL,
    account_label TEXT NOT NULL,
    category      TEXT NOT NULL,
    source        TEXT NOT NULL DEFAULT 'manual',
    email_id      TEXT UNIQUE,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_records_user ON records(username, account_type, personal_type);
CREATE INDEX IF NOT EXISTS idx_records_date ON records(date);
"""

@contextmanager
def _db():
    """Yield a connection; auto-commit on success, rollback on error."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def _init_db():
    with _db() as conn:
        conn.executescript(_SCHEMA)

def _migrate_from_json():
    """
    One-time migration: import users.json and all data/*.json into SQLite,
    then rename the old files to *.bak so migration never runs again.
    """
    if not os.path.exists(_LEGACY_USERS_FILE):
        return
    print("Migrating existing JSON data to SQLite ...")
    try:
        with open(_LEGACY_USERS_FILE, "r") as f:
            users = json.load(f)
    except Exception as e:
        print(f"  Could not read users.json: {e}")
        return

    with _db() as conn:
        for uname, rec in users.items():
            existing = conn.execute(
                "SELECT 1 FROM users WHERE username = ?", (uname,)
            ).fetchone()
            if existing:
                continue
            conn.execute(
                """INSERT INTO users
                   (username, password_hash, salt, balance,
                    account_type, personal_type, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    uname,
                    rec.get("password_hash", ""),
                    rec.get("salt", ""),
                    float(rec.get("balance", 0.0)),
                    rec.get("account_type"),
                    _pt_key(rec.get("personal_type")),
                    rec.get("created_at", datetime.now().isoformat()),
                )
            )

        for (at, pt), filename in _LEGACY_PROFILE_FILES.items():
            fpath = os.path.join(_LEGACY_DATA_DIR, filename)
            if not os.path.exists(fpath):
                continue
            try:
                with open(fpath, "r") as f:
                    data = json.load(f)
            except Exception as e:
                print(f"  Skipping {filename}: {e}")
                continue

            owner = next(
                (u for u, r in users.items()
                 if r.get("account_type") == at
                 and r.get("personal_type") == pt),
                f"__migrated_{at}_{pt}__"
            )
            pt_db = _pt_key(pt)

            for cat in data.get("categories", []):
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO categories
                           (username, account_type, personal_type, name)
                           VALUES (?, ?, ?, ?)""",
                        (owner, at, pt_db, cat)
                    )
                except Exception:
                    pass

            for r in data.get("records", []):
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO records
                           (username, account_type, personal_type,
                            date, description, amount, txn_type,
                            account_label, category, source)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'migrated')""",
                        (
                            owner, at, pt_db,
                            r.get("date", ""),
                            r.get("description", ""),
                            float(r.get("amount", 0)),
                            "Expense" if r.get("type", "Expense") == "Expense" else "Income",
                            r.get("account", owner),
                            r.get("category", "Uncategorized"),
                        )
                    )
                except Exception:
                    pass

    os.rename(_LEGACY_USERS_FILE, _LEGACY_USERS_FILE + ".bak")
    for filename in _LEGACY_PROFILE_FILES.values():
        fpath = os.path.join(_LEGACY_DATA_DIR, filename)
        if os.path.exists(fpath):
            os.rename(fpath, fpath + ".bak")
    print("  Migration complete. Old files renamed to *.bak")

# ── helpers ───────────────────────────────────────────────────────────────────
def _pt_key(personal_type):
    """Store None personal_type as '__none__' so it survives SQL NOT NULL."""
    return personal_type if personal_type else "__none__"

def _pt_val(pt_key):
    """Reverse of _pt_key."""
    return None if pt_key == "__none__" else pt_key

# Initialise DB and migrate on import
_init_db()
_migrate_from_json()

# ── user auth & profile ───────────────────────────────────────────────────────
def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

def register_user(username: str, password: str) -> tuple[bool, str]:
    if len(username) < 3:
        return False, "Username must be at least 3 characters."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    with _db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE lower(username) = lower(?)", (username,)
        ).fetchone()
        if exists:
            return False, "Username already taken. Please choose another."
        salt = secrets.token_hex(16)
        conn.execute(
            """INSERT INTO users (username, password_hash, salt, balance, created_at)
               VALUES (?, ?, ?, 0.0, ?)""",
            (username, _hash_password(password, salt), salt, datetime.now().isoformat())
        )
    return True, ""

def authenticate_user(username: str, password: str) -> tuple[bool, str]:
    with _db() as conn:
        row = conn.execute(
            "SELECT username, password_hash, salt FROM users WHERE lower(username) = lower(?)",
            (username,)
        ).fetchone()
    if not row:
        return False, "Username not found. Please register first."
    if _hash_password(password, row["salt"]) != row["password_hash"]:
        return False, "Incorrect password. Please try again."
    return True, row["username"]

def get_user_balance(username: str) -> float:
    with _db() as conn:
        row = conn.execute(
            "SELECT balance FROM users WHERE username = ?", (username,)
        ).fetchone()
    return float(row["balance"]) if row else 0.0

def set_user_balance(username: str, balance: float):
    with _db() as conn:
        conn.execute(
            "UPDATE users SET balance = ? WHERE username = ?", (balance, username)
        )

def deduct_user_balance(username: str, amount: float):
    set_user_balance(username, get_user_balance(username) - amount)

def add_user_balance(username: str, amount: float):
    set_user_balance(username, get_user_balance(username) + amount)

def get_user_profile(username: str):
    with _db() as conn:
        row = conn.execute(
            "SELECT account_type, personal_type FROM users WHERE username = ?",
            (username,)
        ).fetchone()
    if row and row["account_type"]:
        return row["account_type"], _pt_val(row["personal_type"])
    return None, None

def save_user_profile(username: str, account_type: str, personal_type):
    with _db() as conn:
        conn.execute(
            "UPDATE users SET account_type = ?, personal_type = ? WHERE username = ?",
            (account_type, _pt_key(personal_type), username)
        )

# ── per-profile expense data ──────────────────────────────────────────────────
def load_data(account_type: str, personal_type) -> dict:
    pt = _pt_key(personal_type)
    with _db() as conn:
        cat_rows = conn.execute(
            """SELECT name FROM categories
               WHERE account_type = ? AND personal_type = ?
               ORDER BY name""",
            (account_type, pt)
        ).fetchall()
        rec_rows = conn.execute(
            """SELECT id, date, description, amount, txn_type,
                      account_label, category, source
               FROM records
               WHERE account_type = ? AND personal_type = ?
               ORDER BY date DESC, id DESC""",
            (account_type, pt)
        ).fetchall()

    categories = [r["name"] for r in cat_rows]
    records = [{
        "id":          r["id"],
        "date":        r["date"],
        "description": r["description"],
        "amount":      r["amount"],
        "type":        r["txn_type"],
        "account":     r["account_label"],
        "category":    r["category"],
        "source":      r["source"],
    } for r in rec_rows]
    return {"categories": categories, "records": records}

# ── image & font helpers ───────────────────────────────────────────────────────
def load_logo(size):
    if not os.path.exists(LOGO_PATH):
        return None
    img = Image.open(LOGO_PATH).convert("RGBA")
    img.thumbnail((size, size), Image.LANCZOS)
    return ImageTk.PhotoImage(img)

def _load_pil_font(size, bold=False):
    candidates = (
        ["Calibri Bold.ttf", "calibrib.ttf",
         "/System/Library/Fonts/Supplemental/Calibri Bold.ttf",
         "/Library/Fonts/Calibri Bold.ttf",
         "C:/Windows/Fonts/calibrib.ttf"]
        if bold else
        ["Calibri.ttf", "calibri.ttf",
         "/System/Library/Fonts/Supplemental/Calibri.ttf",
         "/Library/Fonts/Calibri.ttf",
         "C:/Windows/Fonts/calibri.ttf"]
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()

def gradient_label(parent, text, pil_size, bold=False,
                   color_start=GRAD_START, color_end=GRAD_END,
                   bg_rgb=BG_RGB, anchor="center", pady=0, padx=0, side=None):
    font  = _load_pil_font(pil_size, bold=bold)
    dummy = Image.new("RGBA", (1, 1))
    d     = ImageDraw.Draw(dummy)
    bbox  = d.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0] + 6
    h = bbox[3] - bbox[1] + 8
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    d.text((-bbox[0] + 3, -bbox[1] + 4), text, font=font, fill=(255, 255, 255, 255))
    grad = Image.new("RGBA", (w, h))
    for x in range(w):
        t = x / max(w - 1, 1)
        r = int(color_start[0] + t * (color_end[0] - color_start[0]))
        g = int(color_start[1] + t * (color_end[1] - color_start[1]))
        b = int(color_start[2] + t * (color_end[2] - color_start[2]))
        for y in range(h):
            alpha = canvas.getpixel((x, y))[3]
            grad.putpixel((x, y), (r, g, b, alpha))
    out = Image.new("RGBA", (w, h), (*bg_rgb, 255))
    out.paste(grad, mask=grad.split()[3])
    photo = ImageTk.PhotoImage(out)
    bg_hex = f"#{bg_rgb[0]:02x}{bg_rgb[1]:02x}{bg_rgb[2]:02x}"
    lbl = tk.Label(parent, image=photo, bg=bg_hex)
    lbl._photo = photo
    if side is not None:
        lbl.pack(side=side, padx=padx, pady=pady)
    else:
        lbl.pack(pady=pady, padx=padx)
    return lbl


# ── login / onboarding window ─────────────────────────────────────────────────
class LoginWindow(tk.Tk):
    SPLASH_HOLD_MS = 1800
    FADE_STEPS     = 35
    FADE_INTERVAL  = 16

    def __init__(self):
        super().__init__()
        self.title("Expense Tracker")
        self.geometry("520x660")
        self.resizable(False, False)

        self.bg      = "#1a1a1a"
        self.bg2     = "#242424"
        self.bg3     = "#2e2e2e"
        self.accent  = "#ffa726"
        self.teal    = "#3dd68c"
        self.fg      = "#f0f0f0"
        self.fg_dim  = "#888888"
        self.green   = "#3dd68c"
        self.red     = "#ef5350"
        self.border  = "#383838"

        self.configure(bg=self.bg)
        self.font_title  = ("Calibri", 28, "bold")
        self.font_header = ("Calibri", 14, "bold")
        self.font_body   = ("Calibri", 13)
        self.font_small  = ("Calibri", 12)

        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self._img_refs    = []

        self.splash_frame = tk.Frame(self, bg=self.bg)
        self.login_frame  = tk.Frame(self, bg=self.bg)
        for f in (self.splash_frame, self.login_frame):
            f.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._build_splash()
        self._build_login_content()
        self.splash_frame.lift()
        self.after(self.SPLASH_HOLD_MS, self._start_crossfade)

    # ── splash ────────────────────────────────────────────────────────────────
    def _build_splash(self):
        f = self.splash_frame
        logo = load_logo(260)
        if logo:
            self._img_refs.append(logo)
            tk.Label(f, image=logo, bg=self.bg).pack(expand=True, pady=(60, 8))
        else:
            tk.Label(f, text="₹", font=("Calibri", 100, "bold"),
                     bg=self.bg, fg=self.teal).pack(expand=True, pady=(60, 8))
        gradient_label(f, "EXPENSE TRACKER", pil_size=22, bold=True, pady=0)
        tk.Label(f, text="track  ·  save  ·  grow", font=("Calibri", 12),
                 bg=self.bg, fg="#444444").pack(pady=(6, 0))
        dot_row = tk.Frame(f, bg=self.bg)
        dot_row.pack(pady=28)
        self._dots    = []
        self._dot_idx = 0
        self._dot_job = None
        for _ in range(3):
            d = tk.Frame(dot_row, bg="#2e2e2e", width=8, height=8)
            d.pack(side="left", padx=4)
            self._dots.append(d)
        self._animate_dots()

    def _animate_dots(self):
        for i, d in enumerate(self._dots):
            d.config(bg=self.teal if i == self._dot_idx else "#2e2e2e")
        self._dot_idx = (self._dot_idx + 1) % 3
        self._dot_job = self.after(300, self._animate_dots)

    # ── crossfade ─────────────────────────────────────────────────────────────
    def _start_crossfade(self):
        if self._dot_job:
            self.after_cancel(self._dot_job)
        self._cf_step = 0
        self._fade_out()

    def _fade_out(self):
        self._cf_step += 1
        alpha = 1.0 - (self._cf_step / self.FADE_STEPS)
        if alpha <= 0:
            self.splash_frame.lower()
            self.attributes("-alpha", 0.0)
            self._cf_step = 0
            self.after(40, self._fade_in)
            return
        self.attributes("-alpha", max(alpha, 0.0))
        self.after(self.FADE_INTERVAL, self._fade_out)

    def _fade_in(self):
        self._cf_step += 1
        alpha = self._cf_step / self.FADE_STEPS
        if alpha >= 1.0:
            self.attributes("-alpha", 1.0)
            return
        self.attributes("-alpha", min(alpha, 1.0))
        self.after(self.FADE_INTERVAL, self._fade_in)

    # ── shared helpers ────────────────────────────────────────────────────────
    def _clear_login(self):
        for w in self.login_frame.winfo_children():
            w.destroy()

    def _entry(self, parent, textvariable=None, show=None):
        kw = dict(bg=self.bg3, fg=self.fg, insertbackground=self.teal,
                  bd=0, font=self.font_body, width=28,
                  highlightthickness=1, highlightcolor=self.teal,
                  highlightbackground=self.border)
        if textvariable: kw["textvariable"] = textvariable
        if show:         kw["show"] = show
        return tk.Entry(parent, **kw)

    def _card_btn(self, parent, icon, title, subtitle, command):
        card = tk.Frame(parent, bg=self.bg3, cursor="hand2",
                        highlightthickness=1, highlightbackground=self.border)
        card.pack(fill="x", pady=5)
        inner = tk.Frame(card, bg=self.bg3, padx=20, pady=14)
        inner.pack(fill="x")
        tk.Label(inner, text=icon, font=("Calibri", 24),
                 bg=self.bg3, fg=self.teal).pack(side="left", padx=(0, 14))
        txt = tk.Frame(inner, bg=self.bg3)
        txt.pack(side="left", fill="x", expand=True)
        gradient_label(txt, title, pil_size=13, bold=True,
                       bg_rgb=(46, 46, 46), side="top", pady=0)
        tk.Label(txt, text=subtitle, font=self.font_small,
                 bg=self.bg3, fg=self.fg_dim, anchor="w").pack(fill="x")
        arrow = tk.Label(inner, text="→", font=("Calibri", 16),
                         bg=self.bg3, fg="#555555")
        arrow.pack(side="right")

        def on_enter(e):
            card.config(highlightbackground=self.teal)
            arrow.config(fg=self.teal)
        def on_leave(e):
            card.config(highlightbackground=self.border)
            arrow.config(fg="#555555")

        all_widgets = ([card, inner, txt, arrow]
                       + inner.winfo_children()
                       + txt.winfo_children())
        for w in all_widgets:
            w.bind("<Button-1>", lambda e, c=command: c())
            w.bind("<Enter>",    on_enter)
            w.bind("<Leave>",    on_leave)

    def _header(self, parent, step, total_steps, title, subtitle=None):
        top = tk.Frame(parent, bg=self.bg)
        top.pack(pady=(20, 2))
        logo = load_logo(36)
        if logo:
            self._img_refs.append(logo)
            tk.Label(top, image=logo, bg=self.bg).pack(side="left", padx=(0, 8))
        gradient_label(top, "EXPENSE TRACKER", pil_size=12, bg_rgb=BG_RGB, side="left")
        gradient_label(parent, title, pil_size=26, bold=True, bg_rgb=BG_RGB, pady=(2, 0))
        if subtitle:
            tk.Label(parent, text=subtitle, font=self.font_small,
                     bg=self.bg, fg=self.teal).pack(pady=(4, 0))
        step_frame = tk.Frame(parent, bg=self.bg)
        step_frame.pack(pady=12)
        for i in range(1, total_steps + 1):
            color = self.teal if i == step else self.bg3
            tk.Frame(step_frame, bg=color, width=22, height=4).pack(side="left", padx=3)

    def _error_label(self, parent):
        lbl = tk.Label(parent, text="", font=self.font_small,
                       bg=self.bg, fg=self.red, wraplength=340, justify="left")
        lbl.pack(pady=(4, 0))
        return lbl

    def _back_btn(self, parent, command):
        tk.Button(parent, text="← Back", font=self.font_small,
                  bg=self.bg, fg=self.fg_dim, bd=0, cursor="hand2",
                  activebackground=self.bg, activeforeground=self.teal,
                  command=command).pack(pady=(10, 0))

    # ── SCREEN 1 — Welcome ────────────────────────────────────────────────────
    def _build_login_content(self):
        self._clear_login()
        f = self.login_frame
        self._header(f, 1, 5, "WELCOME", "Sign in or create a new account")
        cards = tk.Frame(f, bg=self.bg, padx=50)
        cards.pack(fill="x", pady=8)
        self._card_btn(cards, "🔑", "Sign In",
                       "Continue with your existing account",
                       self._build_signin_form)
        self._card_btn(cards, "✨", "Create Account",
                       "Register a new username and password",
                       self._build_register_form)

    # ── SCREEN 1a — Sign In ───────────────────────────────────────────────────
    def _build_signin_form(self):
        self._clear_login()
        f = self.login_frame
        self._header(f, 1, 5, "SIGN IN", "Enter your credentials to continue")
        form = tk.Frame(f, bg=self.bg, padx=60)
        form.pack(fill="x", pady=10)

        gradient_label(form, "USERNAME", pil_size=12, pady=(10, 2))
        u_entry = self._entry(form, textvariable=self.username_var)
        u_entry.pack(fill="x", ipady=6)

        gradient_label(form, "PASSWORD", pil_size=12, pady=(12, 2))
        self._entry(form, textvariable=self.password_var, show="●").pack(fill="x", ipady=6)

        err = self._error_label(form)

        def do_signin():
            uname = self.username_var.get().strip()
            pwd   = self.password_var.get().strip()
            if not uname:
                err.config(text="⚠  Username cannot be empty.")
                return
            if not pwd:
                err.config(text="⚠  Password cannot be empty.")
                return
            ok, result = authenticate_user(uname, pwd)
            if not ok:
                err.config(text=f"⚠  {result}")
                return
            self.username_var.set(result)
            saved_at, saved_pt = get_user_profile(result)
            if saved_at:
                self._launch(saved_at, saved_pt)
            else:
                self._build_account_type()

        tk.Button(form, text="SIGN IN →", font=self.font_header,
                  bg=self.teal, fg="#000", bd=0, pady=10, cursor="hand2",
                  activebackground="#2ec47a",
                  command=do_signin).pack(fill="x", pady=(16, 0))
        self._back_btn(form, self._build_login_content)
        u_entry.focus()
        self.bind("<Return>", lambda e: do_signin())

    # ── SCREEN 1b — Register ──────────────────────────────────────────────────
    def _build_register_form(self):
        self._clear_login()
        f = self.login_frame
        self._header(f, 1, 5, "CREATE ACCOUNT", "Choose a unique username and password")
        form = tk.Frame(f, bg=self.bg, padx=60)
        form.pack(fill="x", pady=6)

        gradient_label(form, "USERNAME", pil_size=12, pady=(8, 2))
        tk.Label(form, text="Min 3 characters · case-insensitive",
                 font=("Calibri", 10), bg=self.bg, fg=self.fg_dim).pack(anchor="w")
        new_user_var = tk.StringVar()
        u_entry = self._entry(form, textvariable=new_user_var)
        u_entry.pack(fill="x", ipady=6)

        gradient_label(form, "PASSWORD", pil_size=12, pady=(10, 2))
        tk.Label(form, text="Min 6 characters",
                 font=("Calibri", 10), bg=self.bg, fg=self.fg_dim).pack(anchor="w")
        new_pass_var = tk.StringVar()
        self._entry(form, textvariable=new_pass_var, show="●").pack(fill="x", ipady=6)

        gradient_label(form, "CONFIRM PASSWORD", pil_size=12, pady=(10, 2))
        conf_pass_var = tk.StringVar()
        self._entry(form, textvariable=conf_pass_var, show="●").pack(fill="x", ipady=6)

        err    = self._error_label(form)
        ok_lbl = tk.Label(form, text="", font=self.font_small, bg=self.bg, fg=self.green)
        ok_lbl.pack(pady=(2, 0))

        def do_register():
            uname = new_user_var.get().strip()
            pwd   = new_pass_var.get().strip()
            conf  = conf_pass_var.get().strip()
            ok_lbl.config(text="")
            if not uname or not pwd or not conf:
                err.config(text="⚠  All fields are required.")
                return
            if pwd != conf:
                err.config(text="⚠  Passwords do not match.")
                return
            success, reason = register_user(uname, pwd)
            if not success:
                err.config(text=f"⚠  {reason}")
                return
            err.config(text="")
            ok_lbl.config(text=f"✓  Account '{uname}' created! Setting up balance…")
            self.username_var.set(uname)
            self.after(900, lambda u=uname: self._build_initial_balance(u))

        tk.Button(form, text="CREATE ACCOUNT →", font=self.font_header,
                  bg=self.teal, fg="#000", bd=0, pady=10, cursor="hand2",
                  activebackground="#2ec47a",
                  command=do_register).pack(fill="x", pady=(14, 0))
        self._back_btn(form, self._build_login_content)
        u_entry.focus()

    # ── SCREEN 1c — Initial Balance ───────────────────────────────────────────
    def _build_initial_balance(self, username: str):
        self._clear_login()
        f = self.login_frame
        self._header(f, 2, 5, "SET YOUR BALANCE",
                     f"Welcome, {username}! Set your starting balance")
        form = tk.Frame(f, bg=self.bg, padx=60)
        form.pack(fill="x", pady=10)

        tk.Label(form, text="Your initial wallet / account balance",
                 font=self.font_small, bg=self.bg, fg=self.fg_dim).pack(anchor="w", pady=(4, 0))
        gradient_label(form, "STARTING BALANCE (₹)", pil_size=12, pady=(12, 2))
        bal_var = tk.StringVar(value="0")
        bal_entry = self._entry(form, textvariable=bal_var)
        bal_entry.pack(fill="x", ipady=8)
        bal_entry.icursor("end")

        presets_row = tk.Frame(form, bg=self.bg)
        presets_row.pack(fill="x", pady=(8, 0))
        tk.Label(presets_row, text="Quick:", font=("Calibri", 11),
                 bg=self.bg, fg=self.fg_dim).pack(side="left", padx=(0, 6))
        for amount in [1000, 5000, 10000, 50000]:
            tk.Button(presets_row, text=f"₹{amount:,}", font=("Calibri", 11),
                      bg=self.bg3, fg=self.teal, bd=0, padx=8, pady=4, cursor="hand2",
                      activebackground="#1e3a2f", activeforeground=self.teal,
                      command=lambda a=amount: bal_var.set(str(a))).pack(side="left", padx=3)

        err = self._error_label(form)

        def do_set_balance():
            raw = bal_var.get().strip()
            try:
                amount = float(raw)
                if amount < 0:
                    raise ValueError
            except ValueError:
                err.config(text="⚠  Enter a valid non-negative number.")
                return
            set_user_balance(username, amount)
            self.username_var.set(username)
            self._build_account_type()

        tk.Button(form, text="CONTINUE →", font=self.font_header,
                  bg=self.teal, fg="#000", bd=0, pady=10, cursor="hand2",
                  activebackground="#2ec47a",
                  command=do_set_balance).pack(fill="x", pady=(16, 0))
        tk.Label(form, text="You can update this later from the tracker.",
                 font=("Calibri", 10), bg=self.bg, fg=self.fg_dim).pack(pady=(6, 0))
        bal_entry.focus()
        self.bind("<Return>", lambda e: do_set_balance())

    # ── SCREEN 2 — Account Type ───────────────────────────────────────────────
    def _build_account_type(self):
        self._clear_login()
        f = self.login_frame
        self._header(f, 3, 5, "ACCOUNT TYPE")

        info = tk.Frame(f, bg=self.bg2,
                        highlightthickness=1, highlightbackground=self.border)
        info.pack(fill="x", padx=50, pady=(0, 8))
        tk.Label(info, text="🗄  All data is stored in  tracker.db",
                 font=("Calibri", 10), bg=self.bg2, fg=self.fg_dim).pack(pady=6)

        cards = tk.Frame(f, bg=self.bg, padx=50)
        cards.pack(fill="x", pady=4)
        self._card_btn(cards, "👤", "Personal Account", " ", self._build_personal_type)
        self._card_btn(cards, "👨\u200d👩\u200d👧\u200d👦", "Family Account", " ",
                       self._build_family_categories)
        self._card_btn(cards, "🏢", "Business Account", " ",
                       lambda: self._launch("Business", None))
        self._back_btn(f, self._build_signin_form)

    # ── SCREEN 3a — Personal Sub-type ─────────────────────────────────────────
    def _build_personal_type(self):
        self._clear_login()
        f = self.login_frame
        self._header(f, 4, 5, "YOUR PROFILE", "Tell us a bit more about yourself")
        cards = tk.Frame(f, bg=self.bg, padx=50)
        cards.pack(fill="x", pady=8)
        self._card_btn(cards, "🎓", "Student", " ",
                       lambda: self._launch("Personal", "Student"))
        self._card_btn(cards, "💼", "Employee", " ",
                       lambda: self._launch("Personal", "Employee"))
        self._back_btn(f, self._build_account_type)

    # ── SCREEN 3b — Family Category Quick-add ─────────────────────────────────
    def _build_family_categories(self):
        self._clear_login()
        f = self.login_frame
        self._header(f, 4, 5, "FAMILY BUDGET", "Quick-add or open the full tracker")

        CATEGORIES = [
            ("🛒", "Groceries"), ("🏠", "Housing"),  ("👗", "Clothing"),
            ("🎓", "Education"), ("🏥", "Healthcare"), ("🚗", "Transportation"),
        ]
        grid_outer = tk.Frame(f, bg=self.bg, padx=40)
        grid_outer.pack(fill="both", expand=True, pady=6)

        for i, (icon, label) in enumerate(CATEGORIES):
            row, col = divmod(i, 3)
            btn_canvas = tk.Canvas(grid_outer, width=130, height=80,
                                   bg=self.bg, highlightthickness=0, cursor="hand2")
            btn_canvas.grid(row=row, column=col, padx=10, pady=8, sticky="nsew")
            grid_outer.columnconfigure(col, weight=1)
            grid_outer.rowconfigure(row, weight=1)

            def draw_btn(canvas, ico, lbl, hover=False):
                canvas.delete("all")
                w, h, r = 130, 80, 16
                fill    = "#1e3a2f" if hover else self.bg3
                outline = self.teal  if hover else self.border
                pts = [r,0,w-r,0,w,0,w,r,w,h-r,w,h,w-r,h,r,h,0,h,0,h-r,0,r,0,0]
                canvas.create_polygon(pts, smooth=True, fill=fill, outline=outline, width=2)
                canvas.create_text(65, 26, text=ico, font=("Calibri", 20), fill=self.teal)
                canvas.create_text(65, 56, text=lbl, font=("Calibri", 11, "bold"),
                                   fill="#ffffff" if hover else self.fg)

            draw_btn(btn_canvas, icon, label)

            def make_handlers(canvas, ico, lbl):
                def on_enter(e): draw_btn(canvas, ico, lbl, hover=True)
                def on_leave(e): draw_btn(canvas, ico, lbl, hover=False)
                def on_click(e): self._build_category_entry_page(lbl)
                return on_enter, on_leave, on_click

            enter_fn, leave_fn, click_fn = make_handlers(btn_canvas, icon, label)
            btn_canvas.bind("<Enter>",    enter_fn)
            btn_canvas.bind("<Leave>",    leave_fn)
            btn_canvas.bind("<Button-1>", click_fn)

        bottom = tk.Frame(f, bg=self.bg)
        bottom.pack(fill="x", pady=(4, 10), padx=40)
        tk.Button(bottom, text="← Back", font=self.font_small,
                  bg=self.bg, fg=self.fg_dim, bd=0, cursor="hand2",
                  activebackground=self.bg, activeforeground=self.teal,
                  command=self._build_account_type).pack(side="left")
        tk.Button(bottom, text="OPEN FULL TRACKER →", font=self.font_small,
                  bg=self.teal, fg="#000", bd=0, padx=12, pady=6, cursor="hand2",
                  activebackground="#2ec47a",
                  command=lambda: self._launch("Family", None)).pack(side="right")

    # ── Family quick-entry page ───────────────────────────────────────────────
    def _build_category_entry_page(self, category):
        self._clear_login()
        f = self.login_frame
        ICONS = {"Groceries": "🛒", "Housing": "🏠", "Clothing": "👗",
                 "Education": "🎓", "Healthcare": "🏥", "Transportation": "🚗"}
        icon = ICONS.get(category, "💰")

        hdr = tk.Frame(f, bg=self.bg, pady=14)
        hdr.pack(fill="x", padx=30)
        logo = load_logo(32)
        if logo:
            self._img_refs.append(logo)
            tk.Label(hdr, image=logo, bg=self.bg).pack(side="left", padx=(0, 8))
        gradient_label(hdr, "EXPENSE TRACKER", pil_size=11, bg_rgb=BG_RGB, side="left")
        tk.Frame(f, bg=self.border, height=1).pack(fill="x")

        title_row = tk.Frame(f, bg=self.bg, pady=10)
        title_row.pack(fill="x", padx=30)
        tk.Label(title_row, text=icon, font=("Calibri", 30),
                 bg=self.bg, fg=self.teal).pack(side="left", padx=(0, 10))
        title_col = tk.Frame(title_row, bg=self.bg)
        title_col.pack(side="left")
        gradient_label(title_col, category.upper(), pil_size=20, bold=True,
                       bg_rgb=BG_RGB, pady=0)
        tk.Label(title_col, text=datetime.now().strftime("%A, %d %b %Y"),
                 font=self.font_small, bg=self.bg, fg=self.fg_dim).pack(anchor="w")
        tk.Frame(f, bg=self.border, height=1).pack(fill="x")

        body = tk.Frame(f, bg=self.bg)
        body.pack(fill="both", expand=True, padx=30, pady=12)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        left = tk.Frame(body, bg=self.bg)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        tk.Label(left, text="ADD ITEM", font=self.font_header,
                 bg=self.bg, fg=self.teal).pack(anchor="w", pady=(0, 8))
        es = dict(bg=self.bg3, fg=self.fg, insertbackground=self.teal,
                  bd=0, font=self.font_body,
                  highlightthickness=1, highlightcolor=self.teal,
                  highlightbackground=self.border)
        tk.Label(left, text="Item / Description", font=self.font_small,
                 bg=self.bg, fg=self.fg_dim).pack(anchor="w")
        item_var   = tk.StringVar()
        item_entry = tk.Entry(left, textvariable=item_var, **es)
        item_entry.pack(fill="x", ipady=7, pady=(2, 8))
        tk.Label(left, text="Amount Spent (₹)", font=self.font_small,
                 bg=self.bg, fg=self.fg_dim).pack(anchor="w")
        amount_var   = tk.StringVar()
        amount_entry = tk.Entry(left, textvariable=amount_var, **es)
        amount_entry.pack(fill="x", ipady=7, pady=(2, 8))
        msg_lbl = tk.Label(left, text="", font=self.font_small,
                           bg=self.bg, fg=self.red, anchor="w")
        msg_lbl.pack(fill="x")

        pending_items = []

        right = tk.Frame(body, bg=self.bg2,
                         highlightthickness=1, highlightbackground=self.border)
        right.grid(row=0, column=1, sticky="nsew")
        tk.Label(right, text="ITEMS ADDED", font=self.font_header,
                 bg=self.bg2, fg=self.teal).pack(anchor="w", padx=14, pady=(10, 6))
        tk.Frame(right, bg=self.border, height=1).pack(fill="x")

        scroll_canvas = tk.Canvas(right, bg=self.bg2, highlightthickness=0)
        scrollbar = ttk.Scrollbar(right, orient="vertical", command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        scroll_canvas.pack(side="left", fill="both", expand=True)
        items_frame = tk.Frame(scroll_canvas, bg=self.bg2)
        items_win   = scroll_canvas.create_window((0, 0), window=items_frame, anchor="nw")

        def on_frame_conf(e):  scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))
        def on_canvas_conf(e): scroll_canvas.itemconfig(items_win, width=e.width)
        items_frame.bind("<Configure>", on_frame_conf)
        scroll_canvas.bind("<Configure>", on_canvas_conf)

        total_lbl = tk.Label(right, text="Total: ₹0.00",
                             font=("Calibri", 13, "bold"), bg=self.bg2, fg=self.teal)
        total_lbl.pack(side="bottom", anchor="e", padx=14, pady=8)
        tk.Frame(right, bg=self.border, height=1).pack(side="bottom", fill="x")

        def refresh_items():
            for w in items_frame.winfo_children():
                w.destroy()
            if not pending_items:
                tk.Label(items_frame, text="No items yet.", font=self.font_small,
                         bg=self.bg2, fg=self.fg_dim).pack(padx=14, pady=10, anchor="w")
            else:
                for idx, ed in enumerate(pending_items):
                    row = tk.Frame(items_frame, bg=self.bg2)
                    row.pack(fill="x", padx=10, pady=3)
                    tk.Label(row, text=f"{idx+1}.", font=self.font_small,
                             bg=self.bg2, fg=self.fg_dim, width=3).pack(side="left")
                    tk.Label(row, text=ed["item"], font=self.font_body,
                             bg=self.bg2, fg=self.fg, anchor="w").pack(
                             side="left", fill="x", expand=True, padx=(4, 0))
                    tk.Label(row, text=f"₹{ed['amount']:,.2f}",
                             font=("Calibri", 12, "bold"),
                             bg=self.bg2, fg=self.teal).pack(side="right", padx=(4, 4))
                    def make_del(i):
                        def do_del():
                            pending_items.pop(i)
                            refresh_items()
                        return do_del
                    tk.Button(row, text="✕", font=("Calibri", 10), bg=self.bg2,
                              fg=self.red, bd=0, cursor="hand2",
                              activebackground=self.bg2,
                              command=make_del(idx)).pack(side="right")
            total_lbl.config(text=f"Total: ₹{sum(e['amount'] for e in pending_items):,.2f}")

        refresh_items()

        def add_item():
            name = item_var.get().strip()
            raw  = amount_var.get().strip()
            if not name:
                msg_lbl.config(text="⚠  Please enter an item name.")
                return
            try:
                amount = float(raw)
                if amount <= 0: raise ValueError
            except ValueError:
                msg_lbl.config(text="⚠  Enter a valid positive amount.")
                return
            msg_lbl.config(text="")
            pending_items.append({"item": name, "amount": amount})
            item_var.set(""); amount_var.set("")
            item_entry.focus()
            refresh_items()

        def save_all():
            if not pending_items:
                msg_lbl.config(text="⚠  Add at least one item first.")
                return
            username = self.username_var.get().strip()
            pt = _pt_key(None)
            with _db() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO categories
                       (username, account_type, personal_type, name)
                       VALUES (?, 'Family', ?, ?)""",
                    (username, pt, category)
                )
                for ed in pending_items:
                    conn.execute(
                        """INSERT INTO records
                           (username, account_type, personal_type, date, description,
                            amount, txn_type, account_label, category, source)
                           VALUES (?, 'Family', ?, ?, ?, ?, 'Expense', 'Family', ?, 'manual')""",
                        (username, pt,
                         datetime.now().strftime("%Y-%m-%d"),
                         ed["item"], ed["amount"], category)
                    )
            total = sum(e["amount"] for e in pending_items)
            messagebox.showinfo("Saved ✓",
                f"{len(pending_items)} item(s) saved to tracker.db\n"
                f"Category: {category}\nTotal: ₹{total:,.2f}", parent=self)
            self._build_family_categories()

        tk.Button(left, text="+ ADD ITEM", font=self.font_header,
                  bg=self.bg3, fg=self.teal, bd=0, pady=8, cursor="hand2",
                  activebackground="#1e3a2f", activeforeground=self.teal,
                  highlightthickness=1, highlightbackground=self.teal,
                  command=add_item).pack(fill="x", pady=(4, 0))
        item_entry.bind("<Return>",  lambda e: amount_entry.focus())
        amount_entry.bind("<Return>", lambda e: add_item())
        item_entry.focus()

        tk.Frame(f, bg=self.border, height=1).pack(fill="x")
        bottom = tk.Frame(f, bg=self.bg, pady=8)
        bottom.pack(fill="x", padx=30)
        tk.Button(bottom, text="← Back", font=self.font_small,
                  bg=self.bg, fg=self.fg_dim, bd=0, cursor="hand2",
                  activebackground=self.bg, activeforeground=self.teal,
                  command=self._build_family_categories).pack(side="left")
        tk.Button(bottom, text="SAVE ALL EXPENSES ✓", font=self.font_header,
                  bg=self.teal, fg="#000", bd=0, padx=20, pady=8,
                  cursor="hand2", activebackground="#2ec47a",
                  command=save_all).pack(side="right")

    # ── launch main tracker ───────────────────────────────────────────────────
    def _launch(self, account_type, personal_type):
        username = self.username_var.get().strip()
        save_user_profile(username, account_type, personal_type)
        self.destroy()
        app = ExpenseTracker(account_type=account_type,
                             personal_type=personal_type,
                             username=username)
        app.mainloop()


# ── main tracker app ──────────────────────────────────────────────────────────
class ExpenseTracker(tk.Tk):
    MIN_RECORDS_FOR_CHART = 5

    def __init__(self, account_type="Personal", personal_type="Student", username="User"):
        super().__init__()
        self.account_type  = account_type
        self.personal_type = personal_type
        self.username      = username

        self.title("Expense Tracker")
        self.geometry("1200x760")
        self.resizable(True, True)

        self.font_title  = ("Calibri", 28, "bold")
        self.font_header = ("Calibri", 14, "bold")
        self.font_body   = ("Calibri", 13)
        self.font_small  = ("Calibri", 12)

        self.bg         = "#1a1a1a"
        self.bg2        = "#242424"
        self.bg3        = "#2e2e2e"
        self.bg4        = "#333333"
        self.accent     = "#3dd68c"
        self.accent2    = "#ef5350"
        self.teal       = "#3dd68c"
        self.fg         = "#f0f0f0"
        self.fg_dim     = "#888888"
        self.fg_muted   = "#555555"
        self.green      = "#3dd68c"
        self.red        = "#ef5350"
        self.border     = "#383838"
        self.purple     = "#7986cb"
        self.blue       = "#42a5f5"
        self.amber      = "#ffa726"
        self.pink       = "#ec407a"

        self.configure(bg=self.bg)
        self._img_refs = []
        self.data = load_data(account_type, personal_type)
        self._build_ui()
        self.refresh_all()

    def _profile_label(self) -> str:
        badge = f"{self.username}  ·  {self.account_type}"
        if self.personal_type:
            badge += f" / {self.personal_type}"
        return badge

    # ── build main UI ─────────────────────────────────────────────────────────
    def _build_ui(self):
        # Title bar
        title_bar = tk.Frame(self, bg=self.bg, pady=10)
        title_bar.pack(fill="x", padx=28)

        # Left side: logo + title + subtitle
        left_col = tk.Frame(title_bar, bg=self.bg)
        left_col.pack(side="left")

        logo = load_logo(40)
        if logo:
            self._img_refs.append(logo)
            logo_lbl = tk.Label(left_col, image=logo, bg=self.bg)
            logo_lbl.pack(side="left", padx=(0, 10))

        title_text = tk.Frame(left_col, bg=self.bg)
        title_text.pack(side="left")
        tk.Label(title_text, text="Financial Reports", font=("Calibri", 20, "bold"),
                 bg=self.bg, fg=self.fg).pack(anchor="w")
        tk.Label(title_text, text=f"tracker.db · last synced 2 mins ago",
                 font=("Calibri", 12), bg=self.bg, fg=self.fg_dim).pack(anchor="w")

        # Right column: period tabs, export, wallet, logout
        right_col = tk.Frame(title_bar, bg=self.bg)
        right_col.pack(side="right", padx=4)

        # Top row: period tabs + export
        top_right = tk.Frame(right_col, bg=self.bg)
        top_right.pack(anchor="e")

        # Period tab group
        period_frame = tk.Frame(top_right, bg=self.bg3,
                                highlightthickness=1, highlightbackground=self.border)
        period_frame.pack(side="left", padx=(0, 10))
        for i, period in enumerate(["1M", "3M", "6M", "1Y"]):
            active = (period == "3M")
            btn_bg = "#3a3a3a" if active else self.bg3
            btn_fg = self.fg if active else self.fg_dim
            tk.Button(period_frame, text=period, font=("Calibri", 12),
                      bg=btn_bg, fg=btn_fg, bd=0, padx=14, pady=6,
                      cursor="hand2", activebackground="#3a3a3a",
                      activeforeground=self.fg).pack(side="left")

        # Export button
        export_btn = tk.Button(top_right, text="\u25a1  Export", font=("Calibri", 13),
                               bg=self.bg, fg=self.fg, bd=0, padx=18, pady=8,
                               cursor="hand2", activebackground=self.bg3,
                               activeforeground=self.fg,
                               highlightthickness=1, highlightbackground="#555555")
        export_btn.pack(side="left")

        # Bottom row: wallet + logout
        bottom_right = tk.Frame(right_col, bg=self.bg)
        bottom_right.pack(anchor="e", pady=(6, 0))

        bal = get_user_balance(self.username)
        self.balance_lbl = tk.Label(bottom_right,
                                    text=f"Wallet: ₹{bal:,.2f}",
                                    font=("Calibri", 13, "bold"),
                                    bg=self.bg,
                                    fg=self.green if bal >= 0 else self.red)
        self.balance_lbl.pack(side="left", padx=(0, 12))

        tk.Button(bottom_right, text="⏻  Logout", font=("Calibri", 12, "bold"),
                  bg=self.bg3, fg=self.red, bd=0, padx=12, pady=6,
                  cursor="hand2", activebackground="#3a1c1c", activeforeground=self.red,
                  highlightthickness=1, highlightbackground="#3a1c1c",
                  command=self._logout).pack(side="left")

        tk.Frame(self, bg=self.border, height=1).pack(fill="x")

        # Nav bar: ← Back + tab buttons
        nav_bar = tk.Frame(self, bg=self.bg, height=48)
        nav_bar.pack(fill="x")
        nav_bar.pack_propagate(False)

        self._tab_history = []
        self.back_btn = tk.Button(nav_bar, text="← Back", font=("Calibri", 13, "bold"),
                                  bg=self.bg, fg=self.fg_muted, bd=0, padx=16, pady=0,
                                  cursor="hand2", activebackground=self.bg,
                                  activeforeground=self.teal,
                                  command=self._go_back)
        self.back_btn.pack(side="left", fill="y")

        tab_bar = tk.Frame(nav_bar, bg=self.bg)
        tab_bar.pack(side="left", fill="y")
        self.tab_btns = {}
        for label in ["Records", "Categories", "Summary", "Analytics"]:
            btn = tk.Button(tab_bar, text=label.upper(), font=("Calibri", 13, "bold"),
                            bg=self.bg, fg="#666666", bd=0, padx=20, pady=0,
                            cursor="hand2", activebackground=self.bg2,
                            activeforeground=self.fg,
                            command=lambda l=label: self._switch_tab(l))
            btn.pack(side="left", fill="y")
            self.tab_btns[label] = btn

        tk.Frame(self, bg=self.border, height=1).pack(fill="x")
        self.content = tk.Frame(self, bg=self.bg)
        self.content.pack(fill="both", expand=True)

        # Apply ttk styles before building tabs
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Custom.Treeview",
                        background=self.bg2, foreground=self.fg,
                        fieldbackground=self.bg2, rowheight=38,
                        font=("Calibri", 12), borderwidth=0)
        style.configure("Custom.Treeview.Heading",
                        background=self.bg3, foreground="#888888",
                        font=("Calibri", 11, "bold"), borderwidth=0, relief="flat")
        style.map("Custom.Treeview",
                  background=[("selected", self.bg3)],
                  foreground=[("selected", self.teal)])
        style.configure("Vertical.TScrollbar",
                        background=self.bg3,
                        troughcolor=self.bg,
                        bordercolor=self.border,
                        arrowcolor="#666666")

        self.frames = {
            "Records":    self._build_records_tab(),
            "Categories": self._build_categories_tab(),
            "Summary":    self._build_summary_tab(),
            "Analytics":  self._build_analytics_tab(),
        }
        self._current_tab = None
        self._switch_tab("Records")

    def _switch_tab(self, name):
        if self._current_tab and self._current_tab != name:
            self._tab_history.append(self._current_tab)
        self._current_tab = name
        for f in self.frames.values():
            f.pack_forget()
        self.frames[name].pack(fill="both", expand=True)
        for n, b in self.tab_btns.items():
            if n == name:
                b.config(fg=self.teal, bg=self.bg3)
            else:
                b.config(fg="#666666", bg=self.bg)
        self.back_btn.config(fg=self.teal if self._tab_history else self.fg_muted)
        if name == "Summary":
            self._refresh_summary()
        if name == "Analytics":
            self._refresh_analytics()

    def _logout(self):
        if not messagebox.askyesno("Logout", f"Log out of '{self.username}'?", parent=self):
            return
        self.destroy()
        LoginWindow().mainloop()

    def _go_back(self):
        if self._tab_history:
            prev = self._tab_history.pop()
            self._current_tab = None
            self._switch_tab(prev)

    # ── Records tab ───────────────────────────────────────────────────────────
    def _build_records_tab(self):
        frame = tk.Frame(self.content, bg=self.bg)
        toolbar = tk.Frame(frame, bg=self.bg2, pady=10, padx=16)
        toolbar.pack(fill="x")

        tk.Button(toolbar, text="📧 Sync Emails", font=self.font_header,
                  bg=self.bg3, fg=self.teal, bd=0, padx=14, pady=6,
                  cursor="hand2", activebackground="#1e3a2f",
                  command=self._sync_emails).pack(side="left")
        tk.Button(toolbar, text="+ ADD RECORD", font=self.font_header,
                  bg=self.teal, fg="#000", bd=0, padx=14, pady=6,
                  cursor="hand2", activebackground="#2ec47a",
                  command=self._add_record_dialog).pack(side="left", padx=8)
        tk.Button(toolbar, text="✎ EDIT", font=self.font_header,
                  bg=self.bg3, fg=self.blue, bd=0, padx=14, pady=6,
                  cursor="hand2", activebackground="#1a2a3a",
                  command=self._edit_record_dialog).pack(side="left", padx=(0, 8))
        tk.Button(toolbar, text="✕ DELETE", font=self.font_header,
                  bg=self.bg3, fg=self.red, bd=0, padx=14, pady=6,
                  cursor="hand2", command=self._delete_record).pack(side="left")

        filter_frame = tk.Frame(toolbar, bg=self.bg2)
        filter_frame.pack(side="right")
        tk.Label(filter_frame, text="FILTER:", font=self.font_small,
                 bg=self.bg2, fg=self.fg_dim).pack(side="left", padx=(0, 4))
        self.filter_var = tk.StringVar()
        fe = tk.Entry(filter_frame, textvariable=self.filter_var,
                      font=self.font_body, bg=self.bg3, fg=self.fg,
                      insertbackground=self.teal, bd=0, width=18,
                      highlightthickness=1, highlightcolor=self.teal,
                      highlightbackground=self.border)
        fe.pack(side="left", ipady=4, padx=4)
        fe.bind("<KeyRelease>", lambda e: self._refresh_records())

        tree_frame = tk.Frame(frame, bg=self.bg)
        tree_frame.pack(fill="both", expand=True, padx=16, pady=12)

        cols = ("Date", "Description", "Amount", "Type", "Account", "Category")
        self.records_tree = ttk.Treeview(tree_frame, columns=cols,
                                          show="headings", style="Custom.Treeview")
        for col, w in zip(cols, [110, 220, 100, 90, 130, 130]):
            self.records_tree.heading(col, text=col.upper())
            self.records_tree.column(col, width=w, anchor="w")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                            command=self.records_tree.yview)
        self.records_tree.configure(yscrollcommand=vsb.set)
        self.records_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.totals_bar = tk.Frame(frame, bg=self.bg2, pady=12, padx=20)
        self.totals_bar.pack(fill="x", side="bottom")
        tk.Frame(frame, bg=self.border, height=1).pack(side="bottom", fill="x")
        self.lbl_income  = tk.Label(self.totals_bar, text="Income: ₹0",
                                    font=("Calibri", 13, "bold"), bg=self.bg2, fg=self.fg)
        self.lbl_income.pack(side="left", padx=16)
        self.lbl_expense = tk.Label(self.totals_bar, text="Expenses: ₹0",
                                    font=("Calibri", 13, "bold"), bg=self.bg2, fg=self.red)
        self.lbl_expense.pack(side="left", padx=16)
        self.lbl_txn_count = tk.Label(self.totals_bar, text="Transactions: 0",
                                      font=("Calibri", 13, "bold"), bg=self.bg2, fg=self.fg_dim)
        self.lbl_txn_count.pack(side="left", padx=16)
        self.lbl_balance = tk.Label(self.totals_bar, text="Balance: ₹0",
                                    font=("Calibri", 13, "bold"), bg=self.bg2, fg=self.teal)
        self.lbl_balance.pack(side="right", padx=16)
        return frame

    # ── Categories tab ────────────────────────────────────────────────────────
    def _build_categories_tab(self):
        frame = tk.Frame(self.content, bg=self.bg)
        toolbar = tk.Frame(frame, bg=self.bg2, pady=10, padx=16)
        toolbar.pack(fill="x")
        tk.Button(toolbar, text="+ ADD CATEGORY", font=self.font_header,
                  bg=self.teal, fg="#000", bd=0, padx=14, pady=6,
                  cursor="hand2", command=self._add_category_dialog).pack(side="left")
        tk.Button(toolbar, text="✕ DELETE", font=self.font_header,
                  bg=self.bg3, fg=self.red, bd=0, padx=14, pady=6,
                  cursor="hand2", command=self._delete_category).pack(side="left", padx=8)
        tree_frame = tk.Frame(frame, bg=self.bg)
        tree_frame.pack(fill="both", expand=True, padx=16, pady=12)
        self.categories_tree = ttk.Treeview(tree_frame, columns=("Category",),
                                             show="headings", style="Custom.Treeview")
        self.categories_tree.heading("Category", text="CATEGORY NAME")
        self.categories_tree.column("Category", width=600)
        self.categories_tree.pack(fill="both", expand=True)
        return frame

    # ── Summary tab ───────────────────────────────────────────────────────────
    def _build_summary_tab(self):
        frame = tk.Frame(self.content, bg=self.bg)
        self.summary_inner = tk.Frame(frame, bg=self.bg)
        self.summary_inner.pack(fill="both", expand=True, padx=24, pady=20)
        return frame

    def _refresh_summary(self):
        for w in self.summary_inner.winfo_children():
            w.destroy()
        records = self.data["records"]
        income  = sum(r["amount"] for r in records if r["type"] == "Income")
        expense = sum(r["amount"] for r in records if r["type"] == "Expense")
        wallet  = get_user_balance(self.username)

        cards = tk.Frame(self.summary_inner, bg=self.bg)
        cards.pack(fill="x", pady=(0, 20))
        for label, value, color in [
            ("TOTAL INCOME",  f"₹{income:,.2f}",  self.green),
            ("TOTAL EXPENSE", f"₹{expense:,.2f}", self.red),
            ("NET BALANCE",   f"₹{wallet:,.2f}",  self.green if wallet >= 0 else self.red),
        ]:
            card = tk.Frame(cards, bg=self.bg3, padx=24, pady=20,
                            highlightthickness=1, highlightbackground=self.border)
            card.pack(side="left", expand=True, fill="x", padx=8)
            tk.Label(card, text=label, font=("Calibri", 10, "bold"),
                     bg=self.bg3, fg=self.fg_dim).pack(anchor="w")
            tk.Label(card, text=value, font=("Calibri", 22, "bold"),
                     bg=self.bg3, fg=color).pack(anchor="w", pady=(4, 0))

        tk.Label(self.summary_inner, text="SPENDING BY CATEGORY",
                 font=("Calibri", 13, "bold"), bg=self.bg, fg=self.teal).pack(anchor="w", pady=(8, 6))
        cat_totals = {}
        for r in records:
            if r["type"] == "Expense":
                cat_totals[r["category"]] = cat_totals.get(r["category"], 0) + r["amount"]
        if cat_totals:
            max_val = max(cat_totals.values())
            for cat, total in sorted(cat_totals.items(), key=lambda x: -x[1]):
                row = tk.Frame(self.summary_inner, bg=self.bg)
                row.pack(fill="x", pady=3)
                tk.Label(row, text=f"{cat:<20}", font=self.font_body,
                         bg=self.bg, fg=self.fg, width=22, anchor="w").pack(side="left")
                bar_w  = int((total / max_val) * 340)
                bar_bg = tk.Frame(row, bg=self.border, width=340, height=4)
                bar_bg.pack(side="left", padx=8)
                bar_bg.pack_propagate(False)
                tk.Frame(bar_bg, bg=self.amber, width=bar_w, height=4).place(x=0, y=0)
                tk.Label(row, text=f"₹{total:,.2f}", font=self.font_body,
                         bg=self.bg, fg=self.fg_dim).pack(side="left", padx=6)
        else:
            tk.Label(self.summary_inner, text="No expense records yet.",
                     font=self.font_body, bg=self.bg, fg=self.fg_dim).pack(anchor="w")

        if len(records) >= self.MIN_RECORDS_FOR_CHART:
            tk.Frame(self.summary_inner, bg=self.border, height=1).pack(fill="x", pady=(18, 0))
            tk.Label(self.summary_inner, text="MONTHLY OVERVIEW",
                     font=("Calibri", 13, "bold"), bg=self.bg, fg=self.teal).pack(anchor="w", pady=(10, 6))
            chart_host = tk.Frame(self.summary_inner, bg=self.bg)
            chart_host.pack(fill="x")
            self._draw_monthly_histogram(chart_host, height=160, show_net=False)

    # ── Analytics tab ─────────────────────────────────────────────────────────
    def _build_analytics_tab(self):
        frame = tk.Frame(self.content, bg=self.bg)
        hdr = tk.Frame(frame, bg=self.bg2, pady=10, padx=16)
        hdr.pack(fill="x")
        tk.Label(hdr, text="📊  MONTHLY ANALYTICS", font=self.font_header,
                 bg=self.bg2, fg=self.teal).pack(side="left")
        tk.Label(hdr, text="Income vs Expenses vs Net — grouped by month",
                 font=self.font_small, bg=self.bg2, fg=self.fg_dim).pack(side="left", padx=12)

        outer = tk.Frame(frame, bg=self.bg)
        outer.pack(fill="both", expand=True)
        self._analytics_canvas = tk.Canvas(outer, bg=self.bg, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=self._analytics_canvas.yview)
        self._analytics_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._analytics_canvas.pack(side="left", fill="both", expand=True)

        self._analytics_inner = tk.Frame(self._analytics_canvas, bg=self.bg)
        self._analytics_win   = self._analytics_canvas.create_window(
            (0, 0), window=self._analytics_inner, anchor="nw")

        def on_inner_conf(e):
            self._analytics_canvas.configure(scrollregion=self._analytics_canvas.bbox("all"))
        def on_canvas_conf(e):
            self._analytics_canvas.itemconfig(self._analytics_win, width=e.width)

        self._analytics_inner.bind("<Configure>", on_inner_conf)
        self._analytics_canvas.bind("<Configure>", on_canvas_conf)

        def _on_mousewheel(e):
            self._analytics_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        self._analytics_canvas.bind_all("<MouseWheel>", _on_mousewheel)
        return frame

    def _refresh_analytics(self):
        for w in self._analytics_inner.winfo_children():
            w.destroy()
        records = self.data["records"]
        n = len(records)

        if n < self.MIN_RECORDS_FOR_CHART:
            remaining = self.MIN_RECORDS_FOR_CHART - n
            ph = tk.Frame(self._analytics_inner, bg=self.bg)
            ph.pack(expand=True, fill="both", pady=80)
            tk.Label(ph, text="📈", font=("Calibri", 48),
                     bg=self.bg, fg=self.fg_dim).pack()
            tk.Label(ph,
                     text=f"Add {remaining} more record{'s' if remaining != 1 else ''} to unlock analytics",
                     font=("Calibri", 16, "bold"), bg=self.bg, fg=self.fg_dim).pack(pady=(12, 4))
            tk.Label(ph, text=f"{n} of {self.MIN_RECORDS_FOR_CHART} records added",
                     font=self.font_small, bg=self.bg, fg=self.fg_muted).pack()
            pb_outer = tk.Frame(ph, bg=self.bg3, width=300, height=6)
            pb_outer.pack(pady=14)
            pb_outer.pack_propagate(False)
            tk.Frame(pb_outer, bg=self.teal,
                     width=int((n / self.MIN_RECORDS_FOR_CHART) * 300),
                     height=6).place(x=0, y=0)
            return

        sec1 = tk.Frame(self._analytics_inner, bg=self.bg, padx=20, pady=12)
        sec1.pack(fill="x")
        tk.Label(sec1, text="MONTHLY INCOME vs EXPENSES",
                 font=("Calibri", 13, "bold"), bg=self.bg, fg=self.teal).pack(anchor="w", pady=(0, 8))
        self._draw_monthly_histogram(sec1, height=240, show_net=True)

        tk.Frame(self._analytics_inner, bg=self.border, height=1).pack(fill="x", padx=20, pady=4)

        sec2 = tk.Frame(self._analytics_inner, bg=self.bg, padx=20, pady=12)
        sec2.pack(fill="x")
        tk.Label(sec2, text="MONTHLY NET SAVINGS",
                 font=("Calibri", 13, "bold"), bg=self.bg, fg=self.purple).pack(anchor="w", pady=(0, 8))
        self._draw_net_line_chart(sec2, height=180)

        tk.Frame(self._analytics_inner, bg=self.border, height=1).pack(fill="x", padx=20, pady=4)

        sec3 = tk.Frame(self._analytics_inner, bg=self.bg, padx=20, pady=12)
        sec3.pack(fill="x")
        tk.Label(sec3, text="EXPENSE BREAKDOWN BY CATEGORY & MONTH",
                 font=("Calibri", 13, "bold"), bg=self.bg, fg=self.amber).pack(anchor="w", pady=(0, 8))
        self._draw_category_breakdown(sec3, height=220)

    # ── chart helpers ─────────────────────────────────────────────────────────
    def _monthly_data(self):
        inc_by_month = defaultdict(float)
        exp_by_month = defaultdict(float)
        month_order  = {}
        for r in self.data["records"]:
            try:
                dt  = datetime.strptime(r["date"][:7], "%Y-%m")
                key = dt.strftime("%b '%y")
                month_order[key] = dt
                if r["type"] == "Income":
                    inc_by_month[key] += r["amount"]
                else:
                    exp_by_month[key] += r["amount"]
            except Exception:
                pass
        months = sorted(month_order.keys(), key=lambda k: month_order[k])
        return [(m, inc_by_month[m], exp_by_month[m]) for m in months]

    def _draw_monthly_histogram(self, parent, height=200, show_net=True):
        months = self._monthly_data()
        if not months:
            return
        PAD_L, PAD_R, PAD_T, PAD_B = 72, 24, 16, 48
        n = len(months)
        canvas_w = max(PAD_L + PAD_R + n * 64, 600)
        c = tk.Canvas(parent, bg="#2e2e2e", height=height, width=canvas_w, highlightthickness=0)
        c.pack(fill="x", expand=True)
        chart_h = height - PAD_T - PAD_B
        chart_w = canvas_w - PAD_L - PAD_R
        max_val = max((max(inc, exp) for _, inc, exp in months), default=1) or 1

        def y_pos(val):
            return PAD_T + chart_h - int((val / max_val) * chart_h)

        for frac in [0, 0.25, 0.5, 0.75, 1.0]:
            yy  = PAD_T + int(chart_h * (1 - frac))
            val = max_val * frac
            c.create_line(PAD_L, yy, canvas_w - PAD_R, yy, fill="#383838", dash=(4, 4))
            lbl = f"₹{val/1000:.0f}k" if val >= 1000 else f"₹{val:.0f}"
            c.create_text(PAD_L - 4, yy, text=lbl, anchor="e",
                          fill="#666666", font=("Calibri", 9))

        group_w = chart_w / n
        bar_w   = max(int(group_w * 0.3), 6)
        gap     = max(int(group_w * 0.06), 2)

        for i, (month, inc, exp) in enumerate(months):
            cx  = PAD_L + (i + 0.5) * group_w
            bx1 = int(cx - bar_w - gap)
            if inc > 0:
                y0 = y_pos(inc)
                c.create_rectangle(bx1, y0, bx1 + bar_w, PAD_T + chart_h,
                                   fill="#3dd68c", outline="", width=0)
                if y0 < PAD_T + chart_h - 14:
                    c.create_text(bx1 + bar_w // 2, y0 - 5,
                                  text=f"₹{inc/1000:.1f}k" if inc >= 1000 else f"₹{int(inc)}",
                                  fill="#3dd68c", font=("Calibri", 8), anchor="s")
            bx2 = int(cx + gap)
            if exp > 0:
                y0 = y_pos(exp)
                c.create_rectangle(bx2, y0, bx2 + bar_w, PAD_T + chart_h,
                                   fill="#ef5350", outline="", width=0)
                if y0 < PAD_T + chart_h - 14:
                    c.create_text(bx2 + bar_w // 2, y0 - 5,
                                  text=f"₹{exp/1000:.1f}k" if exp >= 1000 else f"₹{int(exp)}",
                                  fill="#ef5350", font=("Calibri", 8), anchor="s")
            if show_net:
                net = inc - exp
                if inc > 0 or exp > 0:
                    net_y = y_pos(max(inc, exp)) - 10
                    col   = "#3dd68c" if net >= 0 else "#ef5350"
                    sign  = "+" if net >= 0 else ""
                    c.create_text(int(cx), net_y,
                                  text=f"{sign}₹{abs(net)/1000:.1f}k" if abs(net) >= 1000
                                       else f"{sign}₹{int(abs(net))}",
                                  fill=col, font=("Calibri", 8, "bold"), anchor="s")
            c.create_text(int(cx), PAD_T + chart_h + 10, text=month,
                          fill="#888888", font=("Calibri", 9), anchor="n")

        c.create_line(PAD_L, PAD_T + chart_h, canvas_w - PAD_R, PAD_T + chart_h,
                      fill="#383838", width=1)
        leg_x = PAD_L
        for color, label in [("#3dd68c", "Income"), ("#ef5350", "Expense")]:
            c.create_rectangle(leg_x, PAD_T - 2, leg_x + 12, PAD_T + 8, fill=color, outline="")
            c.create_text(leg_x + 16, PAD_T + 3, text=label, anchor="w",
                          fill="#888888", font=("Calibri", 9))
            leg_x += 70
        if show_net:
            c.create_text(leg_x + 4, PAD_T + 3, text="Net shown above bars", anchor="w",
                          fill="#888888", font=("Calibri", 9, "italic"))

    def _draw_net_line_chart(self, parent, height=180):
        months = self._monthly_data()
        if not months:
            return
        PAD_L, PAD_R, PAD_T, PAD_B = 72, 24, 20, 40
        n = len(months)
        canvas_w = max(PAD_L + PAD_R + n * 64, 600)
        c = tk.Canvas(parent, bg="#2e2e2e", height=height, width=canvas_w, highlightthickness=0)
        c.pack(fill="x", expand=True)
        chart_h = height - PAD_T - PAD_B
        nets    = [inc - exp for _, inc, exp in months]
        max_abs = max((abs(v) for v in nets), default=1) or 1
        mid_y   = PAD_T + chart_h // 2

        def y_pos(val):
            return mid_y - int((val / max_abs) * (chart_h / 2))

        for sign, frac in [(1, 0.0), (0, 0.5), (-1, 1.0)]:
            yy  = PAD_T + int(chart_h * frac)
            val = max_abs * sign
            c.create_line(PAD_L, yy, canvas_w - PAD_R, yy, fill="#383838", dash=(4, 4))
            lbl = f"₹{val/1000:.0f}k" if abs(val) >= 1000 else f"₹{int(val)}"
            c.create_text(PAD_L - 4, yy, text=lbl, anchor="e",
                          fill="#888888", font=("Calibri", 9))

        group_w = (canvas_w - PAD_L - PAD_R) / max(n, 1)
        points  = []
        for i, net in enumerate(nets):
            px = PAD_L + (i + 0.5) * group_w
            py = y_pos(net)
            points.append((px, py))
            c.create_text(int(px), PAD_T + chart_h + 10, text=months[i][0],
                          fill="#888888", font=("Calibri", 9), anchor="n")

        for i in range(len(points) - 1):
            x1, y1 = points[i]; x2, y2 = points[i + 1]
            c.create_line(int(x1), int(y1), int(x2), int(y2),
                          fill="#7986cb", width=2, smooth=True)

        for i, (px, py) in enumerate(points):
            net = nets[i]
            col = "#3dd68c" if net >= 0 else "#ef5350"
            c.create_oval(px - 4, py - 4, px + 4, py + 4,
                          fill=col, outline="#2e2e2e", width=2)
            sign   = "+" if net >= 0 else ""
            lbl    = (f"{sign}₹{net/1000:.1f}k" if abs(net) >= 1000 else f"{sign}₹{int(net)}")
            anchor = "s" if net >= 0 else "n"
            offset = -8   if net >= 0 else 8
            c.create_text(int(px), int(py) + offset, text=lbl,
                          fill=col, font=("Calibri", 8, "bold"), anchor=anchor)

        c.create_line(PAD_L, mid_y, canvas_w - PAD_R, mid_y,
                      fill="#383838", width=1, dash=(2, 2))
        c.create_line(PAD_L, PAD_T + chart_h, canvas_w - PAD_R, PAD_T + chart_h,
                      fill="#383838", width=1)

    def _draw_category_breakdown(self, parent, height=220):
        records = [r for r in self.data["records"] if r["type"] == "Expense"]
        if not records:
            tk.Label(parent, text="No expense records yet.",
                     font=self.font_body, bg=self.bg, fg=self.fg_dim).pack(anchor="w")
            return
        month_order  = {}
        cat_by_month = defaultdict(lambda: defaultdict(float))
        for r in records:
            try:
                dt  = datetime.strptime(r["date"][:7], "%Y-%m")
                key = dt.strftime("%b '%y")
                month_order[key] = dt
                cat_by_month[key][r["category"]] += r["amount"]
            except Exception:
                pass
        months   = sorted(month_order.keys(), key=lambda k: month_order[k])
        all_cats = sorted({r["category"] for r in records})
        PALETTE  = ["#3dd68c", "#7986cb", "#ffa726", "#42a5f5",
                    "#ef5350", "#ec407a", "#48b8d0", "#e88c2a",
                    "#c066cf", "#3d9e6e"]
        PAD_L, PAD_R, PAD_T, PAD_B = 72, 16, 14, 36
        bar_h    = max(int((height - PAD_T - PAD_B - len(months) * 6) / max(len(months), 1)), 18)
        canvas_h = PAD_T + PAD_B + len(months) * (bar_h + 6)
        canvas_w = 780
        c = tk.Canvas(parent, bg="#2e2e2e", height=canvas_h, width=canvas_w, highlightthickness=0)
        c.pack(fill="x", expand=True)
        max_total = max(sum(cat_by_month[m].values()) for m in months) or 1
        bar_max_w = canvas_w - PAD_L - PAD_R

        for mi, month in enumerate(months):
            by_cat   = cat_by_month[month]
            total    = sum(by_cat.values())
            yy       = PAD_T + mi * (bar_h + 6)
            c.create_text(PAD_L - 6, yy + bar_h // 2, text=month, anchor="e",
                          fill="#f0f0f0", font=("Calibri", 9, "bold"))
            x_cursor = PAD_L
            for ci, cat in enumerate(all_cats):
                amt = by_cat.get(cat, 0)
                if amt <= 0:
                    continue
                seg_w = max(int((amt / max_total) * bar_max_w), 1)
                col   = PALETTE[ci % len(PALETTE)]
                c.create_rectangle(x_cursor, yy, x_cursor + seg_w, yy + bar_h,
                                   fill=col, outline="", width=0)
                if seg_w > 24:
                    c.create_text(x_cursor + seg_w // 2, yy + bar_h // 2,
                                  text=cat[:6], fill="#000000",
                                  font=("Calibri", 8), anchor="center")
                x_cursor += seg_w
            lbl = f"₹{total/1000:.1f}k" if total >= 1000 else f"₹{int(total)}"
            c.create_text(x_cursor + 4, yy + bar_h // 2, text=lbl,
                          anchor="w", fill="#888888", font=("Calibri", 9))

        leg_y = canvas_h - PAD_B + 6
        leg_x = PAD_L
        for ci, cat in enumerate(all_cats):
            col = PALETTE[ci % len(PALETTE)]
            c.create_rectangle(leg_x, leg_y, leg_x + 10, leg_y + 10, fill=col, outline="")
            c.create_text(leg_x + 13, leg_y + 5, text=cat, anchor="w",
                          fill="#888888", font=("Calibri", 9))
            leg_x += len(cat) * 7 + 22
            if leg_x > canvas_w - 120:
                leg_x  = PAD_L
                leg_y += 14

    # ── dialogs & actions ─────────────────────────────────────────────────────
    def _sync_emails(self):
        try:
            from email_poller import sync_emails
        except ImportError:
            messagebox.showerror(
                "Missing Module",
                "email_poller.py not found.\n"
                "Place it in the same folder as application.py."
            )
            return
        dlg = tk.Toplevel(self)
        dlg.title("Syncing Emails")
        dlg.configure(bg=self.bg)
        dlg.geometry("380x140")
        dlg.resizable(False, False)
        dlg.grab_set()
        tk.Label(dlg, text="📧  Connecting to Gmail…",
                 font=self.font_header, bg=self.bg, fg=self.teal).pack(pady=(28, 8))
        tk.Label(dlg, text="A browser window will open for sign-in on first run.",
                 font=self.font_small, bg=self.bg, fg=self.fg_dim).pack()
        dlg.update()
        try:
            result = sync_emails(
                username      = self.username,
                account_type  = self.account_type,
                personal_type = self.personal_type,
                days_back     = 30,
            )
            dlg.destroy()
            self.data = load_data(self.account_type, self.personal_type)
            self.refresh_all()
            messagebox.showinfo(
                "Sync Complete ✓",
                f"✓  {result['imported']} new transaction(s) imported\n"
                f"⏭  {result['skipped']} duplicate(s) skipped\n"
                f"✗  {result['failed']} email(s) could not be parsed"
            )
        except Exception as e:
            dlg.destroy()
            messagebox.showerror("Sync Failed", str(e))

    def _add_record_dialog(self):
        if not self.data["categories"]:
            messagebox.showwarning("No Categories", "Please add a category first.")
            return
        dlg = tk.Toplevel(self)
        dlg.title("Add Record")
        dlg.configure(bg=self.bg)
        dlg.geometry("440x420")
        dlg.resizable(False, False)
        dlg.grab_set()
        fields = {}

        def labeled(parent, text, widget_fn):
            row = tk.Frame(parent, bg=self.bg)
            row.pack(fill="x", pady=6)
            tk.Label(row, text=text, font=self.font_small, bg=self.bg,
                     fg=self.fg_dim, width=14, anchor="w").pack(side="left")
            w = widget_fn(row)
            w.pack(side="left", fill="x", expand=True, ipady=4)
            return w

        tk.Label(dlg, text="NEW RECORD", font=self.font_header,
                 bg=self.bg, fg=self.teal).pack(pady=(16, 8))
        inner = tk.Frame(dlg, bg=self.bg, padx=24)
        inner.pack(fill="both", expand=True)
        es = dict(bg=self.bg3, fg=self.fg, insertbackground=self.teal,
                  bd=0, font=self.font_body,
                  highlightthickness=1, highlightcolor=self.teal,
                  highlightbackground=self.border)

        fields["desc"]   = labeled(inner, "Description", lambda p: tk.Entry(p, **es))
        fields["amount"] = labeled(inner, "Amount (₹)",  lambda p: tk.Entry(p, **es))

        type_var = tk.StringVar(value="Expense")
        def mk_type(p):
            fr = tk.Frame(p, bg=self.bg)
            for t in ["Expense", "Income"]:
                tk.Radiobutton(fr, text=t, variable=type_var, value=t,
                               font=self.font_body, bg=self.bg, fg=self.fg,
                               selectcolor=self.bg3, activebackground=self.bg,
                               activeforeground=self.teal).pack(side="left", padx=6)
            return fr
        labeled(inner, "Type", mk_type)

        cat_var = tk.StringVar(value=self.data["categories"][0])
        labeled(inner, "Category",
                lambda p: ttk.Combobox(p, textvariable=cat_var,
                                       values=self.data["categories"],
                                       font=self.font_body, state="readonly"))

        date_entry = labeled(inner, "Date", lambda p: tk.Entry(p, **es))
        date_entry.insert(0, datetime.now().strftime("%Y-%m-%d"))

        def submit():
            desc   = fields["desc"].get().strip()
            amount = fields["amount"].get().strip()
            if not desc or not amount:
                messagebox.showerror("Error", "Description and amount are required.")
                return
            try:
                amount = float(amount)
            except ValueError:
                messagebox.showerror("Error", "Amount must be a number.")
                return
            pt = _pt_key(self.personal_type)
            with _db() as conn:
                conn.execute(
                    """INSERT INTO records
                       (username, account_type, personal_type, date, description,
                        amount, txn_type, account_label, category, source)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual')""",
                    (self.username, self.account_type, pt,
                     date_entry.get().strip(), desc, amount,
                     type_var.get(), self.username, cat_var.get())
                )
            if type_var.get() == "Expense":
                deduct_user_balance(self.username, amount)
            else:
                add_user_balance(self.username, amount)
            self.data = load_data(self.account_type, self.personal_type)
            self.refresh_all()
            dlg.destroy()

        tk.Button(inner, text="SAVE RECORD", font=self.font_header,
                  bg=self.teal, fg="#000", bd=0, padx=16, pady=8,
                  cursor="hand2", command=submit).pack(pady=12)

    def _edit_record_dialog(self):
        sel = self.records_tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Please select a record to edit.")
            return
        rec = self._filtered_records()[self.records_tree.index(sel[0])]

        if not self.data["categories"]:
            messagebox.showwarning("No Categories", "Please add a category first.")
            return

        dlg = tk.Toplevel(self)
        dlg.title("Edit Record")
        dlg.configure(bg=self.bg)
        dlg.geometry("440x440")
        dlg.resizable(False, False)
        dlg.grab_set()
        fields = {}

        def labeled(parent, text, widget_fn):
            row = tk.Frame(parent, bg=self.bg)
            row.pack(fill="x", pady=6)
            tk.Label(row, text=text, font=self.font_small, bg=self.bg,
                     fg=self.fg_dim, width=14, anchor="w").pack(side="left")
            w = widget_fn(row)
            w.pack(side="left", fill="x", expand=True, ipady=4)
            return w

        tk.Label(dlg, text="EDIT RECORD", font=self.font_header,
                 bg=self.bg, fg=self.blue).pack(pady=(16, 8))
        inner = tk.Frame(dlg, bg=self.bg, padx=24)
        inner.pack(fill="both", expand=True)
        es = dict(bg=self.bg3, fg=self.fg, insertbackground=self.teal,
                  bd=0, font=self.font_body,
                  highlightthickness=1, highlightcolor=self.teal,
                  highlightbackground=self.border)

        fields["desc"] = labeled(inner, "Description", lambda p: tk.Entry(p, **es))
        fields["desc"].insert(0, rec["description"])

        fields["amount"] = labeled(inner, "Amount (₹)", lambda p: tk.Entry(p, **es))
        fields["amount"].insert(0, str(rec["amount"]))

        type_var = tk.StringVar(value=rec["type"])
        def mk_type(p):
            fr = tk.Frame(p, bg=self.bg)
            for t in ["Expense", "Income"]:
                tk.Radiobutton(fr, text=t, variable=type_var, value=t,
                               font=self.font_body, bg=self.bg, fg=self.fg,
                               selectcolor=self.bg3, activebackground=self.bg,
                               activeforeground=self.teal).pack(side="left", padx=6)
            return fr
        labeled(inner, "Type", mk_type)

        cats = self.data["categories"]
        default_cat = rec["category"] if rec["category"] in cats else (cats[0] if cats else "")
        cat_var = tk.StringVar(value=default_cat)
        labeled(inner, "Category",
                lambda p: ttk.Combobox(p, textvariable=cat_var,
                                       values=cats,
                                       font=self.font_body, state="readonly"))

        date_entry = labeled(inner, "Date", lambda p: tk.Entry(p, **es))
        date_entry.insert(0, rec["date"])

        err_lbl = tk.Label(inner, text="", font=self.font_small,
                           bg=self.bg, fg=self.red)
        err_lbl.pack(pady=(2, 0))

        def submit():
            desc   = fields["desc"].get().strip()
            amount = fields["amount"].get().strip()
            if not desc or not amount:
                err_lbl.config(text="⚠  Description and amount are required.")
                return
            try:
                new_amount = float(amount)
                if new_amount <= 0:
                    raise ValueError
            except ValueError:
                err_lbl.config(text="⚠  Amount must be a positive number.")
                return

            new_type   = type_var.get()
            old_type   = rec["type"]
            old_amount = rec["amount"]

            # Reverse the old transaction's effect on the wallet
            if old_type == "Expense":
                add_user_balance(self.username, old_amount)
            else:
                deduct_user_balance(self.username, old_amount)

            # Apply the new transaction's effect
            if new_type == "Expense":
                deduct_user_balance(self.username, new_amount)
            else:
                add_user_balance(self.username, new_amount)

            with _db() as conn:
                conn.execute(
                    """UPDATE records
                       SET date=?, description=?, amount=?, txn_type=?, category=?
                       WHERE id=?""",
                    (date_entry.get().strip(), desc, new_amount,
                     new_type, cat_var.get(), rec["id"])
                )
            self.data = load_data(self.account_type, self.personal_type)
            self.refresh_all()
            dlg.destroy()

        tk.Button(inner, text="SAVE CHANGES", font=self.font_header,
                  bg=self.blue, fg="#000", bd=0, padx=16, pady=8,
                  cursor="hand2", activebackground="#1a6fbb",
                  command=submit).pack(pady=12)

    def _add_category_dialog(self):
        name = simpledialog.askstring("Add Category", "Category name:", parent=self)
        if name and name.strip():
            pt = _pt_key(self.personal_type)
            with _db() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO categories
                       (username, account_type, personal_type, name)
                       VALUES (?, ?, ?, ?)""",
                    (self.username, self.account_type, pt, name.strip())
                )
            self.data = load_data(self.account_type, self.personal_type)
            self.refresh_all()

    def _delete_record(self):
        sel = self.records_tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Please select a record to delete.")
            return
        rec = self._filtered_records()[self.records_tree.index(sel[0])]
        if rec["type"] == "Expense":
            add_user_balance(self.username, rec["amount"])
        else:
            deduct_user_balance(self.username, rec["amount"])
        with _db() as conn:
            conn.execute("DELETE FROM records WHERE id = ?", (rec["id"],))
        self.data = load_data(self.account_type, self.personal_type)
        self.refresh_all()

    def _delete_category(self):
        sel = self.categories_tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Please select a category to delete.")
            return
        cat_name = self.data["categories"][self.categories_tree.index(sel[0])]
        pt = _pt_key(self.personal_type)
        with _db() as conn:
            conn.execute(
                "DELETE FROM categories WHERE account_type=? AND personal_type=? AND name=?",
                (self.account_type, pt, cat_name)
            )
        self.data = load_data(self.account_type, self.personal_type)
        self.refresh_all()

    def _filtered_records(self):
        q = self.filter_var.get().lower()
        return [r for r in self.data["records"]
                if not q or q in r["description"].lower()
                or q in r["category"].lower()
                or q in r["account"].lower()]

    def _refresh_records(self):
        for row in self.records_tree.get_children():
            self.records_tree.delete(row)
        income = expense = count = 0
        for r in self._filtered_records():
            tag = "income" if r["type"] == "Income" else "expense"
            self.records_tree.insert("", "end", tags=(tag,), values=(
                r["date"], r["description"],
                f"₹{r['amount']:,.2f}", r["type"],
                r["account"], r["category"]
            ))
            if r["type"] == "Income":
                income  += r["amount"]
            else:
                expense += r["amount"]
            count += 1
        self.records_tree.tag_configure("income",  foreground="#f0f0f0")
        self.records_tree.tag_configure("expense", foreground="#ef5350")
        self.lbl_income.config( text=f"Income:   ₹{income:,.2f}")
        self.lbl_expense.config(text=f"Expenses: ₹{expense:,.2f}")
        self.lbl_txn_count.config(text=f"Transactions: {count}")
        self.lbl_balance.config(text=f"Balance:  ₹{income - expense:,.2f}",
                                fg=self.green if income >= expense else self.red)

    def _refresh_categories(self):
        for row in self.categories_tree.get_children():
            self.categories_tree.delete(row)
        for cat in self.data["categories"]:
            self.categories_tree.insert("", "end", values=(cat,))

    def refresh_all(self):
        self._refresh_records()
        self._refresh_categories()
        bal = get_user_balance(self.username)
        self.balance_lbl.config(
            text=f"Wallet: ₹{bal:,.2f}",
            fg=self.green if bal >= 0 else self.red
        )


# ── entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    LoginWindow().mainloop()