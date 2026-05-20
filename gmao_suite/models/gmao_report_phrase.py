# -*- coding: utf-8 -*-
from odoo import models, fields


class GmaoReportPhrase(models.Model):
    """Catalogue de phrases-types reutilisables pour le rapport d'intervention
    (symptomes, causes, travaux, recommandations). Selectionner une entree
    insere son texte dans le champ concerne ; saisie libre + quick-create
    toujours possibles (la nouvelle valeur devient reutilisable)."""
    _name = 'gmao.report.phrase'
    _description = "Phrase-type de rapport d'intervention"
    _order = 'category, code, name'

    code = fields.Char(string='Code', index=True)
    name = fields.Char(string='Libellé', required=True)
    category = fields.Selection([
        ('symptom', 'Symptôme'),
        ('cause', 'Cause racine'),
        ('work', 'Travaux réalisés'),
        ('recommendation', 'Recommandation / suivi'),
    ], string='Catégorie', required=True, default='symptom', index=True)
    text = fields.Text(
        string='Texte pré-rempli',
        help="Texte inséré dans le rapport à la sélection. Si vide, le libellé est utilisé.")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Société',
        default=lambda self: self.env.company, index=True)

    def name_get(self):
        res = []
        for rec in self:
            label = "[%s] %s" % (rec.code, rec.name) if rec.code else rec.name
            res.append((rec.id, label))
        return res
