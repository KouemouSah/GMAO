from odoo import models, fields, api

class ResUsersGMAO(models.Model):
    _inherit = 'res.users'

    gmao_admin = fields.Boolean(string="Administrateur général GMAO", 
                                help="Donne tous les droits sur tous les modèles GMAO")

    parts_used_profile = fields.Selection([
        ('reader', 'Lecteur'),
        ('creator', 'Créateur'),
        ('user', 'Utilisateur'),
        ('admin', 'Administrateur')
    ], string='Profil Pièces utilisées', default='reader')

    team_profile = fields.Selection([
        ('reader', 'Lecteur'),
        ('creator', 'Créateur'),
        ('user', 'Utilisateur'),
        ('admin', 'Administrateur')
    ], string='Profil Équipe', default='reader')

    contract_profile = fields.Selection([
        ('reader', 'Lecteur'),
        ('creator', 'Créateur'),
        ('user', 'Utilisateur'),
        ('admin', 'Administrateur')
    ], string='Profil Contrat', default='reader')

    efficacite_energetique_profile = fields.Selection([
        ('reader', 'Lecteur'),
        ('creator', 'Créateur'),
        ('user', 'Utilisateur'),
        ('admin', 'Administrateur')
    ], string='Profil Efficacité énergétique', default='reader')

    equipment_profile = fields.Selection([
        ('reader', 'Lecteur'),
        ('creator', 'Créateur'),
        ('user', 'Utilisateur'),
        ('admin', 'Administrateur')
    ], string='Profil Équipement', default='reader')

    site_profile = fields.Selection([
        ('reader', 'Lecteur'),
        ('creator', 'Créateur'),
        ('user', 'Utilisateur'),
        ('admin', 'Administrateur')
    ], string='Profil Site', default='reader')

    equipment_category_profile = fields.Selection([
        ('reader', 'Lecteur'),
        ('creator', 'Créateur'),
        ('user', 'Utilisateur'),
        ('admin', 'Administrateur')
    ], string='Profil Catégorie d\'équipement', default='reader')
    
    request_profile = fields.Selection([
    ('reader', 'Lecteur'),
    ('creator', 'Créateur'),
    ('user', 'Utilisateur'),
    ('admin', 'Administrateur')
], string='Profil Demande de maintenance', default='reader')

    @api.onchange('gmao_admin')
    def _onchange_gmao_admin(self):
        """Toggle 'Administrateur global GMAO'.

        Plutot que de cascader 32 assignations groups_id via les *_profile
        (qui peuvent etre eat par Odoo entre onchanges), on assigne en UNE SEULE
        operation atomique : ajout/retrait du groupe global. Celui-ci implique
        deja tous les groupes admin/user/creator/reader via 'implied_ids' definis
        dans security/maintenance_security.xml (33 groupes auto-propages au save).
        """
        global_admin = self.env.ref('gmao_suite.group_gmao_admin', raise_if_not_found=False)
        if not global_admin:
            return
        if self.gmao_admin:
            # Ajoute le groupe global. Au save(), Odoo propage les implied_ids.
            self.groups_id = [(4, global_admin.id, 0)]
            # Optionnel : aligner les *_profile pour coherence d'affichage
            for fld in ('parts_used_profile', 'team_profile', 'contract_profile',
                        'efficacite_energetique_profile', 'equipment_profile',
                        'site_profile', 'equipment_category_profile', 'request_profile'):
                setattr(self, fld, 'admin')
        else:
            # Retire le groupe global ET tous les groupes GMAO impliques en cascade.
            to_remove = self.env['res.groups'].search([
                ('category_id', '=', self.env.ref('gmao_suite.module_category_maintenance').id),
            ])
            self.groups_id = [(3, gid, 0) for gid in to_remove.ids]
            for fld in ('parts_used_profile', 'team_profile', 'contract_profile',
                        'efficacite_energetique_profile', 'equipment_profile',
                        'site_profile', 'equipment_category_profile', 'request_profile'):
                setattr(self, fld, 'reader')

    @api.onchange('parts_used_profile', 'team_profile', 'contract_profile',
                  'efficacite_energetique_profile', 'equipment_profile',
                  'site_profile', 'equipment_category_profile', 'request_profile')
    def _onchange_profiles(self):
        """Met a jour groups_id atomiquement quand un profil change.

        Construit la liste complete des commandes (3,...) (retraits) et (4,...)
        (ajouts) en UNE SEULE assignation a groups_id pour ce domaine, evitant
        ainsi le bug d'onchange en cascade. Les groupes inferieurs sont automa-
        tiquement implies par le niveau cible via implied_ids.
        """
        domains = {
            'parts_used': 'gmao_suite.group_parts_used_',
            'team': 'gmao_suite.group_maintenance_team_',
            'contract': 'gmao_suite.group_maintenance_contract_',
            'efficacite_energetique': 'gmao_suite.group_efficacite_energetique_',
            'equipment': 'gmao_suite.group_maintenance_equipment_',
            'site': 'gmao_suite.group_maintenance_site_',
            'equipment_category': 'gmao_suite.group_maintenance_equipment_category_',
            'request': 'gmao_suite.group_request_',
        }
        ops = []
        for domain, prefix in domains.items():
            profile = getattr(self, f'{domain}_profile', None)
            if not profile:
                continue
            for level in ('reader', 'creator', 'user', 'admin'):
                grp = self.env.ref(f'{prefix}{level}', raise_if_not_found=False)
                if not grp:
                    continue
                ops.append((4 if level == profile else 3, grp.id, 0))
        if ops:
            self.groups_id = ops

    # ------------------------------------------------------------------
    # PERSISTANCE FIABLE de gmao_admin (create/write).
    #
    # Pourquoi pas l'onchange seul : la vue form de res.users possede un
    # widget special (sel_groups_/in_group_) qui RECONSTRUIT groups_id au save
    # a partir des cases affichees, ECRASANT toute modif faite par un onchange
    # custom sur groups_id. Resultat : cocher 'gmao_admin' ne persistait pas.
    #
    # Solution : on applique le groupe APRES super().create/write (donc apres
    # la reconstruction native). Odoo propage alors les trans_implied_ids
    # (les 33 groupes GMAO) automatiquement.
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        for user in users:
            if user.gmao_admin:
                user._apply_gmao_admin_groups()
        return users

    def write(self, vals):
        res = super().write(vals)
        if 'gmao_admin' in vals:
            for user in self:
                if vals['gmao_admin']:
                    user._apply_gmao_admin_groups()
                else:
                    user._remove_gmao_groups()
        return res

    def _apply_gmao_admin_groups(self):
        """Ajoute le groupe global GMAO ; Odoo propage les implied_ids (33 groupes)."""
        self.ensure_one()
        grp = self.env.ref('gmao_suite.group_gmao_admin', raise_if_not_found=False)
        if grp:
            # write direct sur groups_id (pas de 'gmao_admin' dans vals => pas de recursion)
            self.sudo().write({'groups_id': [(4, grp.id)]})

    def _remove_gmao_groups(self):
        """Retire tous les groupes de la categorie GMAO Suite."""
        self.ensure_one()
        cat = self.env.ref('gmao_suite.module_category_maintenance', raise_if_not_found=False)
        if not cat:
            return
        gmao_groups = self.env['res.groups'].search([('category_id', '=', cat.id)])
        if gmao_groups:
            self.sudo().write({'groups_id': [(3, g.id) for g in gmao_groups]})