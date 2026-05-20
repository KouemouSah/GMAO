odoo.define('gmao_suite.maintenance_request_form', function (require) {
    "use strict";

    var core = require('web.core');
    var FormController = require('web.FormController');
    var FormView = require('web.FormView');
    var FormRenderer = require('web.FormRenderer');
    var viewRegistry = require('web.view_registry');
	var Dialog = require('web.Dialog');
    var _ = require('underscore');
    var $ = require('jquery');

    var _t = core._t;

    var MaintenanceRequestFormController = FormController.extend({
        custom_events: _.extend({}, FormController.prototype.custom_events, {
            open_kpi_dashboard: '_onOpenKPIDashboard',
        }),
		
		
		
	_onOpenKPIDashboard: function (ev) {
    var self = this;
    this._rpc({
        model: 'gmao.request',
        method: 'get_maintenance_kpis',
        args: [this.model.get(this.handle).res_id],
    }).then(function (result) {
        console.log('Résultat brut de get_maintenance_kpis:', result); // Log initial pour vérifier les données

        if (!result || typeof result !== 'object') {
            // Vérifie si le résultat est bien un objet JSON
            new Dialog(null, {
                title: _t("Erreur KPI"),
                $content: $('<div>').html(_t("Les données KPI sont indisponibles ou corrompues. Veuillez contacter l'administrateur.")),
                buttons: [{text: _t("OK"), close: true}]
            }).open();
            return;
        }

        try {
            var jsonData = JSON.stringify(result);
            console.log('Données JSON pour le tableau de bord KPI:', jsonData); // Vérifier le JSON stringifié

            // Si les données sont valides, exécute l'action
            self.do_action({
                name: _t('Maintenance KPI Dashboard'),
                type: 'ir.actions.act_window',
                res_model: 'gmao.request',
                views: [[false, 'form']],
                target: 'new',
                context: {
                    'default_kpi_data': jsonData,
                },
            });
        } catch (error) {
            console.error('Erreur de conversion JSON:', error); // Log si la conversion JSON échoue
            new Dialog(null, {
                title: _t("Erreur de données"),
                $content: $('<div>').html(_t("Erreur lors de l'analyse des données KPI. Veuillez réessayer.")),
                buttons: [{text: _t("OK"), close: true}]
            }).open();
        }
    }).catch(function (error) {
        console.error('Erreur lors de l\'appel RPC:', error); // Log l'erreur RPC
        new Dialog(null, {
            title: _t("Erreur de connexion"),
            $content: $('<div>').html(_t("Une erreur est survenue lors de la connexion au serveur. Veuillez vérifier votre connexion et réessayer.")),
            buttons: [{text: _t("OK"), close: true}]
        }).open();
    });
},


        renderButtons: function ($node) {
            this._super.apply(this, arguments);
           
        },

        _onStartTimer: function () {
			console.log("Appel de l'action_start_timer");
            this._rpc({
                model: 'gmao.request',
                method: 'action_start_timer',
                args: [this.model.get(this.handle).res_id],
            }).then(this.reload.bind(this));
        },

        _onStopTimer: function () {
			console.log("Appel de l'action_start_timer");
            this._rpc({
                model: 'gmao.request',
                method: 'action_stop_timer',
                args: [this.model.get(this.handle).res_id],
            }).then(this.reload.bind(this));
        },

        _updateButtons: function () {
			console.log("Appel de l'action_start_timer");
            this._super.apply(this, arguments);
            if (this.$buttons) {
                var state = this.model.get(this.handle).data.state;
                this.$buttons.find('.o_maintenance_start_timer').toggle(state === 'new');
                this.$buttons.find('.o_maintenance_stop_timer').toggle(state === 'in_progress');
				
            }
        },
    });

    var MaintenanceRequestFormRenderer = FormRenderer.extend({
        _renderStatButton: function (elem) {
            var $button = this._super.apply(this, arguments);
            if (elem.tag === 'button' && elem.attrs.class === 'oe_stat_button o_maintenance_kpi_dashboard') {
                $button.on('click', this._onKPIDashboardClick.bind(this));
            }
            return $button;
        },

        _onKPIDashboardClick: function (ev) {
            ev.preventDefault();
            this.trigger_up('open_kpi_dashboard');
        },
    });

    var MaintenanceRequestFormView = FormView.extend({
        config: _.extend({}, FormView.prototype.config, {
            Controller: MaintenanceRequestFormController,
            Renderer: MaintenanceRequestFormRenderer,
        }),
    });

    viewRegistry.add('maintenance_request_form', MaintenanceRequestFormView);

    return MaintenanceRequestFormView;
});