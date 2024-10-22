// Copyright (c) 2024, earthians Health Informatics Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Package Subscription", {
	setup: function (frm) {
		frm.set_query("patient", function () {
			return {
				filters: {
					status: "Active",
				},
			};
		});
		frm.set_query("healthcare_package", function () {
			return {
				filters: {
					disabled: 0,
				},
			};
		});
	},

	refresh: function (frm) {
		if(frm.doc.docstatus == 1 && !frm.doc.invoiced){
			frm.add_custom_button(__("Sales Invoice"), () => {
				frappe.route_options = {
					"healthcare_package_subscription": frm.doc.name,
					"patient": frm.doc.patient
				};
				frappe.new_doc("Sales Invoice");
			}, __("Create"));
		}
	},

	healthcare_package: function (frm) {
		if (frm.doc.healthcare_package) {
			frappe.call({
				doc: frm.doc,
				method: "get_package_details",
				callback: function (r) {
					frm.refresh();
				},
			});
		}
	}
});
