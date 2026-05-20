# -*- coding: utf-8 -*-
"""
P4 : Rapport financier consolide GMAO.

TransientModel qui agrege les couts de maintenance sur une periode :
  - Cout total (pieces + main d'oeuvre)
  - Decomposition par equipement / site / type
  - ROI maintenance preventive vs corrective
  - Refacturation (pieces billable) + marge
  - TCO par equipement (cout cumule)

Expose des KPIs computes + 3 tables HTML pour la vue form, et alimente
un rapport QWeb PDF imprimable.
"""
from odoo import api, fields, models, _


class GmaoFinancialReport(models.TransientModel):
    _name = 'gmao.financial.report'
    _description = 'Rapport financier GMAO'

    date_from = fields.Date(
        string='Date debut', required=True,
        default=lambda self: fields.Date.today().replace(month=1, day=1))
    date_to = fields.Date(
        string='Date fin', required=True, default=fields.Date.context_today)
    site_id = fields.Many2one('maintenance.site', string='Site (filtre optionnel)')

    # KPIs globaux
    total_cost = fields.Float('Cout total', compute='_compute_report', digits=(12, 2))
    total_parts_cost = fields.Float('Cout pieces', compute='_compute_report', digits=(12, 2))
    total_labor_cost = fields.Float('Cout main d\'oeuvre', compute='_compute_report', digits=(12, 2))
    preventive_cost = fields.Float('Cout preventif', compute='_compute_report', digits=(12, 2))
    corrective_cost = fields.Float('Cout correctif', compute='_compute_report', digits=(12, 2))
    pct_preventive_cost = fields.Float('% cout preventif', compute='_compute_report', digits=(5, 1))
    billable_amount = fields.Float('Montant refacturable', compute='_compute_report', digits=(12, 2))
    billable_margin = fields.Float('Marge refacturation', compute='_compute_report', digits=(12, 2))
    requests_count = fields.Integer('Nb interventions', compute='_compute_report')
    avg_cost_per_request = fields.Float('Cout moyen / intervention', compute='_compute_report', digits=(12, 2))

    cost_by_equipment_html = fields.Html('Cout par equipement', compute='_compute_report', sanitize=False)
    cost_by_site_html = fields.Html('Cout par site', compute='_compute_report', sanitize=False)
    roi_html = fields.Html('Analyse ROI preventif', compute='_compute_report', sanitize=False)

    def _get_domain(self):
        self.ensure_one()
        domain = [
            ('request_date', '>=', self.date_from),
            ('request_date', '<=', self.date_to),
            ('state', '!=', 'cancel'),
        ]
        if self.site_id:
            domain.append(('site_id', '=', self.site_id.id))
        return domain

    @api.depends('date_from', 'date_to', 'site_id')
    def _compute_report(self):
        Request = self.env['gmao.request']
        PartsUsed = self.env['maintenance.parts.used']
        for record in self:
            requests = Request.search(record._get_domain())
            record.requests_count = len(requests)
            record.total_parts_cost = sum(requests.mapped('total_parts_cost'))
            record.total_labor_cost = sum(requests.mapped('labor_cost'))
            record.total_cost = sum(requests.mapped('total_cost'))
            record.avg_cost_per_request = (
                record.total_cost / record.requests_count if record.requests_count else 0.0)

            preventive = requests.filtered(lambda r: r.maintenance_type == 'preventive')
            corrective = requests.filtered(lambda r: r.maintenance_type == 'corrective')
            record.preventive_cost = sum(preventive.mapped('total_cost'))
            record.corrective_cost = sum(corrective.mapped('total_cost'))
            tot = record.preventive_cost + record.corrective_cost
            record.pct_preventive_cost = (record.preventive_cost / tot * 100) if tot else 0.0

            # Refacturation : pieces billable des interventions de la periode
            billable_parts = PartsUsed.search([
                ('intervention_id', 'in', requests.ids),
                ('part_nature', '=', 'billable'),
                ('state', '!=', 'cancelled'),
            ])
            record.billable_amount = sum(billable_parts.mapped('total_sale_price'))
            record.billable_margin = sum(billable_parts.mapped('margin'))

            # === HTML : cout par equipement ===
            data_eq = Request.read_group(
                record._get_domain(),
                ['equipment_id', 'total_cost:sum', 'total_parts_cost:sum', 'labor_cost:sum'],
                ['equipment_id'],
            )
            data_eq = sorted(data_eq, key=lambda d: -(d.get('total_cost') or 0))
            rows = ['<tr><th>Equipement</th><th class="text-right">Interventions</th>'
                    '<th class="text-right">Pieces</th><th class="text-right">Main d\'oeuvre</th>'
                    '<th class="text-right">Total</th></tr>']
            for item in data_eq:
                eq = item.get('equipment_id')
                if not eq:
                    continue
                eq_name = eq[1] if isinstance(eq, (list, tuple)) else str(eq)
                rows.append(
                    '<tr><td>%s</td><td class="text-right">%s</td>'
                    '<td class="text-right">%.2f</td><td class="text-right">%.2f</td>'
                    '<td class="text-right"><strong>%.2f EUR</strong></td></tr>' % (
                        eq_name, item.get('equipment_id_count', 0),
                        item.get('total_parts_cost', 0.0) or 0.0,
                        item.get('labor_cost', 0.0) or 0.0,
                        item.get('total_cost', 0.0) or 0.0))
            record.cost_by_equipment_html = (
                '<table class="table table-sm table-striped">' + ''.join(rows) + '</table>'
                if len(rows) > 1 else '<p class="text-muted">Aucune donnee.</p>')

            # === HTML : cout par site ===
            data_site = Request.read_group(
                record._get_domain(),
                ['site_id', 'total_cost:sum'],
                ['site_id'],
            )
            data_site = sorted(data_site, key=lambda d: -(d.get('total_cost') or 0))
            rows = ['<tr><th>Site</th><th class="text-right">Interventions</th><th class="text-right">Cout total</th></tr>']
            for item in data_site:
                site = item.get('site_id')
                site_name = (site[1] if isinstance(site, (list, tuple)) else str(site)) if site else 'Sans site'
                rows.append(
                    '<tr><td>%s</td><td class="text-right">%s</td>'
                    '<td class="text-right"><strong>%.2f EUR</strong></td></tr>' % (
                        site_name, item.get('site_id_count', 0), item.get('total_cost', 0.0) or 0.0))
            record.cost_by_site_html = (
                '<table class="table table-sm table-striped">' + ''.join(rows) + '</table>'
                if len(rows) > 1 else '<p class="text-muted">Aucune donnee.</p>')

            # === HTML : ROI preventif ===
            record.roi_html = (
                '<table class="table table-sm">'
                '<tr><th></th><th class="text-right">Preventif</th><th class="text-right">Correctif</th></tr>'
                '<tr><td>Nb interventions</td><td class="text-right">%s</td><td class="text-right">%s</td></tr>'
                '<tr><td>Cout total</td><td class="text-right">%.2f EUR</td><td class="text-right">%.2f EUR</td></tr>'
                '<tr><td>Cout moyen</td><td class="text-right">%.2f EUR</td><td class="text-right">%.2f EUR</td></tr>'
                '</table>'
                '<p class="text-muted"><i>Un ratio preventif eleve reduit generalement '
                'le cout correctif (pannes) a moyen terme. Cible recommandee : &gt; 60%% preventif.</i></p>'
            ) % (
                len(preventive), len(corrective),
                record.preventive_cost, record.corrective_cost,
                (record.preventive_cost / len(preventive)) if preventive else 0.0,
                (record.corrective_cost / len(corrective)) if corrective else 0.0,
            )

    def action_print_pdf(self):
        """Genere le rapport PDF financier."""
        self.ensure_one()
        return self.env.ref('gmao_suite.action_report_gmao_financial').report_action(self)
