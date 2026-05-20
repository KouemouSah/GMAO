from odoo import models, fields

class MaintenanceEquipmentCategory(models.Model):
    _name = 'gmao.equipment.category'
    _description = 'Catégorie d\'équipement GMAO'

    name = fields.Char(string='Nom', required=True)
    code = fields.Char(string='Code')
    description = fields.Text(string='Description')
    parent_id = fields.Many2one('gmao.equipment.category', string='Catégorie parente')
    child_ids = fields.One2many('gmao.equipment.category', 'parent_id', string='Sous-catégories')
    equipment_count = fields.Integer(string='Nombre d\'équipements', compute='_compute_equipment_count')
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.company)
    def _compute_equipment_count(self):
        for category in self:
            category.equipment_count = self.env['gmao.equipment'].search_count([('category_id', '=', category.id)])