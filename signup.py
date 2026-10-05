"""
Standalone self-service registration form for players/parents - no
coordinator login required. Run with:

    python signup.py

Shares the same data as main.py, so anyone who registers here shows up
immediately on the coordinator's Players tab and Roll Call.
"""

import tkinter as tk
from tkinter import ttk, messagebox

import players as store

# The seven netball positions, in court order GS to GK. A list, because it fills the drop-downs
# in that order. Same values as POSITIONS in main.py and players.py.
POSITIONS = ["GS", "GA", "WA", "C", "WD", "GD", "GK"]
# Longest playing history allowed (matches the data dictionary). A whole number named once, so
# the limit, the counter label and the cut-off in on_playing_history_typed() all agree.
PLAYING_HISTORY_MAX_CHARS = 150

# Same colours as the main app
NAVY = "#1f3864"
WHITE = "#ffffff"
LIGHT_GREY = "#f2f2f2"
DARK_GREY = "#555555"
GREEN = "#2e7d32"
RED = "#c62828"
FONT_FAMILY = "Arial"


def setup_styles(root):
    """Sets the same colours and fonts as the main app for every kind of widget used here."""
    style = ttk.Style(root)
    # Use the clam theme if it is available; otherwise keep the default theme
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root.configure(bg=WHITE)
    style.configure("TFrame", background=WHITE)
    style.configure("TLabel", background=WHITE, font=(FONT_FAMILY, 10))
    style.configure("Header.TLabel", background=NAVY, foreground=WHITE,
                    font=(FONT_FAMILY, 16, "bold"))
    style.configure("SubHeader.TLabel", background=WHITE, foreground=NAVY,
                    font=(FONT_FAMILY, 11, "bold"))
    style.configure("Status.TLabel", background=WHITE, foreground=DARK_GREY,
                    font=(FONT_FAMILY, 9))
    style.configure("Required.TLabel", background=WHITE, foreground=RED,
                    font=(FONT_FAMILY, 9))
    style.configure("Valid.TLabel", background=WHITE, foreground=GREEN, font=(FONT_FAMILY, 9))
    style.configure("Invalid.TLabel", background=WHITE, foreground=RED, font=(FONT_FAMILY, 9))
    style.configure("TButton", font=(FONT_FAMILY, 10), padding=6)
    style.configure("Primary.TButton", font=(FONT_FAMILY, 10, "bold"))
    style.map("Primary.TButton", background=[("!disabled", NAVY)], foreground=[("!disabled", WHITE)])
    style.configure("TEntry", padding=4)
    style.configure("TCombobox", padding=4)
    return style


