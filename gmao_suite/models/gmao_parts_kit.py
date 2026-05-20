# -*- coding: utf-8 -*-
"""
Kit de pieces standard (nomenclature de maintenance).

Inspire du pattern mrp.bom natif : definit la liste des pieces recurrentes
pour un type d'intervention preventive donne, rattachable a :
  - un equipement precis (prioritaire), OU
  - une categorie d'equipement (fallback).

A la creation d'une demande PREVENTIVE, le systeme cherche le kit applicable
(equipement d'abord, sinon categorie) et pre-cale les pieces en brouillon.
Le technicien libere (supprime) celles non utilisees.
"""
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class GmaoPartsKit(models.Model):
    _name = 'gmao.parts.kit'
    _description = 'Kit de pieces standard (maintenance preventive)'

    name = fields.Char(string='Nom du kit', required=True)
    active = fields.Boolean(default=True)
    equipment_id = fields.Many2one(
        'gmao.equipment', string='Equipement specifique',
        help="Si renseigne, le kit s'applique a CET equipement (prioritaire).")
    category_id = fields.Many2one(
        'gmao.equipment.category', string="Categorie d'equipement",
        help="Si renseigne (et pas d'equipement), le kit s'applique a toute la categorie.")
    line_ids = fields.One2many('gmao.parts.kit.line', 'kit_id', string='Pieces du kit')
    company_id = fields.Many2one('res.company', string='Societe', default=lambda self: self.env.company)
    note = fields.Text(string='Notes')
    line_count = fields.Integer(compute='_compute_line_count', string='Nb pieces')

    @api.depends('line_ids')
    def _compute_line_count(self):
        for kit in self:
            kit.line_count = len(kit.line_ids)

    @api.constrains('equipment_id', 'category_id')
    def _check_target(self):
        for kit in self:
            if not kit.equipment_id and not kit.category_id:
                raise ValidationError(_(
                    "Un kit doit cibler soit un equipement, soit une categorie d'equipement."))

    @api.model
    def find_applicable_kit(self, equipment):
        """Retourne le kit applicable pour un equipement.

        Priorite : kit rattache a l'equipement precis ; sinon kit rattache
        a la categorie de l'equipement. Retourne un recordset (vide si aucun).
        """
        if not equipment:
            return self.browse()
        kit = self.search([('equipment_id', '=', equipment.id)], limit=1)
        if not kit and equipment.category_id:
            kit = self.search([
                ('category_id', '=', equipment.category_id.id),
                ('equipment_id', '=', False),
            ], limit=1)
        return kit


class GmaoPartsKitLine(models.Model):
    _name = 'gmao.parts.kit.line'
    _description = 'Ligne de kit de pieces'

    kit_id = fields.Many2one('gmao.parts.kit', string='Kit', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Piece', required=True)
    quantity = fields.Float(string='Quantite standard', default=1.0, required=True)
    part_nature = fields.Selection([
        ('consumable', 'Consommable interne'),
        ('billable', 'Refacturable au client'),
    ], string='Nature', default='consumable', required=True)
