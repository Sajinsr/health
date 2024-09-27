// // Copyright (c) 2024, earthians Health Informatics Pvt. Ltd. and contributors
// // For license information, please see license.txt

frappe.ui.form.on("FHIR Resource Mapper", {
	document_type: function (frm) {
		if (frm.doc.document_type) {
			frappe.model.with_doctype(frm.doc.document_type, function () {
				let meta = frappe.get_meta(frm.doc.document_type);
				let fields = meta.fields;

				fields.forEach(field => {
					if (!["Section Break", "Column Break", "Tab Break"].includes(field.fieldtype)) {
						frm.add_child("data", {
							doc_field: field.fieldname,
						});
					}
				});
				frm.refresh("data");
			});
		}
	},
});
