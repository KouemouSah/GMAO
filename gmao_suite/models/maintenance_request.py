# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from dateutil.relativedelta import relativedelta
from odoo.tools import float_round
from datetime import datetime
import io
import csv
import logging
# Cleanup post-refactor : base64, hashlib, Image, matplotlib retires.
# Les methodes _get_graph_image_* + _lazy_plt sont dans
# models/maintenance_request_graphs.py (extension via _inherit).



_logger = logging.getLogger(__name__)

class MaintenanceRequest(models.Model):
    _name = 'gmao.request'
    _description = 'Demande d\'intervention de maintenance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'

    # Champs de base
    name = fields.Char(string='Référence', required=True, copy=False, readonly=True, default='New', index=True)
    request_number = fields.Char(string='Numéro de la demande', index=True)  # Renommé de request_id à request_number
    description = fields.Text(string='Description', required=True, translate=True)
    
    # Champs de date
    request_date = fields.Datetime(string='Date de demande', default=fields.Datetime.now, required=True, index=True)
    schedule_date = fields.Datetime(string='Date planifiée', index=True)
    start_date = fields.Datetime(string='Date de début', index=True)
    close_date = fields.Datetime(string='Date de clôture', index=True)
    report_period_from = fields.Datetime(string='Période de début pour l\'édition du rapport')
    report_period_to = fields.Datetime(string='Période de fin pour l\'édition du rapport')
    
    # Champs relationnels
    equipment_id = fields.Many2one('gmao.equipment', string='Équipement', required=True, index=True)
    category_id = fields.Many2one(related='equipment_id.category_id', string='Catégorie', store=True, index=True)
    site_id = fields.Many2one('maintenance.site', string='Site', compute='_compute_site', store=True, readonly=True, index=True)
    user_id = fields.Many2one('res.partner', string='Client', required=True, index=True)
    technician_id = fields.Many2one('hr.employee', string='Technicien assigné', index=True)
    team_id = fields.Many2one('gmao.team', string='Équipe de maintenance', index=True)
    
    # Champs de sélection
    priority = fields.Selection([
        ('0', 'Très basse'),
        ('1', 'Basse'),
        ('2', 'Normale'),
        ('3', 'Haute'),
        ('4', 'Très haute')
    ], string='Priorité', default='2', index=True)
    
    maintenance_type = fields.Selection([
        ('corrective', 'Corrective'),
        ('preventive', 'Préventive'),
    ], string='Type de maintenance', default='corrective', required=True, index=True)
    
    state = fields.Selection([
        ('new', 'Nouvelle'),
        ('to_validate', 'Valider'),
        ('in_progress', 'En cours'),
        ('repaired', 'Réparée'),
        ('done', 'Terminée'),
        ('cancel', 'Annulée'),
    ], string='État', default='new', tracking=True, index=True)
    
    
    
    # Autres champs
    validator_id = fields.Many2one('res.users', string='Responsable de validation')
    parts_used_ids = fields.One2many('maintenance.parts.used', 'intervention_id', string='Pièces utilisées')
    duration = fields.Float(string='Durée (heures)', compute='_compute_duration', store=True)
    hourly_rate = fields.Float(string='Taux horaire', default=50.0)
    total_parts_cost = fields.Float(string='Coût total des pièces', compute='_compute_total_parts_cost', store=True)
    labor_cost = fields.Float(string='Coût de main d\'œuvre', compute='_compute_labor_cost', store=True)
    total_cost = fields.Float(string='Coût total', compute='_compute_total_cost', store=True)
    downtime = fields.Float(string='Temps d\'arrêt (heures)', compute='_compute_downtime', store=True)
    mttr = fields.Float(string='MTTR (Temps moyen de réparation)', compute='_compute_mttr', store=True)
    mtbf = fields.Float(string='MTBF (Temps moyen entre pannes)', compute='_compute_mtbf', store=True)
    contract_id = fields.Many2one('maintenance.contract', string='Contrat associé')
    devis = fields.Float(string='Devis')
    observations = fields.Text(string='Observations')

    # ------------------------------------------------------------------
    # P6 : Rapport d'intervention (saisi par le technicien, obligatoire
    # avant cloture). Donnees structurees -> analyse de recurrence,
    # prediction des pannes, sens metier des rapports equipement/site.
    # ------------------------------------------------------------------
    failure_code_id = fields.Many2one(
        'gmao.failure.code', string='Code panne / intervention', tracking=True,
        index=True, help="Code normalisé : permet l'analyse de récurrence.")
    failure_severity = fields.Selection([
        ('minor', 'Mineure'),
        ('major', 'Majeure'),
        ('critical', 'Critique'),
    ], string='Sévérité')
    failure_mode = fields.Selection(
        related='failure_code_id.failure_mode', string='Mode de défaillance',
        store=True, index=True, readonly=True)
    symptom = fields.Text(string='Symptôme constaté')
    failure_cause = fields.Text(string='Cause racine')
    work_performed = fields.Text(string='Travaux réalisés')
    recommendation = fields.Text(string='Recommandation / suivi')
    # Selecteurs de phrases-types (catalogue) : inserent leur texte dans le
    # champ correspondant puis se vident. Quick-create -> nouvelle phrase
    # reutilisable. Saisie libre dans le champ texte toujours possible.
    symptom_phrase_id = fields.Many2one(
        'gmao.report.phrase', string='Insérer un symptôme', copy=False,
        domain="[('category', '=', 'symptom')]")
    cause_phrase_id = fields.Many2one(
        'gmao.report.phrase', string='Insérer une cause', copy=False,
        domain="[('category', '=', 'cause')]")
    work_phrase_id = fields.Many2one(
        'gmao.report.phrase', string='Insérer des travaux', copy=False,
        domain="[('category', '=', 'work')]")
    reco_phrase_id = fields.Many2one(
        'gmao.report.phrase', string='Insérer une recommandation', copy=False,
        domain="[('category', '=', 'recommendation')]")
    report_complete = fields.Boolean(
        string='Rapport complet', compute='_compute_report_complete', store=True,
        help="Vrai quand code panne + cause racine + travaux réalisés sont saisis.")

    # P6.5 : tracabilite quand la demande est generee depuis une inspection
    # conformite (rapport d'etude -> demande brouillon).
    origin_inspection_id = fields.Many2one(
        'maintenance.conformite.securite', string='Inspection à l\'origine',
        readonly=True, index=True)

    @staticmethod
    def _insert_phrase(current, phrase):
        """Ajoute le texte (ou libelle) de la phrase au contenu existant."""
        add = (phrase.text or phrase.name or '').strip()
        if not add:
            return current
        return (current + "\n" + add) if current else add

    @api.onchange('symptom_phrase_id')
    def _onchange_symptom_phrase(self):
        if self.symptom_phrase_id:
            self.symptom = self._insert_phrase(self.symptom, self.symptom_phrase_id)
            self.symptom_phrase_id = False

    @api.onchange('cause_phrase_id')
    def _onchange_cause_phrase(self):
        if self.cause_phrase_id:
            self.failure_cause = self._insert_phrase(self.failure_cause, self.cause_phrase_id)
            self.cause_phrase_id = False

    @api.onchange('work_phrase_id')
    def _onchange_work_phrase(self):
        if self.work_phrase_id:
            self.work_performed = self._insert_phrase(self.work_performed, self.work_phrase_id)
            self.work_phrase_id = False

    @api.onchange('reco_phrase_id')
    def _onchange_reco_phrase(self):
        if self.reco_phrase_id:
            self.recommendation = self._insert_phrase(self.recommendation, self.reco_phrase_id)
            self.reco_phrase_id = False

    @api.depends('failure_code_id', 'failure_cause', 'work_performed')
    def _compute_report_complete(self):
        for req in self:
            req.report_complete = bool(
                req.failure_code_id and req.failure_cause and req.work_performed)

    system = fields.Selection([
        ('daisy', 'Plateforme Daisy'),
        ('excel', 'Fichier Excel'),
        ('phone', 'Contact telephonique'),
        ('mail', 'Mail'),
        ('other', 'Autre'),
    ], string='Canal de la demande', required=True, default='other', index=True)
    document_ids = fields.Many2many('ir.attachment', string='Documents attachés')
    company_id = fields.Many2one('res.company', string='Compagnie', required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(
        'res.currency', string='Devise',
        related='company_id.currency_id', store=False, readonly=True,
    )
    active = fields.Boolean(default=True, string='Actif')
    # Fix #3 : le champ state_history_ids et son modele sous-jacent ont ete
    # supprimes. L'historique des changements d'etat est maintenant assure par
    # mail.thread (tracking=True sur le field 'state' ligne ~68), accessible
    # via le chatter du formulaire.

    # A7 : computeds metier "is_overdue" et "days_until_schedule"
    is_overdue = fields.Boolean(
        string='En retard',
        compute='_compute_is_overdue',
        store=True,
        index=True,
        help="True si la demande n'est pas cloturee et que schedule_date < aujourd'hui",
    )
    days_until_schedule = fields.Integer(
        string='Jours avant intervention',
        compute='_compute_days_until_schedule',
        help="Negatif si en retard, positif si planifie dans le futur",
    )

    @api.depends('schedule_date', 'state')
    def _compute_is_overdue(self):
        """A7: en retard si pas cloturee et schedule_date < maintenant."""
        now = fields.Datetime.now()
        closed_states = ('done', 'cancel')
        for record in self:
            record.is_overdue = bool(
                record.schedule_date
                and record.state not in closed_states
                and record.schedule_date < now
            )

    @api.depends('schedule_date')
    def _compute_days_until_schedule(self):
        """A7: nombre de jours entre aujourd'hui et la date planifiee.
        Negatif = en retard, 0 = aujourd'hui, positif = futur.
        """
        today = fields.Date.today()
        for record in self:
            if record.schedule_date:
                delta = record.schedule_date.date() - today
                record.days_until_schedule = delta.days
            else:
                record.days_until_schedule = 0

    @api.model
    def create(self, vals):
        """Surcharge create : sequence + A5 auto-assignment technicien."""
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('gmao.request') or 'New'
        # A5 : si team_id renseigne mais pas de technicien explicite,
        # auto-assigner le chef d'equipe (leader_id) comme technicien.
        if vals.get('team_id') and not vals.get('technician_id'):
            team = self.env['gmao.team'].browse(vals['team_id'])
            if team.leader_id:
                vals['technician_id'] = team.leader_id.id
        request = super(MaintenanceRequest, self).create(vals)
        # P2 : auto-assignation d'equipe par scoring (opt-in via config).
        request._autoassign_team_on_create()
        # Kit de pieces : pre-calage automatique pour la maintenance PREVENTIVE.
        if request.maintenance_type == 'preventive':
            request._load_parts_kit()
        return request

    def _autoassign_team_on_create(self):
        """P2 : si aucune equipe n'est definie ET que l'option est activee
        (ir.config_parameter gmao.team_autoassign_on_create), attribue la
        meilleure equipe par scoring. Opt-in : desactive par defaut, donc
        zero regression sur le comportement existant."""
        self.ensure_one()
        if self.team_id:
            return
        param = self.env['ir.config_parameter'].sudo().get_param(
            'gmao.team_autoassign_on_create', 'False')
        if str(param).strip().lower() not in ('1', 'true', 'yes'):
            return
        team = self.env['gmao.team']._find_best_team(self)
        if not team:
            return
        vals = {'team_id': team.id}
        if not self.technician_id and team.leader_id:
            vals['technician_id'] = team.leader_id.id
        self.write(vals)

    def action_auto_assign_team(self):
        """Bouton : attribue la meilleure equipe (scoring multi-criteres) aux
        demandes selectionnees. Replique l'assignation leader->technicien (le
        write ne declenche pas l'onchange UI). Fallback gracieux si 0 equipe."""
        Team = self.env['gmao.team']
        assigned = 0
        for req in self:
            team = Team._find_best_team(req)
            if not team:
                continue
            vals = {'team_id': team.id}
            if not req.technician_id and team.leader_id:
                vals['technician_id'] = team.leader_id.id
            req.write(vals)
            assigned += 1
        if not assigned:
            # Fallback gracieux : rien n'a change -> notification, pas de reload.
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Aucune equipe attribuee"),
                    'message': _("Aucune equipe validee ne correspond "
                                 "(verifiez societe, etat 'Valide', actif)."),
                    'type': 'warning',
                    'sticky': False,
                },
            }
        # Succes : retourne True -> le client recharge la vue et l'utilisateur
        # voit l'equipe (et le technicien) nouvellement assignes.
        return True

    def _load_parts_kit(self, kit=None):
        """Pre-cale les pieces standard depuis un kit.

        Si `kit` est fourni (choix explicite via le wizard), on l'utilise ;
        sinon on cherche le kit applicable (equipement prioritaire, sinon
        categorie) — utilise par l'auto-calage preventif a la creation.
        Cree les lignes parts.used en brouillon ; le technicien libere ce
        qu'il n'utilise pas. Silencieux si aucun kit / pre-requis manquants.
        """
        self.ensure_one()
        if not self.equipment_id:
            return
        if kit is None:
            kit = self.env['gmao.parts.kit'].find_applicable_kit(self.equipment_id)
        if not kit or not kit.line_ids:
            return
        # Pre-requis parts.used : technicien + emplacement stock
        technician = self.technician_id or (self.team_id.leader_id if self.team_id else False)
        if not technician:
            # Pas de technicien => on ne peut pas creer les lignes (champ requis).
            self.message_post(body=_(
                "Kit '%s' trouve mais non charge : aucun technicien assigne. "
                "Assignez un technicien puis utilisez le bouton 'Charger le kit'.") % kit.name)
            return
        PartsUsed = self.env['maintenance.parts.used']
        stock_loc = PartsUsed._default_stock_location()
        created = 0
        for line in kit.line_ids:
            PartsUsed.create({
                'intervention_id': self.id,
                'product_id': line.product_id.id,
                'quantity': line.quantity,
                'part_nature': line.part_nature,
                'technician_id': technician.id,
                'stock_location_id': stock_loc,
                'state': 'draft',
            })
            created += 1
        if created:
            self.message_post(body=_(
                "Kit '%s' charge automatiquement : %s piece(s) pre-calees en brouillon. "
                "Liberez celles non utilisees.") % (kit.name, created))

    def action_load_parts_kit(self):
        """Bouton manuel : ouvre le wizard de SELECTION du kit a charger
        (au lieu d'imposer le kit applicable). L'utilisateur choisit le kit
        parmi ceux pertinents pour l'equipement."""
        self.ensure_one()
        if not self.equipment_id:
            raise UserError(_("Sélectionnez d'abord un équipement."))
        return {
            'type': 'ir.actions.act_window',
            'name': _("Charger un kit de pièces"),
            'res_model': 'gmao.load.kit.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_request_id': self.id},
        }

    @api.onchange('team_id')
    def _onchange_team_id_assign_technician(self):
        """A5 : a la selection d'une equipe dans le form, pre-remplit le
        technicien avec le chef d'equipe si pas deja saisi.
        """
        if self.team_id and self.team_id.leader_id and not self.technician_id:
            self.technician_id = self.team_id.leader_id

    @api.depends('start_date', 'close_date')
    def _compute_duration(self):
        # Calcule la durée de l'intervention en heures
        for request in self:
            if request.start_date and request.close_date:
                request.duration = (request.close_date - request.start_date).total_seconds() / 3600
            else:
                request.duration = 0

    @api.depends('parts_used_ids.total_cost')
    def _compute_total_parts_cost(self):
        # P1 : somme le COUT reel (standard_price), pas le prix de vente.
        # Exclut les pieces annulees.
        for request in self:
            valid_parts = request.parts_used_ids.filtered(lambda p: p.state != 'cancelled')
            request.total_parts_cost = sum(valid_parts.mapped('total_cost'))

    @api.depends('duration', 'hourly_rate')
    def _compute_labor_cost(self):
        # Calcule le coût de la main d'œuvre
        for request in self:
            request.labor_cost = request.duration * request.hourly_rate

    @api.depends('total_parts_cost', 'labor_cost')
    def _compute_total_cost(self):
        # Calcule le coût total de l'intervention
        for request in self:
            request.total_cost = request.total_parts_cost + request.labor_cost

    @api.depends('schedule_date', 'close_date')
    def _compute_downtime(self):
        # Calcule le temps d'arrêt de l'équipement
        for request in self:
            if request.schedule_date and request.close_date:
                request.downtime = (request.close_date - request.schedule_date).total_seconds() / 3600
            else:
                request.downtime = 0

    @api.depends('duration', 'downtime')
    def _compute_mttr(self):
        # Calcule le Temps Moyen de Réparation (MTTR)
        for request in self:
            request.mttr = request.duration / (request.downtime or 1)
    
    @api.depends('equipment_id')
    def _compute_site(self):
        for record in self:
            if record.equipment_id:
                record.site_id = record.equipment_id.site_id
            else:
                record.site_id = False

    
    @api.depends('equipment_id', 'request_date')
    def _compute_mtbf(self):
        # Calcule le Temps Moyen Entre Pannes (MTBF)
        for request in self:
            previous_request = self.env['gmao.request'].search([
                ('equipment_id', '=', request.equipment_id.id),
                ('close_date', '<', request.request_date),
                ('state', '=', 'done')
            ], order='close_date desc', limit=1)
            
            if previous_request:
                time_between_failures = (request.request_date - previous_request.close_date).total_seconds() / 3600
                request.mtbf = time_between_failures
            else:
                request.mtbf = 0

    @api.constrains('schedule_date', 'close_date')
    def _check_dates(self):
        # Vérifie que la date de clôture est postérieure à la date planifiée
        for request in self:
            if request.schedule_date and request.close_date and request.schedule_date > request.close_date:
                raise ValidationError(_("La date de clôture doit être postérieure à la date planifiée pour la demande %s.") % request.name)

    def action_start_timer(self):
        self.ensure_one()
        if self.state == 'new':
            return self.action_start()
        return True

    def action_stop_timer(self):
        self.ensure_one()
        if self.state == 'in_progress':
            return self.action_done()
        return True
    
    @api.onchange('technician_id')
    def _onchange_technician(self):
        # Met à jour l'équipe de maintenance lorsque le technicien change
        if self.technician_id and self.technician_id.department_id:
            self.team_id = self.env['gmao.team'].search([('department_id', '=', self.technician_id.department_id.id)], limit=1)

    @api.onchange('equipment_id')
    def _onchange_equipment_id(self):
        # Met à jour les informations liées à l'équipement lorsqu'il change
        if self.equipment_id:
            self.site_id = self.equipment_id.site_id
            linked_contracts = self.env['maintenance.contract'].search([
                ('equipment_ids', 'in', self.equipment_id.id), 
                ('state', '=', 'active')
            ], limit=1)
            if linked_contracts:
                self.contract_id = linked_contracts.id
                self.devis = linked_contracts.monthly_amount
            else:
                self.contract_id = False
                self.devis = 0.0
                message = _("Le contrat lié à cet équipement n'est pas actif ou inexistant.")
                return {
                    'warning': {
                        'title': _("Contrat Inactif ou Inexistant"),
                        'message': message,
                    }
                }
            

    def write(self, vals):
        """Surcharge pour notification par email sur changement de state.

        Fix bug #3 : le suivi d'historique d'etat etait fait via le sous-modele
        'maintenance.request.state.history' (doublonne mail.thread tracking).
        Remplace par le tracking natif de mail.thread (tracking=True sur state).
        Le message_post automatique d'Odoo enregistre l'ancien/nouveau state
        dans le chatter avec l'utilisateur et la date.
        """
        if 'state' in vals:
            for record in self:
                new_state = vals['state']
                res = super(MaintenanceRequest, record).write(vals)
                record._send_state_change_notification(new_state)
        else:
            res = super(MaintenanceRequest, self).write(vals)
        return res

    def _send_state_change_notification(self, new_state):
        self.ensure_one()
        template = self.env.ref('gmao_suite.email_template_maintenance_request_state_change', raise_if_not_found=False)
        if template:
            recipients = self._get_notification_recipients(new_state)
            if recipients:
                template.with_context(new_state=new_state).send_mail(self.id, email_values={'email_to': ', '.join(recipients)}, force_send=False)

    def _get_notification_recipients(self, new_state):
        recipients = set()
        if new_state == 'repaired' and self.state == 'validate':
            if self.technician_id and self.technician_id.work_email:
                recipients.add(self.technician_id.work_email)
            if self.team_id:
                recipients.update(self.team_id.member_ids.mapped('work_email'))
        elif new_state in ['repaired', 'done']:
            if self.user_id and self.user_id.email:
                recipients.add(self.user_id.email)
            if self.technician_id and self.technician_id.work_email:
                recipients.add(self.technician_id.work_email)
            request_users = self.env.ref('gmao_suite.group_request_user').users
            request_admins = self.env.ref('gmao_suite.group_request_admin').users
            recipients.update(request_users.mapped('email') + request_admins.mapped('email'))
        
        # Filtrer les emails valides
        return list(filter(lambda x: x and '@' in x, recipients))

    def get_maintenance_kpis(self):
        kpis = {
            'mttr': self.mttr,
            'mtbf': self.mtbf,
            'downtime': self.downtime,
            'total_cost': self.total_cost
        }
        _logger.info("KPI Data retrieved: %s", kpis)
        return kpis

    def get_current_duration(self):
        if self.start_date and not self.close_date:
            return (fields.Datetime.now() - self.start_date).total_seconds() / 3600
        return self.duration

    
    def generate_detailed_report(self):
    # Génère un rapport détaillé de la demande de maintenance
        self.ensure_one()
    
        # Vérification de la période pour l'édition du rapport
        if not self.report_period_from or not self.report_period_to:
            raise UserError(_("Veuillez spécifier une période de début et de fin pour l'édition du rapport."))
    
        return {
            'type': 'ir.actions.report',
            'report_name': 'gmao_suite.report_maintenance_request_detailed',
            'report_type': 'qweb-pdf',
            'data': {
                'request_id': self.id,
                'report_period_from': self.report_period_from,
                'report_period_to': self.report_period_to,
            },
        }


    @api.constrains('contract_id')
    def _check_contract_state(self):
        for request in self:
            if request.contract_id and request.contract_id.state != 'active':
                message = _("Le contrat %s associé à cet équipement n'est pas actif.") % request.contract_id.name
                request.message_post(body=message)

    @api.constrains('devis')
    def _check_devis(self):
        for request in self:
            if request.devis < 0 and not request.contract_id:
                raise ValidationError(_("Le devis doit être supérieur à 0 pour une intervention sans contrat."))

    @api.constrains('validator_id')
    def _check_validator_group(self):
        for record in self:
            if record.validator_id:
                if not (record.validator_id.has_group('gmao_suite.group_request_user') or 
                        record.validator_id.has_group('gmao_suite.group_request_admin') or
                        record.validator_id.has_group('gmao_suite.group_gmao_admin')):
                    raise ValidationError(_("Le responsable de validation doit appartenir à l'un des groupes suivants : Utilisateur de demande, Administrateur de demande ou Administrateur GMAO."))

    def action_validate(self):
        self.ensure_one()
        if self.state != 'new':
            raise UserError(_("Seules les interventions à l'état 'Nouvelle' peuvent être validées."))
        if not (self.env.user.has_group('gmao_suite.group_request_user') or self.env.user.has_group('gmao_suite.group_request_admin')):
            raise UserError(_("Vous n'avez pas les droits nécessaires pour valider cette intervention."))
        self.write({
            'state': 'to_validate',
            'validator_id': self.env.user.id
        })
        self.message_post(body=_("L'intervention %s a été validée par %s.") % (self.name, self.env.user.name))

    def action_start(self):
        """Demarre l'intervention.

        A3 : passe AUSSI l'equipement en state 'in_repair' (coherence data
        entre la demande et l'equipement vu).
        """
        self.ensure_one()
        if self.state != 'to_validate':
            raise UserError(_("La demande doit être à l'état 'Validée' pour être démarrée."))
        self.write({
            'state': 'in_progress',
            'start_date': fields.Datetime.now()
        })
        # A3 : auto-update equipment.state
        if self.equipment_id and self.equipment_id.state == 'operational':
            self.equipment_id.write({'state': 'in_repair'})

    def action_repair(self):
        self.ensure_one()
        if self.state != 'in_progress':
            raise UserError(_("La demande doit être à l'état 'En cours' pour être marquée comme réparée."))
        self.write({'state': 'repaired'})

    def action_done(self):
        """Termine la demande.

        A3 : remet l'equipement en state 'operational' s'il etait en reparation
        a cause de cette demande.
        """
        self.ensure_one()
        if self.state != 'repaired':
            raise UserError(_("La demande doit être à l'état 'Réparée' pour être terminée."))
        # P6 : rapport d'intervention OBLIGATOIRE avant cloture (code +
        # cause + travaux). En preventif, utiliser un code PREV-* (ex.
        # PREV-RAS si aucune anomalie).
        missing = []
        if not self.failure_code_id:
            missing.append(_("Code panne / intervention"))
        if not self.failure_cause:
            missing.append(_("Cause racine"))
        if not self.work_performed:
            missing.append(_("Travaux réalisés"))
        if missing:
            raise UserError(_(
                "Le rapport d'intervention doit être complété avant de "
                "terminer la demande.\nChamps manquants : %s.\n\n"
                "Pour une maintenance préventive sans anomalie, choisir un "
                "code « PREV-… » (ex. PREV-RAS).") % ", ".join(missing))
        self.write({
            'state': 'done',
            'close_date': fields.Datetime.now()
        })
        reserved_parts = self.parts_used_ids.filtered(lambda p: p.state == 'reserved')
        if reserved_parts:
            reserved_parts.action_use()
        else:
            self.message_post(body=_("Aucune pièce réservée n'a été trouvée pour l'intervention %s.") % self.name)
        # A3 : remettre l'equipement en operationnel si plus aucune intervention ouverte
        if self.equipment_id and self.equipment_id.state == 'in_repair':
            other_open = self.search_count([
                ('equipment_id', '=', self.equipment_id.id),
                ('state', 'in', ('to_validate', 'in_progress', 'repaired')),
                ('id', '!=', self.id),
            ])
            if not other_open:
                self.equipment_id.write({'state': 'operational'})
        # P2 (maillon #12) : refacturation AUTO des pieces billable consommees.
        # Genere une facture brouillon client pour les pieces refacturables non
        # encore facturees. Le comptable la validera ensuite (workflow standard).
        self._auto_invoice_billable_parts()
        # Envoi AUTO du bon d'intervention (PDF) au client a la cloture.
        self._send_intervention_report()

    def _send_intervention_report(self):
        """Envoie automatiquement le bon d'intervention PDF au client a la cloture.

        Utilise un mail.template avec report_template (PDF attache nativement).
        Non bloquant : si pas de client/email ou si erreur, on log sans planter.
        """
        self.ensure_one()
        if not self.user_id or not self.user_id.email:
            return
        template = self.env.ref(
            'gmao_suite.email_template_intervention_report', raise_if_not_found=False)
        if not template:
            return
        try:
            template.send_mail(self.id, force_send=True)
            self.message_post(body=_(
                "Bon d'intervention (PDF) envoye automatiquement a %s.") % self.user_id.name)
        except Exception as e:
            _logger.warning("GMAO : envoi auto du bon d'intervention echoue pour %s : %s",
                            self.name, e)

    def _auto_invoice_billable_parts(self):
        """Genere automatiquement la facture des pieces refacturables a la cloture.

        - Ne facture que les pieces part_nature='billable', etat 'used', non deja facturees.
        - Necessite un client (user_id) sur l'intervention.
        - Cree UNE facture brouillon regroupant toutes les pieces (pas une par piece).
        - Silencieux si rien a facturer (pas d'erreur bloquante a la cloture).
        """
        self.ensure_one()
        if not self.user_id:
            return
        billable = self.parts_used_ids.filtered(
            lambda p: p.part_nature == 'billable' and p.state == 'used' and not p.invoice_line_id)
        if not billable:
            return
        try:
            for part in billable:
                part.action_invoice()
            self.message_post(body=_(
                "Facturation automatique : %s piece(s) refacturable(s) ajoutee(s) "
                "a une facture brouillon pour %s.") % (len(billable), self.user_id.name))
        except Exception as e:
            # Ne pas bloquer la cloture si la facturation echoue (ex: compta non configuree)
            _logger.warning("GMAO : auto-facturation echouee pour %s : %s", self.name, e)
            self.message_post(body=_(
                "Facturation automatique des pieces non realisee (a faire manuellement). "
                "Detail technique : %s") % e)

    def action_cancel(self):
        self.ensure_one()
        if self.state in ['done', 'cancel']:
            raise UserError(_("Impossible d'annuler une demande terminée ou déjà annulée."))
        self.write({'state': 'cancel'})

    def action_reset_to_draft(self):
        self.ensure_one()
        if not self.env.user.has_group('gmao_suite.group_maintenance_manager'):
            raise UserError(_("Seuls les responsables de maintenance peuvent réinitialiser une demande."))
        if self.state != 'cancel':
            raise UserError(_("Seules les demandes annulées peuvent être réinitialisées."))
        self.write({'state': 'new'})

    def name_get(self):
        result = []
        for record in self:
            name = f"{record.name} - {record.equipment_id.name} ({record.site_id.name})"
            result.append((record.id, name))
        return result

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        args = args or []
        domain = []
        if name:
            domain = ['|', '|', ('name', operator, name), ('equipment_id.name', operator, name), ('site_id.name', operator, name)]
        return self._search(domain + args, limit=limit, access_rights_uid=name_get_uid)

    def copy(self, default=None):
        default = dict(default or {})
        default.update({
            'name': _('Copie de %s') % self.name,
            'state': 'new',
            'request_date': fields.Datetime.now(),
            'schedule_date': False,
            'start_date': False,
            'close_date': False,
        })
        return super(MaintenanceRequest, self).copy(default)

    def unlink(self):
        for request in self:
            if request.state not in ('new', 'cancel'):
                raise UserError(_("Vous ne pouvez supprimer que les demandes à l'état 'Nouvelle' ou 'Annulée'."))
        return super(MaintenanceRequest, self).unlink()

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        if self.env.user.has_group('base.group_multi_company'):
            domain = domain + [('company_id', 'in', self.env.companies.ids)]
        return super(MaintenanceRequest, self).read_group(domain, fields, groupby, offset, limit, orderby, lazy)

    @api.model
    def get_graph_data(self, domain, groupby, measure, x_fields, y_fields):
        measures = [measure] if isinstance(measure, str) else measure[:3]
        x_fields = [x_fields] if isinstance(x_fields, str) else x_fields[:3]
        y_fields = [y_fields] if isinstance(y_fields, str) else y_fields[:3]

        fields = measures + x_fields + y_fields
        groupby = x_fields + y_fields

        data = self.read_group(
            domain,
            fields=fields,
            groupby=groupby,
            lazy=False
        )

        processed_data = []
        for item in data:
            processed_item = {
                'x': ' - '.join([str(item[x]) for x in x_fields]),
                'y': ' - '.join([str(item[y]) for y in y_fields]),
            }
            for measure in measures:
                processed_item[measure] = item[measure]
            processed_data.append(processed_item)

        return processed_data
        
    @api.model
    def get_table_data(self, domain, groupby, fields, limit=10, offset=0):
        # Récupérer le nombre total de groupes pour la pagination
        total_data = self.read_group(
            domain,
            fields=fields,
            groupby=groupby,
            lazy=False
        )
        total_count = len(total_data)

        # Appel à read_group avec limit et offset pour la pagination
        data = self.read_group(
            domain,
            fields=fields,
            groupby=groupby,
            offset=offset,
            limit=limit,
            lazy=False
        )

        processed_data = []
        for item in data:
            processed_item = {}
            for field in fields:
                processed_item[field] = item.get(field)
            for group in groupby:
                processed_item[group] = item.get(group)
            processed_data.append(processed_item)

        return {
            'data': processed_data,
            'total_count': total_count,
        }

    @api.model
    def export_graph_data(self, domain, groupby):
        data = self.read_group(
            domain,
            fields=['name', 'state', 'maintenance_type', 'duration', 'total_cost'],
            groupby=groupby,
            lazy=False
        )

        output = io.StringIO()
        writer = csv.writer(output)

        # Écrire l'en-tête
        header = ['name', 'state', 'maintenance_type', 'duration', 'total_cost'] + groupby
        writer.writerow(header)

        # Écrire les données
        for item in data:
            row = [
                item['name'],
                item['state'],
                item['maintenance_type'],
                item['duration'],
                item['total_cost']
            ]
            for group in groupby:
                row.append(item[group])
            writer.writerow(row)

        return output.getvalue()

    @api.model
    def get_available_fields(self):
        return {
            field: self._fields[field].string
            for field in self._fields
            if self._fields[field].type in ['integer', 'float', 'monetary', 'many2one']
        }
        
    
    # =============================================================
    # NOTE REFACTOR : les 4 methodes _get_graph_image_* + _lazy_plt ont
    # ete extraites dans models/maintenance_request_graphs.py (refactor
    # d'un monolithique 1107 lignes -> separation des responsabilites :
    # workflow/KPI ici, generation matplotlib la-bas).
    # =============================================================



    
    def _serialize_value(self, value):
    #Fonction utilitaire pour sérialiser les valeurs de manière sûre
    
    #Args:value: Valeur à sérialiser
        
    #Returns:La valeur sérialisée de manière sûre

        if isinstance(value, (bool, int, float, str)):
            return value
        elif isinstance(value, tuple):
            return value[1] if len(value) > 1 else str(value[0])
        elif value is None:
            return False
        else:
            return str(value)
    
    
    
    
    @api.model
    def get_pivot_data(self):
        _logger.info("Début de la récupération des données pivot")
        result = []
        try:
            raw_data = self.read_group(
                [],
                [
                    'team_id',
                    'equipment_id',
                    'maintenance_type',
                    'priority',
                    'duration:avg',
                    'mttr:avg',
                    'mtbf:avg',
                ],
                [
                    'team_id',
                    'equipment_id',
                    'maintenance_type',
                    'priority',
                ],
                lazy=False
            )

            for idx, item in enumerate(raw_data):
                # Gestion de 'team_id'
                team_id = item.get('team_id')
                if team_id:
                    team = team_id[1] if len(team_id) > 1 else str(team_id[0])
                else:
                    team = 'N/A'

                # Gestion de 'equipment_id'
                equipment_id = item.get('equipment_id')
                if equipment_id:
                    equipment = equipment_id[1] if len(equipment_id) > 1 else str(equipment_id[0])
                else:
                    equipment = 'N/A'

                # Gestion de 'maintenance_type'
                maintenance_type_code = item.get('maintenance_type', False)
                maintenance_type_dict = dict(self._fields['maintenance_type'].selection)
                maintenance_type = maintenance_type_dict.get(maintenance_type_code, 'N/A')

                # Gestion de 'priority'
                priority_code = item.get('priority', False)
                priority_dict = dict(self._fields['priority'].selection)
                priority = priority_dict.get(priority_code, 'N/A')

                # Calcul des moyennes
                avg_duration = float(item.get('duration', 0.0))
                avg_mttr = float(item.get('mttr', 0.0))
                avg_mtbf = float(item.get('mtbf', 0.0))

                result.append({
                    'index': idx,
                    'team': team,
                    'equipment': equipment,
                    'maintenance_type': maintenance_type,
                    'priority': priority,
                    'avg_duration': avg_duration,
                    'avg_mttr': avg_mttr,
                    'avg_mtbf': avg_mtbf,
                })

            _logger.info("Données pivot converties avec succès: %s éléments", len(result))
            _logger.debug("Données pivot: %s", result)
            return result

        except Exception as e:
            _logger.exception("Erreur lors de la récupération des données pivot")
            return []



    @api.model
    def _get_default_filters(self):
        return [
            ('request_date', '>=', fields.Date.to_string(fields.Date.today() - relativedelta(days=30))),
            ('state', '!=', 'cancel')
        ]

    @api.model
    def _get_default_group_by(self):
        return ['state', 'maintenance_type']

    def action_request_report(self):
        """Opens the maintenance request list with default filters/groupings.
        Replaces the previous broken xml-id ref (action did not exist).
        """
        return {
            'name': _('Rapport des demandes de maintenance'),
            'type': 'ir.actions.act_window',
            'res_model': 'gmao.request',
            'view_mode': 'tree,kanban,form,pivot,graph',
            'context': {
                'search_default_done': 1,
                'search_default_requests': 1,
                'search_default_contract': 1,
                'group_by': ['system', 'state'],
            },
        }

    

    @api.model
    def _cron_archive_old_requests(self):
        archive_date = fields.Date.today() - relativedelta(years=1)
        old_requests = self.search([
            ('state', '=', 'done'),
            ('close_date', '<=', archive_date),
            ('active', '=', True)
        ])
        if old_requests:
            old_requests.write({'active': False})
            _logger.info(_("Archivage réussi de %s demandes de maintenance"), len(old_requests))

    @api.model
    def _cron_send_weekly_report(self):
        today = fields.Date.today()
        last_week = today - relativedelta(days=7)
        requests = self.search([
            ('request_date', '>=', last_week),
            ('request_date', '<=', today)
        ])
        if requests:
            template = self.env.ref('gmao_suite.email_template_weekly_report', raise_if_not_found=False)
            if template:
                template.with_context(requests=requests).send_mail(self.env.user.id, force_send=True)
                _logger.info(_("Rapport hebdomadaire envoyé avec succès."))
            else:
                _logger.error(_("Template de rapport hebdomadaire non trouvé."))

    @api.model
    def _cron_notify_late_requests(self):
        today = fields.Datetime.now()
        late_requests = self.search([
            ('schedule_date', '<', today),
            ('state', 'not in', ['done', 'cancel'])
        ])
        template = self.env.ref('gmao_suite.email_template_late_request_notification', raise_if_not_found=False)
        if template:
            for request in late_requests:
                template.send_mail(request.id, force_send=True)
            _logger.info(_("Notifications de retard envoyées pour %s demandes"), len(late_requests))
        else:
            _logger.error(_("Template de notification de retard non trouvé."))
        # A2 : escalade automatique - poste un message visible dans le chatter
        # pour chaque demande en retard de + de 48h, avec mention des admins.
        threshold = today - relativedelta(hours=48)
        critical = self.search([
            ('schedule_date', '<', threshold),
            ('state', 'in', ('new', 'to_validate', 'in_progress')),
        ])
        admin_group = self.env.ref('gmao_suite.group_request_admin', raise_if_not_found=False)
        admin_partners = admin_group.users.mapped('partner_id') if admin_group else self.env['res.partner']
        for req in critical:
            if not req.message_ids.filtered(lambda m: 'ESCALADE 48H' in (m.body or '')):
                req.message_post(
                    body=_("<strong>[ESCALADE 48H]</strong> Cette demande est en retard "
                           "de plus de 48 heures. Action immediate requise."),
                    partner_ids=admin_partners.ids,
                    subtype_xmlid='mail.mt_comment',
                )
        if critical:
            _logger.info("GMAO A2 : %s demande(s) escaladee(s) (+48h)", len(critical))

    @api.model
    def _cron_update_mtbf(self):
        equipments = self.env['gmao.equipment'].search([])
        for equipment in equipments:
            last_two_requests = self.search([
                ('equipment_id', '=', equipment.id),
                ('state', '=', 'done')
            ], order='close_date desc', limit=2)

            if len(last_two_requests) == 2:
                time_between_failures = (last_two_requests[0].request_date - last_two_requests[1].close_date).total_seconds() / 3600
                equipment.write({'mtbf': time_between_failures})

    @api.model
    def _cron_create_reminder_activities(self):
        """A4 : pour chaque demande planifiee dans les prochaines 24h sans
        activite de rappel existante, cree une mail.activity assignee au
        technicien (ou au user si pas de tech).
        """
        import logging
        _logger = logging.getLogger(__name__)
        now = fields.Datetime.now()
        in_24h = now + relativedelta(hours=24)
        try:
            activity_type = self.env.ref('mail.mail_activity_data_todo')
        except Exception:
            return 0  # mail_activity_data_todo doit exister, securite
        upcoming = self.search([
            ('schedule_date', '!=', False),
            ('schedule_date', '>=', now),
            ('schedule_date', '<=', in_24h),
            ('state', 'not in', ('done', 'cancel')),
        ])
        created = 0
        for req in upcoming:
            # Skip si activite de rappel existe deja
            existing = self.env['mail.activity'].search([
                ('res_model', '=', 'gmao.request'),
                ('res_id', '=', req.id),
                ('activity_type_id', '=', activity_type.id),
                ('summary', 'ilike', 'Rappel intervention'),
            ], limit=1)
            if existing:
                continue
            assignee = (req.technician_id.user_id if req.technician_id and req.technician_id.user_id
                        else self.env.user)
            req.activity_schedule(
                'mail.mail_activity_data_todo',
                date_deadline=req.schedule_date.date(),
                summary=_("Rappel intervention %s") % req.name,
                note=_("Intervention planifiee sur %s. Pensez a verifier le materiel et les pieces.") % (
                    req.equipment_id.display_name or '-'),
                user_id=assignee.id,
            )
            created += 1
        if created:
            _logger.info("GMAO CRON A4 : %s activite(s) de rappel J-1 cree(s)", created)
        return created

    def action_send_sms(self):
        self.ensure_one()
        template = self.env.ref('gmao_suite.sms_template_maintenance_request', raise_if_not_found=False)
        if template:
            template.send_sms(self.id, force_send=True)
        else:
            raise UserError(_("Modèle SMS non trouvé."))

    @api.model
    def create_from_equipment(self, equipment_id):
        equipment = self.env['gmao.equipment'].browse(equipment_id)
        return self.create({
            'equipment_id': equipment.id,
            'user_id': self.env.user.partner_id.id,
            'description': _("Maintenance préventive pour %s") % equipment.name,
            'maintenance_type': 'preventive',
            'schedule_date': fields.Datetime.now(),
        })

# Fix #3 : la classe MaintenanceRequestStateHistory a ete supprimee.
# Le tracking des changements d'etat est maintenant gere nativement par
# mail.thread + tracking=True sur le field 'state' de MaintenanceRequest.
# Le chatter du formulaire affiche l'historique des transitions avec la
# date, l'utilisateur et l'ancien/nouveau state.
