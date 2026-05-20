# -*- coding: utf-8 -*-
"""P6/P3 — Peuplement des donnees de pannes au -u (le post_init_hook de seed
ne s'execute QU'A l'installation, pas a l'upgrade ; les graphes 'pannes'
restaient donc vides apres un simple -u).

1) Backfill : assigne un code panne + cause + travaux aux demandes 'done' qui
   n'ont pas de rapport (heuristique sur la description / le type). Idempotent
   (ne touche que les demandes sans failure_code_id).
2) Recurrence demo : cree quelques demandes correctives recurrentes sur les
   equipements de demo (EQP-002 tableau, EQP-003 convoyeur) S'ILS EXISTENT et
   si elles n'existent pas deja -> alimente l'analyse de recurrence sur l'essai.
   Sur une base sans ces equipements demo, rien n'est cree.
"""
from datetime import datetime, timedelta
from odoo import api, SUPERUSER_ID


def _fc(env, xmlid):
    rec = env.ref('gmao_suite.%s' % xmlid, raise_if_not_found=False)
    return rec if rec else env['gmao.failure.code'].browse()


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Request = env['gmao.request']

    code_usure = _fc(env, 'failure_code_mec_usure')
    code_ele = _fc(env, 'failure_code_ele_court')
    code_prev = _fc(env, 'failure_code_prev_ins')
    code_aut = _fc(env, 'failure_code_aut')

    # --- 1) Backfill des demandes 'done' sans rapport ---
    done_no_report = Request.search([
        ('state', '=', 'done'), ('failure_code_id', '=', False)])
    for req in done_no_report:
        desc = (req.description or '').lower()
        if req.maintenance_type == 'preventive':
            code = code_prev
        elif any(k in desc for k in ('courroie', 'usure', 'roulement', 'mecan')):
            code = code_usure
        elif any(k in desc for k in ('electr', 'disjonc', 'court', 'tableau')):
            code = code_ele
        else:
            code = code_aut
        if not code:
            continue
        req.write({
            'failure_code_id': code.id,
            'failure_severity': 'major' if req.maintenance_type == 'corrective' else False,
            'failure_cause': req.failure_cause or
            "Donnee historique : rapport renseigne a posteriori (migration).",
            'work_performed': req.work_performed or
            "Intervention cloturee avant la mise en place du rapport structure.",
        })

    # --- 2) Recurrence demo (uniquement si equipements de demo presents) ---
    Equipment = env['gmao.equipment']
    partner = env['res.users'].browse(SUPERUSER_ID).partner_id
    now = datetime.now()
    eqp_conv = Equipment.search([('code', '=', 'EQP-003')], limit=1)
    eqp_tab = Equipment.search([('code', '=', 'EQP-002')], limit=1)

    demo_rows = []
    if eqp_conv and code_usure:
        demo_rows += [
            ("Courroie convoyeur a nouveau usee", eqp_conv, code_usure, 120,
             "Usure prematuree recurrente de la courroie.",
             "Remplacement courroie. Recurrence a surveiller."),
            ("Usure courroie convoyeur (recurrent)", eqp_conv, code_usure, 220,
             "Usure courroie + desalignement poulie suspecte.",
             "Remplacement courroie + controle alignement."),
        ]
    if eqp_tab and code_ele:
        demo_rows += [
            ("Disjonction tableau electrique", eqp_tab, code_ele, 70,
             "Surcharge sur un depart + contact desserre.",
             "Resserrage connexions, equilibrage des charges."),
            ("Nouvelle disjonction tableau electrique", eqp_tab, code_ele, 15,
             "Court-circuit recurrent sur le meme depart.",
             "Remplacement disjoncteur. Cause racine a investiguer."),
        ]

    for desc, eq, code, days_ago, cause, work in demo_rows:
        # idempotent : ne pas recreer si deja present
        if Request.search_count([('description', '=', desc), ('equipment_id', '=', eq.id)]):
            continue
        d0 = now - timedelta(days=days_ago)
        Request.create({
            'description': desc,
            'equipment_id': eq.id,
            'user_id': partner.id,
            'system': 'phone',
            'maintenance_type': 'corrective',
            'priority': '3',
            'state': 'done',
            'schedule_date': d0,
            'start_date': d0,
            'close_date': d0 + timedelta(hours=4),
            'failure_code_id': code.id,
            'failure_severity': 'major',
            'failure_cause': cause,
            'work_performed': work,
        })
