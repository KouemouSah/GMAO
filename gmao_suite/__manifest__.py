# -*- coding: utf-8 -*-
{
    'name': 'GMAO Suite',
    'version': '13.0.2.0.24',
    'category': 'Maintenance',
    'summary': 'Gestion de Maintenance Assistee par Ordinateur (GMAO) - Native Odoo 13 CE',
    'description': """
GMAO Suite — Computerized Maintenance Management System
========================================================

Module complet de Gestion de Maintenance Assistée par Ordinateur pour Odoo 13 Community Edition.

Fonctionnalités principales :

* Sites, équipements (coût cumulé, ratio coût/valeur, recommandation de remplacement) et catégories
* Demandes correctives & préventives — workflow complet + génération préventive automatique (CRON)
* Rapport d'intervention structuré : codes panne/activité (catalogue), symptôme, cause racine,
  travaux, recommandation, sévérité, phrases-types réutilisables — obligatoire avant clôture
* Analyse de récurrence des pannes (code panne x équipement) + tableau de bord temps réel (Chart.js)
* Attribution automatique d'équipe par scoring multi-critères (charge, performance, proximité, compétence)
* Équipes & techniciens (charge, taux d'occupation, MTTR/MTBF), couverture & compétences
* Contrats de maintenance (renouvellement, facturation, alertes d'expiration)
* Pièces utilisées (stock natif, allocation, refacturation, kits de pièces)
* Conformité & sécurité (inspections -> génération de demande corrective)
* Efficacité énergétique (graphique de consommation + plan d'actions traçable)
* Rapports métier écran + PDF (dossier équipement, remplacement, site, analyse pannes, bon d'intervention,
  rapport financier, conformité) avec page détail décisionnelle et prévisualisation split-view des documents
* RBAC fin (8 domaines x 4 niveaux), multi-société, multilingue (i18n .pot), notifications email natives

Voir la roadmap (prédictif, OCR, devis auto, IA, mobile) dans la fiche du module.
    """,
    'author': 'Emac SAH',
    'website': 'https://github.com/kouemousah/GMAO',
    'license': 'LGPL-3',
    # Carrousel de captures sur la page Apps + icone du module
    'images': [
        'static/description/screenshot_dashboard.png',
        'static/description/screenshot_intervention.png',
        'static/description/screenshot_analyse_pannes.png',
        'static/description/screenshot_rapport_site.png',
        'static/description/screenshot_codes_panne.png',
        'static/description/screenshot_equipement.png',
    ],
    'depends': [
        'base',
        'base_address_city',
        'mail',
        'stock',
        'hr',
        'web',
        'account',  # P2 : refacturation des pieces billable (account.move)
    ],
    # PIL/Pillow is bundled with Odoo 13. matplotlib is optional and lazy-loaded
    # only when chart generation methods are called; do NOT block install on it.
    'external_dependencies': {
        'python': ['PIL'],
    },
    'data': [
        # Security first
        'security/maintenance_security.xml',
        'security/ir.model.access.csv',

        # Data (sans mail_template : il reference des reports, charge plus bas)
        'data/paperformat_data.xml',
        'data/maintenance_sequence.xml',
        'data/gmao_activity_types.xml',
        'data/failure_code_data.xml',
        'data/report_phrase_data.xml',

        # Reports FIRST (actions referenced by view buttons via %(...)d
        # ET par mail_template_data.xml via report_template)
        'reports/maintenance_request_report.xml',
        'reports/maintenance_request_analysis_report.xml',
        'reports/maintenance_request_graph_qweb.xml',
        'reports/maintenance_parts_used_report.xml',
        'reports/maintenance_team_report.xml',
        'reports/maintenance_team_planning_report.xml',
        'reports/report_maintenance_contract.xml',
        'reports/equipment_replacement_report.xml',
        'reports/equipment_summary_report.xml',
        'reports/site_report.xml',
        'reports/conformite_securite_report.xml',

        # Mail templates APRES les reports (email_template_intervention_report
        # reference action_report_maintenance_request via report_template ;
        # email_template_replacement_alert reference action_report_equipment_replacement)
        'data/mail_template_data.xml',

        # Wizards (declare actions before views that reference them)
        'wizards/maintenance_graph_wizard_views.xml',
        'wizards/maintenance_team_wizard_views.xml',
        'wizards/maintenance_team_report_wizard_views.xml',
        'wizards/maintenance_parts_used_report_wizard_views.xml',
        'wizards/maintenance_contract_renew_wizard_views.xml',
        'wizards/report_wizard_views.xml',
        'wizards/load_kit_wizard_views.xml',

        # Views (parent before child)
        'views/maintenance_site_views.xml',
        'views/maintenance_equipment_category_views.xml',
        'views/gmao_failure_code_views.xml',
        'views/gmao_report_phrase_views.xml',
        'views/maintenance_equipment_views.xml',
        'views/maintenance_team_views.xml',
        'views/maintenance_contract_views.xml',
        'views/maintenance_parts_used_views.xml',
        'views/maintenance_request_views.xml',
        'views/maintenance_request_graph.xml',
        'views/conformite_securite_views.xml',
        'views/efficacite_energetique_views.xml',
        'views/res_users_views.xml',
        # Dashboard APRES request_views.xml (reference view_maintenance_request_search)
        'views/gmao_parts_kit_views.xml',
        'views/gmao_dashboard_views.xml',
        'views/gmao_dashboard_assets.xml',
        'views/gmao_financial_report_views.xml',

        # Cron (after views/data because tasks reference models)
        'data/maintenance_cron.xml',

        # Menu (last, references actions from views above)
        'views/maintenance_menu_views.xml',
    ],
    'qweb': [
        'static/src/xml/maintenance_request_templates.xml',
        'static/src/xml/maintenance_request_graph_templates.xml',
        'static/src/xml/maintenance_team_chart_template.xml',
        'static/src/xml/maintenance_parts_used_report_template.xml',
        'static/src/xml/gmao_dashboard_templates.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
}
