// Copyright (c) 2022, healthcare and contributors
// For license information, please see license.txt

frappe.ui.form.on('ABDM Settings', {
	refresh: function(frm) {
		if (frm.doc.consent_base_url) {
			frm.add_custom_button(__("Bridge Service"), function () {
				frappe.call({
					method: 'healthcare.regional.india.abdm.utils.get_bridge_by_service_id',
					callback: function (data) {
						let dialog = new frappe.ui.Dialog({
							title: 'Bridge Details',
							fields: [
								{
									fieldname: 'response',
									fieldtype: 'Code',
									read_only: 1
								},
							],
							secondary_action_label: 'Close',
							secondary_action(values) {
								dialog.hide();
							},
						});
						dialog.set_value("response", JSON.stringify(data.message, null, 2));
						dialog.show();
					}
				});
			}, "Get");
			frm.add_custom_button(__("Services"), function () {
				frappe.call({
					method: 'healthcare.regional.india.abdm.utils.get_services_by_bridge_id',
					callback: function (data) {
						let dialog = new frappe.ui.Dialog({
							title: 'Service Details',
							fields: [
								{
									fieldname: 'response',
									fieldtype: 'Code',
									read_only: 1
								},
							],
							secondary_action_label: 'Close',
							secondary_action(values) {
								dialog.hide();
							},
						});
						dialog.set_value("response", JSON.stringify(data.message, null, 2));
						dialog.show();
					}
				});
			}, "Get");
			if (frm.doc.bridge_url) {
				frm.add_custom_button(__("Update Bridge URL"), function () {
					frappe.call({
						method: 'healthcare.regional.india.abdm.utils.update_bridge_url',
						callback: function (data) {}
					});
				});
			}
		}

		if (frm.doc.facility_id) {
			frm.add_custom_button(__("Register Bridge Services"), function () {
				frappe.call({
					method: 'healthcare.regional.india.abdm.utils.register_bridge_service',
					callback: function (data) {}
				});
			});
		}
	}
});
