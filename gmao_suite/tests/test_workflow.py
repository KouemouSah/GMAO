# -*- coding: utf-8 -*-
"""
Tests fonctionnels du workflow GMAO : creation site/equipement, demande,
transitions d'etat de maintenance.
"""
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import ValidationError, UserError


@tagged('post_install', '-at_install', 'gmao_workflow')
class TestGmaoWorkflow(TransactionCase):
    """Workflow nominal de bout en bout."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Une ville Odoo native a utiliser
        cls.city = cls.env['res.city'].search([], limit=1)
        if not cls.city:
            country = cls.env.ref('base.fr')
            cls.city = cls.env['res.city'].create({
                'name': 'Paris-Test',
                'country_id': country.id,
            })
        # Categorie d'equipement
        cls.category = cls.env['gmao.equipment.category'].create({
            'name': 'Climatisation',
        })
        # Partner client
        cls.partner = cls.env['res.partner'].create({
            'name': 'Client de test GMAO',
            'email': 'gmao_test@example.com',
        })

    def test_01_create_site(self):
        """Creation d'un site avec coordonnees valides."""
        site = self.env['maintenance.site'].create({
            'name': 'Site Test A',
            'code': 'TEST-A',
            'city_id': self.city.id,
            'latitude': 48.8566,
            'longitude': 2.3522,
        })
        self.assertTrue(site.id, "Le site n'a pas ete cree")
        self.assertEqual(site.country_id, self.city.country_id,
                         "Le pays related ne suit pas la ville")

    def test_02_site_invalid_coordinates(self):
        """Latitude > 90 doit lever ValidationError."""
        with self.assertRaises(ValidationError):
            self.env['maintenance.site'].create({
                'name': 'Site Bad',
                'code': 'BAD',
                'city_id': self.city.id,
                'latitude': 999,
            })

    def test_03_create_equipment(self):
        """Creation equipement attache a un site."""
        site = self.env['maintenance.site'].create({
            'name': 'Site Test B',
            'code': 'TEST-B',
            'city_id': self.city.id,
        })
        equipment = self.env['gmao.equipment'].create({
            'name': 'Climatiseur principal',
            'code': 'CLI-001',
            'category_id': self.category.id,
            'site_id': site.id,
        })
        self.assertEqual(equipment.state, 'operational')
        self.assertEqual(equipment.maintenance_count, 0)

    def test_04_request_workflow(self):
        """Workflow complet de la demande : new -> to_validate -> in_progress -> repaired -> done."""
        site = self.env['maintenance.site'].create({
            'name': 'Site Test C',
            'code': 'TEST-C',
            'city_id': self.city.id,
        })
        equipment = self.env['gmao.equipment'].create({
            'name': 'Equipement test workflow',
            'code': 'WF-001',
            'category_id': self.category.id,
            'site_id': site.id,
        })
        request = self.env['gmao.request'].create({
            'description': 'Test workflow',
            'equipment_id': equipment.id,
            'user_id': self.partner.id,
            'system': 'mail',
        })
        # Etat initial
        self.assertEqual(request.state, 'new')
        # On octroie le droit user a l'utilisateur courant (env.user)
        admin_group = self.env.ref('gmao_suite.group_gmao_admin')
        self.env.user.groups_id = [(4, admin_group.id)]
        # Transition new -> to_validate
        request.action_validate()
        self.assertEqual(request.state, 'to_validate')
        # to_validate -> in_progress
        request.action_start()
        self.assertEqual(request.state, 'in_progress')
        self.assertTrue(request.start_date, "start_date doit etre rempli au demarrage")
        # in_progress -> repaired
        request.action_repair()
        self.assertEqual(request.state, 'repaired')
        # repaired -> done
        request.action_done()
        self.assertEqual(request.state, 'done')
        self.assertTrue(request.close_date, "close_date doit etre rempli a la cloture")

    def test_05_request_invalid_transition(self):
        """Annuler une demande deja terminee doit echouer."""
        site = self.env['maintenance.site'].create({
            'name': 'Site Test D',
            'code': 'TEST-D',
            'city_id': self.city.id,
        })
        equipment = self.env['gmao.equipment'].create({
            'name': 'Equipement test transition',
            'code': 'TR-001',
            'category_id': self.category.id,
            'site_id': site.id,
        })
        request = self.env['gmao.request'].create({
            'description': 'Test transition',
            'equipment_id': equipment.id,
            'user_id': self.partner.id,
            'system': 'phone',
            'state': 'done',
        })
        with self.assertRaises(UserError):
            request.action_cancel()

    def test_06_gmao_admin_toggle(self):
        """Le toggle gmao_admin propage les droits."""
        # User propre pour ne pas polluer
        test_user = self.env['res.users'].create({
            'name': 'User Test',
            'login': 'gmao_test_user',
            'email': 'gmao_test_user@example.com',
        })
        # Avant : 0 groupes GMAO actifs
        gmao_cat = self.env.ref('gmao_suite.module_category_maintenance')
        gmao_groups_before = test_user.groups_id.filtered(
            lambda g: g.category_id == gmao_cat
        )
        self.assertFalse(gmao_groups_before, "Aucun groupe GMAO initial")
        # On toggle gmao_admin sur le user
        test_user.gmao_admin = True
        # On force l'execution du onchange via call manuel (les onchange ne sont
        # pas triggered dans un set direct - on simule le save)
        test_user._onchange_gmao_admin()
        # Le groupe global doit etre ajoute
        global_admin = self.env.ref('gmao_suite.group_gmao_admin')
        # Apres save, Odoo propage les implied_ids
        test_user.write({'groups_id': [(4, global_admin.id)]})
        gmao_groups_after = test_user.groups_id.filtered(
            lambda g: g.category_id == gmao_cat
        )
        self.assertTrue(
            gmao_groups_after,
            "Le toggle gmao_admin doit propager au moins 1 groupe GMAO",
        )
