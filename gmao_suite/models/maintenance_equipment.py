# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import timedelta

class MaintenanceEquipment(models.Model):
    _name = 'gmao.equipment'
    _description = 'Équipement de Maintenance'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    _sql_constraints = [
        ('unique_equipment_code_per_company',
         'UNIQUE(code, company_id)',
         "Le code d'equipement doit etre unique au sein d'une meme societe."),
    ]

    name = fields.Char(string='Nom de l\'équipement', required=True, tracking=True)
    code = fields.Char(string='Code de l\'équipement', required=True, tracking=True)
    category_id = fields.Many2one('gmao.equipment.category', string='Catégorie', required=True)
    model = fields.Char(string='Modèle')
    serial_number = fields.Char(string='Numéro de série')
    vendor_id = fields.Many2one('res.partner', string='Fournisseur')
    
    site_id = fields.Many2one('maintenance.site', string='Site', required=True)
    location = fields.Char(string='Emplacement précis')
    
    purchase_date = fields.Date(string='Date d\'achat')
    warranty_expiration_date = fields.Date(string='Date d\'expiration de la garantie')
    
    cost = fields.Float(string='Coût d\'achat')
    currency_id = fields.Many2one('res.currency', string='Devise', default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one(
        'res.company', string='Societe',
        default=lambda self: self.env.company, index=True,
    )

    maintenance_team_id = fields.Many2one('gmao.team', string='Équipe de maintenance')
    technician_user_id = fields.Many2one('res.users', string='Technicien responsable')
    
    # O1+O2 : store=True sur computes filtrables (kanban smart count)
    maintenance_count = fields.Integer(
        string='Nombre de maintenances',
        compute='_compute_maintenance_count', store=True)
    maintenance_open_count = fields.Integer(
        string='Maintenances ouvertes',
        compute='_compute_maintenance_count', store=True, index=True)

    # ----- Suivi remplacement (decision repair vs replace) -----
    maintenance_cost_total = fields.Monetary(
        string='Coût cumulé maintenance', currency_field='currency_id',
        compute='_compute_maintenance_costs', store=True,
        help="Somme des coûts de toutes les interventions sur cet équipement.")
    annual_maintenance_cost = fields.Monetary(
        string='Coût maintenance (12 mois)', currency_field='currency_id',
        compute='_compute_maintenance_costs', store=True)
    maintenance_cost_ratio = fields.Float(
        string='Ratio coût/valeur (%)',
        compute='_compute_maintenance_costs', store=True, index=True,
        help="Coût cumulé de maintenance rapporté au coût d'achat (%).")
    replacement_recommended = fields.Boolean(
        string='Remplacement recommandé',
        compute='_compute_maintenance_costs', store=True, index=True,
        help="Vrai quand le ratio coût/valeur dépasse le seuil configuré "
             "(gmao.replacement_threshold, défaut 60%).")
    replacement_alert_sent = fields.Boolean(
        string='Alerte remplacement envoyée', default=False, copy=False)

    period = fields.Integer(string='Périodicité de maintenance préventive (jours)')
    next_maintenance_date = fields.Date(
        string='Prochaine maintenance prévue',
        compute='_compute_next_maintenance', store=True, index=True)
    
    effective_date = fields.Date(string='Date de mise en service')
    scrap_date = fields.Date(string='Date de mise au rebut')
    
    active = fields.Boolean(default=True, string='Actif')
    state = fields.Selection([
        ('operational', 'Opérationnel'),
        ('in_repair', 'En réparation'),
        ('standby', 'En attente'),
        ('scrapped', 'Mis au rebut')
    ], string='État', default='operational', tracking=True)
    
    notes = fields.Text(string='Notes')

    maintenance_ids = fields.One2many('gmao.request', 'equipment_id', string='Demandes de maintenance')
    conformite_securite_ids = fields.One2many('maintenance.conformite.securite', 'equipment_id', string='Inspections de conformité et sécurité')

    @api.model
    def create(self, vals):
        if vals.get('code', 'New') == 'New':
            vals['code'] = self.env['ir.sequence'].next_by_code('gmao.equipment') or 'New'
        return super(MaintenanceEquipment, self).create(vals)

    @api.depends('maintenance_ids', 'maintenance_ids.state')
    def _compute_maintenance_count(self):
        for equipment in self:
            equipment.maintenance_count = len(equipment.maintenance_ids)
            equipment.maintenance_open_count = len(equipment.maintenance_ids.filtered(lambda m: m.state != 'done'))

    @api.depends('period', 'maintenance_ids.close_date', 'maintenance_ids.state')
    def _compute_next_maintenance(self):
        for equipment in self:
            if equipment.period:
                last_maintenance = equipment.maintenance_ids.filtered(lambda m: m.state == 'done').sorted('close_date', reverse=True)[:1]
                if last_maintenance and last_maintenance.close_date:
                    equipment.next_maintenance_date = last_maintenance.close_date.date() + timedelta(days=equipment.period)
                else:
                    equipment.next_maintenance_date = fields.Date.today() + timedelta(days=equipment.period)
            else:
                equipment.next_maintenance_date = False

    def _report_client(self):
        """Client du rapport = partenaire du contrat de maintenance couvrant
        l'equipement (contrat actif prioritaire), sinon recordset vide.
        Utilise dans les rapports PDF equipement."""
        self.ensure_one()
        Contract = self.env['maintenance.contract']
        contract = Contract.search(
            [('equipment_ids', 'in', self.id), ('state', '=', 'active')], limit=1
        ) or Contract.search([('equipment_ids', 'in', self.id)], limit=1)
        return contract.partner_id if contract else self.env['res.partner']

    @api.model
    def _get_replacement_threshold(self):
        """Seuil (%) coût/valeur au-dela duquel le remplacement est recommande.
        Parametrable via ir.config_parameter 'gmao.replacement_threshold'."""
        val = self.env['ir.config_parameter'].sudo().get_param('gmao.replacement_threshold', '60')
        try:
            return float(val)
        except (TypeError, ValueError):
            return 60.0

    @api.depends('maintenance_ids.total_cost', 'maintenance_ids.request_date',
                 'maintenance_ids.state', 'cost')
    def _compute_maintenance_costs(self):
        threshold = self._get_replacement_threshold()
        one_year_ago = fields.Date.today() - timedelta(days=365)
        for eq in self:
            total = sum(eq.maintenance_ids.mapped('total_cost'))
            recent = eq.maintenance_ids.filtered(
                lambda m: m.request_date and m.request_date.date() >= one_year_ago)
            eq.maintenance_cost_total = total
            eq.annual_maintenance_cost = sum(recent.mapped('total_cost'))
            eq.maintenance_cost_ratio = (total / eq.cost * 100.0) if eq.cost else 0.0
            eq.replacement_recommended = bool(eq.cost) and eq.maintenance_cost_ratio >= threshold

    @api.constrains('effective_date', 'scrap_date')
    def _check_dates(self):
        for equipment in self:
            if equipment.effective_date and equipment.scrap_date and equipment.effective_date > equipment.scrap_date:
                raise ValidationError(_("La date de mise en service doit être antérieure à la date de mise au rebut."))

    def action_view_maintenance(self):
        self.ensure_one()
        return {
            'name': 'Maintenances',
            'type': 'ir.actions.act_window',
            'res_model': 'gmao.request',
            'view_mode': 'tree,form',
            'domain': [('equipment_id', '=', self.id)],
        }

    def action_start_maintenance(self):
        self.write({'state': 'in_repair'})

    def action_end_maintenance(self):
        self.write({'state': 'operational'})

    def action_scrap(self):
        self.write({'state': 'scrapped', 'scrap_date': fields.Date.today(), 'active': False})

    # =============================================================
    # A1 : CRON generation auto des demandes preventives
    # =============================================================
    @api.model
    def _cron_generate_preventive_requests(self):
        """Genere une demande de maintenance preventive pour chaque equipement
        operationnel dont next_maintenance_date est aujourd'hui ou dans <= 1 jour.
        Skip si une demande preventive non cloturee existe deja.
        """
        import logging
        _logger = logging.getLogger(__name__)
        today = fields.Date.today()
        threshold = today + timedelta(days=1)
        equipments = self.search([
            ('state', '=', 'operational'),
            ('active', '=', True),
            ('next_maintenance_date', '!=', False),
            ('next_maintenance_date', '<=', threshold),
        ])
        Request = self.env['gmao.request']
        created = 0
        for equipment in equipments:
            # Skip si une demande preventive est deja en cours pour cet equipement
            existing = Request.search([
                ('equipment_id', '=', equipment.id),
                ('maintenance_type', '=', 'preventive'),
                ('state', 'not in', ('done', 'cancel')),
            ], limit=1)
            if existing:
                continue
            partner = self.env.user.partner_id
            Request.create({
                'description': _("Maintenance preventive automatique pour %s") % equipment.name,
                'equipment_id': equipment.id,
                'user_id': partner.id,
                'maintenance_type': 'preventive',
                'system': 'other',
                'schedule_date': fields.Datetime.now(),
                'team_id': equipment.maintenance_team_id.id if equipment.maintenance_team_id else False,
            })
            created += 1
        if created:
            _logger.info("GMAO CRON : %s demande(s) preventive(s) auto-generee(s)", created)
        return created

    # =============================================================
    # Suivi remplacement : alerte auto quand le seuil cout/valeur
    # est franchi (une seule activite par equipement).
    # =============================================================
    @api.model
    def _replacement_alert_recipients(self):
        """Emails destinataires de l'alerte remplacement.

        Source de verite : ir.config_parameter 'gmao.replacement_alert_email'
        (liste d'emails separes par des virgules). Fallback : membres du groupe
        group_gmao_admin disposant d'un email.
        """
        param = self.env['ir.config_parameter'].sudo().get_param(
            'gmao.replacement_alert_email', '')
        emails = [e.strip() for e in (param or '').split(',') if e.strip()]
        if not emails:
            grp = self.env.ref('gmao_suite.group_gmao_admin', raise_if_not_found=False)
            if grp:
                emails = [u.email for u in grp.users if u.email]
        return emails

    def _send_replacement_alert_email(self):
        """Envoie l'email d'alerte remplacement avec le PDF d'aide a la decision.

        Non bloquant (force_send=False : mise en file d'attente native, le cron
        ne bloque pas sur SMTP). Destinataires = config (ou group_gmao_admin)
        + technicien responsable de l'equipement. Retourne True si envoye.
        """
        self.ensure_one()
        import logging
        _logger = logging.getLogger(__name__)
        template = self.env.ref(
            'gmao_suite.email_template_replacement_alert', raise_if_not_found=False)
        if not template:
            return False
        recipients = list(self._replacement_alert_recipients())
        if self.technician_user_id.email:
            recipients.append(self.technician_user_id.email)
        # dedoublonne en preservant l'ordre + retire les vides
        recipients = list(dict.fromkeys([r for r in recipients if r]))
        if not recipients:
            _logger.info(
                "GMAO : alerte remplacement %s sans destinataire (param "
                "gmao.replacement_alert_email vide et aucun email admin/technicien).",
                self.display_name)
            return False
        try:
            template.send_mail(
                self.id, force_send=False,
                email_values={'email_to': ', '.join(recipients)})
            return True
        except Exception as e:
            _logger.warning(
                "GMAO : envoi alerte remplacement echoue pour %s : %s",
                self.display_name, e)
            return False

    def action_send_replacement_report(self):
        """Bouton (form/liste) : envoie a la demande le rapport d'aide a la
        decision par email, independamment du flag d'alerte automatique."""
        sent = 0
        for eq in self:
            if eq._send_replacement_alert_email():
                sent += 1
        return True

    @api.model
    def _cron_check_replacement(self):
        import logging
        _logger = logging.getLogger(__name__)
        threshold = self._get_replacement_threshold()
        to_alert = self.search([
            ('replacement_recommended', '=', True),
            ('replacement_alert_sent', '=', False),
            ('active', '=', True),
        ])
        count = 0
        for eq in to_alert:
            eq.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_("Remplacement à étudier : %s") % eq.name,
                note=_("Coût cumulé de maintenance = %.0f%% du coût d'achat "
                       "(seuil %.0f%%). Étudier le remplacement de l'équipement.") % (
                           eq.maintenance_cost_ratio, threshold),
                user_id=(eq.technician_user_id.id or self.env.user.id),
            )
            # Notification email + PDF d'aide a la decision (non bloquant).
            eq._send_replacement_alert_email()
            eq.replacement_alert_sent = True
            count += 1
        # Reset du flag pour les equipements repasses sous le seuil
        self.search([
            ('replacement_recommended', '=', False),
            ('replacement_alert_sent', '=', True),
        ]).write({'replacement_alert_sent': False})
        if count:
            _logger.info("GMAO CRON : %s equipement(s) signale(s) pour remplacement", count)
        return count

    # Méthodes pour le rapport natif Odoo
    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'gmao.equipment',
            'docs': docs,
            'data': data,
        }

    # Vue de recherche pour le rapport
    @api.model
    def _get_search_domain(self, domain, context):
        if context.get('search_default_active'):
            domain = [('active', '=', True)] + domain
        return domain

    # Vue de liste pour le rapport
    @api.model
    def _get_report_tree_view(self):
        return """
            <tree string="Rapport Équipements" create="false" edit="false" delete="false">
                <field name="name"/>
                <field name="code"/>
                <field name="category_id"/>
                <field name="site_id"/>
                <field name="state"/>
                <field name="maintenance_count"/>
                <field name="next_maintenance_date"/>
            </tree>
        """

    # Action pour le rapport
    @api.model
    def action_equipment_report(self):
        return {
            'name': 'Rapport Équipements',
            'type': 'ir.actions.act_window',
            'res_model': 'gmao.equipment',
            'view_mode': 'tree,form,pivot,graph',
            'view_id': False,
            'domain': [],
            'context': {'search_default_active': 1},
            'help': """
                <p class="o_view_nocontent_smiling_face">
                    Aucun équipement trouvé
                </p>
            """
        }
