odoo.define('gmao_suite.Dashboard', function (require) {
    "use strict";

    /**
     * Dashboard GMAO professionnel (client action Odoo 13).
     *
     * - AbstractAction : ouvre une page plein-ecran (pas une form view).
     * - Donnees fournies par gmao.dashboard.get_dashboard_data() via RPC.
     * - Graphiques rendus avec Chart.js (lib native /web/static/lib/Chart).
     * - Filtres periode + site, rafraichissement live.
     * - KPI cliquables -> ouvrent la liste filtree (do_action act_window).
     */
    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var QWeb = core.qweb;
    var _t = core._t;

    var PALETTE = {
        primary: '#875A7B',
        info: '#17a2b8',
        success: '#28a745',
        warning: '#ffc107',
        danger: '#dc3545',
        orange: '#fd7e14',
        purple: '#6f42c1',
        teal: '#20c997',
        gray: '#6c757d',
    };
    var CHART_COLORS = [
        PALETTE.primary, PALETTE.info, PALETTE.success, PALETTE.warning,
        PALETTE.danger, PALETTE.orange, PALETTE.purple, PALETTE.teal,
    ];

    var GmaoDashboard = AbstractAction.extend({
        hasControlPanel: false,
        events: {
            'click .o_gmao_kpi[data-action]': '_onKpiClick',
            'change .o_gmao_filter_period': '_onPeriodChange',
            'change .o_gmao_filter_date_from': '_onCustomDateChange',
            'change .o_gmao_filter_date_to': '_onCustomDateChange',
            'change .o_gmao_filter_site': '_onSiteChange',
            'change .o_gmao_filter_company': '_onCompanyChange',
            'click .o_gmao_refresh': '_onRefresh',
            'click .o_gmao_recent_row[data-id]': '_onRecentClick',
            'click .o_gmao_sort': '_onSortRecent',
        },

        init: function (parent, action) {
            this._super.apply(this, arguments);
            this.charts = {};
            this.dateFrom = null;
            this.dateTo = null;
            this.siteId = null;
            this.companyIds = null;
            this.period = 'all';
            this.data = null;
            this.sortBy = null;
            this.sortAsc = true;
        },

        willStart: function () {
            return $.when(this._super.apply(this, arguments), this._fetchData());
        },

        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                self._render();
            });
        },

        destroy: function () {
            this._destroyCharts();
            this._super.apply(this, arguments);
        },

        // ----------------------------------------------------------------
        // Data
        // ----------------------------------------------------------------
        _fetchData: function () {
            var self = this;
            return this._rpc({
                model: 'gmao.dashboard',
                method: 'get_dashboard_data',
                args: [this.dateFrom, this.dateTo, this.siteId, this.companyIds],
            }).then(function (data) {
                self.data = data;
            });
        },

        _reload: function () {
            var self = this;
            this.$el.addClass('o_gmao_loading');
            return this._fetchData().then(function () {
                self._render();
                self.$el.removeClass('o_gmao_loading');
            });
        },

        // ----------------------------------------------------------------
        // Render
        // ----------------------------------------------------------------
        _render: function () {
            this._destroyCharts();
            this.$el.html(QWeb.render('gmao_suite.DashboardMain', {
                widget: this,
                kpis: this.data.kpis,
                recent: this.data.recent,
                sites: this.data.sites,
                companies: this.data.companies || [],
                period: this.period,
                siteId: this.siteId,
                companyId: (this.companyIds && this.companyIds[0]) || '',
                dateFrom: this.dateFrom,
                dateTo: this.dateTo,
                fmt: this._fmtMoney.bind(this),
            }));
            this._renderCharts();
        },

        _fmtMoney: function (val) {
            var cur = this.data.kpis.currency || '';
            var n = (val || 0).toLocaleString('fr-FR', {
                minimumFractionDigits: 0, maximumFractionDigits: 0,
            });
            return n + ' ' + cur;
        },

        // ----------------------------------------------------------------
        // Charts (Chart.js v2)
        // ----------------------------------------------------------------
        _destroyCharts: function () {
            _.each(this.charts, function (c) {
                if (c) { c.destroy(); }
            });
            this.charts = {};
        },

        _ctx: function (selector) {
            var canvas = this.$(selector)[0];
            return canvas ? canvas.getContext('2d') : null;
        },

        _renderCharts: function () {
            // Garde : si le bundle n'a pas charge Chart.js, on l'affiche
            // explicitement plutot que de laisser des cartes vides.
            if (typeof Chart === 'undefined') {
                this.$('.o_gmao_canvas_wrap').html(
                    '<div class="o_gmao_chart_err">' +
                    _t('Chart.js indisponible — assets backend non charges.') +
                    '</div>');
                return;
            }
            Chart.defaults.global.defaultFontSize = 11;
            var c = this.data.charts;
            this._safe(function () { this._doughnut('#gmao_chart_state', c.by_state); });
            this._safe(function () { this._line('#gmao_chart_month', c.by_month, _t('Volume')); });
            this._safe(function () { this._bar('#gmao_chart_type', c.by_type, [PALETTE.success, PALETTE.orange]); });
            this._safe(function () { this._hbar('#gmao_chart_equipment', c.top_equipment); });
            this._safe(function () { this._bar('#gmao_chart_site', c.by_site, null); });
            this._safe(function () { this._hbar('#gmao_chart_failure', c.by_failure); });
            this._safe(function () { this._doughnut('#gmao_chart_failure_mode', c.by_failure_mode); });
            this._safe(function () { this._doughnut('#gmao_chart_severity', c.by_severity); });
        },

        _safe: function (fn) {
            try { fn.call(this); }
            catch (e) { console.error('[GMAO dashboard] chart error:', e); }
        },

        _empty: function (sel) {
            // Affiche un message si la serie est vide (sinon canvas blanc).
            this.$(sel).closest('.o_gmao_canvas_wrap')
                .html('<div class="o_gmao_chart_err" style="color:#9a9aab">' +
                      _t('Aucune donnee sur la periode') + '</div>');
        },

        _hasData: function (series) {
            return series && series.data && series.data.some(function (v) { return v; });
        },

        _doughnut: function (sel, series) {
            var ctx = this._ctx(sel);
            if (!ctx) { return; }
            if (!this._hasData(series)) { return this._empty(sel); }
            this.charts[sel] = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: series.labels,
                    datasets: [{ data: series.data, backgroundColor: CHART_COLORS, borderWidth: 2, borderColor: '#fff' }],
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    legend: { position: 'right', labels: { boxWidth: 11, fontSize: 11, padding: 8 } },
                    title: { display: false },
                    cutoutPercentage: 62,
                    layout: { padding: 2 },
                },
            });
        },

        _line: function (sel, series, label) {
            var ctx = this._ctx(sel);
            if (!ctx) { return; }
            if (!this._hasData(series)) { return this._empty(sel); }
            this.charts[sel] = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: series.labels,
                    datasets: [{
                        label: label, data: series.data,
                        borderColor: PALETTE.primary,
                        backgroundColor: 'rgba(135,90,123,0.12)',
                        fill: true, tension: 0.3, pointRadius: 3, pointBackgroundColor: PALETTE.primary,
                    }],
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    legend: { display: false },
                    title: { display: false },
                    scales: { yAxes: [{ ticks: { beginAtZero: true, precision: 0 } }] },
                },
            });
        },

        _bar: function (sel, series, colors) {
            var ctx = this._ctx(sel);
            if (!ctx) { return; }
            if (!this._hasData(series)) { return this._empty(sel); }
            this.charts[sel] = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: series.labels,
                    datasets: [{ data: series.data, backgroundColor: colors || CHART_COLORS, maxBarThickness: 60 }],
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    legend: { display: false },
                    title: { display: false },
                    scales: { yAxes: [{ ticks: { beginAtZero: true, precision: 0 } }] },
                },
            });
        },

        _hbar: function (sel, series) {
            var ctx = this._ctx(sel);
            if (!ctx) { return; }
            if (!this._hasData(series)) { return this._empty(sel); }
            this.charts[sel] = new Chart(ctx, {
                type: 'horizontalBar',
                data: {
                    labels: series.labels,
                    datasets: [{ data: series.data, backgroundColor: PALETTE.info, maxBarThickness: 26 }],
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    legend: { display: false },
                    title: { display: false },
                    scales: { xAxes: [{ ticks: { beginAtZero: true } }] },
                },
            });
        },

        // ----------------------------------------------------------------
        // Events
        // ----------------------------------------------------------------
        _onPeriodChange: function (ev) {
            this.period = $(ev.currentTarget).val();
            var today = new Date();
            var from = null;
            if (this.period === 'month') {
                from = new Date(today.getFullYear(), today.getMonth(), 1);
            } else if (this.period === 'quarter') {
                from = new Date(today.getFullYear(), today.getMonth() - 3, 1);
            } else if (this.period === 'year') {
                from = new Date(today.getFullYear(), 0, 1);
            }
            this.dateFrom = from ? this._isoDate(from) : null;
            this.dateTo = (this.period === 'custom') ? this.dateTo : null;
            if (this.period !== 'custom') {
                this._reload();
            } else {
                this.$('.o_gmao_custom_dates').removeClass('o_hidden');
            }
        },

        _onCustomDateChange: function () {
            this.dateFrom = this.$('.o_gmao_filter_date_from').val() || null;
            this.dateTo = this.$('.o_gmao_filter_date_to').val() || null;
            this._reload();
        },

        _onSiteChange: function (ev) {
            var val = $(ev.currentTarget).val();
            this.siteId = val ? parseInt(val, 10) : null;
            this._reload();
        },

        _onCompanyChange: function (ev) {
            var val = $(ev.currentTarget).val();
            this.companyIds = val ? [parseInt(val, 10)] : null;
            this._reload();
        },

        _onRefresh: function () {
            this._reload();
        },

        _isoDate: function (d) {
            return d.getFullYear() + '-' +
                ('0' + (d.getMonth() + 1)).slice(-2) + '-' +
                ('0' + d.getDate()).slice(-2);
        },

        _baseDomain: function () {
            var domain = [];
            if (this.dateFrom) { domain.push(['request_date', '>=', this.dateFrom]); }
            if (this.dateTo) { domain.push(['request_date', '<=', this.dateTo + ' 23:59:59']); }
            if (this.siteId) { domain.push(['site_id', '=', this.siteId]); }
            return domain;
        },

        _onKpiClick: function (ev) {
            var key = $(ev.currentTarget).data('action');
            var domain = this._baseDomain();
            var name = _t('Demandes');
            var model = 'gmao.request';
            if (key === 'overdue') {
                domain.push(['is_overdue', '=', true]);
                name = _t('Demandes en retard');
            } else if (key === 'open') {
                domain.push(['state', 'in', ['new', 'to_validate', 'in_progress', 'repaired']]);
                name = _t('Demandes ouvertes');
            } else if (key === 'done') {
                domain.push(['state', '=', 'done']);
                name = _t('Demandes terminees');
            } else if (key === 'preventive') {
                domain.push(['maintenance_type', '=', 'preventive']);
                name = _t('Maintenances preventives');
            } else if (key === 'corrective') {
                domain.push(['maintenance_type', '=', 'corrective']);
                name = _t('Maintenances correctives');
            } else if (key === 'repair') {
                model = 'gmao.equipment';
                domain = [['state', '=', 'in_repair']];
                name = _t('Equipements en reparation');
            } else if (key === 'recurring') {
                domain.push(['failure_code_id', '!=', false]);
                domain.push(['maintenance_type', '=', 'corrective']);
                name = _t('Pannes (correctif avec code)');
            }
            this.do_action({
                type: 'ir.actions.act_window',
                name: name,
                res_model: model,
                views: [[false, 'list'], [false, 'form']],
                domain: domain,
                target: 'current',
            });
        },

        _onRecentClick: function (ev) {
            var id = $(ev.currentTarget).data('id');
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: 'gmao.request',
                res_id: id,
                views: [[false, 'form']],
                target: 'current',
            });
        },

        _onSortRecent: function (ev) {
            var key = $(ev.currentTarget).data('sort');
            if (this.sortBy === key) {
                this.sortAsc = !this.sortAsc;
            } else {
                this.sortBy = key; this.sortAsc = true;
            }
            var asc = this.sortAsc;
            this.data.recent.sort(function (a, b) {
                var va = a[key], vb = b[key];
                if (va < vb) { return asc ? -1 : 1; }
                if (va > vb) { return asc ? 1 : -1; }
                return 0;
            });
            this._render();
        },
    });

    core.action_registry.add('gmao_dashboard', GmaoDashboard);

    return GmaoDashboard;
});
