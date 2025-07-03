frappe.ui.form.on("Patient Encounter", {
	refresh: function (frm) {
		if (frappe.boot.sysdefaults.country == "India") {
			if (!frm.is_new() && frm.doc.patient) {
				frm.add_custom_button(__("Link Carecontext"), function () {
					frappe.call({
						method: 'healthcare.regional.india.abdm.utils.link_carecontext',
						args: {
							"doctype": frm.doc.doctype,
							"docname": frm.doc.name
						},
						freeze: true,
						freeze_message: __('Linking...'),
						callback: function (data) {
							if (data.message && data.message.doctype == "Patient") {
								generate_link_token(frm, data.message);
							}
						}
					})
				}, "ABDM");
			}
		}
	}
});

let generate_link_token = function (frm, data) {
	let dialog = new frappe.ui.Dialog({
		title: 'Generate Link Token',
		fields: [
			{
				label: 'ABHA Address',
				fieldname: 'abha_address',
				fieldtype: 'Data',
				reqd: 1
			},
			{
				label: 'ABHA Number',
				fieldname: 'abha_number',
				fieldtype: 'Data',
				reqd: 1
			},
			{
				label: 'Name',
				fieldname: 'name',
				fieldtype: 'Data',
				reqd: 1
			},
			{
				label: 'Gender',
				fieldname: 'gender',
				fieldtype: 'Link',
				options: 'Gender',
				reqd: 1
			},
			{
				label: 'Year of Birth',
				fieldname: 'year_of_birth',
				fieldtype: 'Int',
				reqd: 1
			}
		],
		primary_action_label: 'Generate',
		primary_action(values) {
			frappe.call({
				method: 'healthcare.regional.india.abdm.utils.generate_hip_token',
				args: values,
				freeze: true,
				freeze_message: __('Generating...'),
				callback: function (data) {
					dialog.hide();
					if (data.message.error){
						frappe.show_alert({
							message: __(data.message.error.message),
							indicator: 'red'
						}, 5);
					} else {
						frappe.show_alert({
							message: __('Request to Generate Link Token Success'),
							indicator: 'green'
						}, 5);
					}
				}
			});
		},
	});

	dialog.set_values({
		"abha_address": data.abha_address,
		"abha_number": data.abha_number,
		"name": data.patient_name,
		"gender": data.sex,
		"year_of_birth": moment(data.dob, "YYYY-MM-DD").year()
	})
	dialog.show();
}