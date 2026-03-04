# Superannuation_Income_Monitor

Python + SQLite + Simple Local Web App (Flask) to monitor the Maximum Sustainable Fortnightly Income from superannuation investment

---

## Project Metadata
- **Version:** 0.1.0
- **Created:** 2026-03-04
- **Author:** Wayne Freestun

---

## Overview
This project was created using the New Project Wizard and follows the standard ecosystem structure.

---

## Portfolio + Strategy Model

The app supports multiple portfolios, each with its own strategy set and snapshot history.

- Strategies are portfolio-specific and include:
  - `name`
  - `default_return_5yr`
  - `active_flag`
- New snapshot forms show active strategies only.
- Snapshot records store strategy values and `return_used` per strategy for that month.
- Weighted return is derived from snapshot strategy rows, not entered manually.

### Historical Integrity Rules

- Editing portfolio buffer defaults affects only future snapshots.
- Editing a historical snapshot recalculates only that snapshot.
- Historical strategy values and return rates remain stable unless that snapshot is explicitly edited.

### Deletion Policies

- Strategy delete is blocked if referenced in any snapshot.
- Referenced strategies can be marked inactive instead.
- Portfolio hard delete is allowed only when it has no snapshots.

### Migration Behavior

On startup, schema migration is applied safely and idempotently:

- Adds `strategies` and `snapshot_strategy_values` tables.
- Preserves existing snapshots.
- Seeds default strategies per portfolio:
  - Growth (7%)
  - Balanced (5%)
  - Conservative (3%)
  - Cash (2%)
- Backfills strategy rows for old snapshots using an equal-value split fallback.

## Run The MSFI Flask App

Use Python `3.14.3`.

### One-click startup (recommended)

From the project root, run:

```powershell
.\Run_MSFI_Monitor.cmd
```

This script will:
- Create `msfi_app\venv` if it does not exist
- Install/update dependencies from `msfi_app\requirements.txt`
- Start Flask on `http://127.0.0.1:5000`
- Open that address in your default browser automatically

Press `Ctrl+C` in the script window to stop the app.

### Manual startup (fallback)

The app lives in `msfi_app/`.

```bash
cd msfi_app
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
set FLASK_APP=app.py
flask run
```

Then open the local URL shown in the terminal (typically `http://127.0.0.1:5000`).

---

## Run Unit Tests

From the project root:

```bash
python -m unittest tests.test_calculations -v
python -m unittest tests.test_snapshot_logic -v
```

