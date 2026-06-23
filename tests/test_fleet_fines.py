from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.repositories.sqlite_repository import FLEET_FINES_MIGRATIONS, connect
from app.services.fleet_fines import (
    attachment_access_allowed, build_audit_log, build_dashboard, build_deadlines, build_decision, build_identification, build_infraction,
    build_proceeding, build_protocol, classify_deadline, complete_deadline, compute_nic_risk,
    confirm_identification, driver_can_view_infraction, file_sha256, financial_link_note, find_linked_financial_entry,
    import_mapping, missing_required_documents, next_internal_number, possible_duplicate, soft_delete, suggest_driver,
)
from app.services.fleet_fines_migration import apply_fleet_fines, rollback_fleet_fines, validate_fleet_fines


NOW = "2026-06-21T12:00:00"


def vehicle(**changes):
    return {"vehicle_id": "VEI-001", "plate": "ABC1D23", "renavam": "12345678901", "legal_owner_company": "SannyGold Ltda",
            "operating_company": "SannyGold", "usual_driver_id": "USR-DRIVER", "deleted_at": "", **changes}


def infraction_form(**changes):
    return {"vehicle_id": "VEI-001", "issuing_authority": "Órgão Municipal", "infraction_notice_number": "AUTO-100",
            "infraction_date": "2026-06-20", "infraction_time": "10:30", "notification_type": "autuacao",
            "jurisdiction_type": "municipal", "original_amount": "293,47", "points": "7",
            "driver_identification_required": "1", **changes}


