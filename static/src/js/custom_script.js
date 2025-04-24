odoo.define('stock.StockMoveOne2Many', function (require) {
    "use strict";
    var One2ManyList = require('web.One2ManyList');  // 1

    One2ManyList.include({
        _renderButtons: function () {
            this._super.apply(this, arguments);       // 2

            // 3 : ne s'applique qu'au champ move_ids_without_package
            if (this.fieldName === 'move_ids_without_package') {
                this.$buttons.find('.o_list_button_add').remove();  // 4
            }
        },
    });
});
  