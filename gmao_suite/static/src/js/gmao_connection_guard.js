odoo.define('gmao_suite.connection_guard', function (require) {
    "use strict";

    /**
     * Supprime le faux message "Connexion perdue / Tentative de reconnexion"
     * qui apparait lorsqu'on selectionne / deselectionne une societe.
     *
     * Cause (verifiee dans la source Odoo 13) :
     *   widgets/switch_company_menu.js -> session.setCompanies()
     *   -> core/session.js: location.reload()
     * Le rechargement de page avorte les requetes XHR en vol, ce qui produit
     * une erreur JSON-RPC code -32098 (core/ajax.js) -> crash_manager
     * handleLostConnection() -> bus 'connection_lost'
     * -> AbstractWebClient._onConnectionLost() affiche une notification sticky.
     *
     * Il n'y a pourtant AUCUN probleme reseau : la page est simplement en train
     * de se recharger. On neutralise donc la notification UNIQUEMENT pendant le
     * dechargement de la page, sans masquer les vraies pertes de connexion.
     */
    var AbstractWebClient = require('web.AbstractWebClient');

    var unloading = false;
    window.addEventListener('beforeunload', function () {
        unloading = true;
        // Filet de securite : si la navigation est finalement annulee (la page
        // reste vivante), on reactive l'affichage des vraies pertes de connexion.
        setTimeout(function () { unloading = false; }, 5000);
    });

    AbstractWebClient.include({
        _onConnectionLost: function () {
            if (unloading) {
                return;
            }
            return this._super.apply(this, arguments);
        },
    });
});
