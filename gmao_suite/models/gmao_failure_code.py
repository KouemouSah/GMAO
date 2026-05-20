# -*- coding: utf-8 -*-
from odoo import models, fields


class GmaoFailureCode(models.Model):
    """P6 — Catalogue des codes panne. Normalise la saisie des techniciens
    (liste deroulante) pour permettre l'analyse de recurrence et la prediction
    des pannes. Inspire ISO 14224 (modes de defaillance), version pragmatique."""
    _name = 'gmao.failure.code'
    _description = 'Code panne'
    _order = 'code'

    code = fields.Char(string='Code', required=True, index=True)
    name = fields.Char(string='Libellé', required=True, translate=True)
    failure_mode = fields.Selection([
        ('mechanical', 'Mécanique'),
        ('electrical', 'Électrique'),
        ('hydraulic', 'Hydraulique'),
        ('pneumatic', 'Pneumatique'),
        ('electronic', 'Électronique / Logiciel'),
        ('wear', 'Usure'),
        ('operator', 'Erreur opérateur'),
        ('external', 'Cause externe'),
        ('none', 'Aucune (préventif / RAS)'),
        ('other', 'Autre'),
    ], string='Mode de défaillance', required=True, default='other', index=True)
    applies_to = fields.Selection([
        ('corrective', 'Correctif (panne)'),
        ('preventive', 'Préventif (activité planifiée)'),
        ('both', 'Les deux'),
    ], string='S\'applique à', required=True, default='corrective', index=True,
        help="Filtre le code selon le type de maintenance de la demande "
             "(le technicien ne voit que les codes pertinents).")
    recommended_action = fields.Text(string='Action recommandée')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Société',
        default=lambda self: self.env.company, index=True)

    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)',
         "Ce code panne existe déjà pour cette société."),
    ]

    def name_get(self):
        return [(rec.id, "[%s] %s" % (rec.code, rec.name)) for rec in self]
