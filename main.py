"""
Main GUI for the Netball Trial Management System: login, tabs for Trials,
Players, Roll Call, Rounds and Export, plus the styling shared across all
of them.

can_edit() is defined below but not wired up into the GUI yet - a coach or
referee on the Rounds tab currently has the same view as a coordinator
even though referees should be read-only.
"""

import hashlib
import hmac
import secrets
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import players as store
import algorithm

POSITIONS = ["GS", "GA", "WA", "C", "WD", "GD", "GK"]


# --------------------------------------------------------------------------- #
# Auth & role-based access control
# --------------------------------------------------------------------------- #
# A `User` object represents the logged-in session and knows which tabs its
# role is allowed to see (has_access) and edit (can_edit). login() checks
# username + password + selected role against the users records.

VALID_ROLES = ("coordinator", "coach", "referee", "player")

# Which of the five dashboard tabs each role is allowed to open.
ROLE_PERMISSIONS = {
    "coordinator": {"Trials", "Players", "Roll Call", "Rounds", "Export"},
    "coach":       {"Rounds"},
    "referee":     {"Rounds"},
    "player":      {"Players"},
}

# Whether a role may edit data on a tab it can see, vs. read-only.
# Not enforced in the GUI yet - defined here so it's ready to wire up.
ROLE_CAN_EDIT = {
    "coordinator": {"Trials", "Players", "Roll Call", "Rounds", "Export"},
    "coach":       {"Rounds"},
    "referee":     set(),
    "player":      {"Players"},
}


def new_salt():
    return secrets.token_hex(16)


def hash_password(plain_password, salt_hex):
    """Returns SHA-256(salt + password) as 64 hex characters. Each account
    gets its own random salt so two accounts with the same password don't
    end up with the same hash."""
    salted = bytes.fromhex(salt_hex) + plain_password.encode("utf-8")
    return hashlib.sha256(salted).hexdigest()


def verify_password(plain_password, salt_hex, stored_hash):
    return hmac.compare_digest(hash_password(plain_password, salt_hex or ""), stored_hash)


def has_access(role, tab_name):
    return tab_name in ROLE_PERMISSIONS.get(role, set())


def can_edit(role, tab_name):
    return tab_name in ROLE_CAN_EDIT.get(role, set())


class User:
    """Represents the currently logged-in user for the duration of a session."""

    def __init__(self, user_id, username, role):
        self.user_id = user_id
        self.username = username
        self.role = role

    def has_access(self, tab_name):
        return has_access(self.role, tab_name)

    def can_edit(self, tab_name):
        return can_edit(self.role, tab_name)

    def display_role(self):
        return {
            "coordinator": "Coordinator",
            "coach": "Coach",
            "referee": "Referee",
            "player": "Player/Parent",
        }.get(self.role, self.role.title())


def login(username, password, role):
    """Checks username + password + the role picked on the login screen.
    Returns a User on success, None on failure."""
    record = store.get_user_by_username(username.strip())
    if not record:
        return None
    if record["role"] != role:
        return None
    if not verify_password(password, record.get("salt", ""), record["password_hash"]):
        return None
    return User(record["user_id"], record["username"], record["role"])


# --------------------------------------------------------------------------- #
# Theming & shared widgets
# --------------------------------------------------------------------------- #

NAVY = "#1f3864"
WHITE = "#ffffff"
LIGHT_GREY = "#f2f2f2"
DARK_GREY = "#555555"
GREEN = "#2e7d32"
RED = "#c62828"

FONT_FAMILY = "Arial"


