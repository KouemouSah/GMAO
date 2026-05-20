# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class LoadKitWizard(models.TransientModel):
    """Wizard de selection du kit de pieces a charger sur une demande.
    Remplace l'auto-selection imposee : l'utilisateur CHOISIT le kit."""
    _name = 'gmao.load.kit.wizard'
    _description = 'Charger un kit de pièces'

    request_id = fields.Many2one(
        'gmao.request', string='Demande', required=True, ondelete='cascade')
    equipment_id = fields.Many2one(
        related='request_id.equipment_id', string='Équipement', readonly=True)
    available_kit_ids = fields.Many2many(
        'gmao.parts.kit', compute='_compute_available_kits',
        string='Kits disponibles')
    kit_id = fields.Many2one(
        'gmao.parts.kit', string='Kit à charger', required=True,
        help="Kits pertinents : spécifiques à l'équipement ou à sa catégorie.")

    @api.depends('request_id', 'equipment_id')
    def _compute_available_kits(self):
        Kit = self.env['gmao.parts.kit']
        for wiz in self:
            eq = wiz.equipment_id
            if not eq:
                wiz.available_kit_ids = Kit.browse()
                continue
            domain = ['|', ('equipment_id', '=', eq.id)]
            if eq.category_id:
                domain += ['&', ('equipment_id', '=', False),
                           ('category_id', '=', eq.category_id.id)]
            else:
                # pas de categorie : seulement les kits specifiques equipement
                domain = [('equipment_id', '=', eq.id)]
            wiz.available_kit_ids = Kit.search(domain)

    @api.onchange('available_kit_ids')
    def _onchange_default_kit(self):
        # pre-selectionne le 1er kit pertinent pour aller plus vite
        if self.available_kit_ids and not self.kit_id:
            self.kit_id = self.available_kit_ids[:1]

    def action_load(self):
        self.ensure_one()
        if not self.kit_id:
            raise UserError(_("Sélectionnez un kit à charger."))
        self.request_id._load_parts_kit(kit=self.kit_id)
        return {'type': 'ir.actions.act_window_close'}
