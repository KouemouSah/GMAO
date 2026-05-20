odoo.define('gmao_suite.attachment_preview', function (require) {
    "use strict";

    /**
     * Widget 'many2many_binary_preview' : etend le widget natif d'upload
     * (many2many_binary, upload conserve 100% natif). Au CLIC sur un document,
     * la ZONE DE TRAVAIL est scindee en deux volets cote a cote (PAS un popup) :
     *  - gauche : la vue/donnees courante (le formulaire) ;
     *  - droite : l'apercu du document (iframe).
     * Une barre de separation (gutter) est deplacable a la souris pour ajuster
     * les proportions (20%-80%). Le volet s'insere DANS .o_action_manager
     * (sous la barre de menu) -> aucune superposition de la navbar.
     */
    var relational_fields = require('web.relational_fields');
    var field_registry = require('web.field_registry');
    var core = require('web.core');
    var _t = core._t;

    var Base = relational_fields.FieldMany2ManyBinaryMultiFiles;

    var FieldMany2ManyBinaryPreview = Base.extend({
        events: _.extend({}, Base.prototype.events, {
            'click .o_image_box a': '_onPreviewClick',
            'click .caption a': '_onPreviewClick',
        }),

        destroy: function () {
            this._closeSplit();
            this._super.apply(this, arguments);
        },

        _files: function () {
            return _.map(this.value.data, function (r) {
                return {id: r.res_id, name: (r.data && r.data.name) || ('#' + r.res_id)};
            });
        },

        _onPreviewClick: function (ev) {
            ev.preventDefault();
            var $att = $(ev.currentTarget).closest('.o_attachment');
            var id = $att.find('.o_image_box').first().data('id') ||
                     $att.find('[data-id]').first().data('id');
            if (id) {
                this._openSplit(id);
            }
        },

        _closeSplit: function () {
            var $am = $('.o_action_manager.o_gmao_split_active');
            if (!$am.length) {
                return;
            }
            $am.find('.o_gmao_split_pane, .o_gmao_split_gutter').remove();
            $am.removeClass('o_gmao_split_active');
            $(document).off('.gmaosplit');
        },

        _docName: function (id) {
            var f = _.find(this._files(), function (x) {
                return String(x.id) === String(id);
            });
            return f ? f.name : '';
        },

        _openSplit: function (currentId) {
            var self = this;
            var $am = $('.o_action_manager');
            if (!$am.length) {
                return;
            }
            var url = '/web/content/' + currentId;
            // #pagemode=none : ouvre le lecteur PDF avec sa barre laterale
            //   (vignettes/outline/attachments/layers) REPLIEE par defaut, donc
            //   plus de superposition (PDF.js / Firefox).
            // #navpanes=0 : equivalent pour le lecteur PDF de Chrome.
            // Hash ignore pour les images -> sans effet de bord.
            var previewUrl = url + '#pagemode=none&navpanes=0';

            // Volet deja ouvert -> on met juste a jour l'apercu.
            var $pane = $am.find('.o_gmao_split_pane');
            if ($pane.length) {
                $pane.find('.o_gmao_split_frame').attr('src', previewUrl);
                $pane.find('.o_gmao_split_name').text(self._docName(currentId));
                $pane.find('.o_gmao_split_dl').attr('href', url + '?download=true');
                return;
            }

            // Construit le volet droit.
            var $name = $('<span class="o_gmao_split_name"/>').text(self._docName(currentId));
            var $dl = $('<a class="btn btn-sm btn-secondary o_gmao_split_dl"/>')
                .attr('href', url + '?download=true').attr('target', '_blank')
                .text(_t('Télécharger'));
            var $close = $('<button class="btn btn-sm btn-link o_gmao_split_close" title="Fermer">✕</button>');
            var $bar = $('<div class="o_gmao_split_bar"/>')
                .append($name)
                .append($('<span/>').append($dl).append($close));
            var $frame = $('<iframe class="o_gmao_split_frame"/>').attr('src', previewUrl);
            $pane = $('<div class="o_gmao_split_pane"/>').append($bar).append($frame);
            var $gutter = $('<div class="o_gmao_split_gutter" title="Glisser pour redimensionner"/>');

            $am.addClass('o_gmao_split_active').append($gutter).append($pane);

            $close.on('click', function () { self._closeSplit(); });

            // Gutter draggable : ajuste la largeur du volet (20%-80%).
            $gutter.on('mousedown', function (e) {
                e.preventDefault();
                var rect = $am[0].getBoundingClientRect();
                $frame.css('pointer-events', 'none');  // l'iframe ne mange pas le mousemove
                $('body').css('user-select', 'none');
                $(document).on('mousemove.gmaosplit', function (ev) {
                    var paneW = rect.left + rect.width - ev.clientX;
                    var pct = (paneW / rect.width) * 100;
                    pct = Math.min(80, Math.max(20, pct));
                    $pane.css('flex', '0 0 ' + pct + '%');
                }).on('mouseup.gmaosplit', function () {
                    $frame.css('pointer-events', '');
                    $('body').css('user-select', '');
                    $(document).off('.gmaosplit');
                });
            });
        },
    });

    field_registry.add('many2many_binary_preview', FieldMany2ManyBinaryPreview);

    return FieldMany2ManyBinaryPreview;
});
