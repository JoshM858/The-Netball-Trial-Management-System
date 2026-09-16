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

POSITIONS = ["GS", "GA", "WA", "C", "WD", "GD", "GK"]
PLAYING_HISTORY_MAX_CHARS = 150

NAVY = "#1f3864"
WHITE = "#ffffff"
LIGHT_GREY = "#f2f2f2"
DARK_GREY = "#555555"
GREEN = "#2e7d32"
RED = "#c62828"
FONT_FAMILY = "Arial"


def setup_styles(root):
    style = ttk.Style(root)
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
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, padx=20, pady=16)

        ttk.Label(
            outer, text="* = required field", style="Required.TLabel"
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

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
        entry = ttk.Entry(parent, width=width)
        setattr(self, attr_name, entry)
        return entry

    def _build_trial_picker(self, parent):
        self.trial_var = tk.StringVar()
        combo = ttk.Combobox(parent, textvariable=self.trial_var, state="readonly", width=30)
        combo["values"] = [f"{t['trial_name']} ({t['age_group']})" for t in self.trials]
        combo.current(0)
        combo.bind("<<ComboboxSelected>>", self.on_dob_typed)
        self.trial_combo = combo
        return combo

    def _build_dob_field(self, parent):
        wrapper = ttk.Frame(parent)
        self.dob_entry = ttk.Entry(wrapper, width=16)
        self.dob_entry.pack(side="left")
        self.dob_entry.bind("<KeyRelease>", self.on_dob_typed)
        self.dob_validation_label = ttk.Label(wrapper, text="", style="Valid.TLabel")
        self.dob_validation_label.pack(side="left", padx=(8, 0))
        return wrapper

    def _build_pos1_combo(self, parent):
        self.pos1_combo = ttk.Combobox(parent, values=POSITIONS, state="readonly", width=8)
        return self.pos1_combo

    def _build_pos2_combo(self, parent):
        self.pos2_combo = ttk.Combobox(parent, values=POSITIONS, state="readonly", width=8)
        return self.pos2_combo

    def _build_pos3_combo(self, parent):
        self.pos3_combo = ttk.Combobox(parent, values=[""] + POSITIONS, state="readonly", width=8)
        return self.pos3_combo

    def _build_playing_history(self, parent):
        wrapper = ttk.Frame(parent)
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
        index = self.trial_combo.current()
        if index < 0:
            return None
        return self.trials[index]

    def on_dob_typed(self, event=None):
        """Live eligibility feedback - informational only, never blocks
        registration, since a permit can override it."""
        dob = self.dob_entry.get().strip()
        trial = self.selected_trial()
        if not dob or not trial:
            self.dob_validation_label.configure(text="")
            return
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
        text = self.playing_history_text.get("1.0", "end-1c")
        if len(text) > PLAYING_HISTORY_MAX_CHARS:
            text = text[:PLAYING_HISTORY_MAX_CHARS]
            self.playing_history_text.delete("1.0", "end")
            self.playing_history_text.insert("1.0", text)
        self.playing_history_counter.configure(text=f"{len(text)}/{PLAYING_HISTORY_MAX_CHARS}")

    # ------------------------------------------------------------------ #
    # Submit
    # ------------------------------------------------------------------ #

    def submit(self):
        trial = self.selected_trial()
        if not trial:
            messagebox.showerror("Error", "Select a trial to register for.")
            return

        first_name = self.first_name_entry.get().strip()
        last_name = self.last_name_entry.get().strip()
        dob = self.dob_entry.get().strip()
        pos1 = self.pos1_combo.get()
        pos2 = self.pos2_combo.get()
        pos3 = self.pos3_combo.get()

        if not first_name or not last_name or not dob or not pos1 or not pos2:
            messagebox.showerror(
                "Error", "First name, last name, DOB, Position 1 and Position 2 are required."
            )
            return
        if not store.is_valid_date(dob):
            messagebox.showerror("Error", "DOB must be in DD/MM/YYYY format.")
            return
        if pos1 == pos2:
            messagebox.showerror("Error", "Position 1 and Position 2 must be different.")
            return

        trial_number = store.create_player(
            trial["trial_id"], first_name, last_name, dob, pos1, pos2,
            netball_id=self.netball_id_entry.get().strip(),
            address=self.address_entry.get().strip(),
            phone=self.phone_entry.get().strip(),
            email=self.email_entry.get().strip(),
            parent_name=self.parent_name_entry.get().strip(),
            parent_phone=self.parent_phone_entry.get().strip(),
            parent_email=self.parent_email_entry.get().strip(),
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
