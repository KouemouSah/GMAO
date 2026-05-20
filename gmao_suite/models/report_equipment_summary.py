# -*- coding: utf-8 -*-
from odoo import api, models


class ReportEquipmentSummary(models.AbstractModel):
    """P5.1 — Dossier equipement (PDF). Distinct du rapport d'analyse de
    remplacement : vue d'ensemble (infos + couts + MTBF/MTTR + reco)."""
    _name = 'report.gmao_suite.report_equipment_summary_document'
    _description = "Rapport dossier equipement"

    @api.model
    def _get_report_values(self, docids, data=None):
        equipments = self.env['gmao.equipment'].browse(docids)
        stats = {}
        for eq in equipments:
            done = eq.maintenance_ids.filtered(lambda m: m.state == 'done')
            mtbfs = [m.mtbf for m in done if m.mtbf]
            mttrs = [m.mttr for m in done if m.mttr]
            stats[eq.id] = {
                'avg_mtbf': round(sum(mtbfs) / len(mtbfs), 1) if mtbfs else 0.0,
                'avg_mttr': round(sum(mttrs) / len(mttrs), 1) if mttrs else 0.0,
                'downtime_total': round(sum(eq.maintenance_ids.mapped('downtime')), 1),
                'threshold': eq._get_replacement_threshold(),
            }
        return {
            'doc_ids': docids,
            'doc_model': 'gmao.equipment',
            'docs': equipments,
            'stats': stats,
        }
