# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class EfficaciteAction(models.Model):
    """Action recommandee structuree d'une evaluation d'efficacite energetique.
    Numerotee, suivie (a faire/fait), et peut generer une demande de
    maintenance (brouillon) liee a l'equipement evalue."""
    _name = 'maintenance.efficacite.action'
    _description = "Action recommandée (efficacité énergétique)"
    _order = 'sequence, id'

    efficacite_id = fields.Many2one(
        'maintenance.efficacite.energetique', string='Évaluation',
        required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(
        related='efficacite_id.company_id', store=True, index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Action recommandée', required=True)
    description = fields.Text(string='Détail')
    priority = fields.Selection([
        ('0', 'Basse'), ('1', 'Normale'), ('2', 'Haute'),
    ], string='Priorité', default='1', index=True)
    deadline = fields.Date(string='Échéance')
    state = fields.Selection([
        ('todo', 'À faire'), ('done', 'Fait'),
    ], string='État', default='todo', index=True)
    request_id = fields.Many2one(
        'gmao.request', string='Demande générée', readonly=True, copy=False)

    def action_generate_request(self):
        """Genere (ou rouvre) une demande de maintenance corrective brouillon
        pour cette action, liee a l'equipement de l'evaluation."""
        self.ensure_one()
        if self.request_id:
            return self._open_request()
        eff = self.efficacite_id
        if not eff.equipment_id:
            raise UserError(_(
                "L'évaluation doit être liée à un équipement pour générer "
                "une demande de maintenance."))
        desc = _("Action d'efficacité énergétique (éval. %s) : %s") % (
            eff.name or '', self.name)
        if self.description:
            desc += "\n%s" % self.description
        req = self.env['gmao.request'].create({
            'description': desc,
            'equipment_id': eff.equipment_id.id,
            'user_id': eff.evaluator_id.id or self.env.user.partner_id.id,
            'maintenance_type': 'corrective',
            'company_id': eff.company_id.id,
        })
        self.request_id = req.id
        return self._open_request()

    def _open_request(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Demande de maintenance"),
            'res_model': 'gmao.request',
            'res_id': self.request_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
