odoo.define('gmao_suite.ErrorHandler', function (require) {
    "use strict";

    var core = require('web.core');
    var Dialog = require('web.Dialog');

    var _t = core._t;

    function handleReportError(error) {
        if (error.message.includes("IndexError: list index out of range")) {
            new Dialog(null, {
                title: _t("Erreur de rapport"),
                $content: $('<div>').html(_t("Une erreur s'est produite lors de la génération du rapport. Veuillez contacter votre administrateur système.")),
                buttons: [{
                    text: _t("OK"),
                    close: true
                }]
            }).open();
            return true;
        }
        return false;
    }

    core.crash_registry.add(handleReportError, 5);

    return {
        handleReportError: handleReportError
    };
});