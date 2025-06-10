// Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
// For license information, please see license.txt


frappe.ui.form.on('FHIR Implementation Guide', {
	refresh: function (frm) {
		if (!frm.doc.__islocal) {
			frm.add_custom_button('Preview JSON', () => {
				frappe.call({
					method: 'render',
					doc: frm.doc,
					callback: r => {
						frappe.msgprint({
							title: __('FHIR ImplementationGuide'),
							indicator: 'blue',
							message: `<pre style="white-space:pre-wrap;">${JSON.stringify(r.message, null, 2)}</pre>`
						});
					}
				});
			});

			frm.add_custom_button('Download JSON', () => {
				frappe.call({
					method: 'render',
					doc: frm.doc,
					callback: r => {
						const blob = new Blob(
							[JSON.stringify(r.message, null, 2)],
							{ type: "application/json" }
						);
						const url = URL.createObjectURL(blob);
						const a = document.createElement('a');
						a.href = url;
						a.download = `ImplementationGuide-${frm.doc.name}.json`;
						document.body.appendChild(a);
						a.click();
						a.remove();
						URL.revokeObjectURL(url);
					}
				});
			});
		}
	}
});
