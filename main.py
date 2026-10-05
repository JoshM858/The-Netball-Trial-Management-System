"""
Main GUI for the Netball Trial Management System: login, tabs for Trials,
Players, Roll Call, Rounds and Export, plus the styling shared across all
of them.

can_edit() decides who may change things: on the Rounds tab only the
coordinator sees the Generate Rounds and Round Settings buttons, so a coach only has a
view-only draw.
"""

import hashlib
import hmac
import secrets
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import players as store
import algorithm

# The seven netball positions in court order, goal shooter to goal keeper
POSITIONS = ["GS", "GA", "WA", "C", "WD", "GD", "GK"]

# Longest playing history the form accepts (same limit as the sign-up form)
PLAYING_HISTORY_MAX_CHARS = 150


# --------------------------------------------------------------------------- #
# Auth & role-based access control
# --------------------------------------------------------------------------- #
# A `User` object represents the logged-in session. It keeps its details private and
# hands the questions about tabs to its Role object, which knows which tabs that role
# may see (has_access) and edit (can_edit). login() checks username + password +
# selected role against the users records.

# Roles offered in the login dropdown; each must match the role saved on an account. A tuple,
# not a list, because the roles are fixed and nothing should add to or change them while running.
VALID_ROLES = ("coordinator", "coach", "player")


class Role:
    """Base class for a role. On its own it is the safest role: no tabs and view-only.
    Each real role below only fills in or overrides what is different about it."""

    # The tabs this role may open. A frozenset: the tabs are fixed, a tab is either allowed
    # or not, and `tab_name in tabs` is the whole check.
    tabs = frozenset()

    def __init__(self, name=""):
        """Stores the role's name, e.g. 'coach'."""
        self.name = name

    def display_name(self):
        """Returns the role as it should be shown on screen."""
        return self.name.title()

    def has_access(self, tab_name):
        """Returns True if this role is allowed to open the given tab."""
        return tab_name in self.tabs

    def can_edit(self, tab_name):
        """Returns True if this role may change things on the given tab. False unless a
        subclass overrides this, so a new role is view-only by default."""
        return False


class Coordinator(Role):
    """Can open every tab and change things on all of them."""

    tabs = frozenset({"Trials", "Players", "Roll Call", "Rounds", "Export"})

    def can_edit(self, tab_name):
        """Overrides Role.can_edit(): a coordinator can edit any tab they can open."""
        return self.has_access(tab_name)


class Coach(Role):
    """Can only open the Rounds tab. Does not override can_edit(), so it stays view-only:
    a coach can read the draw but not change it."""

    tabs = frozenset({"Rounds"})


class PlayerParent(Role):
    """Can only open the Players tab, to register a player."""

    tabs = frozenset({"Players"})

    def display_name(self):
        """Overrides Role.display_name(): shown as 'Player/Parent', not 'Player'."""
        return "Player/Parent"

    def can_edit(self, tab_name):
        """Overrides Role.can_edit(): a player or parent may register on the Players tab."""
        return tab_name == "Players"


# Looks up a role's name to find its class. An unknown name falls back to the base Role.
ROLE_CLASSES = {
    "coordinator": Coordinator,
    "coach": Coach,
    "player": PlayerParent,
}


def new_salt():
    """Returns a random 16-byte salt as 32 hex characters. A new one is made for each account."""
    return secrets.token_hex(16)


def hash_password(plain_password, salt_hex):
    """Returns SHA-256(salt + password) as 64 hex characters. Each account
    gets its own random salt so two accounts with the same password don't
    end up with the same hash."""
    salted = bytes.fromhex(salt_hex) + plain_password.encode("utf-8")
    return hashlib.sha256(salted).hexdigest()


def verify_password(plain_password, salt_hex, stored_hash):
    """Hashes the typed password with the stored salt and compares it with the stored hash.
    compare_digest takes the same time whether or not the first characters match."""
    return hmac.compare_digest(hash_password(plain_password, salt_hex or ""), stored_hash)


class User:
    """Represents the currently logged-in user for the duration of a session. The details
    are private (name-mangled) and can only be read through properties, so other code
    cannot change who is logged in."""

    def __init__(self, user_id, username, role):
        """Stores who is logged in: their id, username and role."""
        self.__user_id = user_id
        self.__username = username
        self.__role_name = role
        # An unknown role name gets the base Role: no tabs and view-only
        self.__role = ROLE_CLASSES.get(role, Role)(role)

    @property
    def user_id(self):
        """The account's id (read-only)."""
        return self.__user_id

    @property
    def username(self):
        """The account's username (read-only)."""
        return self.__username

    @property
    def role(self):
        """The role's name, e.g. 'coach' (read-only)."""
        return self.__role_name

    def has_access(self, tab_name):
        """Asks this user's Role whether it can open the tab."""
        return self.__role.has_access(tab_name)

    def can_edit(self, tab_name):
        """Asks this user's Role whether it can change things on the tab. Each Role class
        answers in its own way, so this one call works for every role."""
        return self.__role.can_edit(tab_name)

    def display_role(self):
        """Returns the role as it should be shown on screen, e.g. 'Player/Parent'."""
        return self.__role.display_name()


def login(username, password, role):
    """Checks username + password + the role picked on the login screen.
    Returns a User on success, None on failure."""
    # record is the account row from users.csv, or None if the username does not exist
    record = store.get_user_by_username(username.strip())
    # Each failed check returns None in the same way, so the caller cannot tell which detail was wrong
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

# Colours used by every screen so the look stays the same
NAVY = "#1f3864"
WHITE = "#ffffff"
LIGHT_GREY = "#f2f2f2"
DARK_GREY = "#555555"
GREEN = "#2e7d32"
RED = "#c62828"

# One font for the whole app
FONT_FAMILY = "Arial"


