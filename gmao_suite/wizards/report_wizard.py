# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_round

class MaintenanceReportWizard(models.TransientModel):
    _name = 'maintenance.report.wizard'
    _description = 'Assistant pour la période d’édition du rapport de maintenance'

    # Champs pour choisir la période
    report_period_from = fields.Datetime(string="Période de début", required=True)
    report_period_to = fields.Datetime(string="Période de fin", required=True)

    @api.constrains('report_period_from', 'report_period_to')
    def _check_period_dates(self):
        # Validation pour s'assurer que la date de fin est postérieure à la date de début
        for record in self:
            if record.report_period_from > record.report_period_to:
                raise UserError(_("La date de fin doit être postérieure à la date de début."))

    def action_generate_report(self):
        """Genere le rapport sur la periode selectionnee.

        Fix bug #9 : on passait 'self' (le wizard TransientModel) a report_action
        au lieu des records reels a imprimer. Maintenant on passe le recordset
        des maintenance.request filtre sur la periode.
        """
        self.ensure_one()
        maintenance_requests = self.env['gmao.request'].search([
            ('request_date', '>=', self.report_period_from),
            ('request_date', '<=', self.report_period_to),
        ])
        if not maintenance_requests:
            raise UserError(_("Aucune demande de maintenance n'a ete trouvee pour la periode selectionnee."))

        data = {
            'report_period_from': self.report_period_from.strftime('%d/%m/%Y'),
            'report_period_to': self.report_period_to.strftime('%d/%m/%Y'),
            'maintenance_request_ids': maintenance_requests.ids,
        }
        # Passer les vrais records au report_action, pas le wizard self
        return self.env.ref('gmao_suite.action_report_maintenance_request_analysis').report_action(
            maintenance_requests, data=data,
        )

# Mise à jour du modèle de rapport pour inclure le choix de la période dans le contexte
class MaintenanceRequest(models.Model):
    _inherit = 'gmao.request'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.browse(docids)
        if data and 'report_period_from' in data and 'report_period_to' in data:
            docs = docs.filtered(lambda r: data['report_period_from'] <= r.request_date <= data['report_period_to'])
        return {
            'doc_ids': docids,
            'doc_model': 'gmao.request',
            'docs': docs,
            'data': data,
            'float_round': float_round,
        }
