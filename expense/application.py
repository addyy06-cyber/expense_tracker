import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import json
import os
from datetime import datetime
from PIL import Image, ImageTk, ImageDraw, ImageFont

DATA_FILE  = "expense_data.json"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH  = os.path.join(SCRIPT_DIR, "IMG_0023.GIF")

# gradient colours  (dark teal → light teal based on #7ab9c0)
GRAD_START = (50,  120, 130)
GRAD_END   = (180, 230, 235)
BG_RGB     = (15,  15,  15)    # matches #0f0f0f login bg

# ── shared logo loader ────────────────────────────────────────────────────────
def load_logo(size):
    if not os.path.exists(LOGO_PATH):
        return None
    img = Image.open(LOGO_PATH).convert("RGBA")
    img.thumbnail((size, size), Image.LANCZOS)
    return ImageTk.PhotoImage(img)


# ── gradient text renderer ────────────────────────────────────────────────────
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
    d      = ImageDraw.Draw(canvas)
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


# ── persistence ───────────────────────────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"accounts": [], "categories": [], "records": []}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ── login / onboarding window ─────────────────────────────────────────────────
class LoginWindow(tk.Tk):
    SPLASH_HOLD_MS = 1800
    FADE_STEPS     = 35
    FADE_INTERVAL  = 16

    def __init__(self):
        super().__init__()
        self.title("Expense Tracker")
        self.geometry("520x600")
        self.resizable(False, False)

        self.bg      = "#0f0f0f"
        self.bg2     = "#1a1a1a"
        self.bg3     = "#252525"
        self.accent  = "#f5c518"
        self.teal    = "#7ab9c0"
        self.fg      = "#e8e8e8"
        self.fg_dim  = "#666666"
        self.green   = "#4caf7d"
        self.red     = "#e05555"
        self.border  = "#2e2e2e"

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

    # ── login helpers ─────────────────────────────────────────────────────────
    def _clear_login(self):
        for w in self.login_frame.winfo_children():
            w.destroy()

    def _entry(self, parent, textvariable=None, show=None):
        kw = dict(bg=self.bg3, fg=self.fg, insertbackground=self.accent,
                  bd=0, font=self.font_body, width=28,
                  highlightthickness=1, highlightcolor=self.teal,
                  highlightbackground=self.border)
        if textvariable: kw["textvariable"] = textvariable
        if show:         kw["show"] = show
        return tk.Entry(parent, **kw)

    def _card_btn(self, parent, icon, title, subtitle, command):
        card = tk.Frame(parent, bg=self.bg3, cursor="hand2",
                        highlightthickness=1, highlightbackground=self.border)
        card.pack(fill="x", pady=6)
        inner = tk.Frame(card, bg=self.bg3, padx=20, pady=16)
        inner.pack(fill="x")
        tk.Label(inner, text=icon, font=("Calibri", 26),
                 bg=self.bg3, fg=self.teal).pack(side="left", padx=(0, 14))
        txt = tk.Frame(inner, bg=self.bg3)
        txt.pack(side="left", fill="x", expand=True)

        # gradient card title
        gradient_label(txt, title, pil_size=14, bold=True,
                       bg_rgb=(37, 37, 37), side="top", pady=0)
        tk.Label(txt, text=subtitle, font=self.font_small,
                 bg=self.bg3, fg=self.fg_dim, anchor="w").pack(fill="x")

        arrow = tk.Label(inner, text="→", font=("Calibri", 16),
                         bg=self.bg3, fg=self.fg_dim)
        arrow.pack(side="right")

        def on_enter(e):
            card.config(highlightbackground=self.teal)
            arrow.config(fg=self.teal)
        def on_leave(e):
            card.config(highlightbackground=self.border)
            arrow.config(fg=self.fg_dim)

        for w in [card, inner, txt, arrow] + inner.winfo_children() + txt.winfo_children():
            w.bind("<Button-1>", lambda e, c=command: c())
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)

    def _header(self, parent, step, title, subtitle=None):
        top = tk.Frame(parent, bg=self.bg)
        top.pack(pady=(24, 2))

        logo = load_logo(36)
        if logo:
            self._img_refs.append(logo)
            tk.Label(top, image=logo, bg=self.bg).pack(side="left", padx=(0, 8))

        gradient_label(top, "EXPENSE TRACKER", pil_size=12,
                       bg_rgb=BG_RGB, side="left")

        gradient_label(parent, title, pil_size=28, bold=True,
                       bg_rgb=BG_RGB, pady=(2, 0))

        if subtitle:
            tk.Label(parent, text=subtitle, font=self.font_small,
                     bg=self.bg, fg=self.teal).pack(pady=(4, 0))

        step_frame = tk.Frame(parent, bg=self.bg)
        step_frame.pack(pady=14)
        for i in range(1, 4):
            color = self.teal if i == step else self.bg3
            tk.Frame(step_frame, bg=color, width=28, height=4).pack(side="left", padx=3)

    # ── login screens ─────────────────────────────────────────────────────────
    def _build_login_content(self):
        self._clear_login()
        f = self.login_frame
        self._header(f, 1, "SIGN IN", "Enter your credentials to continue")
        form = tk.Frame(f, bg=self.bg, padx=60)
        form.pack(fill="x", pady=10)

        gradient_label(form, "USERNAME", pil_size=12, pady=(10, 2))
        u_entry = self._entry(form, textvariable=self.username_var)
        u_entry.pack(fill="x", ipady=6)

        gradient_label(form, "PASSWORD", pil_size=12, pady=(12, 2))
        p_entry = self._entry(form, textvariable=self.password_var, show="●")
        p_entry.pack(fill="x", ipady=6)

        self.lbl_error = tk.Label(form, text="", font=self.font_small,
                                   bg=self.bg, fg=self.red)
        self.lbl_error.pack(pady=(6, 0))

        tk.Button(form, text="CONTINUE →", font=self.font_header,
                  bg=self.teal, fg="#000", bd=0, pady=10, cursor="hand2",
                  activebackground="#5a9aa0",
                  command=self._check_login).pack(fill="x", pady=(16, 0))

        tk.Label(form, text="Demo: any username + password works",
                 font=self.font_small, bg=self.bg, fg="#444").pack(pady=(8, 0))

        u_entry.focus()
        self.bind("<Return>", lambda e: self._check_login())

    def _check_login(self):
        if not self.username_var.get().strip():
            self.lbl_error.config(text="⚠  Username cannot be empty.")
            return
        if not self.password_var.get().strip():
            self.lbl_error.config(text="⚠  Password cannot be empty.")
            return
        self._build_account_type()

    def _build_account_type(self):
        self._clear_login()
        f = self.login_frame
        self._header(f, 2, "ACCOUNT TYPE", "How will you be using this tracker?")
        cards = tk.Frame(f, bg=self.bg, padx=50)
        cards.pack(fill="x", pady=8)
        self._card_btn(cards, "👤", "Personal Account",
                       "Track your own income and expenses",
                       self._build_personal_type)
        self._card_btn(cards, "👨\u200d👩\u200d👧\u200d👦", "Family Account",
                       "Shared tracker for household finances",
                       self._build_family_categories)
        tk.Button(f, text="← Back", font=self.font_small,
                  bg=self.bg, fg=self.fg_dim, bd=0, cursor="hand2",
                  activebackground=self.bg, activeforeground=self.teal,
                  command=self._build_login_content).pack(pady=(12, 0))

    def _build_personal_type(self):
        self._clear_login()
        f = self.login_frame
        self._header(f, 3, "YOUR PROFILE", "Tell us a bit more about yourself")
        cards = tk.Frame(f, bg=self.bg, padx=50)
        cards.pack(fill="x", pady=8)
        self._card_btn(cards, "🎓", "Student",
                       "Budget-focused tracking for tuition, food & essentials",
                       lambda: self._launch("Personal", "Student"))
        self._card_btn(cards, "💼", "Employee",
                       "Salary, bills, savings and investment tracking",
                       lambda: self._launch("Personal", "Employee"))
        tk.Button(f, text="← Back", font=self.font_small,
                  bg=self.bg, fg=self.fg_dim, bd=0, cursor="hand2",
                  activebackground=self.bg, activeforeground=self.teal,
                  command=self._build_account_type).pack(pady=(12, 0))

    def _build_family_categories(self):
        self._clear_login()
        f = self.login_frame
        self._header(f, 3, "FAMILY BUDGET", "Select a category to log spending")

        CATEGORIES = [
            ("🛒", "Groceries"),
            ("🏠", "Housing"),
            ("👗", "Clothing"),
            ("🎓", "Education"),
            ("🏥", "Healthcare"),
            ("🚗", "Transportation"),
        ]

        grid_outer = tk.Frame(f, bg=self.bg, padx=40)
        grid_outer.pack(fill="both", expand=True, pady=10)

        for i, (icon, label) in enumerate(CATEGORIES):
            row, col = divmod(i, 3)

            btn_canvas = tk.Canvas(
                grid_outer, width=130, height=80,
                bg=self.bg, highlightthickness=0, cursor="hand2"
            )
            btn_canvas.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
            grid_outer.columnconfigure(col, weight=1)
            grid_outer.rowconfigure(row, weight=1)

            def draw_btn(canvas, ico, lbl, hover=False):
                canvas.delete("all")
                w, h = 130, 80
                r = 16
                fill  = "#1e5f6a" if hover else self.bg3
                outline = self.teal if hover else self.border
                # rounded rectangle via polygon
                points = [
                    r, 0, w - r, 0,
                    w, 0, w, r,
                    w, h - r, w, h,
                    w - r, h, r, h,
                    0, h, 0, h - r,
                    0, r, 0, 0,
                ]
                canvas.create_polygon(points, smooth=True,
                                      fill=fill, outline=outline, width=2)
                canvas.create_text(65, 26, text=ico, font=("Calibri", 20), fill=self.teal)
                canvas.create_text(65, 56, text=lbl, font=("Calibri", 11, "bold"),
                                   fill=self.fg if not hover else "#ffffff")

            draw_btn(btn_canvas, icon, label)

            def make_handlers(canvas, ico, lbl):
                def on_enter(e):
                    draw_btn(canvas, ico, lbl, hover=True)
                def on_leave(e):
                    draw_btn(canvas, ico, lbl, hover=False)
                def on_click(e):
                    self._build_category_entry_page(lbl)
                return on_enter, on_leave, on_click

            enter_fn, leave_fn, click_fn = make_handlers(btn_canvas, icon, label)
            btn_canvas.bind("<Enter>", enter_fn)
            btn_canvas.bind("<Leave>", leave_fn)
            btn_canvas.bind("<Button-1>", click_fn)

        bottom = tk.Frame(f, bg=self.bg)
        bottom.pack(fill="x", pady=(6, 12), padx=40)
        tk.Button(bottom, text="← Back", font=self.font_small,
                  bg=self.bg, fg=self.fg_dim, bd=0, cursor="hand2",
                  activebackground=self.bg, activeforeground=self.teal,
                  command=self._build_account_type).pack(side="left")
        tk.Button(bottom, text="OPEN FULL TRACKER →", font=self.font_small,
                  bg=self.teal, fg="#000", bd=0, padx=12, pady=6, cursor="hand2",
                  activebackground="#5a9aa0",
                  command=lambda: self._launch("Family", None)).pack(side="right")

    def _build_category_entry_page(self, category):
        """Full-page expense entry for a given category with item list."""
        self._clear_login()
        f = self.login_frame

        ICONS = {
            "Groceries": "🛒", "Housing": "🏠", "Clothing": "👗",
            "Education": "🎓", "Healthcare": "🏥", "Transportation": "🚗",
        }
        icon = ICONS.get(category, "💰")

        # ── header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(f, bg=self.bg, pady=16)
        hdr.pack(fill="x", padx=30)

        logo = load_logo(32)
        if logo:
            self._img_refs.append(logo)
            tk.Label(hdr, image=logo, bg=self.bg).pack(side="left", padx=(0, 8))
        gradient_label(hdr, "EXPENSE TRACKER", pil_size=11, bg_rgb=BG_RGB, side="left")

        tk.Frame(f, bg=self.border, height=1).pack(fill="x")

        # ── title row ─────────────────────────────────────────────────────────
        title_row = tk.Frame(f, bg=self.bg, pady=12)
        title_row.pack(fill="x", padx=30)
        tk.Label(title_row, text=icon, font=("Calibri", 30),
                 bg=self.bg, fg=self.teal).pack(side="left", padx=(0, 10))
        title_col = tk.Frame(title_row, bg=self.bg)
        title_col.pack(side="left")
        gradient_label(title_col, category.upper(), pil_size=22, bold=True,
                       bg_rgb=BG_RGB, pady=0)
        tk.Label(title_col, text=datetime.now().strftime("%A, %d %b %Y"),
                 font=self.font_small, bg=self.bg, fg=self.fg_dim).pack(anchor="w")

        tk.Frame(f, bg=self.border, height=1).pack(fill="x")

        # ── two-column body ───────────────────────────────────────────────────
        body = tk.Frame(f, bg=self.bg)
        body.pack(fill="both", expand=True, padx=30, pady=16)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        # LEFT: input form
        left = tk.Frame(body, bg=self.bg)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 20))

        tk.Label(left, text="ADD ITEM", font=self.font_header,
                 bg=self.bg, fg=self.accent).pack(anchor="w", pady=(0, 10))

        es = dict(bg=self.bg3, fg=self.fg, insertbackground=self.teal,
                  bd=0, font=self.font_body,
                  highlightthickness=1, highlightcolor=self.teal,
                  highlightbackground=self.border)

        tk.Label(left, text="Item / Description", font=self.font_small,
                 bg=self.bg, fg=self.fg_dim).pack(anchor="w")
        item_var = tk.StringVar()
        item_entry = tk.Entry(left, textvariable=item_var, **es)
        item_entry.pack(fill="x", ipady=7, pady=(2, 10))

        tk.Label(left, text="Amount Spent (₹)", font=self.font_small,
                 bg=self.bg, fg=self.fg_dim).pack(anchor="w")
        amount_var = tk.StringVar()
        amount_entry = tk.Entry(left, textvariable=amount_var, **es)
        amount_entry.pack(fill="x", ipady=7, pady=(2, 10))

        msg_lbl = tk.Label(left, text="", font=self.font_small,
                            bg=self.bg, fg=self.red, anchor="w")
        msg_lbl.pack(fill="x")

        # pending items list (in-memory before saving)
        pending_items = []   # list of {"item": str, "amount": float}

        # RIGHT: items list display
        right = tk.Frame(body, bg=self.bg2,
                         highlightthickness=1, highlightbackground=self.border)
        right.grid(row=0, column=1, sticky="nsew")

        tk.Label(right, text="ITEMS ADDED", font=self.font_header,
                 bg=self.bg2, fg=self.accent).pack(anchor="w", padx=14, pady=(12, 6))
        tk.Frame(right, bg=self.border, height=1).pack(fill="x")

        scroll_canvas = tk.Canvas(right, bg=self.bg2, highlightthickness=0)
        scrollbar = ttk.Scrollbar(right, orient="vertical",
                                   command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        scroll_canvas.pack(side="left", fill="both", expand=True)

        items_frame = tk.Frame(scroll_canvas, bg=self.bg2)
        items_win = scroll_canvas.create_window((0, 0), window=items_frame,
                                                 anchor="nw")

        def on_frame_configure(e):
            scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))
        def on_canvas_configure(e):
            scroll_canvas.itemconfig(items_win, width=e.width)
        items_frame.bind("<Configure>", on_frame_configure)
        scroll_canvas.bind("<Configure>", on_canvas_configure)

        total_lbl = tk.Label(right, text="Total: ₹0.00",
                              font=("Calibri", 13, "bold"),
                              bg=self.bg2, fg=self.teal)
        total_lbl.pack(side="bottom", anchor="e", padx=14, pady=8)
        tk.Frame(right, bg=self.border, height=1).pack(side="bottom", fill="x")

        def refresh_items_panel():
            for w in items_frame.winfo_children():
                w.destroy()
            if not pending_items:
                tk.Label(items_frame, text="No items yet.",
                         font=self.font_small, bg=self.bg2,
                         fg=self.fg_dim).pack(padx=14, pady=10, anchor="w")
            else:
                for idx, entry_data in enumerate(pending_items):
                    row = tk.Frame(items_frame, bg=self.bg2)
                    row.pack(fill="x", padx=10, pady=3)
                    num = tk.Label(row, text=f"{idx+1}.",
                                   font=self.font_small, bg=self.bg2,
                                   fg=self.fg_dim, width=3)
                    num.pack(side="left")
                    tk.Label(row, text=entry_data["item"],
                             font=self.font_body, bg=self.bg2,
                             fg=self.fg, anchor="w").pack(side="left", fill="x",
                                                           expand=True, padx=(4, 0))
                    tk.Label(row, text=f"₹{entry_data['amount']:,.2f}",
                             font=("Calibri", 12, "bold"), bg=self.bg2,
                             fg=self.teal).pack(side="right", padx=(4, 4))
                    # delete button
                    def make_del(i):
                        def do_del():
                            pending_items.pop(i)
                            refresh_items_panel()
                        return do_del
                    tk.Button(row, text="✕", font=("Calibri", 10),
                              bg=self.bg2, fg=self.red, bd=0, cursor="hand2",
                              activebackground=self.bg2,
                              command=make_del(idx)).pack(side="right")

            total = sum(e["amount"] for e in pending_items)
            total_lbl.config(text=f"Total: ₹{total:,.2f}")

        refresh_items_panel()

        def add_item():
            item_name = item_var.get().strip()
            raw = amount_var.get().strip()
            if not item_name:
                msg_lbl.config(text="⚠  Please enter an item name.")
                return
            try:
                amount = float(raw)
                if amount <= 0:
                    raise ValueError
            except ValueError:
                msg_lbl.config(text="⚠  Enter a valid positive amount.")
                return
            msg_lbl.config(text="")
            pending_items.append({"item": item_name, "amount": amount})
            item_var.set("")
            amount_var.set("")
            item_entry.focus()
            refresh_items_panel()

        def save_all():
            if not pending_items:
                msg_lbl.config(text="⚠  Add at least one item first.")
                return
            data = load_data()
            if not any(a["name"] == "Family" for a in data["accounts"]):
                data["accounts"].append({"name": "Family", "balance": 0})
            if category not in data["categories"]:
                data["categories"].append(category)
            for entry_data in pending_items:
                data["records"].append({
                    "id": len(data["records"]),
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "description": entry_data["item"],
                    "amount": entry_data["amount"],
                    "type": "Expense",
                    "account": "Family",
                    "category": category,
                })
            save_data(data)
            total = sum(e["amount"] for e in pending_items)
            messagebox.showinfo(
                "Saved ✓",
                f"{len(pending_items)} item(s) saved under {category}.\n"
                f"Total: ₹{total:,.2f}",
                parent=self
            )
            self._build_family_categories()

        # ── Add Item button ───────────────────────────────────────────────────
        tk.Button(left, text="+ ADD ITEM", font=self.font_header,
                  bg=self.bg3, fg=self.teal, bd=0, pady=8, cursor="hand2",
                  activebackground="#1e3a3e", activeforeground=self.teal,
                  highlightthickness=1, highlightbackground=self.teal,
                  command=add_item).pack(fill="x", pady=(4, 0))

        item_entry.bind("<Return>", lambda e: amount_entry.focus())
        amount_entry.bind("<Return>", lambda e: add_item())
        item_entry.focus()

        # ── bottom bar ────────────────────────────────────────────────────────
        tk.Frame(f, bg=self.border, height=1).pack(fill="x")
        bottom = tk.Frame(f, bg=self.bg, pady=10)
        bottom.pack(fill="x", padx=30)

        tk.Button(bottom, text="← Back", font=self.font_small,
                  bg=self.bg, fg=self.fg_dim, bd=0, cursor="hand2",
                  activebackground=self.bg, activeforeground=self.teal,
                  command=self._build_family_categories).pack(side="left")

        tk.Button(bottom, text="SAVE ALL EXPENSES ✓", font=self.font_header,
                  bg=self.teal, fg="#000", bd=0, padx=20, pady=8,
                  cursor="hand2", activebackground="#5a9aa0",
                  command=save_all).pack(side="right")

    def _launch(self, account_type, personal_type):
        self.destroy()
        app = ExpenseTracker(account_type=account_type,
                             personal_type=personal_type,
                             username=self.username_var.get().strip())
        app.mainloop()


