# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

class ConformiteSecurite(models.Model):
    _name = 'maintenance.conformite.securite'
    _description = 'Conformité et Sécurité'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Référence', required=True, copy=False, readonly=True, default='New')
    company_id = fields.Many2one(
        'res.company', string='Societe',
        default=lambda self: self.env.company, index=True,
    )
    category = fields.Selection([
        ('equipment', 'Équipement'),
        ('other', 'Autre')
    ], string='Catégorie d\'inspection', required=True, tracking=True)
    equipment_id = fields.Many2one('gmao.equipment', string='Équipement')
    inspection_object = fields.Char(string='Objet d\'inspection')
    inspection_date = fields.Date(string='Date d\'inspection', required=True)
    inspector_id = fields.Many2one('res.partner', string='Inspecteur', required=True)
    
    result = fields.Selection([
        ('conforme', 'Conforme'),
        ('non_conforme', 'Non Conforme'),
        ('action_requise', 'Action Requise')
    ], string='Résultat', required=True)
    
    observations = fields.Text(string='Observations')
    next_inspection_date = fields.Date(string='Prochaine date d\'inspection')
    
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('confirmed', 'Confirmé'),
        ('done', 'Terminé'),
        ('cancelled', 'Annulé')
    ], string='Statut', default='draft', tracking=True)

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('maintenance.conformite.securite') or 'New'
        return super(ConformiteSecurite, self).create(vals)

    # ------------------------------------------------------------------
    # Workflow d'etat (boutons du formulaire). Ces methodes manquaient :
    # tous les boutons (Confirmer/Terminer/Annuler/Remettre en brouillon)
    # crashaient avec AttributeError. Bug corrige.
    # ------------------------------------------------------------------
    def action_confirm(self):
        self.write({'state': 'confirmed'})
        # P6.5 : auto-generation d'une demande de maintenance (brouillon)
        # quand l'inspection revele un probleme (non conforme / action requise)
        # sur un equipement. Anti-doublon via origin_inspection_id.
        for rec in self:
            if (rec.category == 'equipment' and rec.equipment_id
                    and rec.result in ('non_conforme', 'action_requise')):
                rec._create_maintenance_request_from_inspection(raise_if_no_equipment=False)

    def _create_maintenance_request_from_inspection(self, raise_if_no_equipment=True):
        """Cree une demande de maintenance corrective a l'etat 'new' (brouillon
        en attente de validation) depuis l'inspection. Idempotent : ne recree
        pas si une demande liee a cette inspection existe deja. Retourne la
        demande (existante ou creee), ou False."""
        self.ensure_one()
        if self.category != 'equipment' or not self.equipment_id:
            if raise_if_no_equipment:
                raise UserError(_(
                    "Une demande de maintenance ne peut être générée que pour "
                    "une inspection liée à un équipement."))
            return False
        Request = self.env['gmao.request']
        existing = Request.search([('origin_inspection_id', '=', self.id)], limit=1)
        if existing:
            return existing
        result_label = dict(self._fields['result'].selection).get(self.result, self.result)
        desc = _("Suite à l'inspection de conformité %s (%s) — résultat : %s.") % (
            self.name, self.inspection_date or '', result_label)
        if self.observations:
            desc += "\n%s" % self.observations
        return Request.create({
            'description': desc,
            'equipment_id': self.equipment_id.id,
            'user_id': self.inspector_id.id or self.env.user.partner_id.id,
            'maintenance_type': 'corrective',
            'company_id': self.company_id.id,
            'origin_inspection_id': self.id,
        })

    def action_create_maintenance_request(self):
        """Bouton : genere (ou rouvre) la demande de maintenance liee et
        l'affiche."""
        self.ensure_one()
        request = self._create_maintenance_request_from_inspection()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Demande de maintenance"),
            'res_model': 'gmao.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_draft(self):
        self.write({'state': 'draft'})

    @api.onchange('category')
    def _onchange_category(self):
        if self.category == 'equipment':
            self.inspection_object = False
        else:
            self.equipment_id = False

    @api.constrains('category', 'equipment_id', 'inspection_object', 'result')
    def _check_category_fields(self):
        for record in self:
            if record.category == 'equipment' and not record.equipment_id:
                raise ValidationError(_("Un equipement doit etre selectionne pour la categorie 'Equipement'."))
            elif record.category == 'other' and not record.inspection_object:
                raise ValidationError(_("L'objet d'inspection doit etre specifie pour la categorie 'Autre'."))
            if record.category and not record.result:
                raise ValidationError(_("Le resultat doit etre selectionne une fois que la categorie est remplie."))

    @api.onchange('result')
    def _onchange_result(self):
        if self.result:
            if not self.inspection_date:
                raise ValidationError(_("Veuillez d'abord remplir le champ 'Date d'inspection'."))
            if self.result == 'conforme':
                self.next_inspection_date = fields.Date.add(self.inspection_date, months=12)
            elif self.result == 'action_requise':
                self.next_inspection_date = fields.Date.add(self.inspection_date, months=1)
            else:
                self.next_inspection_date = False  # Pour le cas 'non_conforme' ou autre

    @api.constrains('inspection_date', 'next_inspection_date', 'inspector_id', 'category', 'result')
    def _check_inspection_dates(self):
        for record in self:
            if not record.inspector_id:
                raise ValidationError(_("L'inspecteur doit etre selectionne."))
            if not record.inspection_date:
                raise ValidationError(_("La date d'inspection doit etre remplie."))
            if not record.category:
                raise ValidationError(_("La categorie doit etre remplie."))
            if not record.result:
                raise ValidationError(_("Le resultat doit etre selectionne."))
            if record.next_inspection_date and record.inspection_date > record.next_inspection_date:
                raise ValidationError(_("La prochaine date d'inspection doit etre posterieure a la date d'inspection actuelle."))
