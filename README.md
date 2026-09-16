# Netball Trial Management System

VCE Software Development Units 3 & 4 - School-Assessed Task.
Python 3.12, Tkinter. No database, no extra packages needed - just CSV files.

## Files

- `main.py` - the app (GUI, login, roles)
- `algorithm.py` - the position rotation algorithm
- `players.py` - data storage (CSV), CSV export/import, test data
- `signup.py` - standalone registration form for players/parents, no login needed

All four need to be in the same folder.

## Running it

```
python main.py
```

Default login on first run:

- Username: `coordinator`
- Password: `coordinator123`

## Where the data lives

Everything's stored as plain CSV files under a `data/` folder that gets
created next to the scripts (trials, players, attendance, rounds,
assignments, users) - one row per record, open them in Excel/Notepad if
you want to see what's actually stored.

A clean player list per trial also gets written automatically to
`exports/<trial name>_players.csv` every time a trial or player is added,
so there's always an up-to-date CSV sitting there without pressing
anything.

Backups get copied into `backups/` on startup, and on demand from the
Export tab.

## Letting players register themselves

```
python signup.py
```

Opens straight to a registration form, no login. Shares the same data as
main.py so anyone who signs up shows up immediately on the coordinator's
side.

## Loading test players

```
python -c "import players; players.init_data(); players.create_trial('U13 2026', 'U13', '11/09/2026', 2); tid = players.get_all_trials()[0]['trial_id']; [players.create_player(tid, *p) for p in players.generate_test_players(100)]"
```

Or put CSV files in the same folder and run:

```
python players.py
```

Positions have to be one of GS/GA/WA/C/WD/GD/GK - if a row's got something
else in there (wrong sport's CSV, typo, whatever) it'll ask what the
position should actually be instead of just skipping the player.

## Checking the algorithm

```
python algorithm.py
```
