# Changelog

Toutes les modifications notables de ce projet sont documentees ici.
Le format est base sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/)
et le projet adhere au [Semantic Versioning](https://semver.org/lang/fr/).

---

## [13.0.2.0.0] - 2026-05-20

Refonte majeure 2026 par Emac SAH apres reprise du code legacy.

### Ajoute (Added)
- **Vues** : `calendar` (planning interventions sur `schedule_date`) et `activity`
  (suivi mail.activity) sur `maintenance.request`.
- **Groupe** : `group_request_creator` manquant (4 niveaux RBAC complets sur
  demandes de maintenance + acces CSV correspondant).
- **Groupes transverses** : `group_gmao_admin` (raccourci admin global avec
  `implied_ids` vers les 8 admins de domaine) et `group_maintenance_contract_manager`.
- **Sequences** : `maintenance.contract` et `maintenance.parts.used` (manquaient).
- **Champs `company_id`** sur `maintenance.site`, `maintenance.equipment`,
  `maintenance.conformite.securite` (etaient referencees dans `ir.rule`
  multi-societe mais n'existaient pas, crash a l'ouverture).
- **Securite** : `ir.rule` "Lecteur voit ses propres demandes assignees"
  (technicien ne voit pas les demandes des autres).
- **Tests** : 11 tests automatises (5 install + 6 workflow) sous `tests/`.
- **External dependencies** : declaration propre `PIL` uniquement (matplotlib
  lazy-loaded).
- **Documentation** : CHANGELOG.md, README enrichi avec stats reelles +
  dette technique transparente.
- **Site vitrine** : `index.html`, `404.html`, `sitemap.xml`, `robots.txt`,
  meta Open Graph + Twitter Card sur toutes les pages, favicon SVG + PNG.

### Modifie (Changed)
- **Manifest** : `name`, `author='Emac SAH'` (au lieu de `2WT`),
  `website=https://github.com/kouemousah/GMAO`, version bump `13.0.1.1` ->
  `13.0.2.0.0`.
- **Selection `system`** sur `maintenance.request` : keys passees en slugs
  ASCII (`daisy`, `excel`, `phone`, `mail`, `other`) au lieu de strings
  francais ("Plateforme Daisy", etc.) - compatible i18n.
- **`_onchange_gmao_admin`** : refactor complet en operation atomique
  unique sur `groups_id` (etait un cascade de 32 assignations sequentielles
  qui ne propageait pas correctement les groupes).
- **Vue `res.users`** : suppression du bloc redondant "Profils granulaires"
  (doublonnait l'affichage natif Odoo des groupes par categorie). Reste
  uniquement le toggle "Administrateur global GMAO" + l'usage des groupes
  natifs Odoo standard.
- **Menu principal** : reecrit avec 18 menus (au lieu de 6 actifs precedemment ;
  les autres etaient commentes dans le legacy 2WT).
- **Email templates** : `.users[0].field` remplace par `.users[:1].field`
  (9 occurrences) pour eviter `IndexError` sur groupes sans user.

### Supprime (Removed)
- **Doublon `maintenance.team1.py`** : meme `_name='maintenance.team'` que
  `maintenance_team.py`, Odoo refusait le chargement.
- **Imports `matplotlib.pyplot` top-level** (4 fichiers) deplaces en lazy
  imports a l'interieur des methodes graphiques.
- **Decorateur `@cache(...)` casse** (utilise comme decorator avec mauvais
  parametres) : retire de `_get_graph_image_execution_time`.
- **Fichiers obsoletes** : `maintenance_team_report1.xml`,
  `maintenance_team_report3.xml`, `maintenance_request_graph_a_delete.xml`.

### Corrige (Fixed)
- **Manifest data list** : 30+ fichiers XML/CSV qui etaient commentes dans le
  legacy 2WT sont maintenant correctement chargees (security, vues, rapports,
  wizards, crons). Ordonnancement reports avant views (refs `%()d`).
- **`__init__.py` modeles** : import des 11 modeles dans le bon ordre
  (dependances Many2one/One2many resolues).
- **Vues qui crashaient** : `res_users_views.xml` (champs `create_*`
  inexistants -> `*_profile`), `maintenance_request_graph_qweb.xml`
  (`type='graph'` invalide -> `bar`), `maintenance_contract_views.xml`
  (typo `action_report_maintenance_contracts_list` avec 's' final).
- **`action_maintenance_team_groups`** : `eval=` avec `ref(...)` qui crashait
  py.js cote client (`NameError: name 'ref' is not defined`) -> domain plain.
- **Tabs vs spaces** : `maintenance_request.py` (2048 tabs convertis en
  4 spaces, PEP8).
- **`raise ValidationError/UserError`** : 11 occurrences wrappes dans `_()`
  pour i18n.

### Dette technique connue (Roadmap v3.0)
- Collision potentielle avec le module natif Odoo `maintenance` (modeles
  redefinissent `_name='maintenance.equipment'/...` au lieu d'utiliser
  `_inherit`). Documente dans README. Refactor planifie v3.0 (necessite
  une suite de tests TransactionCase complete pour eviter regression).
- Migration Odoo 19 (OWL 2, retrait matplotlib en faveur de Chart.js, etc.)

---

## [13.0.1.1] - Date inconnue (legacy 2WT)

Version initiale du module, developpee par Emac SAH dans le cadre de l'entreprise
**2WT** (aujourd'hui en cessation d'activite). Cette version etait incomplete :
- 30+ fichiers data commentes dans le manifest
- Doublon de modele `maintenance.team`
- Imports matplotlib top-level provoquant `ImportError` au load
- `compute=` orphelins (methodes commentees)
- Groupes manquants referencees dans les vues
- Aucun test automatise

La refonte 13.0.2.0.0 ci-dessus repare ces problemes et constitue la base
publique du module sur GitHub.
