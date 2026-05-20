from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, date

class MaintenanceTeamReportWizard(models.TransientModel):
    _name = 'maintenance.team.report.wizard'
    _description = 'Assistant pour rapport des équipes de maintenance'

    team_id = fields.Many2one('gmao.team', string='Équipe', required=True)
    start_date = fields.Date(string='Date début', required=True, default=lambda self: fields.Date.context_today(self).replace(day=1))
    end_date = fields.Date(string='Date fin', required=True, default=fields.Date.context_today)

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if self.env.context.get('active_model') == 'gmao.team':
            team = self.env['gmao.team'].browse(self.env.context.get('active_id'))
            res.update({
                'team_id': team.id,
                'start_date': team.date_start,
                'end_date': team.date_end
            })
        return res

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for wizard in self:
            if wizard.start_date > wizard.end_date:
                raise ValidationError(_("La date de début doit être antérieure à la date de fin"))

    def action_print_report(self):
        """Action pour générer le rapport depuis le wizard"""
        self.ensure_one()
        if not self.start_date or not self.end_date:
            raise UserError(_("Les dates sont requises pour générer le rapport"))

        return self.env.ref('gmao_suite.action_report_maintenance_team').report_action(
            self.team_id,
            data={
                'start_date': fields.Date.to_string(self.start_date),
                'end_date': fields.Date.to_string(self.end_date),
                'team_id': self.team_id.id
            }
        )
