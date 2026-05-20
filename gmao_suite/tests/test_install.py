# -*- coding: utf-8 -*-
"""
Tests d'installation et de coherence structurelle du module GMAO Suite.

Lance via :
    odoo-bin -c odoo.conf -d <db> --test-enable -i gmao_suite --stop-after-init

Ces tests verifient que le module est correctement installable et que les
elements declares (modeles, groupes, sequences, etc.) sont bien presents
apres l'install.
"""
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'gmao_install')
class TestGmaoInstall(TransactionCase):
    """Verifie que l'install du module s'est correctement effectue."""

    def test_models_registered(self):
        """Tous les modeles principaux doivent etre enregistres."""
        expected_models = [
            'maintenance.site',
            'gmao.equipment',
            'gmao.equipment.category',
            'gmao.team',
            'maintenance.contract',
            'maintenance.parts.used',
            'gmao.request',
            'maintenance.conformite.securite',
            'maintenance.efficacite.energetique',
        ]
        for model in expected_models:
            self.assertIn(
                model, self.env.registry.models,
                f"Modele attendu non enregistre : {model}",
            )

    def test_groups_exist(self):
        """Verifie que les groupes principaux RBAC sont declares."""
        expected_groups = [
            'gmao_suite.group_gmao_admin',
            'gmao_suite.group_request_reader',
            'gmao_suite.group_request_creator',
            'gmao_suite.group_request_user',
            'gmao_suite.group_request_admin',
            'gmao_suite.group_maintenance_equipment_admin',
            'gmao_suite.group_maintenance_site_admin',
            'gmao_suite.group_maintenance_team_admin',
            'gmao_suite.group_maintenance_contract_admin',
            'gmao_suite.group_parts_used_admin',
        ]
        for xml_id in expected_groups:
            group = self.env.ref(xml_id, raise_if_not_found=False)
            self.assertTrue(group, f"Groupe attendu introuvable : {xml_id}")

    def test_sequences_exist(self):
        """Verifie les sequences ir.sequence creees."""
        expected_codes = [
            'gmao.request',
            'gmao.equipment',
            'maintenance.contract',
            'maintenance.conformite.securite',
            'maintenance.parts.used',
        ]
        for code in expected_codes:
            seq = self.env['ir.sequence'].search([('code', '=', code)], limit=1)
            self.assertTrue(seq, f"Sequence introuvable pour code: {code}")

    def test_access_rules_completeness(self):
        """Tous les modeles GMAO doivent avoir au moins une ir.model.access."""
        gmao_models = [
            'maintenance.site',
            'gmao.equipment',
            'gmao.team',
            'maintenance.contract',
            'gmao.request',
            'maintenance.conformite.securite',
        ]
        for model_name in gmao_models:
            rules = self.env['ir.model.access'].search([
                ('model_id.model', '=', model_name),
            ])
            self.assertTrue(
                rules,
                f"Aucune ir.model.access definie pour {model_name}",
            )

    def test_gmao_admin_implies_all_admins(self):
        """Le groupe gmao_admin doit impliquer tous les admins de domaine."""
        global_admin = self.env.ref('gmao_suite.group_gmao_admin')
        implied = global_admin.implied_ids
        expected = [
            'gmao_suite.group_request_admin',
            'gmao_suite.group_maintenance_equipment_admin',
            'gmao_suite.group_maintenance_contract_admin',
            'gmao_suite.group_maintenance_team_admin',
            'gmao_suite.group_maintenance_site_admin',
            'gmao_suite.group_parts_used_admin',
            'gmao_suite.group_efficacite_energetique_admin',
            'gmao_suite.group_maintenance_equipment_category_admin',
        ]
        for xml_id in expected:
            grp = self.env.ref(xml_id, raise_if_not_found=False)
            self.assertIn(
                grp, implied,
                f"gmao_admin n'implique pas {xml_id}",
            )
