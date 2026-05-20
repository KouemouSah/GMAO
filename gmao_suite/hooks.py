# -*- coding: utf-8 -*-
"""
A6 : hook post-init pour seeder des donnees demo minimales si le module
est installe sur une base vide. Ne fait rien si des sites GMAO existent deja.
"""
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(cr, registry):
    """Cree un jeu de donnees demo complet si la base est vierge.

    Genere :
        - 3 sites geolocalises
        - 3 categories d'equipement
        - 5 equipements repartis
        - 2 equipes de maintenance avec chef + membres
        - 1 contrat de maintenance actif
        - 8 demandes d'intervention variees (etats + types + urgentes)

    Skip silencieusement si des sites existent deja.
    """
    from odoo import api, SUPERUSER_ID, fields
    from datetime import datetime, timedelta
    env = api.Environment(cr, SUPERUSER_ID, {})

    Site = env['maintenance.site']
    if Site.search_count([]) > 0:
        _logger.info("GMAO post_init : sites existants detectes, skip seed demo.")
        return

    # IMPORTANT : un seed demo ne doit JAMAIS bloquer l'install. On encapsule
    # tout dans try/except : en cas d'echec, on log et on laisse l'install
    # reussir (le module est installable meme sans donnees demo).
    try:
        _seed_demo_data(env, fields, datetime, timedelta)
    except Exception as e:
        _logger.warning(
            "GMAO post_init : seed demo partiel/echoue (install non bloquee). Detail : %s", e)


