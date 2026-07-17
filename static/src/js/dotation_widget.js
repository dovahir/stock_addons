/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class DotationHistoryWidget extends Component {
    static template = "stock_addons.DotationHistoryWidget";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.state = useState({
            history: null,
            loading: false,
            showPopup: false,
        });
    }

    get isApplicable() {
        return this.props.record.data.is_dotation;
    }

    async loadHistory() {
        this.state.loading = true;
        this.state.showPopup = false;
        try {
            const res = await this.orm.call(
                "stock.request.line",
                "get_last_dotations",
                [[this.props.record.resId]]
            );
            this.state.history = res;
            this.state.showPopup = true;
        } finally {
            this.state.loading = false;
        }
    }

    togglePopup() {
        if (!this.state.history) {
            this.loadHistory();
        } else {
            this.state.showPopup = !this.state.showPopup;
        }
    }
}

registry.category("fields").add("dotation_history_widget", {
    component: DotationHistoryWidget,
    supportedTypes: ["char", "text"],
    extractProps({ field }) {
        return {};
    },
});