def setup_styles(root):
    """Configures a consistent ttk theme across the whole application.
    Call this once, right after creating the root window."""
    style = ttk.Style(root)
    # Use the clam theme if it is available; otherwise keep the default theme
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
    # Tag every row odd or even by its place in the table, so the two colours alternate
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
    # Set each column's heading and width (120 pixels if no widths were given)
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
        """Builds the canvas, scrollbar and inner frame that make up the scrolling area."""
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
        """Returns a function that scrolls the given canvas when the mouse wheel is turned."""
        def handler(event):
            """Scrolls one step per wheel notch (event.delta is 120 per notch on Windows)."""
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return handler


class App(tk.Tk):
    """The main window. Shows the login screen, then the tabs for the logged-in role, and
    keeps track of the current user, the selected trial and the roll call ticks."""
    def __init__(self):
        """Sets up the window, styles and data files, takes a backup, then shows the login screen."""
        super().__init__()
        self.title("Netball Trial Management System")
        self.geometry("900x600")

        setup_styles(self)

        store.init_data()
        store.backup_data()

        # The logged-in User; None while nobody is logged in
        self.current_user = None
        # id of the trial the tabs are working on; None until one is picked
        self.selected_trial_id = None
        # A dictionary of player id -> IntVar, so any player's tick box is found from their id, even
        # while a search hides other rows. An IntVar because a Checkbutton reads and writes 1 or 0,
        # and that same 1/0 is what is saved as is_present in the Attendance CSV.
        self.attendance_vars = {}
        # Text shown in the grey status bar at the bottom of the window
        self.status_var = tk.StringVar(value="No trial selected")

        self.build_login_screen()

    # ----------------------------------------------------------------- #
    # Login
    # ----------------------------------------------------------------- #

    def build_login_screen(self):
        """Draws the username, password and role boxes and the Log In button."""
        build_header_bar(self, "Netball Trial Management System").pack(fill="x")

        # Everything on the login screen sits in this one frame so it can be centred
        self.login_frame = ttk.Frame(self)
        self.login_frame.pack(expand=True)

        ttk.Label(self.login_frame, text="Username").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        self.login_username_entry = ttk.Entry(self.login_frame)
        self.login_username_entry.grid(row=1, column=1, pady=5)

        ttk.Label(self.login_frame, text="Password").grid(row=2, column=0, sticky="e", padx=5, pady=5)
        self.login_password_entry = ttk.Entry(self.login_frame, show="*")
        self.login_password_entry.grid(row=2, column=1, pady=5)

        ttk.Label(self.login_frame, text="Role").grid(row=3, column=0, sticky="e", padx=5, pady=5)
        # Read-only Combobox of VALID_ROLES, so a role can only be picked from the list, never typed.
        self.login_role_combo = ttk.Combobox(
            self.login_frame, values=list(VALID_ROLES), state="readonly"
        )
        # Start on coordinator, the most common login
        self.login_role_combo.set("coordinator")
        self.login_role_combo.grid(row=3, column=1, pady=5)

        ttk.Button(
            self.login_frame, text="Log In", style="Primary.TButton", command=self.attempt_login
        ).grid(row=4, column=0, columnspan=2, pady=15)

        self.login_error_label = ttk.Label(self.login_frame, text="", style="Invalid.TLabel")
        self.login_error_label.grid(row=5, column=0, columnspan=2)

        # First-run help: shows the default account to log in with.
        ttk.Label(
            self.login_frame,
            text="First run? Default login is coordinator / coordinator123",
            style="Status.TLabel",
        ).grid(row=6, column=0, columnspan=2, pady=(10, 0))

    def attempt_login(self):
        """Runs when Log In is pressed: checks the boxes are filled in, then logs in or shows one
        vague error message (so nobody can tell which part was wrong)."""
        # Read the boxes; strip() removes accidental spaces around the username
        username = self.login_username_entry.get().strip()
        password = self.login_password_entry.get()
        role = self.login_role_combo.get()

        # Existence check: all three boxes must have something in them
        if not username or not password or not role:
            self.login_error_label.configure(text="All fields are required.")
            return

        # login() gives back a User if all three details match, otherwise None
        user = login(username, password, role)
        if not user:
            # Deliberately vague, so nobody can tell which of the three details was wrong.
            self.login_error_label.configure(text="Incorrect username, password, or role.")
            self.login_password_entry.delete(0, "end")
            return

        self.current_user = user
        # Remove the login screen's widgets before the dashboard is built
        for widget in self.winfo_children():
            widget.destroy()
        self.build_main_app()

    def log_out(self):
        """Destroys the dashboard, forgets the session and goes back to the login screen."""
        # Remove every widget of the dashboard
        for widget in self.winfo_children():
            widget.destroy()

        # Clear out widget references from the previous session - without
        # this, logging in as a role with fewer tabs (e.g. coach after a
        # coordinator session) would leave stale attributes like
        # self.players_tree pointing at an already-destroyed widget, and
        # select_trial()'s hasattr() checks would wrongly think that tab
        # still exists and crash trying to use it.
        stale_attrs = [
            "trials_tab", "players_tab", "roll_call_tab", "rounds_tab", "export_tab",
            "trials_tree", "players_tree", "roll_call_frame", "round_nav_label",
            "rounds_content", "trial_picker_combo", "roll_call_search_var",
            "court_jump_frame", "round_order_mode",
        ]
        # Delete each of those attributes, if this session created it
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
        """Builds the dashboard after login: header, who is logged in, the trial picker (for roles
        with no Trials tab), the status bar and one tab for each screen the role may see."""
        build_header_bar(self, "Netball Trial Management System").pack(fill="x")

        # Thin bar under the header showing who is logged in, with the Log Out button
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
            # Read-only Combobox: a role without the Trials tab can only pick a trial that exists.
            self.trial_picker_combo = ttk.Combobox(
                picker, textvariable=self.trial_picker_var, state="readonly", width=40
            )
            self.trial_picker_combo.pack(side="left", padx=5)
            self.trial_picker_combo.bind("<<ComboboxSelected>>", self.on_trial_picker_selected)
            # Kept so the dropdown row that is picked can be matched back to a trial id
            self._trial_picker_options = store.get_all_trials()
            self.trial_picker_combo["values"] = [
                f"{t['trial_id']} - {t['trial_name']} ({t['age_group']})"
                for t in self._trial_picker_options
            ]

        # Status bar goes at the bottom, packed BEFORE the notebook (below)
        # so it stays pinned to the bottom edge and the notebook fills
        # whatever vertical space is left over.
        show_status_bar(self, self.status_var).pack(fill="x", side="bottom")

        # The notebook holds one tab for each screen (Trials, Players, Roll Call...)
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        # Only build/add a tab if the logged-in role is actually allowed to
        # see it - tab_name here must match the tab names in the Role classes.
        # A list of tuples: (tab name, attribute name, build method). A list because the tabs must
        # appear in this order; a tuple because each trio always travels together. Holding the build
        # methods lets one loop build only the tabs this role may see.
        tab_definitions = [
            ("Trials", "trials_tab", self.build_trials_tab),
            ("Players", "players_tab", self.build_players_tab),
            ("Roll Call", "roll_call_tab", self.build_roll_call_tab),
            ("Rounds", "rounds_tab", self.build_rounds_tab),
            ("Export", "export_tab", self.build_export_tab),
        ]

        # Loop over every tab; the continue below skips tabs this role may not see
        for tab_name, attr_name, build_method in tab_definitions:
            if not self.current_user.has_access(tab_name):
                continue
            frame = ttk.Frame(notebook)
            setattr(self, attr_name, frame)
            notebook.add(frame, text=tab_name)
            build_method()

    def on_trial_picker_selected(self, event):
        """Runs when a trial is picked in the dropdown (roles with no Trials tab)."""
        # current() is the row picked in the dropdown, or -1 if nothing is picked
        index = self.trial_picker_combo.current()
        if index < 0:
            return
        trial = self._trial_picker_options[index]
        self.select_trial(trial["trial_id"])

    # ----------------------------------------------------------------- #
    # Trials tab
    # ----------------------------------------------------------------- #

    def build_trials_tab(self):
        """Builds the form for creating a trial and the table listing all trials."""
        # form holds the boxes for creating a new trial
        form = ttk.Frame(self.trials_tab)
        form.pack(fill="x", padx=10, pady=10)

        ttk.Label(form, text="Trial Name").grid(row=0, column=0, sticky="w")
        # Entry for free text (a trial name can be anything). It comes back as a str, so create_trial()
        # strips it and checks it before use.
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
        # IntVar holds the spinbox number; starts at 1 court. A Spinbox (1 to 50), because courts is a
        # whole number and the arrows keep it in range. IntVar.get() still fails if text is typed in,
        # so create_trial() catches that.
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

        # Table of all trials; clicking a row makes it the active trial
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
        """Checks the Trials form (required boxes, courts, birth years) and saves a new trial."""
        # Read every box on the form; an empty box gives an empty string
        name = self.trial_name_entry.get().strip()
        age_group = self.age_group_entry.get().strip()
        date = self.trial_date_entry.get().strip()
        min_year_text = self.min_birth_year_entry.get().strip()
        max_year_text = self.max_birth_year_entry.get().strip()

        # Existence check: name, age group and date are all required
        if not name or not age_group or not date:
            messagebox.showerror("Error", "All fields are required.")
            return

        # The date must be a real DD/MM/YYYY date (31/02/2026 is refused)
        if not store.is_valid_date(date):
            messagebox.showerror("Error", "Trial date must be a real date in DD/MM/YYYY format.")
            return

        # Refuse a second trial with the same name on the same date
        for existing in store.get_all_trials():
            if existing["trial_name"].lower() == name.lower() and existing["trial_date"] == date:
                messagebox.showerror("Error", f"A trial called '{name}' on {date} already exists.")
                return

        # IntVar.get() raises TclError if the Spinbox holds something that
        # isn't a whole number (e.g. cleared by hand) rather than quietly
        # falling back to a default.
        try:
            num_courts = self.num_courts_var.get()
        except tk.TclError:
            messagebox.showerror("Error", "Courts must be a whole number.")
            return
        # Range check: a trial needs at least one court
        if num_courts < 1:
            messagebox.showerror("Error", "Courts must be at least 1.")
            return

        # Birth years are optional, but if either is given both must be
        # given and both must actually be numbers.
        # None means no age window, so the trial is created without a birth year check
        min_birth_year = max_birth_year = None
        if min_year_text or max_year_text:
            if not (min_year_text.isdigit() and max_year_text.isdigit()):
                messagebox.showerror("Error", "Birth years must be whole numbers, e.g. 2013.")
                return
            min_birth_year, max_birth_year = int(min_year_text), int(max_year_text)
            # Range check: the earliest birth year can't be after the latest
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
        """Reloads the table of trials from the CSV file."""
        self.trials_tree.delete(*self.trials_tree.get_children())
        # One table row for each trial; the row's id is the trial id, so a click can find the trial
        for t in store.get_all_trials():
            # e.g. '2 courts' or '1 court' - the s is only added for more than one
            courts_text = f"{t['num_courts']} court{'s' if t['num_courts'] > 1 else ''}"
            self.trials_tree.insert(
                "", "end", iid=str(t["trial_id"]),
                values=(t["trial_name"], t["age_group"], t["trial_date"], courts_text),
            )
        stripe_treeview(self.trials_tree)

    def on_select_trial(self, event):
        """Runs when a row in the trials table is clicked and makes that trial the active one."""
        selection = self.trials_tree.selection()
        # Stop if no row is selected
        if not selection:
            return
        self.select_trial(int(selection[0]))

    def select_trial(self, trial_id):
        """Sets the active trial and refreshes whichever tabs the current
        role actually has (a coach won't have players_tree etc,
        since they don't get the Players tab)."""
        self.selected_trial_id = trial_id
        trial = store.get_trial(trial_id)
        # Show the trial's name and number of courts in the status bar
        if trial:
            self.status_var.set(
                f"Trial: {trial['trial_name']} ({trial['age_group']}) - "
                f"{trial['num_courts']} court{'s' if trial['num_courts'] > 1 else ''}"
            )
        # Only refresh the tabs this role has; hasattr() is False for a tab that was never built
        if hasattr(self, "players_tree"):
            self.refresh_players_list()
        if hasattr(self, "roll_call_frame"):
            self.refresh_roll_call()
        # rounds_content is the Rounds tab's real widget (there is no
        # attribute called rounds_display), so view-only roles see the saved
        # draw as soon as they pick a trial.
        if hasattr(self, "rounds_content"):
            self.refresh_rounds_display()

    # ----------------------------------------------------------------- #
    # Players tab
    # ----------------------------------------------------------------- #

    def build_players_tab(self):
        """Builds the registration form (all 14 details, so walk-ons can be entered too)
        and the table of registered players."""
        form = ttk.Frame(self.players_tab)
        form.pack(fill="x", padx=10, pady=10)

        # (label, attribute name of the text box) for the left and right halves of the form
        left_fields = [
            ("First Name", "first_name_entry"), ("Last Name", "last_name_entry"),
            ("DOB (DD/MM/YYYY)", "dob_entry"), ("Netball ID", "netball_id_entry"),
            ("Address", "address_entry"), ("Phone", "phone_entry"), ("Email", "email_entry"),
        ]
        right_fields = [
            ("Parent/Guardian Name", "parent_name_entry"), ("Parent/Guardian Phone", "parent_phone_entry"),
            ("Parent/Guardian Email", "parent_email_entry"),
        ]
        # Left half: one label and text box per row, stored on self under its attribute name
        for row, (label, attr) in enumerate(left_fields):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=2)
            entry = ttk.Entry(form, width=30)
            entry.grid(row=row, column=1, padx=(5, 20), pady=2)
            setattr(self, attr, entry)
        # Right half: the same, in columns 2 and 3
        for row, (label, attr) in enumerate(right_fields):
            ttk.Label(form, text=label).grid(row=row, column=2, sticky="w", pady=2)
            entry = ttk.Entry(form, width=30)
            entry.grid(row=row, column=3, padx=5, pady=2)
            setattr(self, attr, entry)
        self.dob_entry.bind("<KeyRelease>", self.on_dob_typed)

        # Read-only Comboboxes, so only the seven real positions can be picked. A mistyped position
        # could never be given to anyone by the rotation algorithm.
        for row, (label, attr) in enumerate(
                [("Position 1", "pos1_combo"), ("Position 2", "pos2_combo"), ("Position 3", "pos3_combo")],
                start=3):
            ttk.Label(form, text=label).grid(row=row, column=2, sticky="w", pady=2)
            combo = ttk.Combobox(form, values=POSITIONS, state="readonly", width=10)
            combo.grid(row=row, column=3, padx=5, pady=2, sticky="w")
            setattr(self, attr, combo)

        ttk.Label(form, text="Playing History").grid(row=6, column=2, sticky="w", pady=2)
        # Entry (one line) for playing history, because the coordinator types a short note. Its length
        # is checked against PLAYING_HISTORY_MAX_CHARS in create_player().
        self.playing_history_entry = ttk.Entry(form, width=30)
        self.playing_history_entry.grid(row=6, column=3, padx=5, pady=2)

        # Live feedback as the coordinator types - informational only,
        # never blocks registration, since a permit might apply.
        self.dob_validation_label = ttk.Label(form, text="", style="Valid.TLabel")
        self.dob_validation_label.grid(row=7, column=0, columnspan=4, sticky="w", pady=(4, 0))

        ttk.Button(
            form, text="Register Player", style="Primary.TButton", command=self.create_player
        ).grid(row=8, column=0, columnspan=4, pady=8)

        # Table of everyone registered for the selected trial, with every detail
        # (scrollbars because there are too many columns to fit the window)
        table_frame = ttk.Frame(self.players_tab)
        table_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.players_tree = make_striped_treeview(
            table_frame,
            columns=("trial_no", "name", "dob", "netball_id", "address", "phone", "email",
                     "parent_name", "parent_phone", "parent_email", "pos1", "pos2", "pos3", "history"),
            headings=["#", "Name", "DOB", "Netball ID", "Address", "Phone", "Email",
                      "Parent/Guardian", "Parent Phone", "Parent Email", "Pos 1", "Pos 2", "Pos 3", "Playing History"],
            widths=[40, 160, 90, 90, 200, 100, 180, 140, 100, 180, 50, 50, 50, 250],
        )
        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.players_tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.players_tree.xview)
        self.players_tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        y_scroll.pack(side="right", fill="y")
        x_scroll.pack(side="bottom", fill="x")
        self.players_tree.pack(fill="both", expand=True)

    def on_dob_typed(self, event=None):
        """Checks the DOB typed so far against the selected trial's birth
        year window and shows a green tick or red warning. Never blocks
        anything here; the checks that can refuse a player are in create_player()."""
        dob = self.dob_entry.get().strip()
        # Nothing typed, or no trial picked: clear the message and stop
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
        """Checks the registration form and saves a new player for the selected trial."""
        # A player is always saved into a trial, so one must be selected first
        if not self.selected_trial_id:
            messagebox.showerror("Error", "Select a trial first (on the Trials tab).")
            return

        # Read the form; pos1 to pos3 are the position codes picked in the dropdowns. One dictionary of
        # field name -> text, not 14 separate variables: all(details.values()) checks every field in one
        # step, and the keys are the same names players.create_player() uses.
        details = {
            "first_name": self.first_name_entry.get().strip(),
            "last_name": self.last_name_entry.get().strip(),
            "dob": self.dob_entry.get().strip(),
            "netball_id": self.netball_id_entry.get().strip(),
            "address": self.address_entry.get().strip(),
            "phone": self.phone_entry.get().strip(),
            "email": self.email_entry.get().strip(),
            "parent_name": self.parent_name_entry.get().strip(),
            "parent_phone": self.parent_phone_entry.get().strip(),
            "parent_email": self.parent_email_entry.get().strip(),
            "playing_history": self.playing_history_entry.get().strip(),
            "position_1": self.pos1_combo.get(),
            "position_2": self.pos2_combo.get(),
            "position_3": self.pos3_combo.get(),
        }

        # Every one of the 14 details is needed, even for a walk-on
        if not all(details.values()):
            messagebox.showerror("Error", "All fields are required.")
            return

        # Type check: the date of birth must be a real DD/MM/YYYY date
        if not store.is_valid_date(details["dob"]):
            messagebox.showerror("Error", "DOB must be in DD/MM/YYYY format.")
            return
        # Range check: a date of birth can't be after today
        if store.is_future_date(details["dob"]):
            messagebox.showerror("Error", "Date of birth can't be in the future.")
            return
        # A set drops repeats, so fewer than 3 items means two of the positions are the same
        if len({details["position_1"], details["position_2"], details["position_3"]}) < 3:
            messagebox.showerror("Error", "Position 1, Position 2 and Position 3 must all be different.")
            return
        # Names can't contain a digit (checks every character of both names)
        if any(ch.isdigit() for ch in details["first_name"] + details["last_name"]):
            messagebox.showerror("Error", "Names can't contain numbers.")
            return
        # Both phone numbers go through the same check; label names the box in the error message
        for label, key in (("Phone", "phone"), ("Parent/Guardian Phone", "parent_phone")):
            if not store.is_valid_phone(details[key]):
                messagebox.showerror("Error", f"{label} must be an Australian number, e.g. 0412 345 678.")
                return
        # Both email addresses go through the same check
        for label, key in (("Email", "email"), ("Parent/Guardian Email", "parent_email")):
            if not store.is_valid_email(details[key]):
                messagebox.showerror("Error", f"{label} must look like name@example.com.")
                return
        # Range check: playing history has a maximum length
        if len(details["playing_history"]) > PLAYING_HISTORY_MAX_CHARS:
            messagebox.showerror("Error", f"Playing history can be at most {PLAYING_HISTORY_MAX_CHARS} characters.")
            return

        # create_player() saves the row and gives back the number this player wears in the trial
        trial_number = store.create_player(
            self.selected_trial_id, details["first_name"], details["last_name"], details["dob"],
            details["position_1"], details["position_2"],
            netball_id=details["netball_id"], address=details["address"], phone=details["phone"],
            email=details["email"], parent_name=details["parent_name"],
            parent_phone=details["parent_phone"], parent_email=details["parent_email"],
            playing_history=details["playing_history"], position_3=details["position_3"],
        )

        # Empty every box ready for the next player
        for entry in (
            self.first_name_entry, self.last_name_entry, self.dob_entry, self.netball_id_entry,
            self.address_entry, self.phone_entry, self.email_entry, self.parent_name_entry,
            self.parent_phone_entry, self.parent_email_entry, self.playing_history_entry,
        ):
            entry.delete(0, "end")
        self.dob_validation_label.configure(text="")
        # Set the three position dropdowns back to blank
        for combo in (self.pos1_combo, self.pos2_combo, self.pos3_combo):
            combo.set("")

        messagebox.showinfo("Registered", f"Player registered. Trial number: {trial_number}")

        self.refresh_players_list()
        self.refresh_roll_call()

    def refresh_players_list(self):
        """Reloads the players table for the selected trial."""
        self.players_tree.delete(*self.players_tree.get_children())
        # No trial selected: leave the table empty
        if not self.selected_trial_id:
            return
        # players is a list of dicts (one per player) sorted by trial number
        players = store.get_players_for_trial(self.selected_trial_id)
        # One table row per player; the row's id is the player id
        for p in players:
            self.players_tree.insert(
                "", "end", iid=str(p["player_id"]),
                values=(
                    f"#{p['trial_number']}",
                    f"{p['first_name']} {p['last_name']}",
                    p["dob"], p["netball_id"], p["address"], p["phone"], p["email"],
                    p["parent_name"], p["parent_phone"], p["parent_email"],
                    p["position_1"], p["position_2"], p["position_3"], p["playing_history"],
                ),
            )
        stripe_treeview(self.players_tree)

    # ----------------------------------------------------------------- #
    # Roll Call tab
    # ----------------------------------------------------------------- #

    def build_roll_call_tab(self):
        """Builds the search box, Select All / Clear All buttons, the scrolling tick list and
        the Confirm Roll Call button."""
        ttk.Label(
            self.roll_call_tab, text="Tick each player who is present for this trial:"
        ).pack(anchor="w", padx=10, pady=(10, 0))

        # Search box: filters the list below by name or trial number as you type
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

        # A list of player dictionaries in trial-number order, loaded once per trial. A list because
        # the tick boxes are shown in that order. Kept so searching doesn't re-read the CSV.
        self._roll_call_players = []
        # A list of the ids shown after the search filter. Select All and Clear All only use this
        # list, so they change just the players you can see.
        self._visible_player_ids = []

    def refresh_roll_call(self):
        """Reloads the players and their saved ticks for the selected trial, then redraws the list."""
        self.attendance_vars = {}
        # Players for the selected trial.
        # _visible_player_ids (below) are the ones shown after filtering; Select All / Clear All use them.
        self._roll_call_players = []
        # Clear the search box, if the Roll Call tab has been built
        if hasattr(self, "roll_call_search_var"):
            self.roll_call_search_var.set("")

        if self.selected_trial_id:
            self._roll_call_players = store.get_players_for_trial(self.selected_trial_id)
            # existing is {player_id: 0 or 1} from the last saved roll call, so ticks come back when a trial is reopened
            existing = store.get_attendance_map(self.selected_trial_id)
            # One IntVar per player, starting at the saved tick (0 if none was saved)
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
        # Remove the old tick boxes before drawing the filtered list
        for widget in self.roll_call_frame.winfo_children():
            widget.destroy()

        # What is typed in the search box, lower case so capitals do not matter
        query = self.roll_call_search_var.get().strip().lower() if hasattr(self, "roll_call_search_var") else ""
        # A purely numeric search means "trial number", and should match
        # exactly - typing 99 shouldn't also pull in #199, #299, etc.
        query_is_number = query.isdigit()
        self._visible_player_ids = []

        # Draw a tick box for each player that matches the search; continue skips the others
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

        # A search that matches nobody shows a message instead of a blank list
        if query and not self._visible_player_ids:
            ttk.Label(
                self.roll_call_frame, text="No players match that search.", style="Status.TLabel"
            ).pack(anchor="w", pady=6)

    def select_all_present(self):
        """Ticks every player currently shown (so it respects the search filter)."""
        # Set each visible player's tick variable to 1 (ticked)
        for player_id in self._visible_player_ids:
            self.attendance_vars[player_id].set(1)

    def clear_all_present(self):
        """Un-ticks every player currently shown (so it respects the search filter)."""
        # Set each visible player's tick variable to 0 (not ticked)
        for player_id in self._visible_player_ids:
            self.attendance_vars[player_id].set(0)

    def confirm_roll_call(self):
        """Saves each player's tick to the Attendance file and tells the user how many are present."""
        # The roll call is saved against a trial, so one must be selected
        if not self.selected_trial_id:
            messagebox.showerror("Error", "Select a trial first (on the Trials tab).")
            return

        # Save every player's tick, including players hidden by the search
        for player_id, var in self.attendance_vars.items():
            store.set_attendance(player_id, self.selected_trial_id, bool(var.get()))

        # Counts the ticked boxes (var.get() is 1 when ticked)
        present_count = sum(1 for var in self.attendance_vars.values() if var.get())
        messagebox.showinfo("Roll Call Saved", f"{present_count} players marked present.")

    # ----------------------------------------------------------------- #
    # Rounds tab
    # ----------------------------------------------------------------- #

    def build_rounds_tab(self):
        """Builds the Rounds tab. Only roles that can edit it get the Generate and Settings buttons."""
        form = ttk.Frame(self.rounds_tab)
        form.pack(fill="x", padx=10, pady=10)

        # Only roles allowed to edit the Rounds tab get the buttons that
        # change the draw; everyone else just reads it.
        if self.current_user.can_edit("Rounds"):
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
        else:
            ttk.Label(
                self.rounds_tab,
                text="View only: you can see the draw but not change it.",
                style="Status.TLabel",
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
        # 'positional' lines Team B up GS-GS; 'matchup' reverses it so GS faces GK
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
        # A dictionary of court number -> its heading widget, so a "Jump to" button can scroll straight
        # to that court. Emptied and rebuilt every time a round is drawn.
        self._court_anchors = {}  # court_number -> the widget marking that court's section

        self.rounds_scroll = ScrollableFrame(self.rounds_tab)
        self.rounds_scroll.pack(fill="both", expand=True, padx=10, pady=10)
        self.rounds_content = self.rounds_scroll.inner

        self.current_round_number = None
        # Dictionaries inside dictionaries: round -> court -> team -> that team's row. The screen finds
        # a team with three keys instead of searching every row each time Next/Prev is pressed.
        self._rounds_by_number = {}  # {round_number: {court_number: {team: round_row}}}

    def open_round_settings_dialog(self):
        """Lets the coordinator confirm/change the number of courts and
        each court/team's bib colour before generating a round."""
        # Second check of the role: the buttons are hidden from view-only roles, and this refuses them as well
        if not self.current_user.can_edit("Rounds"):
            messagebox.showerror("Not allowed", "Only a coordinator can change the draw.")
            return
        # Settings belong to a trial, so one must be selected
        if not self.selected_trial_id:
            messagebox.showerror("Error", "Select a trial first (on the Trials tab).")
            return

        trial = store.get_trial(self.selected_trial_id)
        # Colours saved earlier for this trial, or {} so the defaults are used
        saved_colours = store.get_trial_bib_colours(self.selected_trial_id) or {}

        # Toplevel is a pop-up window; grab_set() below stops the main window being used until it closes
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
        # Starts on the trial's current number of courts. Same idea as the Trials tab: a whole-number
        # Spinbox backed by an IntVar.
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

        # Holds the colour boxes so their text can be read when Save is pressed. A dictionary inside a
        # dictionary, court -> {"A": Entry, "B": Entry}. It holds the boxes themselves, not just colours,
        # so typed text is kept when the number of courts changes. Entry, because bib colours are free text.
        colour_entries = {}  # court_number -> {"A": Entry, "B": Entry}, current dialog state

        def default_colour(court_number, team):
            """Returns the colour to pre-fill for a team: the saved one if there is one, otherwise the default."""
            existing = saved_colours.get(court_number, {})
            # Use the colour saved for this team if there is one
            if team in existing:
                return existing[team]
            return algorithm.bib_colours_for_court(court_number)[team]

        def rebuild_colour_rows():
            """Redraws the bib colour boxes to match the number of courts, keeping anything already typed."""
            # A half-typed or empty Courts box raises TclError; leave the rows as they are until it is a number
            try:
                num_courts = courts_var.get()
            except tk.TclError:
                return
            num_courts = max(1, num_courts)

            # Remember what is typed in each box before the boxes are destroyed
            typed = {
                court_number: {team: entry.get().strip() for team, entry in teams.items()}
                for court_number, teams in colour_entries.items()
            }

            # Remove the old rows, then forget their boxes
            for widget in rows_inner.winfo_children():
                widget.destroy()
            colour_entries.clear()

            # One row per court: a Team A box and a Team B box, pre-filled with the typed, saved or default colour
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
            """Checks the courts and colour boxes, then saves them to the trial and closes the dialog."""
            # Type check: the Courts box must hold a whole number
            try:
                num_courts = courts_var.get()
            except tk.TclError:
                error_label.configure(text="Courts must be a whole number.")
                return
            # Range check: at least one court
            if num_courts < 1:
                error_label.configure(text="Courts must be at least 1.")
                return

            bib_colours = {}
            # Collect the colour typed for every team on every court; an empty box stops the save
            for court_number in range(1, num_courts + 1):
                team_colours = {}
                # Team A, then Team B, for this court
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
        """Runs the rotation algorithm for the players marked present and saves the draw,
        replacing any earlier draw for this trial."""
        # Second check of the role: the buttons are hidden from view-only roles, and this refuses them as well
        if not self.current_user.can_edit("Rounds"):
            messagebox.showerror("Not allowed", "Only a coordinator can change the draw.")
            return
        # A draw belongs to a trial, so one must be selected
        if not self.selected_trial_id:
            messagebox.showerror("Error", "Select a trial first (on the Trials tab).")
            return

        # Ask before replacing a draw that already exists
        if store.get_rounds_for_trial(self.selected_trial_id) and not messagebox.askyesno(
                "Replace Draw", "This trial already has a draw. Generating again will replace it. Continue?"):
            return

        trial = store.get_trial(self.selected_trial_id)
        num_courts = trial["num_courts"]
        # Colours chosen in Round Settings, or {} to use the default colours
        confirmed_colours = store.get_trial_bib_colours(self.selected_trial_id) or {}

        # Only players ticked present on the roll call go into the draw
        present_players = store.get_present_players(self.selected_trial_id)

        # generate_minimum_rounds() raises ValueError if the draw cannot be made (e.g. too few players present)
        try:
            # rounds_output = every team's line-up, rounds_used = number of rounds, failed = players who missed a preferred position (empty is good)
            rounds_output, rounds_used, failed = algorithm.generate_minimum_rounds(
                present_players, num_courts
            )
        except ValueError as e:
            messagebox.showerror("Cannot Generate Rounds", str(e))
            return

        # Remove the old draw first so the new one replaces it
        store.clear_rounds_for_trial(self.selected_trial_id)

        # Save each team of each round: one Rounds row, then one Assignments row per player
        for round_data in rounds_output:
            court_colours = confirmed_colours.get(round_data["court_number"])
            # Use the colour confirmed in Round Settings if there is one, otherwise the default for that court
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
            # One Assignments row for each player in the team
            for assignment in round_data["assignments"]:
                store.create_assignment(
                    self.selected_trial_id, round_id, assignment["player_id"], assignment["position"]
                )

        # failed is empty when every player got both preferred positions
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
        # Group the saved rows by round, then court, then team (setdefault makes each inner dictionary the first time)
        if self.selected_trial_id:
            for r in store.get_rounds_for_trial(self.selected_trial_id):
                self._rounds_by_number.setdefault(r["round_number"], {}) \
                    .setdefault(r["court_number"], {})[r["team"]] = r

        # Sorted list of the round numbers that exist, e.g. [1, 2, 3]
        round_numbers = sorted(self._rounds_by_number.keys())
        # No draw saved for this trial: show the empty message and clear the screen
        if not round_numbers:
            self.current_round_number = None
            self.round_nav_label.configure(text="No rounds generated yet")
            for widget in self.rounds_content.winfo_children():
                widget.destroy()
            return

        # Stay on the round being viewed if it still exists; otherwise go to the first round
        if self.current_round_number not in round_numbers:
            self.current_round_number = round_numbers[0]
        self.render_round(self.current_round_number)

    def on_round_order_changed(self):
        """Redraws the current round when the Team B order option is changed."""
        # Nothing to redraw until a round is on screen
        if self.current_round_number is not None:
            self.render_round(self.current_round_number)

    def _row_order_for_team(self, team):
        """GS..GK for Team A always, and for Team B too under "Positional"
        mode. Under "Match-Up" mode Team B is reversed (GK..GS), so each
        row lines up with the position that actually marks it on court."""
        # Only Team B in Match-Up mode is reversed
        if team == "B" and self.round_order_mode.get() == "matchup":
            return list(reversed(POSITIONS))
        return POSITIONS

    def render_round(self, round_number):
        """Draws one round: a heading, then each court stacked vertically,
        with that court's two teams side by side as separate tables."""
        round_numbers = sorted(self._rounds_by_number.keys())
        self.current_round_number = round_number
        self.round_nav_label.configure(text=f"Round {round_number} of {round_numbers[-1]}")

        # Clear the last round's tables and the old Jump to buttons
        for widget in self.rounds_content.winfo_children():
            widget.destroy()
        for widget in self.court_jump_frame.winfo_children():
            widget.destroy()
        self._court_anchors = {}

        # courts is {court_number: {team: round row}} for this round
        courts = self._rounds_by_number[round_number]
        court_numbers = sorted(courts.keys())

        # One section per court, top to bottom, starting with its heading
        for court_number in court_numbers:
            heading = ttk.Label(
                self.rounds_content, text=f"Court {court_number}", style="SubHeader.TLabel"
            )
            heading.pack(anchor="w", pady=(10 if court_number > court_numbers[0] else 0, 4))
            self._court_anchors[court_number] = heading

            teams_row = ttk.Frame(self.rounds_content)
            teams_row.pack(fill="x")

            # The court's two teams side by side; a team with no saved row is skipped
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
                # One table row per player, in the order worked out above
                for a in assignments:
                    tree.insert(
                        "", "end",
                        values=(a["position"], f"{a['first_name']} {a['last_name']}", a["trial_number"]),
                    )
                tree.configure(height=max(len(assignments), 1))
                tree.pack()
                stripe_treeview(tree)

        # Jump to buttons are only needed when there is more than one court
        if len(court_numbers) > 1:
            ttk.Label(self.court_jump_frame, text="Jump to:", style="Status.TLabel").pack(side="left")
            # One button per court; c=court_number fixes the court each button scrolls to
            for court_number in court_numbers:
                ttk.Button(
                    self.court_jump_frame, text=f"Court {court_number}",
                    command=lambda c=court_number: self.scroll_to_court(c),
                ).pack(side="left", padx=(4, 0))

    def scroll_to_court(self, court_number):
        """Scrolls the rounds view so the given court's heading is at the top."""
        widget = self._court_anchors.get(court_number)
        # No heading stored for that court, so there is nothing to scroll to
        if not widget:
            return
        canvas = self.rounds_scroll.canvas
        canvas.update_idletasks()
        total_height = self.rounds_content.winfo_height()
        # Avoid dividing by zero before the content has been drawn
        if total_height <= 0:
            return
        # How far down the content the court heading is: 0.0 is the top, 1.0 the bottom
        fraction = widget.winfo_y() / total_height
        canvas.yview_moveto(max(0.0, min(fraction, 1.0)))

    def prev_round(self):
        """Shows the previous round, if there is one."""
        round_numbers = sorted(self._rounds_by_number.keys())
        # No draw, or no round on screen: nothing to move to
        if not round_numbers or self.current_round_number is None:
            return
        index = round_numbers.index(self.current_round_number)
        # Only move back if this is not the first round
        if index > 0:
            self.render_round(round_numbers[index - 1])

    def next_round(self):
        """Shows the next round, if there is one."""
        round_numbers = sorted(self._rounds_by_number.keys())
        # No draw, or no round on screen: nothing to move to
        if not round_numbers or self.current_round_number is None:
            return
        index = round_numbers.index(self.current_round_number)
        # Only move forward if this is not the last round
        if index < len(round_numbers) - 1:
            self.render_round(round_numbers[index + 1])

    # ----------------------------------------------------------------- #
    # Export tab
    # ----------------------------------------------------------------- #

    def build_export_tab(self):
        """Builds the Export Players, game sheet, reference sheet and Back Up Data Now buttons."""
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
            text="Once the rounds are generated: a printable PDF with one selection sheet per court per round, "
                 "and a CSV showing where each player is in every round.",
        ).pack(anchor="w", padx=10)
        ttk.Button(
            self.export_tab, text="Export Game Sheets (PDF)", style="Primary.TButton",
            command=self.export_game_sheets
        ).pack(anchor="w", padx=10, pady=(5, 0))
        ttk.Button(
            self.export_tab, text="Export Player Reference Sheet", style="Primary.TButton",
            command=self.export_reference_sheet
        ).pack(anchor="w", padx=10, pady=(5, 0))

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
        """Asks where to save, then writes the selected trial's players to a CSV file."""
        # Existence checks: a trial must be selected and it must have players
        if not self.selected_trial_id:
            messagebox.showerror("Error", "Select a trial first (on the Trials tab).")
            return

        players = store.get_players_for_trial(self.selected_trial_id)
        if not players:
            messagebox.showerror("Error", "This trial has no registered players yet.")
            return

        trial = store.get_trial(self.selected_trial_id)
        # Suggested file name, with spaces swapped for underscores
        default_name = f"{trial['trial_name'].replace(' ', '_')}_players.csv"

        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV files", "*.csv")],
        )
        # The user pressed Cancel in the save dialog
        if not filepath:
            return

        # A file open in Excel is locked, so show a message instead of crashing
        try:
            store.export_players_csv(players, filepath)
        except OSError:
            messagebox.showerror("Export Failed", "Could not save the file. If it is open in Excel, close it and try again.")
            return
        messagebox.showinfo("Export Complete", f"Player list exported to:\n{filepath}")

    def export_draw_file(self, default_name, extension, file_label, writer, done_message):
        """Shared by the two draw exports: checks a draw exists, asks where to save,
        calls writer(trial_id, filepath) and reports success or the problem."""
        # Existence checks: a trial must be selected and it must have a draw
        if not self.selected_trial_id:
            messagebox.showerror("Error", "Select a trial first (on the Trials tab).")
            return
        if not store.get_rounds_for_trial(self.selected_trial_id):
            messagebox.showerror("Error", "Generate the rounds first (on the Rounds tab).")
            return

        trial = store.get_trial(self.selected_trial_id)
        filepath = filedialog.asksaveasfilename(
            defaultextension=extension,
            initialfile=f"{trial['trial_name'].replace(' ', '_')}_{default_name}{extension}",
            filetypes=[(file_label, "*" + extension)],
        )
        # The user pressed Cancel in the save dialog
        if not filepath:
            return

        # A locked file or a missing PDF library shows a message instead of crashing
        try:
            writer(self.selected_trial_id, filepath)
        except OSError:
            messagebox.showerror("Export Failed", "Could not save the file. If it is open in another program, close it and try again.")
            return
        except ImportError:
            messagebox.showerror("Export Failed", "The PDF library (reportlab) is not installed. Run: pip install reportlab")
            return
        messagebox.showinfo("Export Complete", f"{done_message}\n{filepath}")

    def export_game_sheets(self):
        """Saves every round's selection sheets as one printable PDF."""
        self.export_draw_file("game_sheets", ".pdf", "PDF files",
                              store.export_game_sheets_pdf, "Game sheets saved to:")

    def export_reference_sheet(self):
        """Saves the player-by-round reference table as a CSV file."""
        self.export_draw_file("reference_sheet", ".csv", "CSV files",
                              store.export_reference_sheet_csv, "Player reference sheet saved to:")

    def backup_data_now(self):
        """Makes a dated copy of the data folder and tells the user where it went."""
        backup_path = store.backup_data()
        # backup_data() returns None when there is no data folder to copy
        if backup_path:
            messagebox.showinfo("Backup Complete", f"Data backed up to:\n{backup_path}")
        else:
            messagebox.showerror("Backup Failed", "No data was found to back up.")


if __name__ == "__main__":
    app = App()
    app.mainloop()
