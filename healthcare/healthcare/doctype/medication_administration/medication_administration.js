// Copyright (c) 2023, healthcare and contributors
// For license information, please see license.txt

frappe.ui.form.on("Medication Administration", {
	setup: function(frm) {
		frm.set_query("inpatient_record", function (doc) {
			return {
				filters: {
					patient: frm.doc.patient,
					status: ["in", ["Admitted", "Discharge Scheduled"]],
				},
			};
		});

		if (frm.doc.inpatient_record) {
			frm.set_query("medication_request", function (doc) {
				return {
					filters: {
						docstatus: 1,
						patient: frm.doc.patient,
						inpatient_record: frm.doc.inpatient_record,
					},
				};
			});
		}
	},

	inpatient_record: function(frm) {
		if (frm.doc.inpatient_record) {
			frm.set_query("medication_request", function (doc) {
				return {
					filters: {
						docstatus: 1,
						patient: frm.doc.patient,
						inpatient_record: frm.doc.inpatient_record,
					},
				};
			});
		}
	}
});