def setup_styles(root):
    """Configures a consistent ttk theme across the whole application.
    Call this once, right after creating the root window."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")  # the built-in theme most willing to take colour overrides
    except tk.TclError:
        pass

    root.configure(bg=WHITE)

    style.configure("TFrame", background=WHITE)
    style.configure("TLabel", background=WHITE, font=(FONT_FAMILY, 10))

    style.configure("Header.TLabel", background=NAVY, foreground=WHITE,
                    font=(FONT_FAMILY, 16, "bold"))
    style.configure("SubHeader.TLabel", background=WHITE, foreground=NAVY,
                    font=(FONT_FAMILY, 11, "bold"))
    style.configure("Status.TLabel", background=LIGHT_GREY, foreground=DARK_GREY,
                    font=(FONT_FAMILY, 9))
    style.configure("Valid.TLabel", background=WHITE, foreground=GREEN, font=(FONT_FAMILY, 9))
    style.configure("Invalid.TLabel", background=WHITE, foreground=RED, font=(FONT_FAMILY, 9))

    style.configure("TButton", font=(FONT_FAMILY, 10), padding=6)
    style.configure("Primary.TButton", font=(FONT_FAMILY, 10, "bold"))
    style.map("Primary.TButton",
              background=[("!disabled", NAVY)],
              foreground=[("!disabled", WHITE)])

    style.configure("TNotebook", background=WHITE, tabmargins=[2, 5, 2, 0])
    style.configure("TNotebook.Tab", font=(FONT_FAMILY, 10), padding=[16, 8])
    style.map("TNotebook.Tab",
              background=[("selected", NAVY), ("!selected", LIGHT_GREY)],
              foreground=[("selected", WHITE), ("!selected", "#222222")])

    style.configure("Treeview", font=(FONT_FAMILY, 10), rowheight=26,
                    background=WHITE, fieldbackground=WHITE)
    style.configure("Treeview.Heading", font=(FONT_FAMILY, 10, "bold"),
                    background=NAVY, foreground=WHITE)
    style.map("Treeview.Heading", background=[("active", NAVY)])

    style.configure("TEntry", padding=4)
    style.configure("TCombobox", padding=4)

    return style


def build_header_bar(parent, title_text):
    """Navy title bar shown at the top of the login screen and the main
    dashboard."""
    bar = tk.Frame(parent, bg=NAVY)
    ttk.Label(bar, text=title_text, style="Header.TLabel").pack(
        side="left", padx=16, pady=12
    )
    return bar


def stripe_treeview(tree: ttk.Treeview):
    """Applies alternating light-grey row colouring to a Treeview's existing
    rows. Call this again any time rows are inserted/removed, since the
    stripe pattern is just a tag applied per-row, not automatic."""
    tree.tag_configure("oddrow", background=WHITE)
    tree.tag_configure("evenrow", background=LIGHT_GREY)
    for index, item in enumerate(tree.get_children("")):
        tree.item(item, tags=("evenrow" if index % 2 == 0 else "oddrow",))


def make_striped_treeview(parent, columns, headings, widths=None):
    """
    Builds a ttk.Treeview set up as a table: no visible tree column, just
    the given data columns, headings, and striped rows. Returns the
    Treeview - caller is responsible for calling stripe_treeview(tree)
    again after inserting/removing rows.
    """
    tree = ttk.Treeview(parent, columns=columns, show="headings")
    for i, col in enumerate(columns):
        tree.heading(col, text=headings[i])
        width = widths[i] if widths else 120
        tree.column(col, width=width, anchor="w")
    return tree


def show_status_bar(parent, status_text_var):
    """Light-grey status bar shown at the bottom of the main dashboard,
    bound to a StringVar so callers can update it just by setting the var."""
    bar = tk.Frame(parent, bg=LIGHT_GREY)
    ttk.Label(bar, textvariable=status_text_var, style="Status.TLabel").pack(
        side="left", padx=8, pady=4
    )
    return bar


class ScrollableFrame(ttk.Frame):
    """A frame that can be scrolled with the scrollbar or the mouse wheel.
    Needed because the Roll Call list can have 100+ rows in it, which
    doesn't fit in the window at once.

    Usage: put widgets inside `self.inner` (not `self` directly).
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.canvas = canvas
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = ttk.Frame(canvas)

        self.inner.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Mouse wheel support - only while the pointer is over this canvas,
        # otherwise scrolling here would also scroll other tabs.
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", self._on_mousewheel(canvas)))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

    @staticmethod
    def _on_mousewheel(canvas):
        def handler(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return handler


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Netball Trial Management System")
        self.geometry("900x600")

        setup_styles(self)

        store.init_data()
        store.backup_data()

        self.current_user = None
        self.selected_trial_id = None
        self.attendance_vars = {}  # player_id -> IntVar, used on the Roll Call tab
        self.status_var = tk.StringVar(value="No trial selected")

        self.build_login_screen()

    # ----------------------------------------------------------------- #
    # Login
    # ----------------------------------------------------------------- #

    def build_login_screen(self):
        build_header_bar(self, "Netball Trial Management System").pack(fill="x")

        self.login_frame = ttk.Frame(self)
        self.login_frame.pack(expand=True)

        ttk.Label(self.login_frame, text="Username").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        self.login_username_entry = ttk.Entry(self.login_frame)
        self.login_username_entry.grid(row=1, column=1, pady=5)

        ttk.Label(self.login_frame, text="Password").grid(row=2, column=0, sticky="e", padx=5, pady=5)
        self.login_password_entry = ttk.Entry(self.login_frame, show="*")
        self.login_password_entry.grid(row=2, column=1, pady=5)

        ttk.Label(self.login_frame, text="Role").grid(row=3, column=0, sticky="e", padx=5, pady=5)
        self.login_role_combo = ttk.Combobox(
            self.login_frame, values=list(VALID_ROLES), state="readonly"
        )
        self.login_role_combo.set("coordinator")
        self.login_role_combo.grid(row=3, column=1, pady=5)

        ttk.Button(
            self.login_frame, text="Log In", style="Primary.TButton", command=self.attempt_login
        ).grid(row=4, column=0, columnspan=2, pady=15)

        self.login_error_label = ttk.Label(self.login_frame, text="", style="Invalid.TLabel")
        self.login_error_label.grid(row=5, column=0, columnspan=2)

        # First-run help - the default account until a signup screen exists.
        ttk.Label(
            self.login_frame,
            text="First run? Default login is coordinator / coordinator123",
            style="Status.TLabel",
        ).grid(row=6, column=0, columnspan=2, pady=(10, 0))

    def attempt_login(self):
        username = self.login_username_entry.get().strip()
        password = self.login_password_entry.get()
        role = self.login_role_combo.get()

        if not username or not password or not role:
            self.login_error_label.configure(text="All fields are required.")
            return

        user = login(username, password, role)
        if not user:
            # Deliberately vague - see login()'s docstring for why.
            self.login_error_label.configure(text="Incorrect username, password, or role.")
            self.login_password_entry.delete(0, "end")
            return

        self.current_user = user
        for widget in self.winfo_children():
            widget.destroy()
        self.build_main_app()

    def log_out(self):
        for widget in self.winfo_children():
            widget.destroy()

        # Clear out widget references from the previous session - without
        # this, logging in as a role with fewer tabs (e.g. coach after a
        # coordinator session) would leave stale attributes like
        # self.players_list pointing at an already-destroyed widget, and
        # select_trial()'s hasattr() checks would wrongly think that tab
        # still exists and crash trying to use it.
        stale_attrs = [
            "trials_tab", "players_tab", "roll_call_tab", "rounds_tab", "export_tab",
            "trials_tree", "players_tree", "roll_call_frame", "round_nav_label",
            "rounds_content", "trial_picker_combo", "roll_call_search_var",
            "court_jump_frame", "round_order_mode",
        ]
        for attr in stale_attrs:
            if hasattr(self, attr):
                delattr(self, attr)

        self.current_user = None
        self.selected_trial_id = None
        self.attendance_vars = {}
        self.status_var.set("No trial selected")
        self.build_login_screen()

    # ----------------------------------------------------------------- #
    # Main app (built after a successful login)
    # ----------------------------------------------------------------- #

    def build_main_app(self):
        build_header_bar(self, "Netball Trial Management System").pack(fill="x")

        top_bar = ttk.Frame(self)
        top_bar.pack(fill="x", padx=10, pady=(10, 0))
        ttk.Label(
            top_bar,
            text=f"Logged in: {self.current_user.username} ({self.current_user.display_role()})",
            style="SubHeader.TLabel",
        ).pack(side="left")
        ttk.Button(top_bar, text="Log Out", command=self.log_out).pack(side="right")

        # Coordinators pick their active trial from the list on the Trials
        # tab. Everyone else doesn't get that tab, so they need some other
        # way to say which trial they're working with - a simple dropdown
        # here does the job for now.
        if not self.current_user.has_access("Trials"):
            picker = ttk.Frame(self)
            picker.pack(fill="x", padx=10, pady=5)
            ttk.Label(picker, text="Trial:").pack(side="left")
            self.trial_picker_var = tk.StringVar()
            self.trial_picker_combo = ttk.Combobox(
                picker, textvariable=self.trial_picker_var, state="readonly", width=40
            )
            self.trial_picker_combo.pack(side="left", padx=5)
            self.trial_picker_combo.bind("<<ComboboxSelected>>", self.on_trial_picker_selected)
            self._trial_picker_options = store.get_all_trials()
            self.trial_picker_combo["values"] = [
                f"{t['trial_id']} - {t['trial_name']} ({t['age_group']})"
                for t in self._trial_picker_options
            ]

        # Status bar goes at the bottom, packed BEFORE the notebook (below)
        # so it stays pinned to the bottom edge and the notebook fills
        # whatever vertical space is left over.
        show_status_bar(self, self.status_var).pack(fill="x", side="bottom")

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        # Only build/add a tab if the logged-in role is actually allowed to
        # see it - tab_name here must match the keys used in ROLE_PERMISSIONS.
        tab_definitions = [
            ("Trials", "trials_tab", self.build_trials_tab),
            ("Players", "players_tab", self.build_players_tab),
            ("Roll Call", "roll_call_tab", self.build_roll_call_tab),
            ("Rounds", "rounds_tab", self.build_rounds_tab),
            ("Export", "export_tab", self.build_export_tab),
        ]

        for tab_name, attr_name, build_method in tab_definitions:
            if not self.current_user.has_access(tab_name):
                continue
            frame = ttk.Frame(notebook)
            setattr(self, attr_name, frame)
            notebook.add(frame, text=tab_name)
            build_method()

    def on_trial_picker_selected(self, event):
        index = self.trial_picker_combo.current()
        if index < 0:
            return
        trial = self._trial_picker_options[index]
        self.select_trial(trial["trial_id"])

    # ----------------------------------------------------------------- #
    # Trials tab
    # ----------------------------------------------------------------- #

    def build_trials_tab(self):
        form = ttk.Frame(self.trials_tab)
        form.pack(fill="x", padx=10, pady=10)

        ttk.Label(form, text="Trial Name").grid(row=0, column=0, sticky="w")
        self.trial_name_entry = ttk.Entry(form)
        self.trial_name_entry.grid(row=0, column=1, padx=5)

        ttk.Label(form, text="Age Group").grid(row=1, column=0, sticky="w")
        self.age_group_entry = ttk.Entry(form)
        self.age_group_entry.grid(row=1, column=1, padx=5)

        ttk.Label(form, text="Date (DD/MM/YYYY)").grid(row=2, column=0, sticky="w")
        self.trial_date_entry = ttk.Entry(form)
        self.trial_date_entry.grid(row=2, column=1, padx=5)

        # Plain number input rather than a 1/2-court radio button - some
        # venues run 10+ courts at once, and update_trial_courts() / the
        # Round Settings dialog let this be changed later anyway.
        ttk.Label(form, text="Courts").grid(row=3, column=0, sticky="w")
        self.num_courts_var = tk.IntVar(value=1)
        ttk.Spinbox(
            form, from_=1, to=50, textvariable=self.num_courts_var, width=6
        ).grid(row=3, column=1, sticky="w", padx=5)

        # Optional - if left blank, DOB just isn't checked against an age
        # window for this trial. Filling both in enables the live green/red
        # validation on the Players tab registration form.
        ttk.Label(form, text="Birth Year Range (optional)").grid(row=4, column=0, sticky="w")
        birth_year_frame = ttk.Frame(form)
        birth_year_frame.grid(row=4, column=1, sticky="w")
        self.min_birth_year_entry = ttk.Entry(birth_year_frame, width=8)
        self.min_birth_year_entry.pack(side="left")
        ttk.Label(birth_year_frame, text=" to ").pack(side="left")
        self.max_birth_year_entry = ttk.Entry(birth_year_frame, width=8)
        self.max_birth_year_entry.pack(side="left")

        ttk.Button(form, text="Create Trial", style="Primary.TButton", command=self.create_trial).grid(
            row=5, column=0, columnspan=2, pady=10
        )

        self.trials_tree = make_striped_treeview(
            self.trials_tab,
            columns=("name", "age_group", "date", "courts"),
            headings=["Trial Name", "Age Group", "Date", "Courts"],
            widths=[220, 100, 110, 80],
        )
        self.trials_tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.trials_tree.bind("<<TreeviewSelect>>", self.on_select_trial)

        self.refresh_trials_list()

    def create_trial(self):
        name = self.trial_name_entry.get().strip()
        age_group = self.age_group_entry.get().strip()
        date = self.trial_date_entry.get().strip()
        min_year_text = self.min_birth_year_entry.get().strip()
        max_year_text = self.max_birth_year_entry.get().strip()

        if not name or not age_group or not date:
            messagebox.showerror("Error", "All fields are required.")
            return

        # IntVar.get() raises TclError if the Spinbox holds something that
        # isn't a whole number (e.g. cleared by hand) rather than quietly
        # falling back to a default.
        try:
            num_courts = self.num_courts_var.get()
        except tk.TclError:
            messagebox.showerror("Error", "Courts must be a whole number.")
            return
        if num_courts < 1:
            messagebox.showerror("Error", "Courts must be at least 1.")
            return

        # Birth years are optional, but if either is given both must be
        # given and both must actually be numbers.
        min_birth_year = max_birth_year = None
        if min_year_text or max_year_text:
            if not (min_year_text.isdigit() and max_year_text.isdigit()):
                messagebox.showerror("Error", "Birth years must be whole numbers, e.g. 2013.")
                return
            min_birth_year, max_birth_year = int(min_year_text), int(max_year_text)
            if min_birth_year > max_birth_year:
                messagebox.showerror("Error", "Minimum birth year can't be after the maximum.")
                return

        store.create_trial(name, age_group, date, num_courts, min_birth_year, max_birth_year)
        self.trial_name_entry.delete(0, "end")
        self.age_group_entry.delete(0, "end")
        self.trial_date_entry.delete(0, "end")
        self.min_birth_year_entry.delete(0, "end")
        self.max_birth_year_entry.delete(0, "end")
        self.num_courts_var.set(1)
        self.refresh_trials_list()

    def refresh_trials_list(self):
        self.trials_tree.delete(*self.trials_tree.get_children())
        for t in store.get_all_trials():
            courts_text = f"{t['num_courts']} court{'s' if t['num_courts'] > 1 else ''}"
            self.trials_tree.insert(
                "", "end", iid=str(t["trial_id"]),
                values=(t["trial_name"], t["age_group"], t["trial_date"], courts_text),
            )
        stripe_treeview(self.trials_tree)

    def on_select_trial(self, event):
        selection = self.trials_tree.selection()
        if not selection:
            return
        self.select_trial(int(selection[0]))

    def select_trial(self, trial_id):
        """Sets the active trial and refreshes whichever tabs the current
        role actually has (a coach/referee won't have players_tree etc,
        since they don't get the Players tab)."""
        self.selected_trial_id = trial_id
        trial = store.get_trial(trial_id)
        if trial:
            self.status_var.set(
                f"Trial: {trial['trial_name']} ({trial['age_group']}) - "
                f"{trial['num_courts']} court{'s' if trial['num_courts'] > 1 else ''}"
            )
        if hasattr(self, "players_tree"):
            self.refresh_players_list()
        if hasattr(self, "roll_call_frame"):
            self.refresh_roll_call()
        if hasattr(self, "rounds_display"):
            self.refresh_rounds_display()

    # ----------------------------------------------------------------- #
    # Players tab
    # ----------------------------------------------------------------- #

    def build_players_tab(self):
        form = ttk.Frame(self.players_tab)
        form.pack(fill="x", padx=10, pady=10)

        ttk.Label(form, text="First Name").grid(row=0, column=0, sticky="w")
        self.first_name_entry = ttk.Entry(form)
        self.first_name_entry.grid(row=0, column=1, padx=5)

        ttk.Label(form, text="Last Name").grid(row=1, column=0, sticky="w")
        self.last_name_entry = ttk.Entry(form)
        self.last_name_entry.grid(row=1, column=1, padx=5)

        ttk.Label(form, text="DOB (DD/MM/YYYY)").grid(row=2, column=0, sticky="w")
        self.dob_entry = ttk.Entry(form)
        self.dob_entry.grid(row=2, column=1, padx=5)
        self.dob_entry.bind("<KeyRelease>", self.on_dob_typed)

        # Live feedback as the coordinator types - informational only,
        # never blocks registration, since a permit might apply.
        self.dob_validation_label = ttk.Label(form, text="", style="Valid.TLabel")
        self.dob_validation_label.grid(row=2, column=2, sticky="w", padx=5)

        ttk.Label(form, text="Position 1").grid(row=3, column=0, sticky="w")
        self.pos1_combo = ttk.Combobox(form, values=POSITIONS, state="readonly")
        self.pos1_combo.grid(row=3, column=1, padx=5)

        ttk.Label(form, text="Position 2").grid(row=4, column=0, sticky="w")
        self.pos2_combo = ttk.Combobox(form, values=POSITIONS, state="readonly")
        self.pos2_combo.grid(row=4, column=1, padx=5)

        ttk.Button(
            form, text="Register Player", style="Primary.TButton", command=self.create_player
        ).grid(row=5, column=0, columnspan=2, pady=10)

        self.players_tree = make_striped_treeview(
            self.players_tab,
            columns=("trial_no", "name", "dob", "pos1", "pos2"),
            headings=["#", "Name", "DOB", "Pos 1", "Pos 2"],
            widths=[40, 200, 100, 70, 70],
        )
        self.players_tree.pack(fill="both", expand=True, padx=10, pady=10)

    def on_dob_typed(self, event=None):
        """Checks the DOB typed so far against the selected trial's birth
        year window and shows a green tick or red warning. Never blocks
        anything - create_player() only checks the date format."""
        dob = self.dob_entry.get().strip()
        if not dob:
            self.dob_validation_label.configure(text="")
            return
        if not self.selected_trial_id:
            self.dob_validation_label.configure(text="")
            return

        trial = store.get_trial(self.selected_trial_id)
        if not store.is_valid_date(dob):
            # Don't show "invalid format" on every half-typed keystroke -
            # only once it's plausibly a complete date.
            if len(dob) >= 10:
                self.dob_validation_label.configure(text="Invalid date format", style="Invalid.TLabel")
            else:
                self.dob_validation_label.configure(text="")
            return

        is_valid, message = store.check_dob_eligibility(
            dob, trial.get("min_birth_year"), trial.get("max_birth_year")
        )
        self.dob_validation_label.configure(
            text=message, style="Valid.TLabel" if is_valid else "Invalid.TLabel"
        )

    def create_player(self):
        if not self.selected_trial_id:
            messagebox.showerror("Error", "Select a trial first (on the Trials tab).")
            return

        first_name = self.first_name_entry.get().strip()
        last_name = self.last_name_entry.get().strip()
        dob = self.dob_entry.get().strip()
        pos1 = self.pos1_combo.get()
        pos2 = self.pos2_combo.get()

        if not first_name or not last_name or not dob or not pos1 or not pos2:
            messagebox.showerror("Error", "All fields are required.")
            return

        if not store.is_valid_date(dob):
            messagebox.showerror("Error", "DOB must be in DD/MM/YYYY format.")
            return

        trial_number = store.create_player(
            self.selected_trial_id, first_name, last_name, dob, pos1, pos2
        )

        self.first_name_entry.delete(0, "end")
        self.last_name_entry.delete(0, "end")
        self.dob_entry.delete(0, "end")
        self.dob_validation_label.configure(text="")
        self.pos1_combo.set("")
        self.pos2_combo.set("")

        messagebox.showinfo("Registered", f"Player registered. Trial number: {trial_number}")

        self.refresh_players_list()
        self.refresh_roll_call()

    def refresh_players_list(self):
        self.players_tree.delete(*self.players_tree.get_children())
        if not self.selected_trial_id:
            return
        players = store.get_players_for_trial(self.selected_trial_id)
        for p in players:
            self.players_tree.insert(
                "", "end", iid=str(p["player_id"]),
                values=(
                    f"#{p['trial_number']}",
                    f"{p['first_name']} {p['last_name']}",
                    p["dob"],
                    p["position_1"],
                    p["position_2"],
                ),
            )
        stripe_treeview(self.players_tree)

    # ----------------------------------------------------------------- #
    # Roll Call tab
    # ----------------------------------------------------------------- #

    def build_roll_call_tab(self):
        ttk.Label(
            self.roll_call_tab, text="Tick each player who is present for this trial:"
        ).pack(anchor="w", padx=10, pady=(10, 0))

        search_frame = ttk.Frame(self.roll_call_tab)
        search_frame.pack(fill="x", padx=10, pady=(6, 0))
        ttk.Label(search_frame, text="Search:").pack(side="left")
        self.roll_call_search_var = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self.roll_call_search_var, width=28).pack(
            side="left", padx=(5, 0)
        )
        ttk.Label(
            search_frame, text="Filter by name or trial number", style="Status.TLabel"
        ).pack(side="left", padx=(8, 0))
        self.roll_call_search_var.trace_add("write", lambda *_a: self.render_roll_call_rows())

        buttons_frame = ttk.Frame(self.roll_call_tab)
        buttons_frame.pack(fill="x", padx=10, pady=5)
        ttk.Button(buttons_frame, text="Select All", command=self.select_all_present).pack(side="left")
        ttk.Button(buttons_frame, text="Clear All", command=self.clear_all_present).pack(side="left", padx=5)
        ttk.Label(
            buttons_frame, text="(applies to the players currently shown, e.g. a search result)",
            style="Status.TLabel",
        ).pack(side="left", padx=(8, 0))

        # Scrollable area - a plain Frame packed with 100 checkbuttons just
        # runs off the bottom of the window, so this wraps it in a canvas.
        self.roll_call_scroll = ScrollableFrame(self.roll_call_tab)
        self.roll_call_scroll.pack(fill="both", expand=True, padx=10, pady=5)
        self.roll_call_frame = self.roll_call_scroll.inner

        ttk.Button(
            self.roll_call_tab, text="Confirm Roll Call", style="Primary.TButton",
            command=self.confirm_roll_call
        ).pack(pady=10)

        self._roll_call_players = []
        self._visible_player_ids = []

    def refresh_roll_call(self):
        self.attendance_vars = {}
        self._roll_call_players = []
        if hasattr(self, "roll_call_search_var"):
            self.roll_call_search_var.set("")

        if self.selected_trial_id:
            self._roll_call_players = store.get_players_for_trial(self.selected_trial_id)
            existing = store.get_attendance_map(self.selected_trial_id)
            for p in self._roll_call_players:
                self.attendance_vars[p["player_id"]] = tk.IntVar(
                    value=existing.get(p["player_id"], 0)
                )

        self.render_roll_call_rows()

    def render_roll_call_rows(self):
        """Redraws the Checkbutton list from self._roll_call_players/
        attendance_vars, filtered by whatever's typed in the search box.
        Ticked state lives in attendance_vars (untouched by filtering), so
        searching for someone else and back doesn't lose a tick."""
        for widget in self.roll_call_frame.winfo_children():
            widget.destroy()

        query = self.roll_call_search_var.get().strip().lower() if hasattr(self, "roll_call_search_var") else ""
        # A purely numeric search means "trial number", and should match
        # exactly - typing 99 shouldn't also pull in #199, #299, etc.
        query_is_number = query.isdigit()
        self._visible_player_ids = []

        for p in self._roll_call_players:
            if query_is_number:
                if str(p["trial_number"]) != query:
                    continue
            elif query:
                full_name = f"{p['first_name']} {p['last_name']}".lower()
                if query not in full_name:
                    continue
            self._visible_player_ids.append(p["player_id"])
            ttk.Checkbutton(
                self.roll_call_frame,
                text=f"#{p['trial_number']} {p['first_name']} {p['last_name']}",
                variable=self.attendance_vars[p["player_id"]],
            ).pack(anchor="w")

        if query and not self._visible_player_ids:
            ttk.Label(
                self.roll_call_frame, text="No players match that search.", style="Status.TLabel"
            ).pack(anchor="w", pady=6)

    def select_all_present(self):
        for player_id in self._visible_player_ids:
            self.attendance_vars[player_id].set(1)

    def clear_all_present(self):
        for player_id in self._visible_player_ids:
            self.attendance_vars[player_id].set(0)

    def confirm_roll_call(self):
        if not self.selected_trial_id:
            messagebox.showerror("Error", "Select a trial first (on the Trials tab).")
            return

        for player_id, var in self.attendance_vars.items():
            store.set_attendance(player_id, self.selected_trial_id, bool(var.get()))

        present_count = sum(1 for var in self.attendance_vars.values() if var.get())
        messagebox.showinfo("Roll Call Saved", f"{present_count} players marked present.")

    # ----------------------------------------------------------------- #
    # Rounds tab
    # ----------------------------------------------------------------- #

    def build_rounds_tab(self):
        form = ttk.Frame(self.rounds_tab)
        form.pack(fill="x", padx=10, pady=10)

        ttk.Button(
            form, text="Round Settings…", command=self.open_round_settings_dialog
        ).pack(side="left")
        ttk.Button(
            form, text="Generate Rounds", style="Primary.TButton", command=self.generate_rounds
        ).pack(side="left", padx=(8, 0))

        ttk.Label(
            self.rounds_tab,
            text="Automatically generates the fewest rounds needed so every present player "
                 "gets at least one game in their 1st preference and one in their 2nd "
                 "preference position. Use Round Settings to confirm the number of courts "
                 "and each team's bib colour before generating.",
        ).pack(anchor="w", padx=10)

        nav = ttk.Frame(self.rounds_tab)
        nav.pack(fill="x", padx=10, pady=(10, 0))
        ttk.Button(nav, text="\u25c0 Prev Round", command=self.prev_round).pack(side="left")
        self.round_nav_label = ttk.Label(nav, text="No rounds generated yet", style="SubHeader.TLabel")
        self.round_nav_label.pack(side="left", padx=15)
        ttk.Button(nav, text="Next Round \u25b6", command=self.next_round).pack(side="left")

        order_row = ttk.Frame(self.rounds_tab)
        order_row.pack(fill="x", padx=10, pady=(8, 0))
        ttk.Label(order_row, text="Team B Order:").pack(side="left")
        self.round_order_mode = tk.StringVar(value="positional")
        ttk.Radiobutton(
            order_row, text="Positional (GS-GS)", variable=self.round_order_mode,
            value="positional", command=self.on_round_order_changed,
        ).pack(side="left", padx=(6, 0))
        ttk.Radiobutton(
            order_row, text="Match-Up (GS-GK)", variable=self.round_order_mode,
            value="matchup", command=self.on_round_order_changed,
        ).pack(side="left", padx=(6, 0))

        self.court_jump_frame = ttk.Frame(self.rounds_tab)
        self.court_jump_frame.pack(fill="x", padx=10, pady=(6, 0))
        self._court_anchors = {}  # court_number -> the widget marking that court's section

        self.rounds_scroll = ScrollableFrame(self.rounds_tab)
        self.rounds_scroll.pack(fill="both", expand=True, padx=10, pady=10)
        self.rounds_content = self.rounds_scroll.inner

        self.current_round_number = None
        self._rounds_by_number = {}  # {round_number: {court_number: {team: round_row}}}

    def open_round_settings_dialog(self):
        """Lets the coordinator confirm/change the number of courts and
        each court/team's bib colour before generating a round."""
        if not self.selected_trial_id:
            messagebox.showerror("Error", "Select a trial first (on the Trials tab).")
            return

        trial = store.get_trial(self.selected_trial_id)
        saved_colours = store.get_trial_bib_colours(self.selected_trial_id) or {}

        dialog = tk.Toplevel(self)
        dialog.title("Round Settings")
        dialog.configure(bg=WHITE)
        dialog.transient(self)
        dialog.grab_set()

        container = ttk.Frame(dialog)
        container.pack(fill="both", expand=True, padx=16, pady=16)

        ttk.Label(container, text="Courts", style="SubHeader.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        courts_var = tk.IntVar(value=trial["num_courts"])
        courts_spin = ttk.Spinbox(
            container, from_=1, to=50, textvariable=courts_var, width=6,
            command=lambda: rebuild_colour_rows(),
        )
        courts_spin.grid(row=0, column=1, sticky="w", padx=(8, 0))

        ttk.Label(container, text="Bib Colours", style="SubHeader.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(12, 0)
        )
        ttk.Label(
            container, text="One colour per team. Pre-filled with sensible defaults - "
                             "change any that clash with the venue's actual bibs.",
            style="Status.TLabel", wraplength=360,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 8))

        rows_outer = ttk.Frame(container, height=220)
        rows_outer.grid(row=3, column=0, columnspan=2, sticky="nsew")
        rows_outer.grid_propagate(False)
        rows_canvas = tk.Canvas(rows_outer, borderwidth=0, highlightthickness=0, bg=WHITE)
        rows_scrollbar = ttk.Scrollbar(rows_outer, orient="vertical", command=rows_canvas.yview)
        rows_inner = ttk.Frame(rows_canvas)
        rows_inner.bind(
            "<Configure>", lambda e: rows_canvas.configure(scrollregion=rows_canvas.bbox("all"))
        )
        rows_canvas.create_window((0, 0), window=rows_inner, anchor="nw")
        rows_canvas.configure(yscrollcommand=rows_scrollbar.set)
        rows_canvas.pack(side="left", fill="both", expand=True)
        rows_scrollbar.pack(side="right", fill="y")

        colour_entries = {}  # court_number -> {"A": Entry, "B": Entry}, current dialog state

        def default_colour(court_number, team):
            existing = saved_colours.get(court_number, {})
            if team in existing:
                return existing[team]
            return algorithm.bib_colours_for_court(court_number)[team]

        def rebuild_colour_rows():
            try:
                num_courts = courts_var.get()
            except tk.TclError:
                return
            num_courts = max(1, num_courts)

            typed = {
                court_number: {team: entry.get().strip() for team, entry in teams.items()}
                for court_number, teams in colour_entries.items()
            }

            for widget in rows_inner.winfo_children():
                widget.destroy()
            colour_entries.clear()

            for court_number in range(1, num_courts + 1):
                row = ttk.Frame(rows_inner)
                row.pack(fill="x", pady=3)

                ttk.Label(row, text=f"Court {court_number} - Team A", width=18).pack(side="left")
                entry_a = ttk.Entry(row, width=12)
                entry_a.insert(0, typed.get(court_number, {}).get("A") or default_colour(court_number, "A"))
                entry_a.pack(side="left", padx=(4, 14))

                ttk.Label(row, text="Team B").pack(side="left")
                entry_b = ttk.Entry(row, width=12)
                entry_b.insert(0, typed.get(court_number, {}).get("B") or default_colour(court_number, "B"))
                entry_b.pack(side="left", padx=(4, 0))

                colour_entries[court_number] = {"A": entry_a, "B": entry_b}

        courts_spin.bind("<KeyRelease>", lambda e: rebuild_colour_rows())
        courts_spin.bind("<FocusOut>", lambda e: rebuild_colour_rows())
        rebuild_colour_rows()

        error_label = ttk.Label(container, text="", style="Invalid.TLabel")
        error_label.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

        def save_settings():
            try:
                num_courts = courts_var.get()
            except tk.TclError:
                error_label.configure(text="Courts must be a whole number.")
                return
            if num_courts < 1:
                error_label.configure(text="Courts must be at least 1.")
                return

            bib_colours = {}
            for court_number in range(1, num_courts + 1):
                team_colours = {}
                for team, entry in colour_entries[court_number].items():
                    colour = entry.get().strip()
                    if not colour:
                        error_label.configure(
                            text=f"Court {court_number} Team {team} needs a colour."
                        )
                        return
                    team_colours[team] = colour
                bib_colours[court_number] = team_colours

            store.update_trial_courts(self.selected_trial_id, num_courts)
            store.set_trial_bib_colours(self.selected_trial_id, bib_colours)

            refreshed = store.get_trial(self.selected_trial_id)
            self.status_var.set(
                f"Trial: {refreshed['trial_name']} ({refreshed['age_group']}) - "
                f"{refreshed['num_courts']} court{'s' if refreshed['num_courts'] > 1 else ''}"
            )
            dialog.destroy()

        buttons = ttk.Frame(container)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="left", padx=(0, 6))
        ttk.Button(
            buttons, text="Save Settings", style="Primary.TButton", command=save_settings
        ).pack(side="left")

    def generate_rounds(self):
        if not self.selected_trial_id:
            messagebox.showerror("Error", "Select a trial first (on the Trials tab).")
            return

        trial = store.get_trial(self.selected_trial_id)
        num_courts = trial["num_courts"]
        confirmed_colours = store.get_trial_bib_colours(self.selected_trial_id) or {}

        present_players = store.get_present_players(self.selected_trial_id)

        try:
            rounds_output, rounds_used, failed = algorithm.generate_minimum_rounds(
                present_players, num_courts
            )
        except ValueError as e:
            messagebox.showerror("Cannot Generate Rounds", str(e))
            return

        store.clear_rounds_for_trial(self.selected_trial_id)

        for round_data in rounds_output:
            court_colours = confirmed_colours.get(round_data["court_number"])
            if court_colours and round_data["team"] in court_colours:
                bib_colour = court_colours[round_data["team"]]
            else:
                bib_colour = algorithm.COURT_BIB_COLOURS[round_data["court_number"]][round_data["team"]]
            round_id = store.create_round_entry(
                self.selected_trial_id,
                round_data["round_number"],
                round_data["court_number"],
                round_data["team"],
                bib_colour,
            )
            for assignment in round_data["assignments"]:
                store.create_assignment(
                    self.selected_trial_id, round_id, assignment["player_id"], assignment["position"]
                )

        if failed:
            messagebox.showwarning(
                "Guarantee Not Fully Met",
                f"Hit the {algorithm.MAX_ROUNDS} round safety cap and {len(failed)} player(s) "
                f"still didn't get both preferred positions. The algorithm may need a rethink "
                f"for this roster size.",
            )
        else:
            messagebox.showinfo(
                "Rounds Generated", f"Generated the minimum needed: {rounds_used} round(s)."
            )

        self.current_round_number = None
        self.refresh_rounds_display()

    def refresh_rounds_display(self):
        """Rebuilds the round_number -> court_number -> team lookup, then
        renders whichever round is currently selected (or round 1, on a
        fresh generate)."""
        self._rounds_by_number = {}
        if self.selected_trial_id:
            for r in store.get_rounds_for_trial(self.selected_trial_id):
                self._rounds_by_number.setdefault(r["round_number"], {}) \
                    .setdefault(r["court_number"], {})[r["team"]] = r

        round_numbers = sorted(self._rounds_by_number.keys())
        if not round_numbers:
            self.current_round_number = None
            self.round_nav_label.configure(text="No rounds generated yet")
            for widget in self.rounds_content.winfo_children():
                widget.destroy()
            return

        if self.current_round_number not in round_numbers:
            self.current_round_number = round_numbers[0]
        self.render_round(self.current_round_number)

    def on_round_order_changed(self):
        if self.current_round_number is not None:
            self.render_round(self.current_round_number)

    def _row_order_for_team(self, team):
        """GS..GK for Team A always, and for Team B too under "Positional"
        mode. Under "Match-Up" mode Team B is reversed (GK..GS), so each
        row lines up with the position that actually marks it on court."""
        if team == "B" and self.round_order_mode.get() == "matchup":
            return list(reversed(POSITIONS))
        return POSITIONS

    def render_round(self, round_number):
        """Draws one round: a heading, then each court stacked vertically,
        with that court's two teams side by side as separate tables."""
        round_numbers = sorted(self._rounds_by_number.keys())
        self.current_round_number = round_number
        self.round_nav_label.configure(text=f"Round {round_number} of {round_numbers[-1]}")

        for widget in self.rounds_content.winfo_children():
            widget.destroy()
        for widget in self.court_jump_frame.winfo_children():
            widget.destroy()
        self._court_anchors = {}

        courts = self._rounds_by_number[round_number]
        court_numbers = sorted(courts.keys())

        for court_number in court_numbers:
            heading = ttk.Label(
                self.rounds_content, text=f"Court {court_number}", style="SubHeader.TLabel"
            )
            heading.pack(anchor="w", pady=(10 if court_number > court_numbers[0] else 0, 4))
            self._court_anchors[court_number] = heading

            teams_row = ttk.Frame(self.rounds_content)
            teams_row.pack(fill="x")

            for team in ("A", "B"):
                round_row = courts[court_number].get(team)
                if not round_row:
                    continue

                team_block = ttk.Frame(teams_row)
                team_block.pack(side="left", padx=(0, 20), anchor="n")

                ttk.Label(team_block, text=f"Team {team}", style="SubHeader.TLabel").pack(anchor="w")
                ttk.Label(
                    team_block, text=f"Bib Colour: {round_row['bib_colour']}", style="Status.TLabel"
                ).pack(anchor="w", pady=(0, 4))

                tree = make_striped_treeview(
                    team_block,
                    columns=("position", "player", "number"),
                    headings=["Position", "Player", "Number"],
                    widths=[70, 170, 70],
                )

                assignments = store.get_assignments_for_round(round_row["trial_id"], round_row["round_id"])
                order = self._row_order_for_team(team)
                assignments.sort(key=lambda a: order.index(a["position"]))
                for a in assignments:
                    tree.insert(
                        "", "end",
                        values=(a["position"], f"{a['first_name']} {a['last_name']}", a["trial_number"]),
                    )
                tree.configure(height=max(len(assignments), 1))
                tree.pack()
                stripe_treeview(tree)

        if len(court_numbers) > 1:
            ttk.Label(self.court_jump_frame, text="Jump to:", style="Status.TLabel").pack(side="left")
            for court_number in court_numbers:
                ttk.Button(
                    self.court_jump_frame, text=f"Court {court_number}",
                    command=lambda c=court_number: self.scroll_to_court(c),
                ).pack(side="left", padx=(4, 0))

    def scroll_to_court(self, court_number):
        """Scrolls the rounds view so the given court's heading is at the top."""
        widget = self._court_anchors.get(court_number)
        if not widget:
            return
        canvas = self.rounds_scroll.canvas
        canvas.update_idletasks()
        total_height = self.rounds_content.winfo_height()
        if total_height <= 0:
            return
        fraction = widget.winfo_y() / total_height
        canvas.yview_moveto(max(0.0, min(fraction, 1.0)))

    def prev_round(self):
        round_numbers = sorted(self._rounds_by_number.keys())
        if not round_numbers or self.current_round_number is None:
            return
        index = round_numbers.index(self.current_round_number)
        if index > 0:
            self.render_round(round_numbers[index - 1])

    def next_round(self):
        round_numbers = sorted(self._rounds_by_number.keys())
        if not round_numbers or self.current_round_number is None:
            return
        index = round_numbers.index(self.current_round_number)
        if index < len(round_numbers) - 1:
            self.render_round(round_numbers[index + 1])

    # ----------------------------------------------------------------- #
    # Export tab
    # ----------------------------------------------------------------- #

    def build_export_tab(self):
        ttk.Label(
            self.export_tab,
            text="Exports the full player register for the selected trial as a clean CSV file.",
        ).pack(anchor="w", padx=10, pady=10)

        ttk.Button(
            self.export_tab, text="Export Players to CSV", style="Primary.TButton",
            command=self.export_players_csv
        ).pack(anchor="w", padx=10)

        ttk.Separator(self.export_tab, orient="horizontal").pack(fill="x", padx=10, pady=15)

        ttk.Label(
            self.export_tab,
            text="A dated backup is taken automatically every time the app starts. "
                 "You can also trigger one right now:",
        ).pack(anchor="w", padx=10)
        ttk.Button(
            self.export_tab, text="Back Up Data Now", command=self.backup_data_now
        ).pack(anchor="w", padx=10, pady=(5, 0))

    def export_players_csv(self):
        if not self.selected_trial_id:
            messagebox.showerror("Error", "Select a trial first (on the Trials tab).")
            return

        players = store.get_players_for_trial(self.selected_trial_id)
        if not players:
            messagebox.showerror("Error", "This trial has no registered players yet.")
            return

        trial = store.get_trial(self.selected_trial_id)
        default_name = f"{trial['trial_name'].replace(' ', '_')}_players.csv"

        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV files", "*.csv")],
        )
        if not filepath:
            return

        store.export_players_csv(players, filepath)
        messagebox.showinfo("Export Complete", f"Player list exported to:\n{filepath}")

    def backup_data_now(self):
        backup_path = store.backup_data()
        if backup_path:
            messagebox.showinfo("Backup Complete", f"Data backed up to:\n{backup_path}")
        else:
            messagebox.showerror("Backup Failed", "No data was found to back up.")


if __name__ == "__main__":
    app = App()
    app.mainloop()
