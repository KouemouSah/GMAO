odoo.define('gmao_suite.consumption_chart', function (require) {
    "use strict";

    /**
     * Widget 'gmao_consumption_chart' : rend un graphique a barres (Chart.js)
     * a partir du champ JSON consumption_chart de maintenance.efficacite.energetique
     * ({consumptions:[prec, actuel], labels:[...], savings:...}).
     * Remplace l'affichage du JSON brut. Lecture seule. Chart.js est charge
     * via les assets backend du module.
     */
    var AbstractField = require('web.AbstractField');
    var field_registry = require('web.field_registry');
    var core = require('web.core');
    var _t = core._t;

    var ConsumptionChart = AbstractField.extend({
        className: 'o_gmao_consumption_chart',

        _render: function () {
            var self = this;
            this.$el.empty();
            var data = {};
            try {
                data = JSON.parse(this.value || '{}');
            } catch (e) {
                data = {};
            }
            if (typeof Chart === 'undefined' || !data.consumptions ||
                    !data.consumptions.length) {
                this.$el.append($('<div class="text-muted"/>')
                    .text(_t('Aucune donnée de consommation à afficher.')));
                return;
            }
            var savings = data.savings || 0;
            if (savings) {
                this.$el.append($('<div class="mb-2"/>').append(
                    $('<span class="badge badge-success"/>')
                        .text(_t('Économie : ') + savings + ' kWh')));
            }
            var $canvas = $('<canvas/>');
            this.$el.append($('<div/>')
                .css({position: 'relative', height: '320px'}).append($canvas));

            setTimeout(function () {
                if (self._chart) {
                    self._chart.destroy();
                }
                if (!$canvas[0]) {
                    return;
                }
                self._chart = new Chart($canvas[0].getContext('2d'), {
                    type: 'bar',
                    data: {
                        labels: data.labels || [],
                        datasets: [{
                            label: _t('Consommation (kWh)'),
                            data: data.consumptions || [],
                            backgroundColor: ['#6c757d', '#875A7B'],
                            maxBarThickness: 90,
                        }],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        legend: {display: false},
                        title: {display: false},
                        scales: {yAxes: [{ticks: {beginAtZero: true}}]},
                    },
                });
            }, 0);
        },

        destroy: function () {
            if (this._chart) {
                this._chart.destroy();
            }
            this._super.apply(this, arguments);
        },
    });

    field_registry.add('gmao_consumption_chart', ConsumptionChart);

    return ConsumptionChart;
});
