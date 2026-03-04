"""Lightweight integration tests for snapshot/strategy workflows."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MSFI_APP_DIR = PROJECT_ROOT / "msfi_app"
if str(MSFI_APP_DIR) not in sys.path:
    sys.path.insert(0, str(MSFI_APP_DIR))

from app import create_app
from database import close_db


class SnapshotWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test_msfi.db"
        self.app = create_app({"TESTING": True, "DATABASE": str(self.db_path)})
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            close_db()
        self.tmpdir.cleanup()

    def _db(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_portfolio(self, name: str) -> int:
        self.client.post(
            "/portfolios",
            data={"name": name, "buffer_1_percent": "10", "buffer_2_percent": "20"},
            follow_redirects=True,
        )
        with closing(self._db()) as conn:
            row = conn.execute("SELECT id FROM portfolios WHERE name = ?", (name,)).fetchone()
            return int(row["id"])

    def _create_strategy(self, portfolio_id: int, name: str, default_return_percent: str) -> int:
        self.client.post(
            f"/portfolios/{portfolio_id}/strategies",
            data={"name": name, "default_return_5yr_percent": default_return_percent, "active_flag": "1"},
            follow_redirects=True,
        )
        with closing(self._db()) as conn:
            row = conn.execute(
                "SELECT id FROM strategies WHERE portfolio_id = ? AND name = ?",
                (portfolio_id, name),
            ).fetchone()
            return int(row["id"])

    def _add_snapshot(
        self,
        portfolio_id: int,
        snapshot_date: str,
        total_value: str,
        actual_income: str,
        strategy_values: dict[int, str],
        strategy_returns: dict[int, str],
    ) -> int:
        payload = {
            "portfolio_id": str(portfolio_id),
            "snapshot_date": snapshot_date,
            "total_value": total_value,
            "actual_income": actual_income,
            "notes": "",
        }
        for strategy_id, value in strategy_values.items():
            payload[f"strategy_value_{strategy_id}"] = value
            payload[f"return_percent_{strategy_id}"] = strategy_returns[strategy_id]

        resp = self.client.post("/add", data=payload, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with closing(self._db()) as conn:
            row = conn.execute(
                """
                SELECT id
                FROM snapshots
                WHERE portfolio_id = ?
                ORDER BY snapshot_date DESC, id DESC
                LIMIT 1
                """,
                (portfolio_id,),
            ).fetchone()
            return int(row["id"])

    def test_dashboard_updates_actual_income_for_latest_snapshot(self):
        portfolio_id = self._create_portfolio("Dashboard Update")
        strategy_id = self._create_strategy(portfolio_id, "Income Strategy", "10.0")
        snapshot_id = self._add_snapshot(
            portfolio_id=portfolio_id,
            snapshot_date="2026-03-01",
            total_value="260000",
            actual_income="800",
            strategy_values={strategy_id: "260000"},
            strategy_returns={strategy_id: "10.0"},
        )

        resp = self.client.post(
            f"/snapshots/{snapshot_id}/actual-income",
            data={"actual_income": "950"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Actual fortnightly income updated for latest snapshot.", resp.get_data(as_text=True))

        with closing(self._db()) as conn:
            updated = conn.execute("SELECT actual_income, risk_status FROM snapshots WHERE id = ?", (snapshot_id,)).fetchone()
            self.assertEqual(float(updated["actual_income"]), 950.0)
            self.assertEqual(updated["risk_status"], "Alert")

    def test_dashboard_rejects_actual_income_update_for_non_latest_snapshot(self):
        portfolio_id = self._create_portfolio("Dashboard Update Guardrail")
        strategy_id = self._create_strategy(portfolio_id, "Income Strategy", "10.0")
        first_snapshot_id = self._add_snapshot(
            portfolio_id=portfolio_id,
            snapshot_date="2026-03-01",
            total_value="260000",
            actual_income="800",
            strategy_values={strategy_id: "260000"},
            strategy_returns={strategy_id: "10.0"},
        )
        self._add_snapshot(
            portfolio_id=portfolio_id,
            snapshot_date="2026-03-02",
            total_value="260000",
            actual_income="850",
            strategy_values={strategy_id: "260000"},
            strategy_returns={strategy_id: "10.0"},
        )

        resp = self.client.post(
            f"/snapshots/{first_snapshot_id}/actual-income",
            data={"actual_income": "1200"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Only the latest snapshot can be updated from the dashboard.", resp.get_data(as_text=True))

        with closing(self._db()) as conn:
            first = conn.execute("SELECT actual_income, risk_status FROM snapshots WHERE id = ?", (first_snapshot_id,)).fetchone()
            self.assertEqual(float(first["actual_income"]), 800.0)
            self.assertEqual(first["risk_status"], "Safe")

    def test_snapshot_strategy_lifecycle_and_delete_policies(self):
        portfolio_id = self._create_portfolio("Integration Portfolio")

        # Create required strategies for this portfolio, plus one extra unused strategy.
        for name, ret in [
            ("Growth", "8.0"),
            ("Balanced", "6.0"),
            ("Conservative", "4.0"),
            ("Cash", "2.0"),
            ("Unused Strategy", "4.5"),
        ]:
            self.client.post(
                f"/portfolios/{portfolio_id}/strategies",
                data={"name": name, "default_return_5yr_percent": ret, "active_flag": "1"},
                follow_redirects=True,
            )

        with closing(self._db()) as conn:
            strategies = conn.execute(
                "SELECT id, name FROM strategies WHERE portfolio_id = ? ORDER BY id ASC",
                (portfolio_id,),
            ).fetchall()
        strategy_map = {row["name"]: int(row["id"]) for row in strategies}

        # Add snapshot with mixed strategy values/returns.
        add_payload = {
            "portfolio_id": str(portfolio_id),
            "snapshot_date": "2026-03-04",
            "total_value": "1000000",
            "actual_income": "2000",
            "notes": "integration snapshot",
        }
        add_payload[f"strategy_value_{strategy_map['Growth']}"] = "400000"
        add_payload[f"return_percent_{strategy_map['Growth']}"] = "8.5"
        add_payload[f"strategy_value_{strategy_map['Balanced']}"] = "300000"
        add_payload[f"return_percent_{strategy_map['Balanced']}"] = "6.0"
        add_payload[f"strategy_value_{strategy_map['Conservative']}"] = "200000"
        add_payload[f"return_percent_{strategy_map['Conservative']}"] = "4.0"
        add_payload[f"strategy_value_{strategy_map['Cash']}"] = "100000"
        add_payload[f"return_percent_{strategy_map['Cash']}"] = "2.0"
        add_payload[f"strategy_value_{strategy_map['Unused Strategy']}"] = "0"
        add_payload[f"return_percent_{strategy_map['Unused Strategy']}"] = "4.5"

        resp = self.client.post("/add", data=add_payload, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with closing(self._db()) as conn:
            snapshot = conn.execute(
                "SELECT * FROM snapshots WHERE portfolio_id = ? ORDER BY id DESC LIMIT 1",
                (portfolio_id,),
            ).fetchone()
            self.assertIsNotNone(snapshot)
            snapshot_id = int(snapshot["id"])
            strategy_rows = conn.execute(
                "SELECT COUNT(*) AS cnt FROM snapshot_strategy_values WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
            self.assertEqual(int(strategy_rows["cnt"]), len(strategy_map))

        # Edit snapshot only.
        edit_payload = {
            "snapshot_date": "2026-03-04",
            "total_value": "1000000",
            "actual_income": "2100",
            "buffer_1_percent": "12",
            "buffer_2_percent": "20",
            "notes": "integration snapshot updated",
        }
        for name, sid in strategy_map.items():
            if name == "Growth":
                edit_payload[f"strategy_value_{sid}"] = "450000"
                edit_payload[f"return_percent_{sid}"] = "9.0"
            elif name == "Balanced":
                edit_payload[f"strategy_value_{sid}"] = "250000"
                edit_payload[f"return_percent_{sid}"] = "6.0"
            elif name == "Conservative":
                edit_payload[f"strategy_value_{sid}"] = "200000"
                edit_payload[f"return_percent_{sid}"] = "4.0"
            elif name == "Cash":
                edit_payload[f"strategy_value_{sid}"] = "100000"
                edit_payload[f"return_percent_{sid}"] = "2.0"
            else:
                edit_payload[f"strategy_value_{sid}"] = "0"
                edit_payload[f"return_percent_{sid}"] = "4.5"

        resp = self.client.post(f"/edit/{snapshot_id}", data=edit_payload, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with closing(self._db()) as conn:
            updated = conn.execute("SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)).fetchone()
            self.assertEqual(updated["notes"], "integration snapshot updated")
            self.assertAlmostEqual(float(updated["buffer_1_percent"]), 0.12, places=6)

        # Strategy in use cannot be deleted.
        growth_id = strategy_map["Growth"]
        resp = self.client.post(f"/strategies/{growth_id}/delete", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with closing(self._db()) as conn:
            growth_exists = conn.execute("SELECT id FROM strategies WHERE id = ?", (growth_id,)).fetchone()
            self.assertIsNotNone(growth_exists)

        # Unused strategy can be deleted.
        unused_id = strategy_map["Unused Strategy"]
        with closing(self._db()) as conn:
            conn.execute("DELETE FROM snapshot_strategy_values WHERE strategy_id = ?", (unused_id,))
            conn.commit()
        resp = self.client.post(f"/strategies/{unused_id}/delete", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with closing(self._db()) as conn:
            unused_exists = conn.execute("SELECT id FROM strategies WHERE id = ?", (unused_id,)).fetchone()
            self.assertIsNone(unused_exists)

        # Portfolio with snapshots cannot be deleted.
        resp = self.client.post(f"/portfolios/{portfolio_id}/delete", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with closing(self._db()) as conn:
            portfolio_exists = conn.execute("SELECT id FROM portfolios WHERE id = ?", (portfolio_id,)).fetchone()
            self.assertIsNotNone(portfolio_exists)


if __name__ == "__main__":
    unittest.main()