class SignupApp(tk.Tk):
    """One form: pick the trial you're registering for, fill in your
    details, submit. Loops back to a blank form so the same kiosk can be
    used for the next player straight away."""

    def __init__(self):
        """Builds the window and header, loads the trials and shows the form (or a message if none exist)."""
        super().__init__()
        self.title("Netball Trial Registration")
        self.geometry("520x680")
        setup_styles(self)

        store.init_data()

        header = tk.Frame(self, bg=NAVY)
        ttk.Label(header, text="Player Registration", style="Header.TLabel").pack(
            side="left", padx=16, pady=12
        )
        header.pack(fill="x")

        # Trials shown in the dropdown; if there are none only a message is shown. A list in date order:
        # combo.current() gives a position number, which is used as an index to find the chosen trial.
        self.trials = store.get_all_trials()
        if not self.trials:
            ttk.Label(
                self, text="No trials are open for registration yet - check back later, "
                           "or ask the coordinator to create one.",
                style="Invalid.TLabel", wraplength=460,
            ).pack(padx=20, pady=30)
            return

        self.build_form()

    # ------------------------------------------------------------------ #
    # Form
    # ------------------------------------------------------------------ #

    def build_form(self):
        """Lays out every label and input box of the registration form, then the Save button."""
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, padx=20, pady=16)

        ttk.Label(
            outer, text="* = required field", style="Required.TLabel"
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        # Row counter: each field method returns the next free row
        row = 1
        row = self._labelled(outer, row, "Trial *", self._build_trial_picker)
        row = self._labelled(outer, row, "First Name *", lambda p: self._entry(p, "first_name_entry"))
        row = self._labelled(outer, row, "Last Name *", lambda p: self._entry(p, "last_name_entry"))
        row = self._labelled(outer, row, "DOB * (DD/MM/YYYY)", self._build_dob_field)
        row = self._labelled(outer, row, "Netball ID", lambda p: self._entry(p, "netball_id_entry"))
        row = self._labelled(outer, row, "Address", lambda p: self._entry(p, "address_entry"))
        row = self._labelled(outer, row, "Phone", lambda p: self._entry(p, "phone_entry"))
        row = self._labelled(outer, row, "Email", lambda p: self._entry(p, "email_entry"))
        row = self._labelled(outer, row, "Parent/Guardian Name", lambda p: self._entry(p, "parent_name_entry"))
        row = self._labelled(outer, row, "Parent/Guardian Phone", lambda p: self._entry(p, "parent_phone_entry"))
        row = self._labelled(outer, row, "Parent/Guardian Email", lambda p: self._entry(p, "parent_email_entry"))
        row = self._labelled(outer, row, "Position 1 *", self._build_pos1_combo)
        row = self._labelled(outer, row, "Position 2 *", self._build_pos2_combo)
        row = self._labelled(outer, row, "Position 3 (optional)", self._build_pos3_combo)
        row = self._labelled(outer, row, "Playing History", self._build_playing_history)

        ttk.Button(
            outer, text="Save Player", style="Primary.TButton", command=self.submit
        ).grid(row=row, column=0, columnspan=2, pady=16)
        self.result_label = ttk.Label(outer, text="", style="Valid.TLabel", wraplength=460)
        self.result_label.grid(row=row + 1, column=0, columnspan=2, sticky="w")

        outer.columnconfigure(1, weight=1)

    @staticmethod
    def _labelled(parent, row, text, builder):
        """Places a label and its field on the given row, returns the next
        free row number."""
        ttk.Label(parent, text=text).grid(row=row, column=0, sticky="ne", padx=(0, 8), pady=4)
        builder(parent).grid(row=row, column=1, sticky="ew", pady=4)
        return row + 1

    def _entry(self, parent, attr_name, width=32):
        """Makes a text box and stores it on self under attr_name so submit() can read it later."""
        # Entry for free-text answers (names, address, phone, email). Everything typed is a str, so
        # submit() strips each value and checks it before saving.
        entry = ttk.Entry(parent, width=width)
        setattr(self, attr_name, entry)
        return entry

    def _build_trial_picker(self, parent):
        """Makes the dropdown of trials, starting on the first one."""
        self.trial_var = tk.StringVar()
        # Read-only Combobox, so a player can only register for a trial that exists, not type one.
        combo = ttk.Combobox(parent, textvariable=self.trial_var, state="readonly", width=30)
        combo["values"] = [f"{t['trial_name']} ({t['age_group']})" for t in self.trials]
        combo.current(0)
        combo.bind("<<ComboboxSelected>>", self.on_dob_typed)
        self.trial_combo = combo
        return combo

    def _build_dob_field(self, parent):
        """Makes the date of birth box with a label beside it for live feedback."""
        wrapper = ttk.Frame(parent)
        self.dob_entry = ttk.Entry(wrapper, width=16)
        self.dob_entry.pack(side="left")
        self.dob_entry.bind("<KeyRelease>", self.on_dob_typed)
        self.dob_validation_label = ttk.Label(wrapper, text="", style="Valid.TLabel")
        self.dob_validation_label.pack(side="left", padx=(8, 0))
        return wrapper

    def _build_pos1_combo(self, parent):
        """Makes the read-only dropdown for Position 1."""
        # Read-only Combobox of POSITIONS: only the seven real positions can be chosen.
        self.pos1_combo = ttk.Combobox(parent, values=POSITIONS, state="readonly", width=8)
        return self.pos1_combo

    def _build_pos2_combo(self, parent):
        """Makes the read-only dropdown for Position 2."""
        self.pos2_combo = ttk.Combobox(parent, values=POSITIONS, state="readonly", width=8)
        return self.pos2_combo

    def _build_pos3_combo(self, parent):
        """Makes the read-only dropdown for Position 3 (can be left blank)."""
        # The same list with a blank choice added, so the optional Position 3 can be left empty.
        self.pos3_combo = ttk.Combobox(parent, values=[""] + POSITIONS, state="readonly", width=8)
        return self.pos3_combo

    def _build_playing_history(self, parent):
        """Makes the multi-line playing history box with its live character counter."""
        wrapper = ttk.Frame(parent)
        # Text box (several lines), not an Entry, because playing history is a sentence or two. It is
        # capped at PLAYING_HISTORY_MAX_CHARS so the saved CSV cell stays short.
        self.playing_history_text = tk.Text(wrapper, width=32, height=4, wrap="word", font=(FONT_FAMILY, 10))
        self.playing_history_text.pack(anchor="w")
        self.playing_history_counter = ttk.Label(
            wrapper, text=f"0/{PLAYING_HISTORY_MAX_CHARS}", style="Status.TLabel"
        )
        self.playing_history_counter.pack(anchor="w")
        self.playing_history_text.bind("<KeyRelease>", self.on_playing_history_typed)
        return wrapper

    # ------------------------------------------------------------------ #
    # Live feedback
    # ------------------------------------------------------------------ #

    def selected_trial(self):
        """Returns the trial picked in the dropdown as a dict, or None."""
        index = self.trial_combo.current()
        # current() is -1 when nothing is picked
        if index < 0:
            return None
        return self.trials[index]

    def on_dob_typed(self, event=None):
        """Live eligibility feedback - informational only, never blocks
        registration, since a permit can override it."""
        dob = self.dob_entry.get().strip()
        trial = self.selected_trial()
        # Nothing typed or no trial: clear the message and stop
        if not dob or not trial:
            self.dob_validation_label.configure(text="")
            return
        # Only say 'Invalid date format' once 10 characters are typed, not on every keystroke
        if not store.is_valid_date(dob):
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

    def on_playing_history_typed(self, event=None):
        """Caps playing history at PLAYING_HISTORY_MAX_CHARS and keeps the
        counter beside it live."""
        # Tk text boxes start at line 1 char 0; end-1c leaves off the automatic final newline
        text = self.playing_history_text.get("1.0", "end-1c")
        # Over the limit: cut the text back and put the shortened text in the box
        if len(text) > PLAYING_HISTORY_MAX_CHARS:
            text = text[:PLAYING_HISTORY_MAX_CHARS]
            self.playing_history_text.delete("1.0", "end")
            self.playing_history_text.insert("1.0", text)
        self.playing_history_counter.configure(text=f"{len(text)}/{PLAYING_HISTORY_MAX_CHARS}")

    # ------------------------------------------------------------------ #
    # Submit
    # ------------------------------------------------------------------ #

    def submit(self):
        """Checks the form, saves the player, shows the trial number and clears the form for the next player."""
        trial = self.selected_trial()
        # Existence check: a trial must be picked
        if not trial:
            messagebox.showerror("Error", "Select a trial to register for.")
            return

        # Read the form; pos1 to pos3 are the position dropdowns (pos3 is optional)
        first_name = self.first_name_entry.get().strip()
        last_name = self.last_name_entry.get().strip()
        dob = self.dob_entry.get().strip()
        pos1 = self.pos1_combo.get()
        pos2 = self.pos2_combo.get()
        pos3 = self.pos3_combo.get()
        # The optional contact details; they are only checked if something was typed in the box
        phone = self.phone_entry.get().strip()
        parent_phone = self.parent_phone_entry.get().strip()
        email = self.email_entry.get().strip()
        parent_email = self.parent_email_entry.get().strip()

        # Existence check: the five required details
        if not first_name or not last_name or not dob or not pos1 or not pos2:
            messagebox.showerror(
                "Error", "First name, last name, DOB, Position 1 and Position 2 are required."
            )
            return
        # Type check: the date of birth must be a real DD/MM/YYYY date
        if not store.is_valid_date(dob):
            messagebox.showerror("Error", "DOB must be in DD/MM/YYYY format.")
            return
        # Range check: a date of birth can't be after today
        if store.is_future_date(dob):
            messagebox.showerror("Error", "Date of birth can't be in the future.")
            return
        # The two required positions must be different
        if pos1 == pos2:
            messagebox.showerror("Error", "Position 1 and Position 2 must be different.")
            return
        # Names can't contain a digit (checks every character of both names)
        if any(ch.isdigit() for ch in first_name + last_name):
            messagebox.showerror("Error", "Names can't contain numbers.")
            return
        # Each phone number is checked only if one was typed; label names the box in the error message
        for label, value in (("Phone", phone), ("Parent/Guardian Phone", parent_phone)):
            if value and not store.is_valid_phone(value):
                messagebox.showerror("Error", f"{label} must be an Australian number, e.g. 0412 345 678.")
                return
        # Each email address is checked only if one was typed
        for label, value in (("Email", email), ("Parent/Guardian Email", parent_email)):
            if value and not store.is_valid_email(value):
                messagebox.showerror("Error", f"{label} must look like name@example.com.")
                return

        trial_number = store.create_player(
            trial["trial_id"], first_name, last_name, dob, pos1, pos2,
            netball_id=self.netball_id_entry.get().strip(),
            address=self.address_entry.get().strip(),
            phone=phone,
            email=email,
            parent_name=self.parent_name_entry.get().strip(),
            parent_phone=parent_phone,
            parent_email=parent_email,
            playing_history=self.playing_history_text.get("1.0", "end-1c").strip(),
            position_3=pos3,
        )

        self.result_label.configure(
            text=f"Registered! {first_name} {last_name} is trial number #{trial_number} "
                 f"for {trial['trial_name']}.",
            style="Valid.TLabel",
        )
        self.clear_form()

    def clear_form(self):
        """Empties every box and dropdown, ready for the next person."""
        # Empty each text box by its attribute name
        for attr in (
            "first_name_entry", "last_name_entry", "dob_entry", "netball_id_entry",
            "address_entry", "phone_entry", "email_entry", "parent_name_entry",
            "parent_phone_entry", "parent_email_entry",
        ):
            getattr(self, attr).delete(0, "end")
        self.pos1_combo.set("")
        self.pos2_combo.set("")
        self.pos3_combo.set("")
        self.playing_history_text.delete("1.0", "end")
        self.playing_history_counter.configure(text=f"0/{PLAYING_HISTORY_MAX_CHARS}")
        self.dob_validation_label.configure(text="")


if __name__ == "__main__":
    app = SignupApp()
    app.mainloop()
