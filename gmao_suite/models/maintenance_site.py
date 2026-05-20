# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class MaintenanceSite(models.Model):
    _name = 'maintenance.site'
    _description = 'Site de maintenance'
    _rec_name = 'name'

    _sql_constraints = [
        ('unique_site_code_per_company',
         'UNIQUE(code, company_id)',
         "Le code de site doit etre unique au sein d'une meme societe."),
    ]

    name = fields.Char(string='Nom du site', required=True)
    code = fields.Char(string='Code du site', required=True, index=True)
    address = fields.Char(string='Adresse')
    city_id = fields.Many2one('res.city', string='Ville', required=True)
    state_id = fields.Many2one('res.country.state', string='État/Région', related='city_id.state_id', store=True)
    country_id = fields.Many2one('res.country', string='Pays', related='city_id.country_id', store=True)
    
    latitude = fields.Float(string='Latitude', digits=(10, 8))
    longitude = fields.Float(string='Longitude', digits=(11, 8))
    distance_from_office = fields.Float(string='Distance des bureaux (km)', digits=(10, 2))

    company_id = fields.Many2one(
        'res.company', string='Societe',
        default=lambda self: self.env.company, index=True,
    )
    active = fields.Boolean(default=True, string='Actif')

    # ------------------------------------------------------------------
    # Rapport metier site : equipements lies + KPI maintenance agreges
    # (non stockes : calcules a l'affichage du form-rapport).
    # ------------------------------------------------------------------
    equipment_ids = fields.One2many(
        'gmao.equipment', 'site_id', string='Équipements du site')
    report_nb_equipment = fields.Integer(
        string='Nombre d\'équipements', compute='_compute_report_kpis')
    report_nb_requests = fields.Integer(
        string='Nombre d\'interventions', compute='_compute_report_kpis')
    report_total_cost = fields.Monetary(
        string='Coût total maintenance', compute='_compute_report_kpis',
        currency_field='report_currency_id')
    report_downtime_total = fields.Float(
        string='Temps d\'arrêt cumulé (h)', compute='_compute_report_kpis')
    report_avg_mtbf = fields.Float(
        string='MTBF moyen (h)', compute='_compute_report_kpis')
    report_avg_mttr = fields.Float(
        string='MTTR moyen (h)', compute='_compute_report_kpis')
    report_pct_preventive = fields.Float(
        string='% préventif', compute='_compute_report_kpis')
    report_currency_id = fields.Many2one(
        'res.currency', compute='_compute_report_kpis')

    def _compute_report_kpis(self):
        Request = self.env['gmao.request']
        for site in self:
            requests = Request.search([('site_id', '=', site.id)])
            done = requests.filtered(lambda r: r.state == 'done')
            mtbfs = [r.mtbf for r in done if r.mtbf]
            mttrs = [r.mttr for r in done if r.mttr]
            preventive = requests.filtered(lambda r: r.maintenance_type == 'preventive')
            site.report_nb_equipment = len(site.equipment_ids)
            site.report_nb_requests = len(requests)
            site.report_total_cost = sum(requests.mapped('total_cost'))
            site.report_downtime_total = round(sum(requests.mapped('downtime')), 1)
            site.report_avg_mtbf = round(sum(mtbfs) / len(mtbfs), 1) if mtbfs else 0.0
            site.report_avg_mttr = round(sum(mttrs) / len(mttrs), 1) if mttrs else 0.0
            site.report_pct_preventive = round(
                len(preventive) / len(requests) * 100, 1) if requests else 0.0
            site.report_currency_id = site.company_id.currency_id

    @api.depends('name', 'code', 'city_id')
    def name_get(self):
        result = []
        for site in self:
            name = f"[{site.code}] {site.name} ({site.city_id.name})"
            result.append((site.id, name))
        return result

    @api.constrains('latitude', 'longitude')
    def _check_coordinates(self):
        for site in self:
            if site.latitude and (site.latitude < -90 or site.latitude > 90):
                raise ValidationError(_("La latitude doit être comprise entre -90 et 90."))
            if site.longitude and (site.longitude < -180 or site.longitude > 180):
                raise ValidationError(_("La longitude doit être comprise entre -180 et 180."))

    def compute_distance(self):
        # Cette méthode devrait être implémentée pour calculer la distance
        # entre le site et les bureaux principaux.
        # Vous pouvez utiliser une API de géolocalisation ou une formule de calcul de distance.
        pass

    def action_open_google_maps(self):
        """V2 : ouvre le site dans Google Maps (nouvel onglet du navigateur)."""
        self.ensure_one()
        if not (self.latitude and self.longitude):
            raise ValidationError(_(
                "Renseignez d'abord la latitude et la longitude du site."))
        url = "https://www.google.com/maps/search/?api=1&query=%s,%s" % (
            self.latitude, self.longitude)
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }