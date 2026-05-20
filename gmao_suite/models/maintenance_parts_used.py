# -*- coding: utf-8 -*-
"""
Pieces utilisees en maintenance — refonte ERP 2026.

Distingue 2 natures (cf besoin metier) :
  - 'consumable' : materiel consomme en interne pour reparer (impute en COUT
    a l'intervention, valorise au standard_price / cout).
  - 'billable'   : piece refacturable au client (valorisee au list_price /
    prix de vente, peut generer une facture account.move).

Integration stock native (P3) :
  - La validation (action_use) cree un vrai stock.move depuis l'emplacement
    magasin vers un emplacement de consommation (inventory loss), garantissant
    tracabilite + valorisation comptable.
  - Le reapprovisionnement est delegue a stock.warehouse.orderpoint natif
    (regles min/max), pas recode ici.
"""
import logging
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class MaintenancePartsUsed(models.Model):
    _name = 'maintenance.parts.used'
    _description = 'Pieces utilisees en maintenance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'usage_date desc, id desc'

    _sql_constraints = [
        ('unique_name', 'unique(name)', 'La reference doit etre unique.'),
    ]

    # === Identification ===
    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True,
        default='New', index=True)
    intervention_id = fields.Many2one(
        'gmao.request', string='Intervention', required=True,
        tracking=True, index=True, ondelete='cascade')
    product_id = fields.Many2one(
        'product.product', string='Piece', required=True,
        tracking=True, index=True)
    quantity = fields.Float(string='Quantite', default=1.0, required=True, tracking=True)
    serial_number = fields.Char(string='Numero de serie')
    usage_date = fields.Date(string="Date d'utilisation", default=fields.Date.context_today, required=True)
    withdrawal_date = fields.Date(string='Date de retrait', required=True, default=fields.Date.context_today)
    technician_id = fields.Many2one('hr.employee', string='Technicien', required=True)
    stock_location_id = fields.Many2one(
        'stock.location', string='Emplacement magasin', required=True,
        domain="[('usage', '=', 'internal')]",
        default=lambda self: self._default_stock_location())
    company_id = fields.Many2one('res.company', string='Societe', default=lambda self: self.env.company)
    notes = fields.Text(string='Notes')

    # === P2 : nature consommable vs facturable ===
    part_nature = fields.Selection([
        ('consumable', 'Consommable interne'),
        ('billable', 'Refacturable au client'),
    ], string='Nature', default='consumable', required=True, tracking=True,
       help="Consommable : impute en cout a l'intervention.\n"
            "Refacturable : valorise au prix de vente, peut generer une facture client.")

    # === P1 : separation COUT (interne) vs PRIX DE VENTE (refacturation) ===
    unit_cost = fields.Float(
        string='Cout unitaire', related='product_id.standard_price', readonly=True,
        help="Cout d'acquisition de la piece (standard_price). Sert a l'imputation interne.")
    total_cost = fields.Float(
        string='Cout total', compute='_compute_amounts', store=True,
        help="quantite x cout unitaire. Impute a l'intervention.")
    unit_sale_price = fields.Float(
        string='Prix de vente unitaire', related='product_id.list_price', readonly=True,
        help="Prix de vente (list_price). Utilise uniquement si refacturable.")
    total_sale_price = fields.Float(
        string='Total refacturable', compute='_compute_amounts', store=True,
        help="quantite x prix de vente. Montant refacture au client si billable.")
    margin = fields.Float(
        string='Marge', compute='_compute_amounts', store=True,
        help="total_sale_price - total_cost (si refacturable).")

    # === Workflow ===
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('reserved', 'Reserve'),
        ('used', 'Utilisee'),
        ('cancelled', 'Annulee'),
    ], string='Statut', default='draft', tracking=True, index=True)

    # === Stock (lecture seule, delegue au natif) ===
    current_stock = fields.Float(
        string='Stock disponible', compute='_compute_current_stock',
        help="Quantite disponible dans l'emplacement magasin (live, via stock.quant).")
    stock_move_id = fields.Many2one(
        'stock.move', string='Mouvement de stock', readonly=True, copy=False,
        help="Mouvement stock genere a la validation (tracabilite).")

    # === P2 : refacturation ===
    invoice_line_id = fields.Many2one(
        'account.move.line', string='Ligne de facture', readonly=True, copy=False)
    invoice_id = fields.Many2one(
        'account.move', string='Facture', related='invoice_line_id.move_id',
        readonly=True, store=True)
    is_invoiced = fields.Boolean(string='Facture', compute='_compute_is_invoiced', store=True)

    # ------------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------------
    @api.model
    def _default_stock_location(self):
        """Premier emplacement interne de la societe courante.

        On filtre par societe (+ emplacements partages company_id=False) pour
        eviter d'affecter une location d'une autre societe, ce qui declenche
        la regle multi-societe native de stock.location a la lecture.
        """
        loc = self.env['stock.location'].search([
            ('usage', '=', 'internal'),
            ('company_id', 'in', [self.env.company.id, False]),
        ], limit=1)
        return loc.id if loc else False

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('maintenance.parts.used') or 'New'
        return super(MaintenancePartsUsed, self).create(vals)

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('quantity', 'unit_cost', 'unit_sale_price', 'part_nature')
    def _compute_amounts(self):
        """P1 : calcule cout interne ET montant refacturable separement."""
        for record in self:
            record.total_cost = record.quantity * record.unit_cost
            record.total_sale_price = record.quantity * record.unit_sale_price
            record.margin = (record.total_sale_price - record.total_cost
                             if record.part_nature == 'billable' else 0.0)

    @api.depends('product_id', 'stock_location_id')
    def _compute_current_stock(self):
        for record in self:
            if record.product_id and record.stock_location_id:
                record.current_stock = self.env['stock.quant']._get_available_quantity(
                    record.product_id, record.stock_location_id)
            else:
                record.current_stock = 0.0

    @api.depends('invoice_line_id')
    def _compute_is_invoiced(self):
        for record in self:
            record.is_invoiced = bool(record.invoice_line_id)

    # ------------------------------------------------------------------
    # Contraintes
    # ------------------------------------------------------------------
    @api.constrains('quantity')
    def _check_quantity(self):
        for record in self:
            if record.quantity <= 0:
                raise ValidationError(_("La quantite doit etre superieure a zero."))

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def action_reserve(self):
        """Reserve la piece (verifie le stock disponible)."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Cette piece ne peut plus etre reservee."))
        if self.quantity > self.current_stock:
            raise UserError(_("Stock insuffisant. Disponible : %s") % self.current_stock)
        self.write({'state': 'reserved'})

    def action_use(self):
        """Valide la consommation : cree le stock.move reel (P3).

        Le mouvement va de l'emplacement magasin vers l'emplacement de
        consommation (inventory loss) = sortie de stock tracee + valorisee.
        """
        self.ensure_one()
        if self.state not in ('draft', 'reserved'):
            raise UserError(_("Cette piece a deja ete utilisee ou annulee."))
        if not self.withdrawal_date:
            raise UserError(_("Veuillez specifier la date de retrait."))
        if self.quantity > self.current_stock:
            raise UserError(_("Stock insuffisant. Disponible : %s") % self.current_stock)

        move = self._create_stock_move()
        self.write({'state': 'used', 'stock_move_id': move.id})
        self.message_post(body=_("Piece consommee : %s x %s (cout %.2f).") % (
            self.quantity, self.product_id.display_name, self.total_cost))

    def _create_stock_move(self):
        """P3 : cree et valide un stock.move de sortie."""
        self.ensure_one()
        # Emplacement de consommation : 'inventory loss' (virtual) de la societe
        scrap_loc = self.env['stock.location'].search([
            ('scrap_location', '=', True),
            ('company_id', 'in', (self.company_id.id, False)),
        ], limit=1)
        if not scrap_loc:
            scrap_loc = self.env.ref('stock.stock_location_scrapped', raise_if_not_found=False)
        if not scrap_loc:
            # Fallback : un emplacement virtuel inventory
            scrap_loc = self.env['stock.location'].search([('usage', '=', 'inventory')], limit=1)
        if not scrap_loc:
            raise UserError(_("Aucun emplacement de consommation (scrap/inventory) trouve."))

        move = self.env['stock.move'].create({
            'name': _("Maintenance %s - %s") % (self.intervention_id.name, self.product_id.display_name),
            'product_id': self.product_id.id,
            'product_uom_qty': self.quantity,
            'product_uom': self.product_id.uom_id.id,
            'location_id': self.stock_location_id.id,
            'location_dest_id': scrap_loc.id,
            'company_id': self.company_id.id,
            'origin': self.intervention_id.name,
        })
        move._action_confirm()
        move._action_assign()
        # Forcer la quantite faite
        for ml in move.move_line_ids:
            ml.qty_done = ml.product_uom_qty
        if not move.move_line_ids:
            move._set_quantity_done(self.quantity)
        move._action_done()
        return move

    def action_invoice(self):
        """P2 : genere une facture client pour les pieces refacturables."""
        self.ensure_one()
        if self.part_nature != 'billable':
            raise UserError(_("Seules les pieces 'Refacturable au client' peuvent etre facturees."))
        if self.invoice_line_id:
            raise UserError(_("Cette piece est deja facturee (%s).") % self.invoice_id.name)
        partner = self.intervention_id.user_id
        if not partner:
            raise UserError(_("L'intervention n'a pas de client (user_id) pour la facturation."))

        # Odoo 13 : le champ s'appelle 'type' (pas 'move_type' qui est Odoo 14+).
        # On cherche une facture brouillon existante pour ce client + cette intervention.
        invoice = self.env['account.move'].search([
            ('partner_id', '=', partner.id),
            ('type', '=', 'out_invoice'),
            ('state', '=', 'draft'),
            ('invoice_origin', '=', self.intervention_id.name),
        ], limit=1)
        line_vals = {
            'product_id': self.product_id.id,
            'name': _("%s (intervention %s)") % (self.product_id.display_name, self.intervention_id.name),
            'quantity': self.quantity,
            'price_unit': self.unit_sale_price,
        }
        if not invoice:
            # Creation via invoice_line_ids (one2many) = Odoo gere journal + comptes
            # via les onchange/_compute natifs. Plus robuste que creer la ligne a part.
            invoice = self.env['account.move'].with_context(
                default_type='out_invoice').create({
                'type': 'out_invoice',
                'partner_id': partner.id,
                'invoice_origin': self.intervention_id.name,
                'invoice_line_ids': [(0, 0, line_vals)],
            })
            line = invoice.invoice_line_ids[:1]
        else:
            line = self.env['account.move.line'].with_context(
                check_move_validity=False).create(dict(line_vals, move_id=invoice.id))
        self.invoice_line_id = line.id if line else False
        return self.action_view_invoice()

    def action_view_invoice(self):
        """Ouvre la facture liee."""
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_("Aucune facture liee a cette piece."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Facture'),
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_cancel(self):
        """Annule. Si un mouvement stock existe deja, cree un mouvement inverse."""
        self.ensure_one()
        if self.state == 'used' and self.stock_move_id:
            # Mouvement retour (consommation -> magasin)
            return_move = self.env['stock.move'].create({
                'name': _("Retour maintenance %s") % self.name,
                'product_id': self.product_id.id,
                'product_uom_qty': self.quantity,
                'product_uom': self.product_id.uom_id.id,
                'location_id': self.stock_move_id.location_dest_id.id,
                'location_dest_id': self.stock_location_id.id,
                'company_id': self.company_id.id,
            })
            return_move._action_confirm()
            return_move._action_assign()
            for ml in return_move.move_line_ids:
                ml.qty_done = ml.product_uom_qty
            if not return_move.move_line_ids:
                return_move._set_quantity_done(self.quantity)
            return_move._action_done()
        self.write({'state': 'cancelled'})

    def action_draft(self):
        self.write({'state': 'draft'})

    # ------------------------------------------------------------------
    # CRON (P3 : delegation a orderpoint natif, on garde juste un check)
    # ------------------------------------------------------------------
    @api.model
    def _cron_recompute_stock_alerts(self):
        """Conserve par compat manifest cron. Le reappro est gere par les
        regles stock.warehouse.orderpoint natives. Ici on log juste les
        produits sous le seuil pour info.
        """
        Orderpoint = self.env['stock.warehouse.orderpoint']
        low = Orderpoint.search([])
        flagged = low.filtered(lambda o: o.qty_on_hand < o.product_min_qty) if low else low
        if flagged:
            _logger.info("GMAO : %s produit(s) sous le seuil de reappro (orderpoint natif).", len(flagged))

    @api.model
    def _cron_update_forecast_demand(self):
        """Obsolete : la prevision est geree par les regles de reappro natives.
        Conserve en no-op pour compat manifest cron (a retirer en v3)."""
        return True

    # ------------------------------------------------------------------
    # Rapport
    # ------------------------------------------------------------------
    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'maintenance.parts.used',
            'docs': docs,
            'data': data,
        }
