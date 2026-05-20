# -*- coding: utf-8 -*-
"""
Tableau de bord central GMAO Suite : TransientModel avec KPIs metiers calcules
en temps reel (live).

Approche pragmatique pour Odoo 13 :
- TransientModel = enregistrement ephemere stocke en memoire
- Champs computed = lecture rapide depuis les modeles de production
- Vue form = layout en cards Bootstrap, sans widget OWL custom
- Action ouvre une nouvelle instance a chaque clic = data fraiche

Alternative consideree : AbstractModel + widget OWL custom (Chart.js).
Choix : TransientModel + cards car compatibilite OWL 1 (Odoo 13) +
rendu standard Odoo + zero JS custom a maintenir.
"""
from datetime import timedelta
from odoo import api, fields, models


class GmaoDashboard(models.TransientModel):
    _name = 'gmao.dashboard'
    _description = 'Tableau de bord GMAO Suite'

    # === Compteurs par etat ===
    total_requests = fields.Integer('Total demandes', compute='_compute_kpis')
    new_count = fields.Integer('Nouvelles', compute='_compute_kpis')
    to_validate_count = fields.Integer('A valider', compute='_compute_kpis')
    in_progress_count = fields.Integer('En cours', compute='_compute_kpis')
    done_count = fields.Integer('Terminees', compute='_compute_kpis')
    cancel_count = fields.Integer('Annulees', compute='_compute_kpis')
    overdue_count = fields.Integer('En retard', compute='_compute_kpis')

    # === Repartition par type ===
    preventive_count = fields.Integer('Preventives', compute='_compute_kpis')
    corrective_count = fields.Integer('Correctives', compute='_compute_kpis')
    pct_preventive = fields.Float('% Preventives', compute='_compute_kpis', digits=(5, 1))

    # === Performance globale ===
    avg_mttr = fields.Float('MTTR moyen (h)', compute='_compute_kpis', digits=(8, 2))
    avg_mtbf = fields.Float('MTBF moyen (h)', compute='_compute_kpis', digits=(8, 2))
    avg_availability = fields.Float('Disponibilite (%)', compute='_compute_kpis', digits=(5, 1))
    avg_duration = fields.Float('Duree moy. (h)', compute='_compute_kpis', digits=(8, 2))

    # === Couts ===
    total_cost_month = fields.Float('Cout mois en cours (EUR)', compute='_compute_kpis', digits=(12, 2))
    total_cost_year = fields.Float('Cout annee (EUR)', compute='_compute_kpis', digits=(12, 2))
    total_parts_cost = fields.Float('Cout pieces (EUR)', compute='_compute_kpis', digits=(12, 2))
    total_labor_cost = fields.Float('Cout main d\'oeuvre (EUR)', compute='_compute_kpis', digits=(12, 2))

    # === Ressources ===
    sites_count = fields.Integer('Sites', compute='_compute_kpis')
    equipment_count = fields.Integer('Equipements', compute='_compute_kpis')
    equipment_in_repair = fields.Integer('Equipements en reparation', compute='_compute_kpis')
    teams_count = fields.Integer('Equipes', compute='_compute_kpis')
    contracts_active = fields.Integer('Contrats actifs', compute='_compute_kpis')

    # === Top 5 equipements les plus defaillants ===
    top_equipment_html = fields.Html('Top equipements defaillants', compute='_compute_kpis', sanitize=False)
    recent_activity_html = fields.Html('Activite recente', compute='_compute_kpis', sanitize=False)

    @api.depends_context('uid')
    def _compute_kpis(self):
        """Lit en live les KPIs depuis les modeles de production.

        Toutes les KPIs sont recalculees a chaque ouverture (TransientModel).
        Performance OK car les requetes sont indexees (state, schedule_date,
        is_overdue stored, equipment_id).
        """
        Request = self.env['gmao.request']
        Equipment = self.env['gmao.equipment']
        Site = self.env['maintenance.site']
        Team = self.env['gmao.team']
        Contract = self.env['maintenance.contract']
        today = fields.Date.today()
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)

        for record in self:
            # Counts par etat
            record.total_requests = Request.search_count([])
            record.new_count = Request.search_count([('state', '=', 'new')])
            record.to_validate_count = Request.search_count([('state', '=', 'to_validate')])
            record.in_progress_count = Request.search_count([('state', '=', 'in_progress')])
            record.done_count = Request.search_count([('state', '=', 'done')])
            record.cancel_count = Request.search_count([('state', '=', 'cancel')])
            record.overdue_count = Request.search_count([('is_overdue', '=', True)])

            # Type
            record.preventive_count = Request.search_count([('maintenance_type', '=', 'preventive')])
            record.corrective_count = Request.search_count([('maintenance_type', '=', 'corrective')])
            total = record.preventive_count + record.corrective_count
            record.pct_preventive = (record.preventive_count / total * 100) if total else 0.0

            # Performance (sur done seulement)
            done_requests = Request.search([('state', '=', 'done')])
            if done_requests:
                durations = done_requests.mapped('duration')
                mttrs = [r.mttr for r in done_requests if r.mttr]
                mtbfs = [r.mtbf for r in done_requests if r.mtbf]
                record.avg_duration = sum(durations) / len(durations) if durations else 0.0
                record.avg_mttr = sum(mttrs) / len(mttrs) if mttrs else 0.0
                record.avg_mtbf = sum(mtbfs) / len(mtbfs) if mtbfs else 0.0
                # Disponibilite (Availability) = MTBF / (MTBF + MTTR) x 100
                if record.avg_mtbf + record.avg_mttr > 0:
                    record.avg_availability = (
                        record.avg_mtbf / (record.avg_mtbf + record.avg_mttr) * 100
                    )
                else:
                    record.avg_availability = 0.0
            else:
                record.avg_duration = record.avg_mttr = record.avg_mtbf = record.avg_availability = 0.0

            # Couts
            month_requests = Request.search([('request_date', '>=', month_start)])
            year_requests = Request.search([('request_date', '>=', year_start)])
            record.total_cost_month = sum(month_requests.mapped('total_cost'))
            record.total_cost_year = sum(year_requests.mapped('total_cost'))
            record.total_parts_cost = sum(year_requests.mapped('total_parts_cost'))
            record.total_labor_cost = sum(year_requests.mapped('labor_cost'))

            # Ressources
            record.sites_count = Site.search_count([])
            record.equipment_count = Equipment.search_count([])
            record.equipment_in_repair = Equipment.search_count([('state', '=', 'in_repair')])
            record.teams_count = Team.search_count([])
            record.contracts_active = Contract.search_count([('state', '=', 'active')])

            # === HTML : Top 5 equipements les plus defaillants ===
            data = Request.read_group(
                [('state', 'in', ('done', 'in_progress'))],
                ['equipment_id', 'total_cost:sum', 'duration:sum'],
                ['equipment_id'],
            )
            top5 = sorted(data, key=lambda d: -(d.get('total_cost') or 0))[:5]
            rows = ['<tr><th>Equipement</th><th class="text-right">Interventions</th>'
                    '<th class="text-right">Cout total</th><th class="text-right">Heures</th></tr>']
            for item in top5:
                eq = item.get('equipment_id')
                if not eq:
                    continue
                eq_name = eq[1] if isinstance(eq, (list, tuple)) else str(eq)
                count = item.get('equipment_id_count', 0)
                cost = item.get('total_cost', 0.0) or 0.0
                duration = item.get('duration', 0.0) or 0.0
                rows.append(
                    f'<tr><td>{eq_name}</td><td class="text-right">{count}</td>'
                    f'<td class="text-right">{cost:,.2f} EUR</td>'
                    f'<td class="text-right">{duration:,.1f} h</td></tr>'
                )
            if len(rows) > 1:
                record.top_equipment_html = (
                    '<table class="table table-sm table-striped">' + ''.join(rows) + '</table>'
                )
            else:
                record.top_equipment_html = '<p class="text-muted">Aucune intervention enregistree.</p>'

            # === HTML : Activite recente (5 dernieres demandes) ===
            recent = Request.search([], order='request_date desc', limit=5)
            if recent:
                state_dict = dict(Request._fields['state'].selection)
                rows = ['<tr><th>Date</th><th>Reference</th><th>Equipement</th><th>Etat</th></tr>']
                for r in recent:
                    state_label = state_dict.get(r.state, r.state)
                    date_str = fields.Datetime.context_timestamp(r, r.request_date).strftime('%d/%m %H:%M') if r.request_date else '-'
                    rows.append(
                        f'<tr><td>{date_str}</td><td>{r.name}</td>'
                        f'<td>{r.equipment_id.display_name or "-"}</td>'
                        f'<td><span class="badge badge-info">{state_label}</span></td></tr>'
                    )
                record.recent_activity_html = (
                    '<table class="table table-sm">' + ''.join(rows) + '</table>'
                )
            else:
                record.recent_activity_html = '<p class="text-muted">Aucune demande recente.</p>'

    # === Actions raccourcies vers les vues filtrees ===
    def action_view_overdue(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Demandes en retard',
            'res_model': 'gmao.request',
            'view_mode': 'kanban,tree,form',
            'domain': [('is_overdue', '=', True)],
            'target': 'current',
        }

    def action_view_open(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Demandes ouvertes',
            'res_model': 'gmao.request',
            'view_mode': 'kanban,tree,form',
            'domain': [('state', 'in', ('new', 'to_validate', 'in_progress', 'repaired'))],
            'target': 'current',
        }

    def action_view_done(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Demandes terminees',
            'res_model': 'gmao.request',
            'view_mode': 'kanban,tree,form',
            'domain': [('state', '=', 'done')],
            'target': 'current',
        }

    def action_view_equipment_in_repair(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Equipements en reparation',
            'res_model': 'gmao.equipment',
            'view_mode': 'kanban,tree,form',
            'domain': [('state', '=', 'in_repair')],
            'target': 'current',
        }

    # ==================================================================
    # API JSON pour le DASHBOARD PRO (client action JS + Chart.js).
    # Consomme par static/src/js/gmao_dashboard.js via RPC.
    # ==================================================================
    @api.model
    def get_dashboard_data(self, date_from=None, date_to=None, site_id=None, company_ids=None):
        """Agrege toutes les donnees du dashboard, filtrables.

        :param date_from/date_to: bornes str 'YYYY-MM-DD' sur request_date (optionnel)
        :param site_id: filtre site (int, optionnel)
        :param company_ids: liste d'ids societe (optionnel ; sinon societes autorisees)
        :return: dict JSON-serialisable {kpis, charts, recent, sites, companies}
        """
        Request = self.env['gmao.request']
        Equipment = self.env['gmao.equipment']
        Site = self.env['maintenance.site']
        Team = self.env['gmao.team']
        Contract = self.env['maintenance.contract']

        # Filtre societe : sous-ensemble explicite, sinon toutes les societes autorisees.
        comp_domain = []
        if company_ids:
            company_ids = [int(c) for c in company_ids]
            comp_domain = [('company_id', 'in', company_ids)]

        domain = list(comp_domain)
        if date_from:
            domain.append(('request_date', '>=', date_from))
        if date_to:
            domain.append(('request_date', '<=', date_to + ' 23:59:59'))
        if site_id:
            domain.append(('site_id', '=', int(site_id)))

        all_requests = Request.search(domain)
        done = all_requests.filtered(lambda r: r.state == 'done')
        preventive = all_requests.filtered(lambda r: r.maintenance_type == 'preventive')
        corrective = all_requests.filtered(lambda r: r.maintenance_type == 'corrective')

        total = len(all_requests)
        overdue = len(all_requests.filtered(lambda r: r.is_overdue))
        open_count = len(all_requests.filtered(
            lambda r: r.state in ('new', 'to_validate', 'in_progress', 'repaired')))
        mttrs = [r.mttr for r in done if r.mttr]
        mtbfs = [r.mtbf for r in done if r.mtbf]
        avg_mttr = round(sum(mttrs) / len(mttrs), 1) if mttrs else 0.0
        avg_mtbf = round(sum(mtbfs) / len(mtbfs), 1) if mtbfs else 0.0
        availability = round(avg_mtbf / (avg_mtbf + avg_mttr) * 100, 1) if (avg_mtbf + avg_mttr) else 0.0
        total_cost = round(sum(all_requests.mapped('total_cost')), 2)

        state_labels = dict(Request._fields['state'].selection)

        # Graphe : repartition par etat (donut)
        by_state = {}
        for r in all_requests:
            by_state[r.state] = by_state.get(r.state, 0) + 1
        state_chart = {
            'labels': [state_labels.get(k, k) for k in by_state.keys()],
            'data': list(by_state.values()),
        }

        # Graphe : evolution mensuelle (ligne)
        month_grp = Request.read_group(
            domain + [('request_date', '!=', False)],
            ['request_date'], ['request_date:month'], lazy=False)
        month_chart = {
            'labels': [g.get('request_date:month') or 'N/A' for g in month_grp],
            'data': [g.get('__count', 0) for g in month_grp],
        }

        # Graphe : preventif vs correctif (barres)
        type_chart = {
            'labels': ['Preventif', 'Correctif'],
            'data': [len(preventive), len(corrective)],
        }

        # Graphe : top 5 equipements par cout (barres horizontales)
        eq_grp = Request.read_group(
            domain, ['equipment_id', 'total_cost:sum'], ['equipment_id'], lazy=False)
        eq_grp = sorted(eq_grp, key=lambda g: -(g.get('total_cost') or 0))[:5]
        equipment_chart = {
            'labels': [g['equipment_id'][1] if g.get('equipment_id') else 'N/A' for g in eq_grp],
            'data': [round(g.get('total_cost') or 0, 2) for g in eq_grp],
        }

        # Graphe : cout par site (barres)
        site_grp = Request.read_group(
            domain, ['site_id', 'total_cost:sum'], ['site_id'], lazy=False)
        site_grp = sorted(site_grp, key=lambda g: -(g.get('total_cost') or 0))
        site_chart = {
            'labels': [g['site_id'][1] if g.get('site_id') else 'Sans site' for g in site_grp],
            'data': [round(g.get('total_cost') or 0, 2) for g in site_grp],
        }

        # Graphe : top pannes recurrentes (code panne x frequence) — P6.
        # Met en evidence les pannes repetitives pour cibler le preventif.
        fail_grp = Request.read_group(
            domain + [('failure_code_id', '!=', False)],
            ['failure_code_id', 'total_cost:sum'], ['failure_code_id'], lazy=False)
        fail_grp = sorted(fail_grp, key=lambda g: -(g.get('__count') or 0))[:8]
        failure_chart = {
            'labels': [g['failure_code_id'][1] if g.get('failure_code_id') else 'N/A' for g in fail_grp],
            'data': [g.get('__count', 0) for g in fail_grp],
        }
        # KPI : pannes recurrentes = codes panne correctifs apparaissant >= 2 fois.
        corr_fail_grp = Request.read_group(
            domain + [('failure_code_id', '!=', False), ('maintenance_type', '=', 'corrective')],
            ['failure_code_id'], ['failure_code_id'], lazy=False)
        recurring_failures = sum(1 for g in corr_fail_grp if (g.get('__count') or 0) >= 2)

        # Graphe : repartition par mode de defaillance (donut) — categorise les pannes.
        mode_labels = dict(self.env['gmao.failure.code']._fields['failure_mode'].selection)
        mode_grp = Request.read_group(
            domain + [('failure_mode', '!=', False)],
            ['failure_mode'], ['failure_mode'], lazy=False)
        mode_chart = {
            'labels': [mode_labels.get(g.get('failure_mode'), g.get('failure_mode') or 'N/A') for g in mode_grp],
            'data': [g.get('__count', 0) for g in mode_grp],
        }
        # Graphe : severite des pannes (donut) — qualifie la gravite.
        sev_labels = dict(Request._fields['failure_severity'].selection)
        sev_grp = Request.read_group(
            domain + [('failure_severity', '!=', False)],
            ['failure_severity'], ['failure_severity'], lazy=False)
        sev_chart = {
            'labels': [sev_labels.get(g.get('failure_severity'), g.get('failure_severity') or 'N/A') for g in sev_grp],
            'data': [g.get('__count', 0) for g in sev_grp],
        }

        # Activite recente (6 dernieres)
        recent = Request.search(domain, order='request_date desc', limit=6)
        recent_list = [{
            'id': r.id,
            'name': r.name,
            'equipment': r.equipment_id.display_name or '-',
            'state': state_labels.get(r.state, r.state),
            'state_raw': r.state,
            'date': fields.Datetime.context_timestamp(r, r.request_date).strftime('%d/%m %H:%M') if r.request_date else '',
            'is_overdue': r.is_overdue,
        } for r in recent]

        return {
            'kpis': {
                'total': total,
                'open': open_count,
                'overdue': overdue,
                'done': len(done),
                'preventive': len(preventive),
                'corrective': len(corrective),
                'pct_preventive': round(len(preventive) / total * 100, 1) if total else 0,
                'avg_mttr': avg_mttr,
                'avg_mtbf': avg_mtbf,
                'availability': availability,
                'total_cost': total_cost,
                'equipment_count': Equipment.search_count(comp_domain),
                'equipment_in_repair': Equipment.search_count(comp_domain + [('state', '=', 'in_repair')]),
                'sites_count': Site.search_count(comp_domain),
                'teams_count': Team.search_count(comp_domain),
                'contracts_active': Contract.search_count(comp_domain + [('state', '=', 'active')]),
                'recurring_failures': recurring_failures,
                'currency': self.env.user.company_id.currency_id.symbol or 'EUR',
            },
            'charts': {
                'by_state': state_chart,
                'by_month': month_chart,
                'by_type': type_chart,
                'top_equipment': equipment_chart,
                'by_site': site_chart,
                'by_failure': failure_chart,
                'by_failure_mode': mode_chart,
                'by_severity': sev_chart,
            },
            'recent': recent_list,
            'sites': [{'id': s.id, 'name': s.name} for s in Site.search(comp_domain, order='name')],
            'companies': [{'id': c.id, 'name': c.name} for c in self.env.companies],
        }
