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

		frm.add_custom_button(__("Preview Resource"), () => {
			const frappe_doctype = frm.doc.frappe_doctype;

			if (!frappe_doctype) {
				frappe.throw(__("Please map a doctype and fields to generate preview"))
			}

			const dialog = new frappe.ui.Dialog({
				title: __("FHIR Resource Preview"),
				fields: [
					{
						label: __(`Select a ${frappe_doctype} Document`),
						fieldname: "docname",
						fieldtype: "Link",
						options: frappe_doctype,
						reqd: true
					}
				],
				primary_action_label: "Preview",
				primary_action(values) {
					let docname = values.docname;
					frappe.call({

						method: "preview_fhir_resource",
						doc: frm.doc,
						args: { docname: docname },
						callback(res) {

							const json = JSON.stringify(res.message[0], null, 2);
							const blob = new Blob([json], { type: 'application/json' });
							const url = URL.createObjectURL(blob);
							const downloadId = frappe.utils.get_random(8);

							const html = `
								<pre style="max-height: 600px; overflow: auto;">${frappe.utils.escape_html(json)}</pre>
								<div style="margin-top: 1rem;">
									<a id="download-${downloadId}" href="${url}" download="${frappe_doctype}-${docname}-Marley-FHIR.json" class="btn btn-sm btn-primary">
										${__("Download JSON")}
									</a>
								</div>
							`;
							dialog.hide();

							frappe.msgprint({
								title: __("FHIR Resource Preview"),
								message: html,
								indicator: "blue",
								wide: 1,
							});
						}
					});
				}
			});

			dialog.show();
		}); // button Preview Resource

	}
});

function show_map_dialog(frm) {
	frappe.model.with_doctype(frm.doc.frappe_doctype, () => {
		let doc_fields = [];

		doc_fields.push({
			value: "name",
			label: "ID",
		});
		const meta = frappe.get_meta(frm.doc.frappe_doctype);

		// Get main doctype fields
		meta.fields.forEach(df => {
			if (!["Section Break", "Column Break", "Tab Break"].includes(df.fieldtype)) {
				if (df.fieldtype === "Table" && df.options) {

					const child_meta = frappe.get_meta(df.options);
					const child_table_label = df.label || df.fieldname;

					child_meta.fields.forEach(sub_df => {
						if (!["Section Break", "Column Break", "Tab Break"].includes(sub_df.fieldtype)) {
							doc_fields.push({
								value: `${df.fieldname}.${sub_df.fieldname}`,
								label: `${sub_df.label} (${child_table_label})`,
							});
						}
					});
				} else {
					doc_fields.push({
						value: df.fieldname,
						label: df.label || df.fieldname,
					});
				}
			}
		});


		frappe.db.get_doc("FHIR Structure Definition", frm.doc.fhir_structure_def)
			.then(sd => {
				let elements = sd.element_paths;
				const dialog = new frappe.ui.Dialog({
					title: __("Map FHIR {0} ({1}) → Frappe {2}", [sd.fhir_sd, sd.sd_version, frm.doc.frappe_doctype]),
					size: "extra-large",
					fields: [{ fieldtype: "HTML", fieldname: "map_table" }],
					primary_action_label: __("Save Mapping"),
					primary_action: () => {

						const element_maps = [];
						dialog.$wrapper.find("tbody tr").each(function () {

							const $row = $(this);
							const element = elements.find(({ path }) => path === $row.attr("data-path"));
							console.log(element);
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
								is_choice_type: element.is_choice_type,
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
					+ "<th style='width:30%;'>" + __("FHIR Element Path") + "</th>"
					+ "<th style='width:20%;'>" + __("Data Type") + "</th>"
					+ "<th style='width:10%;'>" + __("Min Card") + "</th>"
					+ "<th style='width:20%;'>" + __("Frappe Field") + "</th>"
					+ "<th style='width:20%;'>" + __("Default Value") + "</th>"
					+ "</tr></thead>"
					+ "<tbody>";

				elements.forEach(el => {

					const is_id = el.path === `${sd.fhir_sd}.id`; // path .id is mapped to name
					const is_dt = el.path === sd.fhir_sd; // resource is mapped to doctype
					const is_editable = el.is_choice_type; // is datatype choice element

					// if already mapped, set that
					const map = frm.doc.map.find(({ fhir_path }) => fhir_path === el.path);
					const id_val = is_id ? "ID" : ((map ? map.frappe_field : "") || "");
					const dt_val = is_dt ? frm.doc.frappe_doctype : ((map ? map.default_value : "") || "");

					// fhir element paths (not readonly cos of choice)
					html += `<tr data-path=${el.path}>`
					+ "<td><input class='form-control' type='text'"
					+ " value='" + (el.path || "") + `' ${!is_editable ? " readonly" : ""}></td>`

					// Data Type (not readonly cos of choice)
					+ "<td><input class='form-control' type='text'"
					+ " value='" + (el.type || "") + `' ${!is_editable ? " readonly" : ""}></td>`

					// Min Card (readonly)
					+ "<td><input class='form-control' type='text'"
					+ " value='" + (el.min || 0) + "' readonly></td>"

					// Frappe field
					html += `<td><select class='form-control'${(is_dt || is_id ? " disabled" : "")}>`;
					html += `<option value="">${__("-- Select to Map --")}</option>`;

					doc_fields.forEach(f => {
						const sel = (f.label === id_val) ? " selected" : "";
						html += `<option value="${f.value}"${sel}>${f.label}</option>`;
					});
					html += "</select></td>";

					// Default Value
					html += "<td><input class='form-control default-value'"
					+ " value='" + dt_val + "'" + (is_dt ? " readonly" : "") + ">"
					+ "</td>"
					+ "<td hidden>" + (el.short || "") + "</td>"
					+ "<td hidden>" + (el.definition || "") + "</td>"
					+ "</tr>";
				});

				html += "</tbody></table>";
				dialog.fields_dict.map_table.$wrapper.html(html);
				dialog.show();

			}); // db.get_doc FHIR Structure Definition

	});
}
