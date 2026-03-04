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

## Multi-Portfolio Upgrade

The app now supports multiple portfolios, each with independent buffer settings and snapshot history.

- Create portfolios from the `Portfolios` page.
- Select a portfolio from the navbar dropdown to focus the dashboard and actions.
- Add snapshots per portfolio using that portfolio's active buffer percentages.
- Edit a portfolio's buffers to change **future** calculations only.

### How Buffer Modification Works

- Portfolio-level `Buffer 1` and `Buffer 2` percentages are defaults for future snapshots.
- When you add a snapshot, the current portfolio buffer percentages are copied into that snapshot.
- Snapshot records store:
  - `buffer_1_percent`
  - `buffer_2_percent`
  - `buffer_1_value`
  - `buffer_2_value`
- Risk status is calculated from the values stored on that snapshot.

### Historical Integrity

- Historical records remain stable after portfolio buffer changes.
- Editing a snapshot recalculates only that snapshot.
- Other snapshots (past/future) are not modified.

### Migration Logic

On startup, the app auto-migrates legacy single-portfolio data:

- Creates `portfolios` table.
- Creates new `snapshots` table with `portfolio_id` foreign key.
- Creates `Default Portfolio` if needed.
- Migrates legacy snapshot rows into the new schema while preserving financial values.

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