# ── main app ──────────────────────────────────────────────────────────────────
class ExpenseTracker(tk.Tk):
    def __init__(self, account_type="Personal", personal_type="Student", username="User"):
        super().__init__()
        self.account_type  = account_type
        self.personal_type = personal_type
        self.username      = username

        self.title("Expense Tracker")
        self.geometry("1000x680")
        self.resizable(True, True)

        self.font_title  = ("Calibri", 28, "bold")
        self.font_header = ("Calibri", 14, "bold")
        self.font_body   = ("Calibri", 13)
        self.font_small  = ("Calibri", 12)

        self.bg      = "#034752"
        self.bg2     = "#020202"
        self.bg3     = "#252525"
        self.accent  = "#7ab9c0"
        self.accent2 = "#df7a36"
        self.fg      = "#e8e8e8"
        self.fg_dim  = "#666666"
        self.green   = "#4caf7d"
        self.red     = "#e05555"
        self.border  = "#2e2e2e"

        self.configure(bg=self.bg)
        self._img_refs = []

        self.data = load_data()
        self._build_ui()
        self.refresh_all()

    def _build_ui(self):
        title_bar = tk.Frame(self, bg=self.bg, pady=10)
        title_bar.pack(fill="x", padx=16)

        logo = load_logo(40)
        if logo:
            self._img_refs.append(logo)
            tk.Label(title_bar, image=logo, bg=self.bg).pack(side="left", padx=(0, 10))

        tk.Label(title_bar, text="EXPENSE TRACKER", font=self.font_title,
                 bg=self.bg, fg=self.accent).pack(side="left")

        badge = f"{self.username}  ·  {self.account_type}"
        if self.personal_type:
            badge += f" / {self.personal_type}"
        tk.Label(title_bar, text=badge, font=("Calibri", 11),
                 bg=self.bg, fg=self.fg_dim).pack(side="left", padx=14)
        tk.Label(title_bar, text=datetime.now().strftime("%A, %d %b %Y"),
                 font=self.font_small, bg=self.bg, fg=self.fg_dim).pack(side="right", padx=4)

        tk.Frame(self, bg=self.border, height=1).pack(fill="x")

        tab_bar = tk.Frame(self, bg=self.bg2)
        tab_bar.pack(fill="x")
        self.tab_btns = {}
        for label in ["Records", "Accounts", "Categories", "Summary"]:
            btn = tk.Button(tab_bar, text=label.upper(), font=self.font_header,
                            bg=self.bg2, fg=self.fg_dim, bd=0, padx=20, pady=10,
                            cursor="hand2", activebackground=self.bg2,
                            activeforeground=self.accent,
                            command=lambda l=label: self._switch_tab(l))
            btn.pack(side="left")
            self.tab_btns[label] = btn

        tk.Frame(self, bg=self.border, height=1).pack(fill="x")

        self.content = tk.Frame(self, bg=self.bg)
        self.content.pack(fill="both", expand=True)

        self.frames = {
            "Records":    self._build_records_tab(),
            "Accounts":   self._build_accounts_tab(),
            "Categories": self._build_categories_tab(),
            "Summary":    self._build_summary_tab(),
        }
        self._switch_tab("Records")

    def _switch_tab(self, name):
        for f in self.frames.values():
            f.pack_forget()
        self.frames[name].pack(fill="both", expand=True)
        for n, b in self.tab_btns.items():
            b.config(fg=self.accent if n == name else self.fg_dim,
                     bg=self.bg3 if n == name else self.bg2)
        if name == "Summary":
            self._refresh_summary()

    def _build_records_tab(self):
        frame = tk.Frame(self.content, bg=self.bg)
        toolbar = tk.Frame(frame, bg=self.bg2, pady=10, padx=16)
        toolbar.pack(fill="x")
        tk.Button(toolbar, text="+ ADD RECORD", font=self.font_header,
                  bg=self.accent, fg="#000", bd=0, padx=14, pady=6,
                  cursor="hand2", activebackground="#d4a800",
                  command=self._add_record_dialog).pack(side="left")
        tk.Button(toolbar, text="✕ DELETE", font=self.font_header,
                  bg=self.bg3, fg=self.red, bd=0, padx=14, pady=6,
                  cursor="hand2", command=self._delete_record).pack(side="left", padx=8)

        filter_frame = tk.Frame(toolbar, bg=self.bg2)
        filter_frame.pack(side="right")
        tk.Label(filter_frame, text="FILTER:", font=self.font_small,
                 bg=self.bg2, fg=self.fg_dim).pack(side="left", padx=(0, 4))
        self.filter_var = tk.StringVar()
        fe = tk.Entry(filter_frame, textvariable=self.filter_var,
                      font=self.font_body, bg=self.bg3, fg=self.fg,
                      insertbackground=self.accent, bd=0, width=18,
                      highlightthickness=1, highlightcolor=self.accent,
                      highlightbackground=self.border)
        fe.pack(side="left", ipady=4, padx=4)
        fe.bind("<KeyRelease>", lambda e: self._refresh_records())

        tree_frame = tk.Frame(frame, bg=self.bg)
        tree_frame.pack(fill="both", expand=True, padx=16, pady=12)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Custom.Treeview",
                        background=self.bg2, foreground=self.fg,
                        fieldbackground=self.bg2, rowheight=36,
                        font=self.font_body, borderwidth=0)
        style.configure("Custom.Treeview.Heading",
                        background=self.bg3, foreground=self.accent,
                        font=self.font_header, borderwidth=0, relief="flat")
        style.map("Custom.Treeview",
                  background=[("selected", self.bg3)],
                  foreground=[("selected", self.accent)])

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

        self.totals_bar = tk.Frame(frame, bg=self.bg3, pady=10, padx=16)
        self.totals_bar.pack(fill="x", side="bottom")
        self.lbl_income = tk.Label(self.totals_bar, text="Income: ₹0",
                                    font=self.font_header, bg=self.bg3, fg=self.green)
        self.lbl_income.pack(side="left", padx=16)
        self.lbl_expense = tk.Label(self.totals_bar, text="Expenses: ₹0",
                                     font=self.font_header, bg=self.bg3, fg=self.red)
        self.lbl_expense.pack(side="left", padx=16)
        self.lbl_balance = tk.Label(self.totals_bar, text="Balance: ₹0",
                                     font=self.font_header, bg=self.bg3, fg=self.accent)
        self.lbl_balance.pack(side="right", padx=16)
        return frame

    def _build_accounts_tab(self):
        frame = tk.Frame(self.content, bg=self.bg)
        toolbar = tk.Frame(frame, bg=self.bg2, pady=10, padx=16)
        toolbar.pack(fill="x")
        tk.Button(toolbar, text="+ ADD ACCOUNT", font=self.font_header,
                  bg=self.accent, fg="#000", bd=0, padx=14, pady=6,
                  cursor="hand2", command=self._add_account_dialog).pack(side="left")
        tk.Button(toolbar, text="✕ DELETE", font=self.font_header,
                  bg=self.bg3, fg=self.red, bd=0, padx=14, pady=6,
                  cursor="hand2", command=self._delete_account).pack(side="left", padx=8)
        tree_frame = tk.Frame(frame, bg=self.bg)
        tree_frame.pack(fill="both", expand=True, padx=16, pady=12)
        self.accounts_tree = ttk.Treeview(tree_frame,
                                           columns=("Account Name", "Balance"),
                                           show="headings", style="Custom.Treeview")
        self.accounts_tree.heading("Account Name", text="ACCOUNT NAME")
        self.accounts_tree.heading("Balance", text="BALANCE")
        self.accounts_tree.column("Account Name", width=400)
        self.accounts_tree.column("Balance", width=200)
        self.accounts_tree.pack(fill="both", expand=True)
        return frame

    def _build_categories_tab(self):
        frame = tk.Frame(self.content, bg=self.bg)
        toolbar = tk.Frame(frame, bg=self.bg2, pady=10, padx=16)
        toolbar.pack(fill="x")
        tk.Button(toolbar, text="+ ADD CATEGORY", font=self.font_header,
                  bg=self.accent, fg="#000", bd=0, padx=14, pady=6,
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
        balance = income - expense

        cards = tk.Frame(self.summary_inner, bg=self.bg)
        cards.pack(fill="x", pady=(0, 20))
        for label, value, color in [
            ("TOTAL INCOME",  f"₹{income:,.2f}",  self.green),
            ("TOTAL EXPENSE", f"₹{expense:,.2f}", self.red),
            ("NET BALANCE",   f"₹{balance:,.2f}", self.accent),
        ]:
            card = tk.Frame(cards, bg=self.bg3, padx=24, pady=18)
            card.pack(side="left", expand=True, fill="x", padx=8)
            tk.Label(card, text=label, font=self.font_small,
                     bg=self.bg3, fg=self.fg_dim).pack(anchor="w")
            tk.Label(card, text=value, font=("Calibri", 22, "bold"),
                     bg=self.bg3, fg=color).pack(anchor="w", pady=(4, 0))

        tk.Label(self.summary_inner, text="SPENDING BY CATEGORY",
                 font=self.font_header, bg=self.bg, fg=self.accent).pack(anchor="w", pady=(8, 6))

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
                bar_w = int((total / max_val) * 340)
                bar_bg = tk.Frame(row, bg=self.bg3, width=340, height=18)
                bar_bg.pack(side="left", padx=8)
                bar_bg.pack_propagate(False)
                tk.Frame(bar_bg, bg=self.accent2, width=bar_w, height=18).place(x=0, y=0)
                tk.Label(row, text=f"₹{total:,.2f}", font=self.font_body,
                         bg=self.bg, fg=self.fg_dim).pack(side="left", padx=6)
        else:
            tk.Label(self.summary_inner, text="No expense records yet.",
                     font=self.font_body, bg=self.bg, fg=self.fg_dim).pack(anchor="w")

    def _add_record_dialog(self):
        if not self.data["accounts"]:
            messagebox.showwarning("No Accounts", "Please add an account first.")
            return
        if not self.data["categories"]:
            messagebox.showwarning("No Categories", "Please add a category first.")
            return

        dlg = tk.Toplevel(self)
        dlg.title("Add Record")
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

        tk.Label(dlg, text="NEW RECORD", font=self.font_header,
                 bg=self.bg, fg=self.accent).pack(pady=(18, 10))
        inner = tk.Frame(dlg, bg=self.bg, padx=24)
        inner.pack(fill="both", expand=True)

        es = dict(bg=self.bg3, fg=self.fg, insertbackground=self.accent,
                  bd=0, font=self.font_body,
                  highlightthickness=1, highlightcolor=self.accent,
                  highlightbackground=self.border)

        fields["desc"]   = labeled(inner, "Description", lambda p: tk.Entry(p, **es))
        fields["amount"] = labeled(inner, "Amount (₹)",  lambda p: tk.Entry(p, **es))

        type_var = tk.StringVar(value="Expense")
        def mk_type(p):
            f = tk.Frame(p, bg=self.bg)
            for t in ["Expense", "Income"]:
                tk.Radiobutton(f, text=t, variable=type_var, value=t,
                               font=self.font_body, bg=self.bg, fg=self.fg,
                               selectcolor=self.bg3, activebackground=self.bg,
                               activeforeground=self.accent).pack(side="left", padx=6)
            return f
        labeled(inner, "Type", mk_type)

        acc_var = tk.StringVar(value=self.data["accounts"][0]["name"])
        labeled(inner, "Account",
                lambda p: ttk.Combobox(p, textvariable=acc_var,
                                       values=[a["name"] for a in self.data["accounts"]],
                                       font=self.font_body, state="readonly"))

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
            self.data["records"].append({
                "id": len(self.data["records"]),
                "date": date_entry.get().strip(),
                "description": desc,
                "amount": amount,
                "type": type_var.get(),
                "account": acc_var.get(),
                "category": cat_var.get(),
            })
            save_data(self.data)
            self.refresh_all()
            dlg.destroy()

        tk.Button(inner, text="SAVE RECORD", font=self.font_header,
                  bg=self.accent, fg="#000", bd=0, padx=16, pady=8,
                  cursor="hand2", command=submit).pack(pady=14)

    def _add_account_dialog(self):
        name = simpledialog.askstring("Add Account", "Account name:", parent=self)
        if name and name.strip():
            self.data["accounts"].append({"name": name.strip(), "balance": 0})
            save_data(self.data)
            self.refresh_all()

    def _add_category_dialog(self):
        name = simpledialog.askstring("Add Category", "Category name:", parent=self)
        if name and name.strip():
            self.data["categories"].append(name.strip())
            save_data(self.data)
            self.refresh_all()

    def _delete_record(self):
        sel = self.records_tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Please select a record to delete.")
            return
        rec = self._filtered_records()[self.records_tree.index(sel[0])]
        self.data["records"] = [r for r in self.data["records"] if r["id"] != rec["id"]]
        save_data(self.data)
        self.refresh_all()

    def _delete_account(self):
        sel = self.accounts_tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Please select an account to delete.")
            return
        self.data["accounts"].pop(self.accounts_tree.index(sel[0]))
        save_data(self.data)
        self.refresh_all()

    def _delete_category(self):
        sel = self.categories_tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Please select a category to delete.")
            return
        self.data["categories"].pop(self.categories_tree.index(sel[0]))
        save_data(self.data)
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
        income = expense = 0
        for r in self._filtered_records():
            tag = "income" if r["type"] == "Income" else "expense"
            self.records_tree.insert("", "end", tags=(tag,), values=(
                r["date"], r["description"],
                f"₹{r['amount']:,.2f}", r["type"],
                r["account"], r["category"]
            ))
            if r["type"] == "Income":
                income += r["amount"]
            else:
                expense += r["amount"]
        self.records_tree.tag_configure("income",  foreground=self.green)
        self.records_tree.tag_configure("expense", foreground=self.red)
        self.lbl_income.config( text=f"Income:   ₹{income:,.2f}")
        self.lbl_expense.config(text=f"Expenses: ₹{expense:,.2f}")
        self.lbl_balance.config(text=f"Balance:  ₹{income - expense:,.2f}",
                                 fg=self.green if income >= expense else self.red)

    def _refresh_accounts(self):
        for row in self.accounts_tree.get_children():
            self.accounts_tree.delete(row)
        for acc in self.data["accounts"]:
            bal = sum(
                (r["amount"] if r["type"] == "Income" else -r["amount"])
                for r in self.data["records"] if r["account"] == acc["name"]
            )
            self.accounts_tree.insert("", "end", values=(acc["name"], f"₹{bal:,.2f}"))

    def _refresh_categories(self):
        for row in self.categories_tree.get_children():
            self.categories_tree.delete(row)
        for cat in self.data["categories"]:
            self.categories_tree.insert("", "end", values=(cat,))

    def refresh_all(self):
        self._refresh_records()
        self._refresh_accounts()
        self._refresh_categories()


# ── entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = LoginWindow()
    app.mainloop()