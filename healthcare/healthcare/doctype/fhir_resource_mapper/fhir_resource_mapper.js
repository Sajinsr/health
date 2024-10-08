// // Copyright (c) 2024, earthians Health Informatics Pvt. Ltd. and contributors
// // For license information, please see license.txt

var common_docfields = ["doctype", "name"];
var fields_excluded = ["Section Break", "Column Break", "Tab Break", "HTML"];

frappe.ui.form.on("FHIR Resource Mapper", {
	document_type: function (frm) {
		if (frm.doc.document_type) {
			frm.clear_table("resource_maps");
			frappe.model.with_doctype(frm.doc.document_type, () => {
				common_docfields.forEach(function (field) {
					frm.add_child("resource_maps", {
						doc_field: field,
					});
				});

				frappe.get_meta(frm.doc.document_type).fields.forEach(function (d) {
					if (!fields_excluded.includes(d.fieldtype)) {
						if (["Table", "Table MultiSelect"].includes(d.fieldtype)) {
							frappe.model.with_doctype(d.options, () => {
								frappe.get_meta(d.options).fields.forEach(function (child) {
									if (!fields_excluded.includes(child.fieldtype)) {
										frm.add_child("resource_maps", {
											doc_field: child.fieldname,
											parent_docfield: d.fieldname,
										});
									}
								});
							});
						} else {
							frm.add_child("resource_maps", {
								doc_field: d.fieldname,
							});
						}
					}
				});
				frm.refresh_field("resource_maps");
			});
		}
	},
});
