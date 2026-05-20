# -*- coding: utf-8 -*-
"""
Extension de gmao.request qui isole les methodes de generation de graphiques
matplotlib (PNG en base64 pour rapports QWeb).

Separe du fichier principal maintenance_request.py pour reduire sa taille
(refactor d'un fichier monolithique 1107 lignes) et clarifier la separation
de responsabilites :
- maintenance_request.py    : modele de base, workflow, CRUD, KPIs metier
- maintenance_request_graphs.py : generation visuelle (matplotlib lazy)

Matplotlib est importe lazy (cf _lazy_plt) - si non installe, seules les
methodes graphiques echouent (en log uniquement). Le module install et
fonctionne sans.
"""
import base64
import io
from datetime import datetime

from odoo import api, models


class MaintenanceRequestGraphs(models.Model):
    """Heritage non-functional de gmao.request pour les graphics."""

    _inherit = 'gmao.request'

    # =============================================================
    # Utilitaire : import lazy de matplotlib (dependance optionnelle)
    # =============================================================
    @staticmethod
    def _lazy_plt():
        """Lazy import de matplotlib + reglage backend non-interactif (Agg).

        Permet :
        - install Odoo possible sans matplotlib (depend ext optionnelle)
        - generation PNG headless (compatible serveur sans display)
        """
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        return plt

    @staticmethod
    def _png_to_base64(plt, fig):
        """Helper commun : sauvegarde la figure dans un buffer + b64 encode.

        Factorisation : avant ce refactor, ce bloc etait dupliquee 4 fois
        a la fin de chaque _get_graph_image_*. DRY.
        """
        from PIL import Image as PILImage
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=100)
        plt.close(fig)
        buffer.seek(0)
        # Compression PNG via PIL
        image = PILImage.open(buffer)
        buffer_compressed = io.BytesIO()
        image.save(buffer_compressed, format='PNG', optimize=True)
        buffer_compressed.seek(0)
        return base64.b64encode(buffer_compressed.getvalue()).decode('utf-8')

    # =============================================================
    # Graphique 1 : Evolution mensuelle du nombre d'interventions
    # =============================================================
    @api.model
    def _get_graph_image_line(self):
        """Chart line : nb d'interventions par mois sur tout l'historique."""
        # read_group avec lang=en_US pour format de date 'YYYY-MM' coherent
        data = self.with_context(lang='en_US').read_group(
            [('request_date', '!=', False)],
            [],
            ['request_date:month'],
            lazy=False,
        )
        labels, counts, dates = [], [], []
        for item in data:
            date_value = item.get('request_date:month')
            try:
                date_obj = datetime.strptime(date_value, '%Y-%m') if date_value else None
                dates.append(date_obj)
                labels.append(date_obj.strftime('%b %Y') if date_obj else (date_value or 'N/A'))
            except (ValueError, TypeError):
                dates.append(None)
                labels.append(date_value or 'N/A')
            counts.append(item.get('__count', 0))
        # Tri chronologique
        combined = sorted(zip(dates, labels, counts), key=lambda x: x[0] or datetime.min)
        if not combined:
            return False
        _dates, labels_sorted, counts_sorted = zip(*combined)

        plt = self._lazy_plt()
        plt.style.use('default')
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.plot(labels_sorted, counts_sorted, marker='o', linestyle='-', color='#4BC0C0')
        ax.set_xlabel('Mois')
        ax.set_ylabel('Nombre de demandes')
        ax.set_title("Evolution du nombre d'interventions")
        plt.xticks(rotation=45)
        plt.grid(True, which='both', linestyle='--', linewidth=0.5)
        plt.tight_layout()
        return self._png_to_base64(plt, fig)

    # =============================================================
    # Graphique 2 : Repartition par etat
    # =============================================================
    @api.model
    def _get_graph_image_bar(self):
        """Chart bar : nb de demandes par state, avec couleurs metier."""
        data = self.with_context(lang='en_US').read_group(
            [('state', '!=', False)], [], ['state'], lazy=False,
        )
        states = dict(self._fields['state'].selection)
        labels = [states.get(item['state'], 'N/A') for item in data]
        counts = [item.get('__count', 0) for item in data]
        if not labels:
            return False

        plt = self._lazy_plt()
        plt.style.use('default')
        fig, ax = plt.subplots(figsize=(6, 4))
        color_map = {
            'Annulée': '#FF8C00',
            'En cours': '#1E90FF',
            'Terminée': '#32CD32',
        }
        bar_colors = [color_map.get(label, '#B0C4DE') for label in labels]
        ax.bar(labels, counts, color=bar_colors)
        ax.set_xlabel('Etat')
        ax.set_ylabel('Nombre de demandes')
        ax.set_title("Nombre de demandes par etat")
        plt.xticks(rotation=45)
        plt.tight_layout()
        return self._png_to_base64(plt, fig)

    # =============================================================
    # Graphique 3 : Repartition corrective vs preventive
    # =============================================================
    @api.model
    def _get_graph_image_pie(self):
        """Chart pie : % de demandes preventives vs correctives."""
        types = dict(self._fields['maintenance_type'].selection)
        data = self.read_group(
            [('maintenance_type', '!=', False)], [], ['maintenance_type'], lazy=False,
        )
        labels = [types.get(item['maintenance_type'], 'N/A') for item in data]
        counts = [item.get('__count', 0) for item in data]
        if not labels:
            return False

        plt = self._lazy_plt()
        plt.style.use('default')
        fig, ax = plt.subplots(figsize=(6, 4))
        color_map = {'Corrective': '#FF6347', 'Préventive': '#4682B4'}
        pie_colors = [color_map.get(label, '#B0C4DE') for label in labels]
        ax.pie(counts, labels=labels, autopct='%1.1f%%', startangle=140, colors=pie_colors)
        ax.set_title('Repartition des types de maintenance')
        plt.tight_layout()
        return self._png_to_base64(plt, fig)

    # =============================================================
    # Graphique 4 : Duree moyenne d'execution par type sur periode
    # =============================================================
    @api.model
    def _get_graph_image_execution_time(self, date_from=None, date_to=None):
        """Chart line multi-series : duree moyenne par type sur periode.

        Si la periode > 30 jours : agregation par mois. Sinon par jour.
        """
        domain = [('maintenance_type', '!=', False)]
        if date_from:
            domain.append(('request_date', '>=', date_from))
        if date_to:
            domain.append(('request_date', '<=', date_to))

        period_grouping = ('request_date:month'
                           if date_to and date_from and (date_to - date_from).days > 30
                           else 'request_date:day')
        data = self.read_group(
            domain,
            ['maintenance_type', 'duration:avg'],
            [period_grouping, 'maintenance_type'],
            lazy=False,
        )
        labels = sorted({item[period_grouping] for item in data if item.get(period_grouping)})
        maintenance_types = sorted({item['maintenance_type'] for item in data})
        if not labels or not maintenance_types:
            return False
        durations = {mt: [0] * len(labels) for mt in maintenance_types}
        for item in data:
            idx = labels.index(item[period_grouping])
            durations[item['maintenance_type']][idx] = item['duration']

        plt = self._lazy_plt()
        plt.style.use('default')
        fig, ax = plt.subplots(figsize=(10, 6))
        colors = ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF']
        for i, (mt, values) in enumerate(durations.items()):
            ax.plot(labels, values, marker='o', linestyle='-',
                    color=colors[i % len(colors)], label=mt)
        ax.set_xlabel('Periode (jour ou mois)')
        ax.set_ylabel('Duree moyenne (heures)')
        ax.set_title('Suivi du temps moyen par type de maintenance')
        ax.legend()
        plt.xticks(rotation=45)
        plt.tight_layout()
        return self._png_to_base64(plt, fig)
