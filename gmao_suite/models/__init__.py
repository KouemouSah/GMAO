# -*- coding: utf-8 -*-
# Ordre d'import contrôlé : modèles de base d'abord, puis ceux qui en dépendent.

from . import maintenance_models               # res.users inherit
from . import maintenance_site                  # leaf
from . import maintenance_equipment_category    # leaf
from . import gmao_failure_code                  # leaf (catalogue code panne P6)
from . import gmao_report_phrase                  # leaf (phrases-types rapport)
from . import maintenance_equipment             # deps: site, category
from . import maintenance_team                  # deps: hr.employee
from . import maintenance_contract              # deps: equipment, partner
from . import maintenance_parts_used            # deps: product, request
from . import maintenance_request               # deps: equipment, team, contract, parts_used
from . import maintenance_request_graphs        # extension graphics matplotlib (refactor 2026)
from . import conformite_securite               # deps: equipment
from . import efficacite_energetique            # deps: equipment, site
from . import efficacite_action                  # deps: efficacite, request
from . import maintenance_parts_used_report     # AbstractModel report
from . import report_equipment_summary           # AbstractModel report (P5.1)
from . import report_site                         # AbstractModel report (P5.2)
from . import gmao_parts_kit
from . import gmao_dashboard
from . import gmao_financial_report                     # TransientModel KPI dashboard
