// Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("FHIR Resource", {
	refresh: function (frm) {
		if (!frm.doc.__islocal) {
			frm.call("get_rendered_html").then((r) => {
				frm.fields_dict.resource_html.$wrapper.html(r.message);
			});

			frm.add_custom_button("Validate FHIR JSON", () => {
				frm.call("validate_fhir_resource_with_validator")
					.then((r) => {

						const issues = r.message.issues || [];
						const summary = issues.map((i, idx) => {
							const sev = i.severity;
							const details = i.details?.text || "";
							const loc = i.expression ? i.expression.join(", ") : "";
							return `
					<div class="mb-2">
					<span class="badge badge-${sev === "error" ? "danger" : sev === "warning" ? "warning" : "info"}">${sev}</span>
					<strong>${details}</strong>
					${loc ? `<div class="text-muted">${loc}</div>` : ""}
					</div>
					`;
						}).join("") || `<div class='text-green-700'>Raw Response: ${JSON.stringify(r)}</div>`;

						frappe.msgprint({
							title: `FHIR Validation Result`,
							indicator: issues.length ? "orange" : "green",
							message: summary
						});

					})
					.catch(() => {
						frappe.msgprint({
							title: "FHIR Validation Error",
							indicator: "red",
							message: r.message.error
						});
					});
			});
		}
	},

	resource_json: function (frm) {
		if (!frm.is_dirty()) {
			frm.trigger("refresh");
		}
	}

});