def _seed_demo_data(env, fields, datetime, timedelta):
    """Corps du seed demo, isole pour pouvoir etre wrappe en try/except."""
    Site = env['maintenance.site']

    # === Ressources de base : ville, employes ===
    city = env['res.city'].search([], limit=1)
    if not city:
        country = env['res.country'].search([('code', '=', 'FR')], limit=1) or env['res.country'].search([], limit=1)
        city = env['res.city'].create({
            'name': 'Demo City',
            'country_id': country.id,
        })

    # Quelques employes (creer si pas assez)
    Employee = env['hr.employee']
    employees = Employee.search([], limit=5)
    if len(employees) < 2:
        Partner = env['res.partner']
        for name in ['Jean Dupont', 'Marie Martin', 'Paul Bernard']:
            partner = Partner.create({'name': name, 'email': name.lower().replace(' ', '.') + '@demo.local'})
            Employee.create({'name': name, 'work_email': partner.email})
        employees = Employee.search([], limit=5)

    # === Categories ===
    Category = env['gmao.equipment.category']
    cat_climat = Category.search([('name', '=', 'Climatisation')], limit=1) or Category.create({'name': 'Climatisation'})
    cat_elec = Category.search([('name', '=', 'Electrique')], limit=1) or Category.create({'name': 'Electrique'})
    cat_meca = Category.search([('name', '=', 'Mecanique')], limit=1) or Category.create({'name': 'Mecanique'})

    # === 3 sites ===
    sites_data = [
        {'name': 'Atelier principal', 'code': 'SITE-001', 'city_id': city.id,
         'latitude': 48.8566, 'longitude': 2.3522},
        {'name': 'Entrepot Nord', 'code': 'SITE-002', 'city_id': city.id,
         'latitude': 50.6292, 'longitude': 3.0573},
        {'name': 'Centre logistique Sud', 'code': 'SITE-003', 'city_id': city.id,
         'latitude': 43.2965, 'longitude': 5.3698},
    ]
    sites = [Site.create(data) for data in sites_data]

    # === 2 equipes de maintenance ===
    # member_ids est REQUIS (NOT NULL) : on garantit toujours au moins 1 membre
    # (sinon contrainte violee => erreur SQL => transaction install cassee).
    Team = env['gmao.team']
    teams = []
    if len(employees) >= 1:
        leader = employees[0]
        members = employees[1:3] if len(employees) >= 2 else employees  # au moins le leader
        team_a = Team.create({
            'name': 'Equipe Maintenance Site Principal',
            'leader_id': leader.id,
            'member_ids': [(6, 0, members.ids or [leader.id])],
            'state': 'validated',
            # P2 : couverture (proximite) + competences (pour le scoring auto)
            'site_ids': [(6, 0, [sites[0].id])] if sites else False,
            'category_ids': [(6, 0, [cat_climat.id, cat_elec.id])],
        })
        teams.append(team_a)
        if len(employees) >= 3:
            leader2 = employees[-1]
            # Membres = tous sauf le leader2 ; fallback sur leader2 lui-meme si vide
            members2 = employees - leader2
            team_b = Team.create({
                'name': 'Equipe Maintenance Logistique',
                'leader_id': leader2.id,
                'member_ids': [(6, 0, members2.ids or [leader2.id])],
                'state': 'validated',
                'site_ids': [(6, 0, [s.id for s in sites[1:]])] if len(sites) > 1 else False,
                'category_ids': [(6, 0, [cat_meca.id, cat_climat.id, cat_elec.id])],
            })
            teams.append(team_b)

    # === 5 equipements ===
    Equipment = env['gmao.equipment']
    eq_specs = [
        ('Climatiseur central', 'EQP-001', sites[0], cat_climat, 90),
        ('Tableau electrique principal', 'EQP-002', sites[0], cat_elec, 180),
        ('Convoyeur logistique', 'EQP-003', sites[1], cat_meca, 60),
        ('Climatiseur entrepot', 'EQP-004', sites[1], cat_climat, 90),
        ('Groupe electrogene', 'EQP-005', sites[2], cat_elec, 365),
    ]
    equipments = []
    for i, (name, code, site, cat, period) in enumerate(eq_specs):
        team_id = teams[i % len(teams)].id if teams else False
        eq = Equipment.create({
            'name': name, 'code': code, 'site_id': site.id,
            'category_id': cat.id, 'period': period,
            'maintenance_team_id': team_id,
        })
        equipments.append(eq)

    # === 1 contrat de maintenance ===
    Contract = env['maintenance.contract']
    Partner = env['res.partner']
    client = Partner.search([('customer_rank', '>', 0)], limit=1) or Partner.create({
        'name': 'Client Demo SARL',
        'email': 'contact@demo-client.local',
        'customer_rank': 1,
    })
    Contract.create({
        'partner_id': client.id,
        'type': 'standard',
        'start_date': fields.Date.today() - timedelta(days=30),
        'end_date': fields.Date.today() + timedelta(days=335),
        'total_amount': 24000.0,
        'equipment_ids': [(6, 0, [e.id for e in equipments[:3]])] if equipments else False,
        'state': 'active',
        'note': 'Contrat de demo - maintenance preventive annuelle.',
    })

    # === 8 demandes de maintenance variees ===
    Request = env['gmao.request']
    partner_user = env.user.partner_id
    now = datetime.now()

    # Codes panne/intervention (seedes dans data/failure_code_data.xml) pour
    # alimenter les rapports d'intervention demo + l'analyse de recurrence.
    def _fc(xmlid):
        rec = env.ref('gmao_suite.%s' % xmlid, raise_if_not_found=False)
        return rec.id if rec else False
    fc_usure = _fc('failure_code_mec_usure')
    fc_vib = _fc('failure_code_mec_vibration')
    fc_ele_cc = _fc('failure_code_ele_court')
    fc_prev_ins = _fc('failure_code_prev_ins')
    fc_prev_lub = _fc('failure_code_prev_lub')
    # mix d'etats / types / dates pour alimenter le dashboard
    requests_data = [
        # En retard (schedule_date < now et state != done) - pour is_overdue
        {'description': 'Climatiseur en panne, fuite refrigerant',
         'equipment_id': equipments[0].id, 'user_id': partner_user.id,
         'system': 'phone', 'maintenance_type': 'corrective',
         'priority': '3', 'state': 'in_progress',
         'schedule_date': now - timedelta(days=2),
         'team_id': teams[0].id if teams else False,
         'technician_id': teams[0].leader_id.id if teams else False},
        # Preventive en cours
        {'description': 'Maintenance preventive trimestrielle climatiseur',
         'equipment_id': equipments[0].id, 'user_id': partner_user.id,
         'system': 'mail', 'maintenance_type': 'preventive',
         'priority': '2', 'state': 'to_validate',
         'schedule_date': now + timedelta(days=7),
         'team_id': teams[0].id if teams else False},
        # Demande nouvelle (urgente)
        {'description': 'Tableau electrique fait disjoncter, anomalies frequentes',
         'equipment_id': equipments[1].id, 'user_id': partner_user.id,
         'system': 'phone', 'maintenance_type': 'corrective',
         'priority': '4', 'state': 'new',
         'schedule_date': now + timedelta(days=1)},
        # Demande terminee (historique) AVEC rapport d'intervention
        {'description': 'Remplacement courroie convoyeur',
         'equipment_id': equipments[2].id, 'user_id': partner_user.id,
         'system': 'mail', 'maintenance_type': 'corrective',
         'priority': '2', 'state': 'done',
         'schedule_date': now - timedelta(days=20),
         'start_date': now - timedelta(days=20),
         'close_date': now - timedelta(days=19),
         'team_id': teams[1].id if len(teams) > 1 else (teams[0].id if teams else False),
         'failure_code_id': fc_usure, 'failure_severity': 'major',
         'symptom': "Glissement et bruit de la courroie du convoyeur.",
         'failure_cause': "Courroie d'entrainement usee (fin de vie).",
         'work_performed': "Remplacement de la courroie et reglage de la tension."},
        # Demande terminee historique 2 (preventif) AVEC rapport
        {'description': 'Verification capteurs convoyeur',
         'equipment_id': equipments[2].id, 'user_id': partner_user.id,
         'system': 'other', 'maintenance_type': 'preventive',
         'priority': '1', 'state': 'done',
         'schedule_date': now - timedelta(days=45),
         'start_date': now - timedelta(days=45),
         'close_date': now - timedelta(days=44),
         'failure_code_id': fc_prev_ins,
         'symptom': "Controle preventif planifie.",
         'failure_cause': "Inspection preventive (aucune anomalie).",
         'work_performed': "Verification et nettoyage des capteurs, RAS."},
        # === RECURRENCE : courroie convoyeur (EQP-003) re-usure x2 ===
        {'description': 'Courroie convoyeur a nouveau usee',
         'equipment_id': equipments[2].id, 'user_id': partner_user.id,
         'system': 'phone', 'maintenance_type': 'corrective',
         'priority': '3', 'state': 'done',
         'schedule_date': now - timedelta(days=120),
         'start_date': now - timedelta(days=120),
         'close_date': now - timedelta(days=119),
         'failure_code_id': fc_usure, 'failure_severity': 'major',
         'symptom': "Arret du convoyeur, courroie detendue.",
         'failure_cause': "Usure prematuree recurrente de la courroie.",
         'work_performed': "Remplacement courroie. Recurrence a surveiller (3e fois)."},
        {'description': 'Usure courroie convoyeur (recurrent)',
         'equipment_id': equipments[2].id, 'user_id': partner_user.id,
         'system': 'phone', 'maintenance_type': 'corrective',
         'priority': '3', 'state': 'done',
         'schedule_date': now - timedelta(days=220),
         'start_date': now - timedelta(days=220),
         'close_date': now - timedelta(days=219),
         'failure_code_id': fc_usure, 'failure_severity': 'major',
         'symptom': "Bruit et glissement courroie.",
         'failure_cause': "Usure courroie + desalignement poulie suspecte.",
         'work_performed': "Remplacement courroie + controle alignement."},
        # === RECURRENCE : tableau electrique (EQP-002) disjonctions x2 ===
        {'description': 'Disjonction tableau electrique',
         'equipment_id': equipments[1].id, 'user_id': partner_user.id,
         'system': 'phone', 'maintenance_type': 'corrective',
         'priority': '4', 'state': 'done',
         'schedule_date': now - timedelta(days=70),
         'start_date': now - timedelta(days=70),
         'close_date': now - timedelta(days=70),
         'failure_code_id': fc_ele_cc, 'failure_severity': 'critical',
         'symptom': "Disjoncteur general qui declenche.",
         'failure_cause': "Surcharge sur un depart + contact desserre.",
         'work_performed': "Resserrage connexions, equilibrage des charges."},
        {'description': 'Nouvelle disjonction tableau electrique',
         'equipment_id': equipments[1].id, 'user_id': partner_user.id,
         'system': 'phone', 'maintenance_type': 'corrective',
         'priority': '4', 'state': 'done',
         'schedule_date': now - timedelta(days=15),
         'start_date': now - timedelta(days=15),
         'close_date': now - timedelta(days=15),
         'failure_code_id': fc_ele_cc, 'failure_severity': 'critical',
         'symptom': "Coupure electrique repetee.",
         'failure_cause': "Court-circuit recurrent sur le meme depart.",
         'work_performed': "Remplacement disjoncteur. Investigation cause racine recommandee."},
        # Demande planifiee future
        {'description': 'Revision annuelle groupe electrogene',
         'equipment_id': equipments[4].id, 'user_id': partner_user.id,
         'system': 'mail', 'maintenance_type': 'preventive',
         'priority': '2', 'state': 'new',
         'schedule_date': now + timedelta(days=14)},
        # Demande corrective normale
        {'description': 'Bruit anormal climatiseur entrepot',
         'equipment_id': equipments[3].id, 'user_id': partner_user.id,
         'system': 'phone', 'maintenance_type': 'corrective',
         'priority': '2', 'state': 'to_validate',
         'schedule_date': now + timedelta(days=3)},
        # Demande annulee (test workflow)
        {'description': 'Demande de test annulee',
         'equipment_id': equipments[0].id, 'user_id': partner_user.id,
         'system': 'other', 'maintenance_type': 'corrective',
         'priority': '0', 'state': 'cancel',
         'schedule_date': now - timedelta(days=5)},
    ]
    # === Kits de pieces standard (auto-calage preventif) ===
    # Crees AVANT les demandes pour que les demandes preventives auto-chargent le kit.
    Kit = env['gmao.parts.kit']
    Product = env['product.product']
    # Produits demo (crees ici si pas encore presents, reutilises plus bas)
    kit_products = []
    for ref, pname, price in [
        ('PART-FILT', 'Filtre a air industriel', 45.0),
        ('PART-COUR', 'Courroie de transmission', 120.0),
        ('PART-FUS', 'Fusible 32A industriel', 18.0),
    ]:
        p = Product.search([('default_code', '=', ref)], limit=1)
        if not p:
            p = Product.create({
                'name': pname, 'default_code': ref, 'type': 'product',
                'list_price': price, 'standard_price': price * 0.7,
            })
        kit_products.append(p)
    # Kit par categorie Climatisation : filtre + fusible
    Kit.create({
        'name': 'Revision climatiseur (preventif)',
        'category_id': cat_climat.id,
        'line_ids': [
            (0, 0, {'product_id': kit_products[0].id, 'quantity': 1.0, 'part_nature': 'consumable'}),
            (0, 0, {'product_id': kit_products[2].id, 'quantity': 2.0, 'part_nature': 'consumable'}),
        ],
    })
    # Kit par categorie Mecanique : courroie
    Kit.create({
        'name': 'Entretien mecanique (preventif)',
        'category_id': cat_meca.id,
        'line_ids': [
            (0, 0, {'product_id': kit_products[1].id, 'quantity': 1.0, 'part_nature': 'consumable'}),
        ],
    })

    requests = []
    for data in requests_data:
        requests.append(Request.create(data))

    # === Pieces utilisees (lien avec demandes corrective) ===
    PartsUsed = env['maintenance.parts.used']
    Product = env['product.product']
    # Recupere ou cree 3 produits demo
    products_demo = []
    for ref, name, price in [
        ('PART-FILT', 'Filtre a air industriel', 45.0),
        ('PART-COUR', 'Courroie de transmission', 120.0),
        ('PART-FUS', 'Fusible 32A industriel', 18.0),
    ]:
        p = Product.search([('default_code', '=', ref)], limit=1)
        if not p:
            p = Product.create({
                'name': name,
                'default_code': ref,
                'type': 'product',
                'list_price': price,
                'standard_price': price * 0.7,
            })
        products_demo.append(p)

    stock_loc = env['stock.location'].search([('usage', '=', 'internal')], limit=1)
    tech_emp = employees[:1] if employees else env['hr.employee']
    today = fields.Date.today()

    # Allocations + Utilisations sur les demandes existantes
    corrective_requests = [r for r in requests if r.maintenance_type == 'corrective' and r.state != 'cancel']
    parts_specs = [
        # (intervention, product, quantity, state, nature)
        (corrective_requests[0] if corrective_requests else None, products_demo[0], 2.0, 'draft', 'consumable'),
        (corrective_requests[0] if corrective_requests else None, products_demo[2], 5.0, 'draft', 'consumable'),
        (corrective_requests[1] if len(corrective_requests) > 1 else None, products_demo[1], 1.0, 'reserved', 'billable'),
        (corrective_requests[2] if len(corrective_requests) > 2 else None, products_demo[2], 3.0, 'reserved', 'consumable'),
        (corrective_requests[2] if len(corrective_requests) > 2 else None, products_demo[0], 1.0, 'draft', 'billable'),
    ]
    for spec in parts_specs:
        intervention, product, qty, st, nature = spec
        if not intervention or not tech_emp or not stock_loc:
            continue
        # Note : on cree en draft/reserved (pas 'used') car action_use cree
        # un stock.move reel qui exige du stock disponible. Le seed ne garantit
        # pas de stock physique => on reste en draft/reserved pour la demo.
        PartsUsed.create({
            'intervention_id': intervention.id,
            'product_id': product.id,
            'quantity': qty,
            'usage_date': today,
            'withdrawal_date': today,
            'technician_id': tech_emp[0].id,
            'stock_location_id': stock_loc.id,
            'part_nature': nature,
            'state': st,
        })

    # === Inspections conformite & securite ===
    Conformite = env['maintenance.conformite.securite']
    inspector = client  # res.partner reutilise comme inspecteur
    conformite_specs = [
        (equipments[0], 'equipment', None, 'conforme', today - timedelta(days=30)),
        (equipments[1], 'equipment', None, 'non_conforme', today - timedelta(days=15)),
        (None, 'other', 'Verification extincteurs site principal', 'conforme', today - timedelta(days=10)),
        (equipments[4], 'equipment', None, 'action_requise', today - timedelta(days=5)),
    ]
    for eq, cat, obj_str, result, date in conformite_specs:
        Conformite.create({
            'category': cat,
            'equipment_id': eq.id if eq else False,
            'inspection_object': obj_str or False,
            'inspection_date': date,
            'inspector_id': inspector.id,
            'result': result,
            'observations': 'Inspection demo automatique.',
            'state': 'done' if result == 'conforme' else 'confirmed',
        })

    # === Evaluations efficacite energetique ===
    Efficacite = env['maintenance.efficacite.energetique']
    efficacite_specs = [
        (equipments[0], 4500.0, today - timedelta(days=60), 'c'),
        (equipments[0], 4200.0, today - timedelta(days=30), 'b'),  # variation -6.7%
        (equipments[3], 2800.0, today - timedelta(days=20), 'a'),
        (equipments[4], 8500.0, today - timedelta(days=15), 'd'),
    ]
    for eq, conso, date, rating in efficacite_specs:
        Efficacite.create({
            'equipment_id': eq.id,
            'measurement_date': date,
            'evaluator_id': inspector.id,
            'energy_consumption': conso,
            'efficiency_rating': rating,  # champ requis (NOT NULL)
            'observations': 'Mesure demo, baseline ou comparaison.',
        })

    _logger.info(
        "GMAO post_init : seed demo data cree (%s sites, %s equipements, %s equipes, "
        "1 contrat, %s demandes, %s pieces, %s inspections, %s mesures energie)",
        len(sites_data), len(eq_specs), len(teams), len(requests_data),
        len([s for s in parts_specs if s[0]]), len(conformite_specs), len(efficacite_specs),
    )


def uninstall_hook(cr, registry):
    """Cleanup optionnel a la desinstallation (place-holder)."""
    _logger.info("GMAO uninstall_hook : module desinstalle (aucun cleanup specifique).")
