// Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
// For license information, please see license.txt

const COMPLEX_FHIR_DATATYPES = [
    "HumanName",
    "Address",
    "ContactPoint",
    "Reference",
    "Period",
    "Identifier",
    "CodeableConcept",
    "Coding",
    "Attachment",
    "Signature",
    "Quantity",
    "Money",
    "Ratio",
    "SampledData",
    "Age",
    "Distance",
    "Count",
    "Range",
    "Duration",
    "Timing",
    "Annotation",
    "Narrative",
    "Extension",
    "BackboneElement",
    "ElementDefinition",
    "Meta",
    "Dosage",
    "RelatedArtifact",
    "UsageContext",
    "DataRequirement",
    "ParameterDefinition",
    "Expression",
    "TriggerDefinition",
]

frappe.ui.form.on("FHIR Resource Map", {
	onload_post_render: (frm) => {
		frm.set_query("fhir_profile", () => ({
			filters: {
				fhir_version: frm.doc.fhir_version,
				is_active: 1,
			},
		}));

		frm.set_query("fhir_structure_def", () => ({
			filters: {
				fhir_version: frm.doc.fhir_version,
				fhir_profile: frm.doc.fhir_profile,
			},
		}));

		frm.set_query("frappe_doctype", () => ({
			filters: {
				istable: 0,
			},
		}));
	},

	refresh: (frm) => {
		frm.fields_dict["map"].grid.wrapper.find(".grid-add-row").hide();
		frm.fields_dict["map"].grid.add_custom_button(__("Map Fields"), () => {
			show_map_dialog(frm);
		});

		frm.add_custom_button(__("Preview Resource"), () => {
			if (!frm.doc.frappe_doctype) {
				frappe.throw(__("Please map a Doctype and fields to generate preview."));
			}
			const dialog = new frappe.ui.Dialog({
				title: __("FHIR Resource Preview"),
				fields: [
					{
						label: __(`Select a ${frm.doc.frappe_doctype} Document`),
						fieldname: "docname",
						fieldtype: "Link",
						options: frm.doc.frappe_doctype,
						reqd: true
					}
				],
				primary_action_label: "Preview",
				primary_action(values) {
					const docname = values.docname;
					frappe.call({
						method: "preview_fhir_resource",
						doc: frm.doc,
						args: { docname: docname },
						callback(res) {
							const json = JSON.stringify(res.message, null, 2);
							const blob = new Blob([json], { type: 'application/json' });
							const url = URL.createObjectURL(blob);
							const downloadId = frappe.utils.get_random(8);

							const html = `
								<pre style="max-height: 600px; overflow: auto;">${frappe.utils.escape_html(json)}</pre>
								<div style="margin-top: 1rem;">
									<a id="download-${downloadId}" href="${url}" download="${frm.doc.frappe_doctype}-${docname}-Marley-FHIR.json" class="btn btn-sm btn-primary">
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
		});
	}
});

function show_map_dialog(frm) {

	if (!frm.doc.frappe_doctype) {
		frappe.throw("Please select a DocType and Structure Definition to start mapping");
	}
	frappe.model.with_doctype(frm.doc.frappe_doctype, () => {
		let doc_fields = [];
		doc_fields.push({ value: "name", label: "ID" });
		const meta = frappe.get_meta(frm.doc.frappe_doctype);

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

		if (!frm.doc.fhir_structure_def) {
			frappe.throw("Please select a Structure Definition and Doctype to start mapping");
		}
		frappe.db.get_doc("FHIR Structure Definition", frm.doc.fhir_structure_def)
			.then(sd => {
				let elements = sd.element_paths;
				let path_to_mapping = {};

				const dialog = new frappe.ui.Dialog({
					title: __("Map FHIR {0} ({1}) → Frappe {2}", [sd.fhir_sd, sd.sd_version, frm.doc.frappe_doctype]),
					size: "extra-large",
					fields: [{ fieldtype: "HTML", fieldname: "map_table" }],
					primary_action_label: __("Save Mapping"),
					primary_action: () => {
						const element_maps = Object.values(path_to_mapping);
						const missing_required = element_maps.filter(
							el => el.is_required && !COMPLEX_FHIR_DATATYPES.includes(el.datatype) && !el.frappe_field && !el.default_value
						);
						if (missing_required.length) {
							frappe.msgprint(__("Not all mandatory FHIR fields are mapped. Missing: ") + missing_required.map(e => e.fhir_path).join(", "));
							return;
						}
						frm.call("save_mapped_elements", {
							elements: element_maps,
						}).then(() => {
							frappe.show_alert({ "indicator": "success", "message": __("Saved") });
							frm.reload_doc();
						}).catch(() => {
							frappe.show_alert({ "indicator": "error", "message": __("Couldn't Save Mapping") });
						});
						dialog.hide();
					},
				});

				let html = `<input class="form-control mb-2" placeholder="${__("Search...")}" id="map-search">
					<table class='table table-bordered'>`
				html += get_header_row_html();
				html += `<tbody>`

				elements.forEach(el => {
				    if (el.path === sd.fhir_sd) return;

					const is_id = el.path === `${sd.fhir_sd}.id`;
					const is_dt = el.path === sd.fhir_sd;
					const is_editable = el.is_choice_type;

					const map = frm.doc.map.find(({ fhir_path }) =>
						fhir_path === el.path ||
						(el.path.includes("[x]") && fhir_path.startsWith(el.path.replace("[x]", "")))
					);
					const id_val = is_id ? "name" : (map ? map.frappe_field : "");
					const dt_val = is_dt ? frm.doc.frappe_doctype : (map ? (map.default_value || "") : "");
					const type_val = (map && map.datatype) || el.datatype || "";
					const path_val = (map && map.fhir_path) || el.path || "";
					const is_container = COMPLEX_FHIR_DATATYPES.includes(el.datatype)

					path_to_mapping[el.path] = {
						fhir_path: el.path,
						frappe_field: id_val || null,
						datatype: type_val || el.type,
						min: el.min,
						max: el.max,
						short: el.short,
						definition: el.definition,
						is_required: el.is_required,
						is_choice_type: el.is_choice_type,
						valueset_url: el.valueset_url,
						binding_strength: el.binding_strength,
						fixed_value: el.fixed_value,
						pattern_value: el.pattern_value,
						default_value: dt_val || el.default_value,
						target_profiles: el.target_profiles,
					};

					html += `<tr data-path="${el.path}">
						<td><input class='form-control path' value="${path_val}" ${!is_editable ? "readonly" : ""}></td>
						<td><input class='form-control type' value="${type_val}" ${!is_editable ? "readonly" : ""}></td>
						<td><input class='form-control' value="${el.min || 0}" readonly></td>
						<td><select class='form-control frappe-field' ${is_dt || is_id || is_container ? "disabled" : ""}>
							<option value="">${__("-- Select --")}</option>
							${doc_fields.map(f => `<option value="${f.value}" ${f.value === id_val ? "selected" : ""}>${f.label}</option>`).join("")}
						</select></td>
						<td><input class='form-control default-value' value="${dt_val}" ${is_dt || is_id || is_container ? "readonly" : ""}></td>
						</tr>`;
				});

				html += "</tbody></table>";
				dialog.fields_dict.map_table.$wrapper.html(html);

				dialog.$wrapper.find("#map-search").on("input", function () {
					const query = $(this).val().toLowerCase();
					dialog.$wrapper.find("tbody tr").each(function () {
						const path = $(this).find(".path").val().toLowerCase();
						$(this).toggle(path.includes(query)); // show / hide, for search
					});
				});

				dialog.$wrapper.find("tbody").on("change", "select, input", function () {
					const $tr = $(this).closest("tr");
					const path = $tr.data("path");
					path_to_mapping[path].datatype = $tr.find(".type").val() || null;
					path_to_mapping[path].frappe_field = $tr.find(".frappe-field").val() || null;
					path_to_mapping[path].default_value = $tr.find(".default-value").val() || null;
				});

				dialog.show();
			});
	});
}

function get_frappe_doc_fields(doctype) {
	let fields = [{ value: "name", label: "ID" }];
	const meta = frappe.get_meta(doctype);
	meta.fields.forEach(df => {
		if (!["Section Break", "Column Break", "Tab Break"].includes(df.fieldtype)) {
			if (df.fieldtype === "Table" && df.options) {
				const child_meta = frappe.get_meta(df.options);
				const child_table_label = df.label || df.fieldname;
				child_meta.fields.forEach(sub_df => {
					if (!["Section Break", "Column Break", "Tab Break"].includes(sub_df.fieldtype)) {
						fields.push({
							value: `${df.fieldname}.${sub_df.fieldname}`,
							label: `${sub_df.label} (${child_table_label})`,
						});
					}
				});
			} else {
				fields.push({ value: df.fieldname, label: df.label || df.fieldname });
			}
		}
	});
	return fields;
}

function get_header_row_html() {
	return `
		<thead>
			<tr>
			<th style='width:30%;'>${__("FHIR Element Path")}</th>
			<th style='width:20%;'>${__("Data Type")}</th>
			<th style='width:10%;'>${__("Min Card")}</th>
			<th style='width:20%;'>${__("Frappe Field")}</th>
			<th style='width:20%;'>${__("Default Value")}</th>
			</tr>
		</thead>
	`;
}
