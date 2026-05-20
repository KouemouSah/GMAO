import base64
import time
import datetime
from io import BytesIO
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from dateutil.relativedelta import relativedelta
from datetime import timedelta
import json
import logging
# NOTE: matplotlib and numpy are imported lazily inside chart-generating methods
# to avoid hard dependency at module load time (Odoo CE base does not require them).

_logger = logging.getLogger(__name__)

class MaintenanceTeam(models.Model):
    _name = 'gmao.team'
    _description = 'Équipe de Maintenance'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # Champs de base
    name = fields.Char(string='Nom de l\'équipe', required=True, tracking=True, index=True)
    active = fields.Boolean(default=True, tracking=True, index=True)
    color = fields.Integer(string='Couleur')
    leader_id = fields.Many2one('hr.employee', string='Chef d\'équipe', required=True, tracking=True, index=True)
    member_ids = fields.Many2many('hr.employee', string='Membres de l\'équipe', required=True, index=True)

    request_ids = fields.One2many('gmao.request', 'team_id', string='Demandes d\'intervention')

    notes = fields.Text(string='Notes')

    # Ajout des nouveaux champs pour l'optimisation
    last_metrics_update = fields.Datetime('Dernière mise à jour métriques', readonly=True)
    metrics_data = fields.Text('Données métriques', readonly=True)

    # Champs calculés
    total_members = fields.Integer(string='Nombre total de membres', compute='_compute_total_members', store=True)
    open_requests_count = fields.Integer(string='Demandes ouvertes', compute='_compute_open_requests_count')
    success_rate = fields.Float(string='Taux de réussite (%)', compute='_compute_success_rate', store=True)
    workload = fields.Integer(string='Charge de travail', compute='_compute_workload', store=True)
    occupation_rate = fields.Float(string='Taux d\'occupation (%)', compute='_compute_occupation_rate', store=True)

    # Calcul des métriques
    mean_response_time = fields.Float(string='Temps Moyen de Réponse', compute='_compute_mean_response_time', store=True)

    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('validated', 'Validé'),
    ], string='État', default='draft', tracking=True, index=True)

    company_id = fields.Many2one('res.company', string='Société', default=lambda self: self.env.company)

    # P2 : couverture & competences (attribution auto par scoring)
    site_ids = fields.Many2many(
        'maintenance.site', 'gmao_team_site_rel', 'team_id', 'site_id',
        string='Sites couverts',
        help="Sites pris en charge par l'équipe (critère de proximité du scoring).")
    category_ids = fields.Many2many(
        'gmao.equipment.category', 'gmao_team_category_rel', 'team_id', 'category_id',
        string='Spécialités',
        help="Catégories d'équipement maîtrisées (critère de compétence du scoring).")

    date_start = fields.Date(string='Date de début', default=fields.Date.context_today)
    date_end = fields.Date(string='Date de fin', default=fields.Date.context_today)

    @api.depends('member_ids')
    def _compute_total_members(self):
        """Calcule le nombre total de membres dans l'équipe."""
        for team in self:
            team.total_members = len(team.member_ids)

    @api.depends('request_ids.state')
    def _compute_open_requests_count(self):
        """Calcule le nombre de demandes d'intervention ouvertes pour l'équipe."""
        for team in self:
            team.open_requests_count = self.env['gmao.request'].search_count([
                ('team_id', '=', team.id),
                ('state', 'not in', ['done', 'cancel'])
            ])

    # ------------------------------------------------ Nouvelles méthodes d'optimisation récupération des métriques ---------------------------

    @api.depends('request_ids.state', 'date_start', 'date_end')
    def _compute_metrics(self):
        """Méthode centralisée pour le calcul de toutes les métriques.
        Utilise le système de cache optimisé pour éviter les calculs redondants.

        Cette méthode est déclenchée automatiquement lors des changements dans :
        - Les états des demandes (request_ids.state)
        - Les dates de début et fin (date_start, date_end)"""

        # Récupération des métriques via le système optimisé
        for team in self:
            try:
                # Mise à jour des champs calculés
                metrics = team.get_team_metrics(team.date_start, team.date_end)
                team.success_rate = metrics.get('success_rate', 0)
                team.workload = metrics.get('workload', 0)
                team.occupation_rate = metrics.get('occupation_rate', 0)
                team.mean_response_time = metrics.get('mean_response_time', 0)

            except Exception as e:
                _logger.error(f"Erreur lors du calcul des métriques pour l'équipe {team.name}: {str(e)}")
                # Valeurs par défaut en cas d'erreur
                team.success_rate = 0
                team.workload = 0
                team.occupation_rate = 0
                team.mean_response_time = 0

    # ---------------------------------------------------------------------------------------------
    def _get_all_metrics(self, start_date, end_date):
        """
        Calcule toutes les métriques en une seule requête pour optimiser les performances.

        Args:
            start_date (date): Date de début de la période
            end_date (date): Date de fin de la période

        Returns:
            dict: Dictionnaire contenant toutes les métriques calculées
        """

        self.ensure_one()
        domain = [
            ('team_id', '=', self.id),
            ('create_date', '>=', start_date),
            ('create_date', '<=', end_date)
        ]

        requests = self.env['gmao.request'].search(domain).prefetch_related(
            'state',
            'maintenance_type',
            'schedule_date',
            'close_date'
        )

        # Calcul de toutes les métriques en une fois
        try:
            metrics = {
                'total_requests': len(requests),
                'open_requests': len(requests.filtered(lambda r: r.state not in ['done', 'cancel'])),
                'success_rate': self._calculate_success_rate_from_data(requests),
                'workload': self._calculate_workload_from_data(requests),
                'occupation_rate': self._calculate_occupation_rate_from_data(requests),
                'mean_response_time': self._calculate_mean_response_time_from_data(requests),
                'mttr': self._calculate_mttr_from_data(requests),
                'mtbf': self._calculate_mtbf_from_data(requests)
            }
            return metrics
        except Exception as e:
            _logger.error(f"Erreur lors du calcul des métriques détaillées: {str(e)}")
            return {}

    # -----------------------------------------------------------

    def _calculate_success_rate_from_data(self, requests):
        """
        Calcule le taux de réussite à partir des données déjà chargées.

        Args:
            requests (recordset): Ensemble des demandes d'intervention

        Returns:
            float: Pourcentage de réussite (0-100)
        """
        try:
            total_requests = len(requests)
            if not total_requests:
                return 0
            successful_requests = len(requests.filtered(lambda r: r.state == 'done'))
            return (successful_requests / total_requests * 100) if total_requests else 0
        except Exception as e:
            _logger.error(f"Erreur calcul taux de réussite: {str(e)}")
            return 0

    # --------------------------------------

    def _calculate_workload_from_data(self, requests):
        """
        Calcule la charge de travail à partir des données déjà chargées.

        Args:
            requests (recordset): Ensemble des demandes d'intervention

        Returns:
            int: Nombre de demandes actives
        """
        try:
            return len(requests.filtered(lambda r: r.state in ['new', 'in_progress']))
        except Exception as e:
            _logger.error(f"Erreur calcul charge de travail: {str(e)}")
            return 0

    # -------------------------------------------------------------------------------------

    def _calculate_occupation_rate_from_data(self, requests):
        """
        Calcule le taux d'occupation à partir des données déjà chargées.

        Args:
            requests (recordset): Ensemble des demandes d'intervention

        Returns:
            float: Pourcentage d'occupation (0-100)
        """
        try:
            total_capacity = len(self.member_ids) * 8 * 5  # 8h/jour, 5 jours/semaine
            if not total_capacity:
                return 0

            active_requests = requests.filtered(lambda r: r.state == 'in_progress')
            total_hours = sum(request.duration for request in active_requests if request.duration)

            return (total_hours / total_capacity * 100) if total_capacity else 0
        except Exception as e:
            _logger.error(f"Erreur calcul taux d'occupation: {str(e)}")
            return 0

    # ------------------------------------------------------------------------------------------

    def _calculate_mean_response_time_from_data(self, requests):
        """
        Calcule le temps moyen de réponse à partir des données déjà chargées.

        Args:
            requests (recordset): Ensemble des demandes d'intervention

        Returns:
            float: Temps moyen en heures
        """
        try:
            response_times = []
            for request in requests:
                if request.request_date and request.schedule_date:
                    response_time = (request.schedule_date - request.request_date).total_seconds() / 3600
                    response_times.append(response_time)

            return sum(response_times) / len(response_times) if response_times else 0
        except Exception as e:
            _logger.error(f"Erreur calcul temps moyen de réponse: {str(e)}")
            return 0

    # ----------------------------------------------------------------------------------------------------

    def _calculate_mttr_from_data(self, requests):
        """
        Calcule le MTTR (Mean Time To Repair) à partir des données déjà chargées.

        Args:
            requests (recordset): Ensemble des demandes d'intervention

        Returns:
            float: MTTR en heures
        """
        try:
            repair_times = []
            for request in requests.filtered(lambda r: r.state == 'done'):
                if request.start_date and request.close_date:
                    repair_time = (request.close_date - request.start_date).total_seconds() / 3600
                    repair_times.append(repair_time)

            return sum(repair_times) / len(repair_times) if repair_times else 0
        except Exception as e:
            _logger.error(f"Erreur calcul MTTR: {str(e)}")
            return 0

    # -----------------------------------------------------------------------------------------------------------

    def _calculate_mtbf_from_data(self, requests):
        """
        Calcule le MTBF (Mean Time Between Failures) à partir des données déjà chargées.

        Args:
            requests (recordset): Ensemble des demandes d'intervention

        Returns:
            float: MTBF en heures
        """
        try:
            sorted_requests = requests.sorted(key=lambda r: r.request_date)
            if len(sorted_requests) < 2:
                return 0

            time_between_failures = []
            for i in range(len(sorted_requests) - 1):
                current = sorted_requests[i]
                next_req = sorted_requests[i + 1]
                if current.close_date and next_req.request_date:
                    time_diff = (next_req.request_date - current.close_date).total_seconds() / 3600
                    time_between_failures.append(time_diff)

            return sum(time_between_failures) / len(time_between_failures) if time_between_failures else 0
        except Exception as e:
            _logger.error(f"Erreur calcul MTBF: {str(e)}")
            return 0

    # ----------------------------------------------------------------------------------------------------------

    def get_team_metrics(self, start_date, end_date, force_update=False):
        """
        Récupère ou calcule les métriques de l'équipe avec système de mise en cache.

        Args:
            start_date (date): Date de début de la période
            end_date (date): Date de fin de la période
            force_update (bool): Force le recalcul même si les données sont récentes

        Returns:
            dict: Toutes les métriques calculées
        """
        self.ensure_one()

        if not force_update and self.last_metrics_update:
            # Vérifie si une mise à jour est nécessaire (seuil de 5 minutes)
            threshold = fields.Datetime.now() - timedelta(minutes=5)
            if self.last_metrics_update > threshold:
                try:
                    return json.loads(self.metrics_data or '{}')
                except Exception as e:
                    _logger.error(f"Erreur décodage métriques en cache: {str(e)}")

        # Calcul des nouvelles métriques
        metrics = self._get_all_metrics(start_date, end_date)

        # Mise à jour du cache
        self.write({
            'metrics_data': json.dumps(metrics),
            'last_metrics_update': fields.Datetime.now()
        })

        return metrics

    # ----------------------------------------------------------------------------------------------------------------

    # ==================================================================
    # P2 : attribution automatique d'equipe par scoring multi-criteres.
    # ==================================================================
    @api.model
    def _score_weights(self):
        """Poids du scoring, parametrables via ir.config_parameter."""
        ICP = self.env['ir.config_parameter'].sudo()

        def _w(key, default):
            try:
                return float(ICP.get_param(key, default))
            except (TypeError, ValueError):
                return float(default)
        return {
            'load': _w('gmao.team_score_weight_load', 30),
            'perf': _w('gmao.team_score_weight_perf', 25),
            'response': _w('gmao.team_score_weight_response', 15),
            'proximity': _w('gmao.team_score_weight_proximity', 15),
            'competence': _w('gmao.team_score_weight_competence', 15),
        }

    def _score_components(self, request):
        """Scores 0-100 par critere de cette equipe pour une demande."""
        self.ensure_one()
        load = max(0.0, min(100.0, 100.0 - (self.occupation_rate or 0.0)))
        perf = max(0.0, min(100.0, self.success_rate or 0.0))
        response = 100.0 / (1.0 + max(0.0, self.mean_response_time or 0.0))
        # Proximite : site de l'equipement couvert par l'equipe.
        if not self.site_ids:
            proximity = 50.0  # equipe non configuree : neutre, non penalisee
        elif request.site_id and request.site_id in self.site_ids:
            proximity = 100.0
        else:
            proximity = 0.0
        # Competence : categorie de l'equipement maitrisee par l'equipe.
        cat = request.equipment_id.category_id
        if not self.category_ids:
            competence = 50.0
        elif cat and cat in self.category_ids:
            competence = 100.0
        else:
            competence = 0.0
        return {'load': load, 'perf': perf, 'response': response,
                'proximity': proximity, 'competence': competence}

    def _score_for_request(self, request, weights=None):
        """Score pondere global 0-100 de l'equipe pour la demande.

        `weights` peut etre fourni pour eviter de relire les ir.config_parameter
        a chaque equipe (optimisation appelee par _find_best_team)."""
        self.ensure_one()
        comps = self._score_components(request)
        if weights is None:
            weights = self._score_weights()
        total_w = sum(weights.values())
        if not total_w:
            return 0.0
        return sum(comps[k] * weights[k] for k in weights) / total_w

    @api.model
    def _find_best_team(self, request):
        """Meilleure equipe pour une demande : filtre dur (active, validee,
        meme societe) puis scoring. Retourne un recordset (1) ou vide.
        Aucune exclusion par charge : une equipe surchargee reste eligible
        si c'est la seule du perimetre."""
        candidates = self.search([
            ('active', '=', True),
            ('state', '=', 'validated'),
            ('company_id', '=', request.company_id.id),
        ])
        if not candidates:
            return self.browse()
        # Poids lus UNE seule fois (pas N x 5 lectures config_parameter).
        weights = self._score_weights()
        scored = sorted(
            candidates, key=lambda t: (-t._score_for_request(request, weights), t.id))
        return scored[0]

    @api.constrains('member_ids', 'request_ids')
    def _check_member_availability(self):
        """Vérifie la disponibilité des membres de l'équipe."""
        for team in self:
            for member in team.member_ids:
                conflicting_requests = self.env['gmao.request'].search([
                    ('technician_id', '=', member.id),
                    ('state', 'in', ['new', 'in_progress']),
                    ('team_id', '!=', team.id)
                ])
                if conflicting_requests:
                    raise UserError(_("Le membre %s est déjà assigné à une autre tâche dans une équipe différente.") % member.name)

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        """Vérifie que la date de fin est postérieure à la date de début."""
        for team in self:
            if team.date_start and team.date_end and team.date_start > team.date_end:
                raise ValidationError(_("La date de fin doit être postérieure à la date de début."))

    def action_validate_team(self):
        """Valide l'équipe si toutes les conditions sont remplies."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("L'équipe doit être à l'état brouillon pour être validée."))
        if not self.member_ids:
            raise UserError(_("Vous ne pouvez pas valider une équipe sans membres."))
        if not self.leader_id:
            raise UserError(_("Vous devez désigner un chef d'équipe avant de valider l'équipe."))
        self.state = 'validated'
        self._send_team_composition_notification()

    def _send_team_composition_notification(self):
        """Envoie une notification de la composition de l'équipe."""
        self.ensure_one()
        template = self.env.ref('gmao_suite.email_template_team_composition', raise_if_not_found=False)
        if not template:
            _logger.warning(_("Le template d'email pour la composition d'équipe n'a pas été trouvé."))
            return

        team_admin_group = self.env.ref('gmao_suite.group_maintenance_team_admin')
        team_user_group = self.env.ref('gmao_suite.group_maintenance_team_user')
        recipients = team_admin_group.users | team_user_group.users | self.create_uid | self.leader_id.user_id
        recipient_partners = recipients.mapped('partner_id')

        try:
            template.send_mail(self.id, force_send=True, email_values={'recipient_ids': [(6, 0, recipient_partners.ids)]})
        except Exception as e:
            _logger.error(_("Erreur lors de l'envoi de l'e-mail de composition d'équipe : %s"), str(e))

        members_without_email = self.member_ids.filtered(lambda m: not m.work_email)
        if members_without_email:
            message = _("Les membres suivants n'ont pas d'adresse e-mail : %s") % ', '.join(members_without_email.mapped('name'))
            self.message_post(body=message, message_type='comment', subtype='mail.mt_note')

    def action_mark_as_done(self):
        self.ensure_one()
        for request in self.request_ids.filtered(lambda r: r.state != 'done'):
            request.write({'state': 'done'})
        self._send_team_release_notification()

    def _send_team_release_notification(self):
        self.ensure_one()
        template = self.env.ref('gmao_suite.email_template_team_release', raise_if_not_found=False)
        if not template:
            _logger.warning(_("Le template d'email pour la libération d'équipe n'a pas été trouvé."))
            return

        team_admin_group = self.env.ref('gmao_suite.group_maintenance_team_admin')
        team_user_group = self.env.ref('gmao_suite.group_maintenance_team_user')
        recipients = team_admin_group.users | team_user_group.users | self.create_uid | self.leader_id.user_id
        recipient_partners = recipients.mapped('partner_id')

        try:
            template.send_mail(self.id, force_send=True, email_values={'recipient_ids': [(6, 0, recipient_partners.ids)]})
        except Exception as e:
            _logger.error(_("Erreur lors de l'envoi de l'e-mail de libération d'équipe : %s"), str(e))

    @api.model
    def _cron_check_team_availability(self):
        teams = self.search([('state', '=', 'validated')])
        for team in teams:
            if all(request.state == 'done' for request in team.request_ids):
                team.action_mark_as_done()

    @api.model
    def _cron_update_occupation_rate(self):
        teams = self.search([])
        for team in teams:
            try:
                team._compute_occupation_rate()
            except Exception as e:
                team.message_post(body=_("Erreur lors de la mise à jour du taux d'occupation : %s") % str(e))

    def name_get(self):
        result = []
        for team in self:
            name = _("%s (%s membres)") % (team.name, team.total_members)
            result.append((team.id, name))
        return result

    @api.model
    def create(self, vals):
        try:
            team = super(MaintenanceTeam, self).create(vals)
            team.message_subscribe(partner_ids=team.member_ids.mapped('user_id.partner_id').ids)
            return team
        except Exception as e:
            raise UserError(_("Erreur lors de la création de l'équipe : %s") % str(e))

    def write(self, vals):
        try:
            res = super(MaintenanceTeam, self).write(vals)
            if 'member_ids' in vals:
                self.message_subscribe(partner_ids=self.member_ids.mapped('user_id.partner_id').ids)
            return res
        except Exception as e:
            raise UserError(_("Erreur lors de la modification de l'équipe : %s") % str(e))

    def _unlink_except_open_requests(self):
        for team in self:
            if team.request_ids.filtered(lambda r: r.state not in ['done', 'cancel']):
                raise UserError(_("Vous ne pouvez pas supprimer l'équipe %s car elle a des demandes d'intervention en cours.") % team.name)
        return super(MaintenanceTeam, self).unlink()

    def toggle_active(self):
        for team in self:
            if team.active and team.request_ids.filtered(lambda r: r.state not in ['done', 'cancel']):
                raise UserError(_("Vous ne pouvez pas archiver l'équipe %s car elle a des demandes d'intervention en cours.") % team.name)
        return super(MaintenanceTeam, self).toggle_active()

    def action_view_team_requests(self):
        """Smart button : demandes d'intervention de l'equipe."""
        self.ensure_one()
        return {
            'name': _("Demandes de l'équipe"),
            'type': 'ir.actions.act_window',
            'res_model': 'gmao.request',
            'view_mode': 'tree,form,kanban',
            'domain': [('team_id', '=', self.id)],
            'context': {'default_team_id': self.id},
        }

    def action_view_last_month(self):
        end_date = fields.Date.context_today(self)
        start_date = end_date - relativedelta(months=1)
        self.write({'date_start': start_date, 'date_end': end_date})
        return self.action_view_maintenance_team()

    def action_view_last_year(self):
        end_date = fields.Date.context_today(self)
        start_date = end_date - relativedelta(years=1)
        self.write({'date_start': start_date, 'date_end': end_date})
        return self.action_view_maintenance_team()

    def action_view_maintenance_team(self):
        return {
            'name': _('Équipes de Maintenance'),
            'view_mode': 'graph,pivot',
            'res_model': 'gmao.team',
            'type': 'ir.actions.act_window',
            'target': 'current',
            'domain': [('id', 'in', self.ids)],
        }

    # ----------------------------------- Génération des graphiques -----------------------------------------

    @staticmethod
    def _lazy_matplotlib():
        """Lazy import of matplotlib/numpy to avoid hard dep at module load."""
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
        return plt, np

    def generate_performance_chart(self, start_date, end_date):
        """
        Génère le graphique principal de performance.

        Args:
            start_date (date): Date début de la période
            end_date (date): Date fin de la période

        Returns:
            str: Image encodée en base64
        """
        try:
            plt, _np = self._lazy_matplotlib()
            # Récupération des métriques optimisées
            metrics = self.get_team_metrics(start_date, end_date)

            plt.figure(figsize=(10, 6))
            labels = ['Taux de réussite', 'Charge de travail', 'Taux d\'occupation']
            values = [
                metrics.get('success_rate', 0),
                metrics.get('workload', 0),
                metrics.get('occupation_rate', 0)
            ]
            colors = ['#4BC0C0', '#FF6384', '#36A2EB']

            plt.bar(labels, values, color=colors)
            plt.title('Performance de l\'équipe')
            plt.ylim(0, 100)
            plt.ylabel('Pourcentage / Valeur')
            plt.grid(True, linestyle='--', alpha=0.7)

            # Ajout des valeurs sur les barres
            for i, v in enumerate(values):
                plt.text(i, v + 1, f'{v:.1f}', ha='center')

            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
            plt.close()
            buffer.seek(0)
            return base64.b64encode(buffer.getvalue()).decode()
        except Exception as e:
            _logger.error(f"Erreur génération graphique performance: {str(e)}")
            return None

    # ----------------------------------------- Graphique de l'évolution du Taux de Réussite sur la période --------------------------

    def generate_success_rate_chart(self, start_date, end_date):
        """
        Génère le graphique d'évolution du taux de réussite.

        Args:
            start_date (date): Date début période
            end_date (date): Date fin période

        Returns:
            str: Image encodée en base64
        """
        try:
            plt, _np = self._lazy_matplotlib()
            # Calcul des points mensuels
            current = start_date
            dates = []
            rates = []

            while current <= end_date:
                next_date = min(
                    current + relativedelta(months=1),
                    end_date
                )
                metrics = self.get_team_metrics(current, next_date)
                dates.append(current.strftime('%b %Y'))
                rates.append(metrics.get('success_rate', 0))
                current = next_date

            plt.figure(figsize=(12, 6))
            plt.plot(dates, rates, marker='o', linestyle='-', linewidth=2)
            plt.title('Évolution du taux de réussite')
            plt.xlabel('Période')
            plt.ylabel('Taux de réussite (%)')
            plt.grid(True, linestyle='--', alpha=0.7)
            plt.xticks(rotation=45)

            # Ajout des valeurs sur les points
            for i, v in enumerate(rates):
                plt.text(i, v + 1, f'{v:.1f}%', ha='center')

            plt.tight_layout()
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
            plt.close()
            buffer.seek(0)
            return base64.b64encode(buffer.getvalue()).decode()
        except Exception as e:
            _logger.error(f"Erreur génération graphique taux de réussite: {str(e)}")
            return None

    # ---------------------------------------------------------- Graphique de répartition des types de demandes traitées --------------

    def generate_request_type_pie_chart(self, start_date, end_date):
        """
        Génère le graphique de répartition des types de demandes.

        Args:
            start_date (date): Date début période
            end_date (date): Date fin période

        Returns:
            str: Image encodée en base64
        """
        try:
            plt, np = self._lazy_matplotlib()
            metrics = self.get_team_metrics(start_date, end_date)
            requests = self.env['gmao.request'].search([
                ('team_id', '=', self.id),
                ('create_date', '>=', start_date),
                ('create_date', '<=', end_date)
            ])

            # Agrégation par type
            type_counts = {}
            for request in requests:
                type_name = request.maintenance_type or 'Non défini'
                type_counts[type_name] = type_counts.get(type_name, 0) + 1

            if not type_counts:
                return None

            plt.figure(figsize=(8, 8))
            labels = list(type_counts.keys())
            sizes = list(type_counts.values())
            colors = plt.cm.Pastel1(np.linspace(0, 1, len(labels)))

            plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%',
                    startangle=90)
            plt.axis('equal')
            plt.title('Répartition des types de demandes')

            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
            plt.close()
            buffer.seek(0)
            return base64.b64encode(buffer.getvalue()).decode()
        except Exception as e:
            _logger.error(f"Erreur génération graphique types de demandes: {str(e)}")
            return None

    # --------------------------------------------- ACTIONS ÉDITION DES RAPPORTS ---------------------------------------

    def _prepare_report_data(self, start_date, end_date):
        """
        Prépare toutes les données nécessaires pour le rapport.

        Args:
            start_date (date): Date début période
            end_date (date): Date fin période

        Returns:
            dict: Données complètes pour le rapport
        """

        # Initialisation des valeurs par défaut
        metrics = {}
        charts = {
            'performance': None,
            'success_rate': None,
            'request_type': None
        }

        # Ajout validation dates
        if not start_date or not end_date:
            raise ValidationError(_("Les dates sont requises pour générer le rapport"))

        try:
            # Récupération des métriques optimisées
            metrics = self.get_team_metrics(start_date, end_date)

            _logger.info(f"Metrics for report: {metrics}")
            _logger.info(f"Preparing report data for team {self.name} from {start_date} to {end_date}")

            # Génération des graphiques
            performance_chart = self.generate_performance_chart(start_date, end_date)
            success_rate_chart = self.generate_success_rate_chart(start_date, end_date)
            request_type_chart = self.generate_request_type_pie_chart(start_date, end_date)

            # Mise à jour des graphiques dans le dictionnaire
            charts.update({
                'performance': performance_chart,
                'success_rate': success_rate_chart,
                'request_type': request_type_chart
            })

            # Construction du dictionnaire de données
            return {
                'team': self,
                'metrics': metrics,
                'charts': charts,
                'period': {
                    'start': start_date,
                    'end': end_date
                }
            }
        except Exception as e:
            _logger.error(f"Erreur préparation données rapport: {str(e)}")
            return {}

    # -----------------------------------------------------------------------------------

    @api.model
    def _get_report_values(self, docids, data=None):
        """
        Méthode pour récupérer les valeurs du rapport
        """
        docs = self.env['gmao.team'].browse(docids)
        report_data = []
        for team in docs:
            report_data.append(team._prepare_report_data(data['start_date'], data['end_date']))
        return {
            'doc_ids': docids,
            'doc_model': 'gmao.team',
            'data': data,
            'docs': docs,
            'team_data': report_data,
        }

    # -------------------------------------- ACTION PRINT -------------------------------------------------

    def action_print_form_report(self):
        """
        Action pour imprimer le rapport depuis la vue formulaire,
        utilisant les dates de l'équipe (date_start et date_end)
        """
        self.ensure_one()
        if not self.date_start or not self.date_end:
            raise UserError(_("Les dates de début et de fin de l'équipe doivent être définies"))
        return self.env.ref('gmao_suite.action_report_maintenance_team').report_action(
            self,
            data={
                'start_date': self.date_start,
                'end_date': self.date_end,
                'team_id': self.id,
                'is_form_report': True  # Flag pour identifier la source
            }
        )

    def action_open_report_wizard(self):
        """
        Action pour ouvrir le wizard de sélection de dates
        """
        self.ensure_one()
        return {
            'name': _('Imprimer Rapport Personnalisé'),
            'type': 'ir.actions.act_window',
            'res_model': 'maintenance.team.report.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_team_id': self.id,
                'default_start_date': self.date_start,
                'default_end_date': self.date_end,
            }
        }
