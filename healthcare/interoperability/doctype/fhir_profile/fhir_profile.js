// Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("FHIR Profile", {
	refresh: function (frm) {
		frm.add_custom_button(__("Load Structure Definitions"), () => {

			frappe.confirm(__("This will import all Structure Definitions once again if done earlier, confirm?"), ()=> {

				frm.call("import_structure_definitions")
				.then(r => {
					frappe.show_alert({
						"indicator": "green",
						"message": __("Request Queued"),
					});
				});

			});

		});
	},

	schema_file: function (frm) {
		if (!frm.doc.package_file.endsWith(".tar.gz") || !frm.doc.package_file.endsWith(".tgz")) {
			frappe.msgprint(__("Please upload a valid FHIR Package (.tgz / tar.gz) file."));
		}
	}
});