class FleetFineDomainTest(unittest.TestCase):
    def build(self, records=None, **changes):
        return build_infraction(infraction_form(**changes), records=records or [], vehicles=[vehicle()], user_id="USR-ADMIN", now=NOW)

    def test_registration_links_existing_vehicle_and_numbers_record(self):
        record = self.build()
        self.assertEqual(record["vehicle_id"], "VEI-001")
        self.assertEqual(record["vehicle_plate_snapshot"], "ABC1D23")
        self.assertEqual(record["internal_number"], "MULTA-2026-000001")
        self.assertAlmostEqual(record["original_amount"], 293.47)

    def test_exact_duplicate_is_blocked(self):
        first = self.build()
        with self.assertRaisesRegex(ValueError, "Duplicidade bloqueada"):
            self.build([first])

    def test_possible_duplicate_requires_human_review(self):
        first = self.build()
        with self.assertRaisesRegex(ValueError, "Possível duplicidade"):
            self.build([first], infraction_date="2026-06-19")
        reviewed = self.build([first], infraction_date="2026-06-19", duplicate_review_confirmed="1", duplicate_review_notes="Notificação retificada com outra data")
        self.assertEqual(reviewed["duplicate_review_status"], "revisado")
        self.assertEqual(possible_duplicate(reviewed, [first])["id"], first["id"])

    def test_multiple_distinct_infractions_for_same_vehicle_are_allowed(self):
        first = self.build()
        second = self.build([first], infraction_notice_number="AUTO-101")
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(next_internal_number([first, second], "2026-01-01"), "MULTA-2026-000003")

    def test_driver_is_suggested_from_assignment_but_not_confirmed(self):
        record = self.build()
        suggestion = suggest_driver(record, assignments=[{"id": "ASG-1", "vehicle_id": "VEI-001", "driver_id": "USR-ROTA", "route_id": "ROT-1", "delivered_at": "2026-06-20T08:00:00", "returned_at": "2026-06-20T18:00:00", "deleted_at": ""}], checklists=[], vehicles=[vehicle()])
        identification = build_identification(record, suggestion, existing=[], now=NOW)
        self.assertEqual(suggestion["confidence"], "alta")
        self.assertEqual(identification["suggested_driver_id"], "USR-ROTA")
        self.assertEqual(identification["confirmed_driver_id"], "")

    def test_driver_confirmation_requires_another_human(self):
        identification = build_identification(self.build(), {"driver_id": "USR-DRIVER", "confidence": "alta", "score": 100, "evidence": ["rota"]}, existing=[], now=NOW)
        with self.assertRaises(PermissionError):
            confirm_identification(identification, driver_id="USR-DRIVER", user_id="USR-DRIVER", now=NOW)
        confirmed = confirm_identification(identification, driver_id="USR-DRIVER", user_id="USR-MANAGER", now=NOW, notes="Rota e checklist conferidos")
        self.assertEqual(confirmed["status"], "confirmado_internamente")
        self.assertEqual(confirmed["confirmed_by"], "USR-MANAGER")

    def test_unidentified_driver_is_explicit(self):
        suggestion = suggest_driver(self.build(), assignments=[], checklists=[], vehicles=[vehicle(usual_driver_id="")])
        identification = build_identification(self.build(), suggestion, existing=[], now=NOW)
        self.assertEqual(identification["status"], "nao_identificado")

    def test_deadline_alerts_and_overdue_classification(self):
        self.assertEqual(classify_deadline({"official_deadline": "2026-06-20"}, today=date(2026, 6, 21))["classification"], "vencido")
        self.assertEqual(classify_deadline({"official_deadline": "2026-06-21"}, today=date(2026, 6, 21))["classification"], "vence_hoje")
        self.assertEqual(classify_deadline({"official_deadline": "2026-06-24"}, today=date(2026, 6, 21))["classification"], "urgente")

    def test_deadlines_preserve_source_and_checker(self):
        record = self.build()
        deadlines = build_deadlines({"driver_identification_deadline": "2026-07-01", "driver_identification_deadline_internal": "2026-06-28", "driver_identification_deadline_source": "Página 2 da notificação"}, infraction_id=record["id"], existing=[], user_id="USR-ADMIN", now=NOW)
        self.assertEqual(deadlines[0]["source"], "Página 2 da notificação")
        self.assertEqual(deadlines[0]["checked_by"], "USR-ADMIN")

    def test_deadline_completion_requires_proof_or_justification(self):
        deadline = {"id": "FDL-1", "status": "aberto"}
        with self.assertRaises(ValueError):
            complete_deadline(deadline, user_id="USR-1", now=NOW)
        self.assertEqual(complete_deadline(deadline, user_id="USR-1", now=NOW, justification="Protocolo físico conferido")["status"], "concluido")

    def test_nic_risk_high_and_overdue(self):
        record = self.build()
        record["driver_identification_status"] = "nao_identificado"
        deadline = {"infraction_id": record["id"], "deadline_type": "driver_identification", "official_deadline": "2026-06-24", "status": "aberto"}
        self.assertEqual(compute_nic_risk(record, [deadline], today=date(2026, 6, 21)), "alto_risco")
        deadline["official_deadline"] = "2026-06-20"
        self.assertEqual(compute_nic_risk(record, [deadline], today=date(2026, 6, 21)), "prazo_vencido")

    def test_nic_must_link_original_infraction(self):
        with self.assertRaisesRegex(ValueError, "vinculada"):
            self.build(notification_type="nic")
        nic = self.build(notification_type="nic", infraction_notice_number="NIC-1", original_infraction_id="FINF-000001")
        self.assertEqual(nic["original_infraction_id"], "FINF-000001")

    def test_required_documents_report_missing_items(self):
        template = [{"document_type": "notificacao", "is_required": True}, {"document_type": "cnh_motorista", "is_required": True}]
        docs = [{"document_type": "notificacao", "status": "aprovado", "deleted_at": ""}]
        self.assertEqual(missing_required_documents(template, docs), ["cnh_motorista"])

    def test_protocol_requires_proof_or_authorized_reason(self):
        form = {"protocol_date": "2026-06-21", "protocol_channel": "PRF", "protocol_number": "P-1"}
        with self.assertRaisesRegex(ValueError, "comprovante"):
            build_protocol(form, infraction_id="FINF-1", records=[], user_id="USR-1", now=NOW)
        allowed = build_protocol({**form, "proof_override_authorized": "1", "proof_override_reason": "Portal indisponível; recibo será juntado"}, infraction_id="FINF-1", records=[], user_id="USR-1", now=NOW)
        self.assertTrue(allowed["proof_override_authorized"])

    def test_defense_and_appeal_proceedings(self):
        defense = build_proceeding({"proceeding_type": "preliminary_defense", "status": "em_preparacao"}, infraction_id="FINF-1", records=[], user_id="USR-1", now=NOW)
        appeal = build_proceeding({"proceeding_type": "jari", "status": "em_preparacao"}, infraction_id="FINF-1", records=[defense], user_id="USR-1", now=NOW)
        self.assertNotEqual(defense["id"], appeal["id"])

    def test_discount_waiver_decision_requires_acknowledgement(self):
        form = {"decision": "recognize_pay", "justification": "Documentos conferidos", "discount_requires_waiver": "1"}
        with self.assertRaisesRegex(ValueError, "renúncia"):
            build_decision(form, infraction_id="FINF-1", records=[], user_id="USR-1", now=NOW)
        decision = build_decision({**form, "waiver_warning_acknowledged": "1"}, infraction_id="FINF-1", records=[], user_id="USR-1", now=NOW)
        self.assertTrue(decision["waiver_warning_acknowledged"])

    def test_financial_link_is_idempotent(self):
        note = financial_link_note("FINF-1")
        entries = [{"id": "LAN-1", "notes": note}]
        self.assertEqual(find_linked_financial_entry(entries, "FINF-1")["id"], "LAN-1")
        self.assertIsNone(find_linked_financial_entry(entries, "FINF-2"))

    def test_dashboard_reports_deadlines_nic_and_values(self):
        record = self.build()
        record.update({"nic_risk_status": "alto_risco", "driver_identification_status": "nao_identificado", "payment_status": "pendente"})
        result = build_dashboard([record], [{"infraction_id": record["id"], "official_deadline": "2026-06-20", "status": "aberto"}], [])
        self.assertEqual(result["counts"]["nic_risk"], 1)
        self.assertEqual(result["counts"]["overdue"], 1)

    def test_spreadsheet_mapping_and_correction(self):
        mapped = import_mapping({"placa": "ABC1D23", "numero_do_auto": "A-1", "orgao": "PRF", "data": "2026-06-20", "valor": "100"})
        self.assertEqual(mapped["infraction_notice_number"], "A-1")
        record = build_infraction({**mapped, "vehicle_id": "VEI-001", "notification_type": "autuacao", "jurisdiction_type": "federal"}, records=[], vehicles=[vehicle()], user_id="USR-1", now=NOW)
        corrected = build_infraction({**record, "id": record["id"], "infraction_description": "Dado corrigido"}, records=[record], vehicles=[vehicle()], user_id="USR-2", now="2026-06-21T13:00:00")
        self.assertEqual(corrected["infraction_description"], "Dado corrigido")

    def test_file_hash_detects_content(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "notificacao.pdf"
            path.write_bytes(b"conteudo-ficticio")
            self.assertEqual(len(file_sha256(path)), 64)

    def test_soft_delete_is_preserved_by_domain_record(self):
        record = self.build()
        archived = soft_delete(record, now=NOW)
        self.assertEqual(archived["deleted_at"], NOW)
        self.assertNotEqual(archived["id"], "")

    def test_driver_permissions_require_relationship_and_formal_release(self):
        record = self.build()
        record["driver_id"] = "USR-DRIVER"
        self.assertFalse(driver_can_view_infraction(record, "USR-DRIVER"))
        record["released_to_driver_at"] = NOW
        self.assertTrue(driver_can_view_infraction(record, "USR-DRIVER"))
        self.assertFalse(driver_can_view_infraction(record, "USR-OTHER"))

    def test_sensitive_document_access_is_separate(self):
        record = {**self.build(), "driver_id": "USR-DRIVER", "released_to_driver_at": NOW}
        attachment = {"is_sensitive": True}
        self.assertFalse(attachment_access_allowed(attachment, record, user_id="USR-DRIVER", role="leitura", can_view_sensitive=False))
        self.assertTrue(attachment_access_allowed(attachment, record, user_id="USR-ADMIN", role="admin", can_view_sensitive=True))

    def test_audit_log_preserves_before_after_and_justification(self):
        log = build_audit_log(log_id="FAL-1", infraction_id="FINF-1", user_id="USR-1", action="edit",
                              before={"status": "recebida"}, after={"status": "em_conferencia"},
                              justification="Notificação conferida", created_at=NOW)
        self.assertEqual(log["previous_data"]["status"], "recebida")
        self.assertEqual(log["new_data"]["status"], "em_conferencia")
        self.assertEqual(log["justification"], "Notificação conferida")


class FleetFineMigrationTest(unittest.TestCase):
    def test_apply_validate_and_rollback(self):
        with tempfile.TemporaryDirectory(prefix="fleet-fines-migration-") as tempdir:
            root = Path(tempdir)
            data, backups = root / "data", root / "backups"
            data.mkdir()
            (data / "settings.json").write_text("{}", encoding="utf-8")
            result = apply_fleet_fines(data_dir=data, db_path=data / "sannygold.db", backups_dir=backups)
            self.assertTrue(result["validation"]["ok"])
            self.assertTrue(validate_fleet_fines(data / "sannygold.db")["ok"])
            with connect(data / "sannygold.db") as connection:
                applied = {row[0] for row in connection.execute("SELECT id FROM schema_migrations")}
            self.assertTrue(set(FLEET_FINES_MIGRATIONS).issubset(applied))
            settings = json.loads((data / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(settings["fleet_fines_alert_days"], [15, 10, 7, 5, 3, 1, 0])
            rollback = rollback_fleet_fines(data_dir=data, backups_dir=backups, snapshot_dir=Path(result["snapshot_dir"]))
            self.assertIn("sannygold.db", rollback["removed_files"])

    def test_database_natural_key_enforces_duplicate(self):
        with tempfile.TemporaryDirectory(prefix="fleet-fines-db-") as tempdir:
            root = Path(tempdir)
            data = root / "data"
            data.mkdir()
            apply_fleet_fines(data_dir=data, db_path=data / "sannygold.db", backups_dir=root / "backups")
            with connect(data / "sannygold.db") as connection:
                columns = "id,internal_number,issuing_authority,infraction_notice_number,infraction_date,vehicle_plate_snapshot,created_at,updated_at,deleted_at,source_file,payload_json,payload_hash,migrated_at"
                values = ("F1", "MULTA-2026-000001", "PRF", "A1", "2026-06-20", "ABC1D23", NOW, NOW, "", "test.json", "{}", "h1", NOW)
                connection.execute(f"INSERT INTO fleet_traffic_infractions ({columns}) VALUES ({','.join('?' for _ in values)})", values)
                duplicate = ("F2", "MULTA-2026-000002", "PRF", "A1", "2026-06-20", "ABC1D23", NOW, NOW, "", "test.json", "{}", "h2", NOW)
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(f"INSERT INTO fleet_traffic_infractions ({columns}) VALUES ({','.join('?' for _ in duplicate)})", duplicate)


if __name__ == "__main__":
    unittest.main()
