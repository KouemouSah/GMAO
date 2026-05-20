# -*- coding: utf-8 -*-
"""Re-synchronise les utilisateurs deja marques `gmao_admin=True`.

Contexte : le champ booleen `gmao_admin` a existe AVANT l'override
create/write qui applique reellement le groupe `group_gmao_admin`
(et propage ses 8 groupes admin implicites). Les utilisateurs coches
avant ce correctif se retrouvent donc avec `gmao_admin=True` mais sans
aucun groupe GMAO -> ils ne voient pas les menus.

Un simple redemarrage / -u ne re-declenche pas write() sur ces users.
Cette migration force la synchronisation une fois, de maniere idempotente.
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    grp = env.ref('gmao_suite.group_gmao_admin', raise_if_not_found=False)
    if not grp:
        return
    users = env['res.users'].search([('gmao_admin', '=', True)])
    fixed = 0
    for user in users:
        if grp not in user.groups_id:
            # write (4, ...) declenche la propagation native des implied_ids
            user.sudo().write({'groups_id': [(4, grp.id)]})
            fixed += 1
    if fixed:
        import logging
        logging.getLogger(__name__).info(
            "gmao_suite: %s utilisateur(s) gmao_admin re-synchronise(s) "
            "dans group_gmao_admin", fixed)
