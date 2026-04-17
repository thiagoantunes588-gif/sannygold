import os
import tempfile
import unittest
from pathlib import Path

os.environ["ROTAFLOW_STORAGE_DIR"] = tempfile.mkdtemp(prefix="sannygold-ui-test-")

from app.main import app, ensure_storage_dirs  # noqa: E402


class OperationalUiImprovementsTest(unittest.TestCase):
    def setUp(self):
        ensure_storage_dirs()
        self.client = app.test_client()

    def test_operational_shortcuts_and_filters_are_rendered(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("quick-actions-bar", html)
        self.assertIn("driver-pane", html)
        self.assertIn("client-search", html)
        self.assertIn("event-filter", html)
        self.assertIn("equipment-filter", html)
        self.assertIn("data-confirm-message", html)
        self.assertIn("backup-status", html)
        self.assertIn("formatCurrencyBRL", html)
        self.assertIn("customer-history", html)
        self.assertIn("daily-closeout", html)
        self.assertIn("preventive-warning", html)
        self.assertIn("calendar-grid", html)
        self.assertIn("real-map-panel", html)

    def test_mobile_control_center_exposes_all_core_functions(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("mobile-control-center", html)
        self.assertIn("mobile-action-grid", html)
        for label in (
            "Resumo",
            "Eventos",
            "Clientes",
            "Frota",
            "Estoque",
            "Agenda",
            "Histórico",
            "Motorista",
            "Validar/Gerar",
            "Mapa real",
            "PDF",
            "Fechar dia",
            "Backup",
        ):
            self.assertIn(label, html)

    def test_backup_download_records_timestamp(self):
        response = self.client.get("/backup/system.zip")
        self.assertEqual(response.status_code, 200)

        settings_path = Path(os.environ["ROTAFLOW_STORAGE_DIR"]) / "data" / "settings.json"
        self.assertIn("last_backup_at", settings_path.read_text(encoding="utf-8"))

    def test_daily_closeout_download_records_timestamp(self):
        response = self.client.get("/daily-closeout.zip")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/zip")

        settings_path = Path(os.environ["ROTAFLOW_STORAGE_DIR"]) / "data" / "settings.json"
        self.assertIn("last_closeout_at", settings_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
