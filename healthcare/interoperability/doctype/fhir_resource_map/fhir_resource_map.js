// Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("FHIR Resource Map", {
	onload_post_render: (frm) => {

		frm.set_query("fhir_profile", () => {
			return {
				filters: {
					fhir_version: frm.doc.fhir_version,
					is_active: 1,
				},
			}
		});

		frm.set_query("fhir_structure_def", () => {
			return {
				filters: {
					fhir_version: frm.doc.fhir_version,
					fhir_profile: frm.doc.fhir_profile,
				},
			}
		});

		frm.set_query("frappe_doctype", () => {
			return {
				filters: {
					istable: 0,
				},
			}
		});
	},

	refresh: (frm) => {
		frm.fields_dict["map"].grid.wrapper.find(".grid-add-row").hide();
		frm.fields_dict["map"].grid.add_custom_button(__("Map Fields"), () => {
			show_map_dialog(frm);
		});
	}
});

function show_map_dialog(frm) {
	frappe.model.with_doctype(frm.doc.frappe_doctype, () => {
		let doc_fields = frappe.get_meta(frm.doc.frappe_doctype)
			.fields
			.filter(df => !["Section Break", "Column Break", "Tab Break"].includes(df.fieldtype))
			.map(df => df.fieldname);

		doc_fields.push("name");

		frappe.db.get_doc("FHIR Structure Definition", frm.doc.fhir_structure_def)
			.then(sd => {
				let elements = sd.element_paths;
				const dialog = new frappe.ui.Dialog({
					title: __("Map FHIR {0} ({1}) → Frappe {2}", [sd.fhir_sd, sd.sd_version, frm.doc.frappe_doctype]),
					size: "large",
					fields: [{ fieldtype: "HTML", fieldname: "map_table" }],
					primary_action_label: __("Save Mapping"),
					primary_action: () => {

						const element_maps = [];
						dialog.$wrapper.find("tbody tr").each(function () {

							const $row = $(this);
							const element = elements.find(({ path }) => path === $row.attr("data-path"));

							element_maps.push({
								fhir_path: $row.attr("data-path"),
								frappe_field: $row.find("select").val() || null,
								default_value: $row.find("input.default-value").val() || null,
								// copy/overwrite from structure definition
								fhir_datatype: element.type,
								min: element.min,
								max: element.max,
								short: element.short,
								definition: element.definition,
								is_required: element.is_required,
							});
						});

						// save
						frm.call("save_mapped_elements", {

							elements: element_maps,
						}).then(r => {

							frappe.show_alert({
								"indicator": "success",
								"message": __("Saved"),
							});
						}).catch(() => {

							frappe.show_alert({
								"indicator": "error",
								"message": __("Couldn't Save Mapping"),
							});
						});

						frm.reload_doc();
						dialog.hide();

					},
				}); // dialog

				// build map_table
				let html = ""
					+ "<table class='table table-bordered'>"
					+ "<thead><tr>"
					+ "<th>" + __("FHIR Element Path") + "</th>"
					+ "<th>" + __("Frappe Field") + "</th>"
					+ "<th>" + __("Data Type") + "</th>"
					+ "<th>" + __("Min Card") + "</th>"
					+ "<th>" + __("Default Value") + "</th>"
					+ "</tr></thead>"
					+ "<tbody>";

				elements.forEach(el => {

					const is_id = el.path === `${sd.fhir_sd}.id`; // path .id is mapped to name
					const is_dt = el.path === sd.fhir_sd; // resource is mapped to doctype

					// if already mapped, set that
					const map = frm.doc.map.find(({ fhir_path }) => fhir_path === el.path);
					const id_val = is_id ? "name" : ((frm.doc.map.length ? map.frappe_field : "") || "");
					const dt_val = is_dt ? frm.doc.frappe_doctype : ((frm.doc.map.length ? map.default_value : "") || "");

					// fhir element paths
					html += "<tr data-path='" + el.path + "'>" // new row
						+ "<td>" + el.path + "</td>"

						// Frappe Field
						// set select options
						+ "<td><select class='form-control'" + (is_dt || is_id ? " disabled" : "") + ">"
						+ "<option value=''>" + __("-- Select --") + "</option>";
					doc_fields.forEach(f => {
						const sel = (f === id_val) ? " selected" : ""; // name is selected
						html += "<option value='" + f + "'" + sel + ">" + f + "</option>";
					});
					html += "</select></td>"

						// Data Type (readonly) Remove?
						+ "<td><input class='form-control' type='text'"
						+ " value='" + (el.type || "") + "' readonly></td>"

						// Min Card (readonly)
						+ "<td><input class='form-control' type='text'"
						+ " value='" + (el.min || 0) + "' readonly></td>"

						// Default Value
						+ "<td><input class='form-control default-value'"
						+ " value='" + dt_val + "'" + (is_dt ? " readonly" : "") + ">"
						+ "</td>"

						+ "</tr>";
				});

				html += "</tbody></table>";
				dialog.fields_dict.map_table.$wrapper.html(html);
				dialog.show();

			}); // db.get_doc FHIR Structure Definition

	});
}
