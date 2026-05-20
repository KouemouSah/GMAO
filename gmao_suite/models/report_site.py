# -*- coding: utf-8 -*-
from odoo import api, models


class ReportSite(models.AbstractModel):
    """P5.2 — Rapport site (PDF). Agrege par site : equipements + interventions
    (nb, couts, temps d'arret) + KPI site, pour l'aide a la decision.

    maintenance.site n'a pas de one2many equipements -> on recherche via
    gmao.equipment.site_id et gmao.request.site_id.
    """
    _name = 'report.gmao_suite.report_site_document'
    _description = "Rapport site"

    @api.model
    def _get_report_values(self, docids, data=None):
        Equipment = self.env['gmao.equipment']
        Request = self.env['gmao.request']
        sites = self.env['maintenance.site'].browse(docids)
        site_data = {}
        for site in sites:
            equipments = Equipment.search([('site_id', '=', site.id)])
            requests = Request.search([('site_id', '=', site.id)])
            done = requests.filtered(lambda r: r.state == 'done')
            mtbfs = [r.mtbf for r in done if r.mtbf]
            mttrs = [r.mttr for r in done if r.mttr]
            preventive = requests.filtered(lambda r: r.maintenance_type == 'preventive')
            rows = []
            for eq in equipments:
                eq_reqs = requests.filtered(lambda r: r.equipment_id.id == eq.id)
                rows.append({
                    'equipment': eq,
                    'nb': len(eq_reqs),
                    'cost': round(sum(eq_reqs.mapped('total_cost')), 2),
                    'downtime': round(sum(eq_reqs.mapped('downtime')), 1),
                    'ratio': eq.maintenance_cost_ratio,
                    'replace': eq.replacement_recommended,
                })
            site_data[site.id] = {
                'rows': rows,
                'nb_equipment': len(equipments),
                'nb_requests': len(requests),
                'total_cost': round(sum(requests.mapped('total_cost')), 2),
                'downtime_total': round(sum(requests.mapped('downtime')), 1),
                'avg_mtbf': round(sum(mtbfs) / len(mtbfs), 1) if mtbfs else 0.0,
                'avg_mttr': round(sum(mttrs) / len(mttrs), 1) if mttrs else 0.0,
                'pct_preventive': round(len(preventive) / len(requests) * 100, 1) if requests else 0.0,
                'currency': site.company_id.currency_id,
            }
        return {
            'doc_ids': docids,
            'doc_model': 'maintenance.site',
            'docs': sites,
            'site_data': site_data,
        }
