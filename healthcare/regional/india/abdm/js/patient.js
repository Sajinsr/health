frappe.ui.form.on('Patient', {
	refresh: function (frm) {
		if (frappe.boot.sysdefaults.country == 'India') {
			unhide_field(['abha_number', 'abha_address']);
			if (!frm.doc.abha_address && !frm.doc.abha_number) {
				frm.add_custom_button(__('Verify ABHA'), function () {
					search_by_abha_address(frm)
				}, 'ABDM');
			}
			if (frm.doc.abha_number) {
				frm.add_custom_button(__('Verify ABHA Number'), function () {
					verify_health_id(frm, frm.doc.abha_number)
				}, 'ABDM');
			}
			if (!(frm.doc.abha_address || frm.doc.abha_number)) {
				frm.add_custom_button(__('Create ABHA'), function () {
					create_abha(frm)
				}, 'ABDM');
			}
			if (frm.doc.abha_number && frm.doc.abha_address){
				frm.add_custom_button(__('Generate Link Token'), function () {
					generate_link_token(frm);
				}, 'ABDM');
			}
		} else {
			hide_field(['abha_number', 'abha_address']);
		}
	}
});

// search by ABHA address. If know ABHA number, can be verified
let search_by_abha_address = function (frm) {
	let txnId = null;
	let dialog = new frappe.ui.Dialog({
		title: 'Enter ABHA Address / Number',
		fields: [
			{
				label: 'Verification Type',
				fieldname: 'verification_type',
				fieldtype: 'Select',
				options: "ABHA Address\nABHA Number",
				default: "ABHA Address",
				reqd: 1,
				read_only_depends_on: "eval: doc.otp_send",
			},
			{
				label: 'ABHA Address',
				fieldname: 'abha_address',
				fieldtype: 'Data',
				mandatory_depends_on: "eval: doc.verification_type=='ABHA Address'",
				depends_on: "eval: doc.verification_type=='ABHA Address'",
				description: "eg: john123@abdm"
			},
			{
				label: 'ABHA Number',
				fieldname: 'abha_number',
				fieldtype: 'Data',
				mandatory_depends_on: "eval: doc.verification_type=='ABHA Number'",
				depends_on: "eval: doc.verification_type=='ABHA Number'",
				description: "eg: xx-xxxx-xxxx-xxxx"
			},
			{
				fieldname: 'sb1',
				fieldtype: 'Section Break',
				depends_on: "eval: doc.otp_send",
			},
			{
				fieldtype: "Check",
				label: "OTP Send",
				fieldname: "otp_send",
				hidden: 1,
				default: 0,
			},
			{
				label: 'OTP',
				fieldname: 'otp',
				fieldtype: 'Data',
				depends_on: "eval: doc.otp_send",
				mandatory_depends_on: "eval: doc.otp_send",
			},
			{
				fieldname: "cb-01",
				fieldtype: "Column Break",
			},
			{
				label: 'Verify OTP',
				fieldname: 'verify',
				fieldtype: 'Button',
				depends_on: "eval: doc.otp_send",
				mandatory_depends_on: "eval: doc.otp_send",
				click: function () {
					let payload = {
						"scope": [
							dialog.get_value("verification_type") == "ABHA Number" ? "abha-login" : "abha-address-login",
							"aadhaar-verify"
						],
						"authData": {
							"authMethods": [
								"otp"
							],
							"otp": {
								"txnId": txnId,
								"otpValue": dialog.get_value("otp")
							}
						}
					}
					show_message(dialog, '', '', '', 'abha_number')
					show_message(dialog, '', '', '', 'abha_address')
					let url_key = dialog.get_value("verification_type") == "ABHA Number" ? "verify_abha_number_otp" : "verify_abha_address_otp"
					verify_otp(frm, dialog, payload, url_key, "otpValue");
				},
			},
			{
				fieldname: 'sb2',
				fieldtype: 'Section Break',
				depends_on: "eval: doc.otp_send",
			},
			{
				fieldname: 'qr_data',
				fieldtype: 'HTML'
			},
			{
				fieldname: 'scanned_data',
				fieldtype: 'Small Text',
				hidden: 1
			},
		],
		primary_action_label: 'Send ABHA OTP',
		primary_action(values) {
			if (values.verification_type == "ABHA Address" && !values.abha_address) {
				frappe.throw({
					message: __("ABHA Address is required to search"),
					title: __("ABHA Address Required")
				});
			} else if (values.verification_type == "ABHA Number" && !values.abha_number) {
				frappe.throw({
					message: __("ABHA Number is required to search"),
					title: __("ABHA Number Required")
				});
			} else {
				show_message(dialog, 'Searching...', 'black', '', values.verification_type == "ABHA Address"? 'abha_address' : "abha_number");
				let payload = {
					"abhaAddress": values.abha_address
				};
				if (values.verification_type == "ABHA Number") {
					payload = {
						"scope": [
							"abha-login",
							"aadhaar-verify"
						],
						"loginHint": "abha-number",
						"loginId": values.abha_number,
						"otpSystem": "aadhaar"
					}
				}
				let args = {
					'payload': payload,
					'url_key': values.verification_type == "ABHA Address" ? "verify_abha_address" : "verify_abha_number",
					'req_type': 'Health ID',
					"to_be_enc": values.verification_type == "ABHA Number" ? "loginId" : null
				}

				frappe.call({
					method: 'healthcare.regional.india.abdm.utils.abdm_request',
					args: args,
					freeze: true,
					freeze_message: __('Searching...'),
					callback: async function (data) {
						if (values.verification_type == "ABHA Number") {
							if (data.message["txnId"]) {
								show_message(dialog, data.message['message'], 'green', '', 'abha_number')
								dialog.set_value("otp_send", 1);
								txnId = data.message["txnId"];

								dialog.get_primary_btn().attr('disabled', true);
							} else if (data.message["code"]) {
								show_message(dialog, data.message['message'], 'red', '', 'abha_number')
							} else {
								show_message(dialog, '', '', '', 'abha_number')
							}
						} else {
							if (data.message['healthIdNumber']) {
								show_message(dialog, 'Status:' + data.message['status'], 'green', '', 'abha_address')
								dialog.set_values ({
									'abha_number': data.message['healthIdNumber']
								})
								txnId = await send_abha_address_otp(frm, dialog, values.abha_address)
								dialog.get_primary_btn().attr('disabled', true);
							} else {
								show_message(dialog, data.message.message || data.message, 'red', '', 'abha_address')
							}
						}
					}
				});
			}
		},
		secondary_action_label: 'Save',
		secondary_action(values) {
			// save data from qr_scan/api fetch, save to form
			var scanned_data = JSON.parse(dialog.get_value("scanned_data"));
			if (scanned_data && scanned_data["token"]) {
				let url_key = dialog.get_value("verification_type") == "ABHA Number" ? "get_account_profile" : "get_profile"
				get_profile_details(frm, dialog, scanned_data, url_key);
			}
		}
	});
	dialog.show();

	dialog.get_secondary_btn().attr('disabled', true);
	dialog.fields_dict['scanned_data'].df.onchange = () => {
		if (dialog.get_value('scanned_data')) {
			dialog.get_secondary_btn().attr('disabled', false);
		}
	}
}


let verify_otp = function(frm, dialog, payload, url_key, to_be_enc) {
	show_message(dialog, 'Verifying...', 'black', '', 'otp')
	let args = {
		'payload': payload,
		'url_key': url_key,
		'req_type': 'Health ID',
		"to_be_enc": to_be_enc
	}
	frappe.call({
		method: 'healthcare.regional.india.abdm.utils.abdm_request',
		args: args,
		freeze: true,
		freeze_message: __(`Verifying OTP... <br>
			<small>Please note, this may take a while</small>`),
		callback: function (data) {
			if (data.message["authResult"] == "success") {
				show_message(dialog, data.message['message'], 'green', '', 'otp');
				if (data.message["accounts"]) {
					let account_data = data.message["accounts"][0];
					account_data["token"] = data.message["token"];
					dialog.set_values({
						'scanned_data': JSON.stringify(account_data)
					});
					let abha_details = $(`
						<table class="table table-bordered" style="width: 100%; margin: 0;">
							<tbody>
								<tr>
									<th>Name</th>
									<td>${account_data['name'] || '-'}</td>
								</tr>
								<tr>
									<th style="width: 50%;">ABHA Number</th>
									<td style="width: 50%;">${account_data['ABHANumber'] || '-'}</td>
								</tr>
								<tr>
									<th style="width: 50%;">ABHA Address</th>
									<td style="width: 50%;">${account_data['preferredAbhaAddress'] || '-'}</td>
								</tr>
								<tr>
									<th style="width: 50%;">Status</th>
									<td style="width: 50%;">${account_data['status'] || '-'}</td>
								</tr>
							</tbody>
						</table>
					`);
					$(dialog.fields_dict.qr_data.$wrapper).html(abha_details);
				} else if (data.message["users"]) {
					let user_data = data.message["users"][0];
					user_data["token"] = data.message["tokens"]["token"]
					dialog.set_values({
						'scanned_data': JSON.stringify(user_data)
					});
					let abha_details = $(`
						<table class="table table-bordered" style="width: 100%; margin: 0;">
							<tbody>
								<tr>
									<th>Name</th>
									<td>${user_data['fullName'] || '-'}</td>
								</tr>
								<tr>
									<th style="width: 50%;">ABHA Number</th>
									<td style="width: 50%;">${user_data['abhaNumber'] || '-'}</td>
								</tr>
								<tr>
									<th style="width: 50%;">ABHA Address</th>
									<td style="width: 50%;">${user_data['abhaAddress'] || '-'}</td>
								</tr>
								<tr>
									<th style="width: 50%;">Status</th>
									<td style="width: 50%;">${user_data['status'] || '-'}</td>
								</tr>
								<tr>
									<th style="width: 50%;">KYC Status</th>
									<td style="width: 50%;">${user_data['kycStatus'] || '-'}</td>
								</tr>
							</tbody>
						</table>
					`);
					$(dialog.fields_dict.qr_data.$wrapper).html(abha_details);
				} else {
					$(dialog.fields_dict.qr_data.$wrapper).html("There is no details to show here");
				}
			} else if (data.message["authResult"] == "failed") {
				show_message(dialog, data.message['message'], 'red', '', 'otp');
			} else {
				if (data.message["code"]) {
					show_message(dialog, data.message["message"], "red", "", 'otp');
				} else if (data.message[0]["code"]) {
					show_message(dialog, data.message[0]["message"], "red", "", 'otp');
				} else {
					show_message(dialog, "", "", "", 'otp');
				}
			}
		}
	});
};


let send_abha_address_otp = async function(frm, dialog, abha_address) {
	show_message(dialog, 'Sending OTP...', 'black', '', 'abha_address')
	let txnId = null;
	let args = {
		'payload': {
			"scope": [
				"abha-address-login",
				"aadhaar-verify"
			],
			"loginHint": "abha-address",
			"loginId": abha_address,
			"otpSystem": "aadhaar"
		},
		'url_key': "send_abha_address_otp",
		'req_type': 'Health ID',
		"to_be_enc": "loginId"
	}
	let response = (
		await frappe.call(
			"healthcare.regional.india.abdm.utils.abdm_request",
			args
		)
	).message;
	if (response["txnId"]) {
		show_message(dialog, response['message'], 'green', '', 'abha_address')
		txnId = response["txnId"];
		dialog.set_value("otp_send", 1);
		return txnId
	} else if (Array.isArray(response)) {
		show_message(dialog, response[0]["message"], 'red', '', 'abha_address')
	} else {
		if (response["code"]) {
			show_message(dialog, response['message'], 'red', '', 'abha_address')
		}
	}
};

let get_profile_details = function(frm, dialog, scanned_data, url_key) {
	frappe.call({
		method: 'healthcare.regional.india.abdm.utils.abdm_request',
		args: {
			'payload': {},
			'url_key': url_key,
			'req_type': 'Health ID',
			'rec_headers': {
				'X-Token': 'Bearer '+ scanned_data.token
			},
		},
		freeze: true,
		freeze_message: __(`Getting Profile Details.`),
		callback: async function (data) {
			let message = null;
			let color = "red";
			if (data.message["ABHANumber"] || data.message["abhaNumber"]) {
				await set_data_to_form(frm, data.message, dialog, null);
				dialog.hide();
				let card_url = url_key == "get_account_profile" ? "get_account_card" : "get_card"
				show_id_card_dialog(frm, scanned_data.token, card_url);
			} else if (data.message["message"]) {
				message = `${data.message['message']}`;
				let description = data.message["description"] ? data.message["description"] : ""
				if (description) {
					message += `, Description: ${description}`;
				}
			} else if (data.message["error"]) {
				message = data.message['error']["message"];
			} else {
				message = null;
			}
			if (message) {
				frappe.show_alert({
					message:__(message),
					indicator: color
				}, 10);
			}
		}
	});
};


let show_id_card_dialog = function(frm, token, card_url) {
	frappe.run_serially([
		() =>frm.save(),
		() =>{
			frappe.call({
				method: 'healthcare.regional.india.abdm.utils.abdm_request',
				args: {
					'payload': {},
					'url_key': card_url,
					'req_type': 'Health ID',
					'rec_headers': {
						'X-Token': 'Bearer '+ token
					},
					'patient_name': frm.doc.name
				},
				freeze: true,
				freeze_message: __(`Getting Health ID`),
				callback: function (data) {
					if (data.message) {
						frm.set_value('abha_card', data.message)
						frm.save();
						let abha_id_dialog = new frappe.ui.Dialog({
							title: 'ABHA Card',
							fields: [
								{
									fieldname: 'abha_card_html',
									fieldtype: 'HTML',
								}
							],
							primary_action_label: 'Print',
							primary_action(values) {
								let result = `<div style="text-align: center;">
									<img src="${data.message}" style="max-width: 100%; height: auto; border-radius: 6px;" />
								</div>`
								frappe.render_pdf(result, { orientation: "Portrait", "report_name": `abha_card-${frm.doc.patient_name}`});
							},
						})
						$(abha_id_dialog.fields_dict.abha_card_html.$wrapper).html(
							`<div style="text-align: center;">
								<img src="${data.message}" style="max-width: 100%; height: auto; border-radius: 6px;" />
							</div>`
						)
						abha_id_dialog.show();
					}
				}
			})
		}
	])
}


let verify_health_id = function (frm, recieved_abha_number = '') {
	let txnId = null;
	let d = new frappe.ui.Dialog({
		title: 'Verify ABHA',
		fields: [
			{
				label: 'ABHA Number',
				fieldname: 'abha_number',
				fieldtype: 'Data'
			},
			{
				label: 'Authentication Method',
				fieldname: 'auth_method',
				fieldtype: 'Select',
				options: ['Aadhaar OTP', 'Mobile OTP'],
				default: 'Aadhaar OTP'
			},
			{
				label: 'Mobile',
				fieldname: 'mobile',
				fieldtype: 'Data',
				depends_on: "eval: doc.auth_method=='Mobile OTP'"
			},
			{
				fieldname: 'sb1',
				fieldtype: 'Section Break',
				depends_on: "eval: doc.otp_send",
			},
			{
				fieldtype: "Check",
				label: "OTP Send",
				fieldname: "otp_send",
				hidden: 1,
				default: 0,
			},
			{
				label: 'OTP',
				fieldname: 'otp',
				fieldtype: 'Data',
				depends_on: "eval: doc.otp_send",
				mandatory_depends_on: "eval: doc.otp_send",
			},
			{
				fieldname: "cb-01",
				fieldtype: "Column Break",
			},
			{
				label: 'Verify OTP',
				fieldname: 'verify',
				fieldtype: 'Button',
				depends_on: "eval: doc.otp_send",
				mandatory_depends_on: "eval: doc.otp_send",
				click: function () {
					let payload = {
						"scope": [
							"abha-login",
							d.get_value("auth_method") == "Mobile OTP" ? "mobile-verify" : "aadhaar-verify",

						],
						"authData": {
							"authMethods": [
								"otp"
							],
							"otp": {
								"txnId": txnId,
								"otpValue": d.get_value("otp")
							}
						}
					}
					show_message(d, '', '', '', 'auth_method')
					verify_otp(frm, d, payload, "verify_abha_number_otp", "otpValue");
				},
			},
			{
				fieldname: 'sb2',
				fieldtype: 'Section Break'
			},
			{
				fieldname: 'qr_data',
				fieldtype: 'HTML'
			},
			{
				fieldname: 'scanned_data',
				fieldtype: 'Small Text',
				hidden: 1
			},
			{
				fieldname: 'abha_card',
				fieldtype: 'Attach',
				hidden: 1
			}
		],
		primary_action_label: 'Send OTP',
		primary_action(values) {
			d.get_primary_btn().attr('disabled', true);
			show_message(d, '', '', '', 'auth_method')
			frappe.run_serially([
				() =>frappe.db.get_value('Patient', {abha_number: d.get_value('abha_number'), name: ['!=', frm.doc.name]	}, ['name', 'abha_card'])
					.then(r =>{
						if (r.message.name) {
							frappe.set_route("Form", "Patient", r.message.name);
							if (r.message.abha_card) {
								frappe.throw({
									message: __("<img src='"+ r.message.abha_card + "'>"),
									title: __("Patient already exist")
								});
							} else {
								frappe.throw({
									message: __('<a href="/app/patient/'+r.message.name+'">' + r.message.name + '</a>'),
									title: __("Patient already exist")
								});
							}
						}
					}),
				() => {show_message(d, 'Sending Auth OTP...', 'black', '', 'auth_method')
					let payload = {
						"scope": [
							"abha-login",
							values.auth_method=='Mobile OTP' ? "mobile-verify" : "aadhaar-verify"
						],
						"loginHint": values.auth_method=='Mobile OTP' ? "mobile" : "abha-number",
						"loginId": values.auth_method=='Mobile OTP' ? values.mobile : values.abha_number,
						"otpSystem": values.auth_method=='Mobile OTP' ? "abdm" : "aadhaar"
					}
					frappe.call({
						method: 'healthcare.regional.india.abdm.utils.abdm_request',
						args: {
							'payload': payload,
							'url_key': 'verify_abha_number',
							'req_type': 'Health ID',
							'to_be_enc': 'loginId'
						},
						freeze: true,
						freeze_message: __('Generating OTP...'),
						callback: function (data) {
							if (data.message["txnId"]) {
								show_message(d, data.message['message'], 'green', '', 'auth_method')
								d.set_value("otp_send", 1);
								txnId = data.message["txnId"];

								d.get_primary_btn().attr('disabled', true);
							} else if (data.message["code"]) {
								show_message(d, data.message['message'], 'red', '', 'auth_method')
							} else {
								show_message(d, '', '', '', 'auth_method')
							}
						}
					});
				}
			])
		},
		secondary_action_label: 'Save',
		secondary_action(values) {
			// save data from qr_scan/api fetch, save to form
			var scanned_data = JSON.parse(d.get_value('scanned_data'));
			if (scanned_data && scanned_data["token"]) {
				let url_key = "get_account_profile"
				get_profile_details(frm, d, scanned_data, url_key);
			}
		}
	});

	// QR scanner field
	setup_qr_scanner(d)

	if (recieved_abha_number) {
		d.set_values({
			'abha_number': recieved_abha_number
		});
	}
	d.get_secondary_btn().attr('disabled', true);
	d.fields_dict['scanned_data'].df.onchange = () => {
		if (d.get_value('scanned_data')) {
			d.get_secondary_btn().attr('disabled', false);
		}
	}
	d.fields_dict['abha_number'].df.onchange = () => {
		d.get_primary_btn().attr('disabled', false);
	}

	d.show();
}


let setup_qr_scanner = function(dialog) {
	dialog.fields_dict.abha_number.$wrapper.find('.control-input').append(
		`<span class="link-btn" style="display:inline">
			<a class="btn-open no-decoration" title="${__("Scan")}">
				${frappe.utils.icon('scan', 'sm')}
			</a>
		</span>`
	);
	let scan_btn = dialog.$body.find('.link-btn');
	scan_btn.toggle(true);

	scan_btn.on('click', 'a', () => {
		new frappe.ui.Scanner({
			dialog: true,
			multiple: false,
			on_scan(data) {
				if (data && data.result && data.result.text) {
					var scanned_data = JSON.parse(data.decodedText);
					dialog.set_values({
						'scanned_data': data.decodedText,
						'abha_number': (scanned_data['hidn'] ? scanned_data['hidn'] : '')
					});
					set_qr_scanned_data(dialog, scanned_data)
				}
			}
		});
	});
}

// to create html table
let set_qr_scanned_data = function(d, scanned_data) {
	let wrapper = $(d.fields_dict['qr_data'].wrapper).empty();
	let dob = '';
	if (scanned_data['dob']) {
		dob = scanned_data['dob']
	} else {
		dob = `${scanned_data['dayOfBirth'] ? scanned_data['dayOfBirth'] : '-'} -
		${scanned_data['monthOfBirth'] ? scanned_data['monthOfBirth'] : '-'} -
		${scanned_data['yearOfBirth']}`;
	}

	let qr_table = $(`<table class="table table-bordered" style="cursor:pointer; margin:0px;">
		<tbody></tbody</table>`).appendTo(wrapper);
	const row =
		$(`<tr>
			<td>Name</td>
			<td>${scanned_data['name']}</td>
		</tr>
		<tr>
			<td>Gender</td>
			<td>${scanned_data['gender'] || '-'}</td>
		</tr>
		<tr>
			<td>Mobile</td>
			<td>${scanned_data['mobile'] ||  '-'}</td>
		</tr>
		<tr>
			<td>DOB</td>
			<td>${dob}</td>
		</tr>
		<tr>
			<td>ABHA Address</td>
			<td>${scanned_data['healthId'] || scanned_data['hid'] || scanned_data['hidn'] ||'-'}</td>
		</tr>`);
	qr_table.find('tbody').append(row);
}


let create_abha = function (frm) {
	let d = new frappe.ui.Dialog({
		title: 'Create ABHA',
		size: "medium",
		fields: [
			{
				label: 'Enter Aadhaar',
				fieldname: 'aadhaar',
				fieldtype: 'Data',
				mandatory: 1
			},
			{
				label:'Patient Consent',
				fieldname: 'patient_consent',
				fieldtype: 'Section Break'
			},
			{
				label:'Patient Consent Form',
				fieldname: 'patient_consent',
				fieldtype: 'Link',
				options: 'Terms and Conditions',
				read_only: 0
			},
			{
				fieldname: 'sb2',
				fieldtype: 'Section Break',
				hide_border: 1
			},
			{
				label: 'Attach Patient Consent',
				fieldname: 'patient_consent_attach',
				fieldtype: 'Attach',
				description: `Please attach patient's signed consent for using their Aadhaar for ABHA creation`
			},
		],
		primary_action_label: 'Send OTP',
		primary_action(values) {
			if (d.get_value('patient_consent_attach')) {
				frappe.throw({
					message: __(`Patient Consent is required for ABHA creation`),
					title: __("Consent Required")
				});
			} else {
				create_abha_with_aadhaar(frm, d)
				d.hide();
			}
		}
	});

	let $field_wrapper = d.fields_dict.patient_consent.$wrapper;
	let $control_input = $field_wrapper.find('.control-input');

	$control_input.find('.print-icon-btn').remove();

	let $print_icon = $(`
		<div class="print-icon-btn" style="position: absolute; right: 35px; top: 50%; transform: translateY(-50%); cursor: pointer;">
			<svg class="icon icon-sm">
				<use href="#icon-printer"></use>
			</svg>
		</div>
	`);

	$control_input.css('position', 'relative').append($print_icon);
	$print_icon.on('click', function () {
		let consent_doc = d.get_value('patient_consent');
		if (!consent_doc) {
			frappe.msgprint("Please select a Patient Consent Form first.");
			return;
		}
		frappe.db.get_value('Terms and Conditions', consent_doc, 'terms')
		.then(r => {
			let result = frappe.render_template(r.message.terms, { "doc": {} });
			frappe.render_pdf(result, { orientation: "Portrait", "report_name": "ABDM Consent Form" });
		});
	});

	frappe.db.get_value('ABDM Settings', {
		company: frappe.defaults.get_user_default("Company"),
		default: 1
	}, 'patient_aadhaar_consent')
	.then(r => {
		if (r.message.patient_aadhaar_consent) {
			d.set_values({
				'patient_consent': r.message.patient_aadhaar_consent
			});
		}
	})
	d.show();
}


let set_data_to_form = function(frm, profile, dialog, d) {
	if (profile) {
		let dob = '';
		if (profile['dob']) {
			dob = profile['dob'];
		} else if (profile['dateOfBirth']) {
			dob = profile['dateOfBirth'];
		} else {
			dob = `${profile['dayOfBirth'] ? profile['dayOfBirth'] : '01'}-
			${profile['monthOfBirth'] ? profile['monthOfBirth'] : '01'}-
			${profile['yearOfBirth']}`;
		}
		for (var k in profile) {
			if (k == 'phrAddress' || k == 'healthId' || k == 'preferredAbhaAddress' || k == "abhaAddress"){
				if (Array.isArray(profile[k])) {
					frm.set_value('abha_address', profile[k][0]);
				} else {
					frm.set_value('abha_address', profile[k])
				}
			}
			if (k == 'ABHANumber' || k == 'healthIdNumber' || k == "abhaNumber"){frm.set_value('abha_number', profile[k])}
			if (k == 'firstName'){frm.set_value('first_name', profile[k])}
			if (k == 'middleName'){frm.set_value('middle_name', profile[k])}
			if (k == 'lastName'){frm.set_value('last_name', profile[k])}
			if (dob){
				frm.set_value('dob', moment(dob, 'DD/MM/YYYY').format('YYYY-MM-DD'))
			}
			if (!frm.doc.email) {
				if (k == 'email'){frm.set_value('email', profile[k])}
			}
			if (dialog.get_value('mobile')) {
				frm.set_value('mobile', dialog.get_value('mobile'))
			} else if (k == 'mobile'){
				frm.set_value('mobile', profile[k])
			}
			if (k == 'gender'){
				let gender = profile[k] == 'M' ? 'Male' :
				profile[k] == 'F' ? 'Female' :
				profile[k] == 'U' ? 'Prefer not to say' : 'Other'
				frm.set_value('sex', gender)
			}
			if (d && d.get_value('patient_consent_attach')) {
				frm.set_value('consent_for_aadhaar_use', d.get_value('patient_consent_attach'))
			}
		}
		if (dialog.get_value('abha_card')) {
			frm.set_value('abha_card', dialog.get_value('abha_card'))
		}
	}
}


let setup_search_btn = function(dialog) {
	dialog.fields_dict.username.$wrapper.find('.control-input').append(
		`<span class="link-btn search" style="display:inline">
		<a class="search-icons" title="${__("Search")}">
			${frappe.utils.icon("search", "sm")}
			</a>
		</span>`
	);
	let search_btn = dialog.$body.find('.search');
	search_btn.toggle(true);

	search_btn.on('click', 'a', () => {
		if (dialog.get_value('username')) {
			show_message(dialog, 'Verifying...', 'black', '', 'username')
			frappe.call({
				method: 'healthcare.regional.india.abdm.utils.abdm_request',
				args: {
					'payload': {
						"healthId": dialog.get_value('username')
					},
					'url_key': 'exists_by_health_id',
					'req_type': 'Health ID'
				},
				freeze: true,
				freeze_message: __('Verifying...'),
				callback: function (data) {
					if (data.message['status'] == false) {
						show_message(dialog, 'ABHA Address can be used', 'green', '', 'username')
						dialog.get_primary_btn().attr('disabled', false);
					} else if (data.message['status'] == true) {
						show_message(dialog, 'ABHA Address is already existing', 'red', '', 'username')
						dialog.get_primary_btn().attr('disabled', true);
					}
				}
			});
		}
	});
}


let create_abha_with_aadhaar = function(frm, d) {
	let txn_id = null;
	let error_msg = null;
	frappe.call({
		method: 'healthcare.regional.india.abdm.utils.abdm_request',
		args: {
			'payload': {
				"txnId": "",
				"scope": [
					"abha-enrol"
				],
				"loginHint": "aadhaar",
				"loginId": d.get_value('aadhaar'),
				"otpSystem": "aadhaar"
			},
			'url_key': 'generate_aadhaar_otp',
			'req_type': 'Health ID',
			'to_be_enc': 'loginId'
		},
		freeze: true,
		freeze_message: __('Sending OTP...'),
		callback: function (r) {
			if (r.message['txnId']) {
				txn_id = r.message['txnId'];
				frappe.show_alert({
					message: __(r.message['message']),
					indicator: 'green' }, 5
				);
			} else {
				error_msg = r.message
			}
			if (r.message['txnId']) {
				let dialog = new frappe.ui.Dialog({
					title: 'Create',
					fields: [
					{
						label: 'Aadhaar OTP',
						fieldname: 'otp',
						fieldtype: 'Data',
						reqd: 1
					},
					{
						fieldname: 'resent_txn_id',
						fieldtype: 'Data',
						hidden: 1
					},
					{
						fieldname: 'sb1',
						fieldtype: 'Section Break',
					},
					{
						label: 'Mobile',
						fieldname: 'mobile',
						fieldtype: 'Data',
					},
					{
						fieldname: 'sb2',
						fieldtype: 'Section Break'
					},
					{
						label: 'Choose ABHA Address',
						fieldname: 'sb5',
						fieldtype: 'Section Break',
						collapsible: 1
					},
					{
						label: 'Choose ABHA Address (Optional)',
						fieldname: 'username',
						fieldtype: 'Data'
					},
					{
						fieldname: 'sb3',
						fieldtype: 'Section Break',
						hide_border: 1
					}
					],
					primary_action_label: 'Create ABHA ID',
					primary_action(values) {
						let payload = {
							"authData": {
								"authMethods": [
									"otp"
								],
								"otp": {
									"txnId": r.message['txnId'],
									"otpValue": values.otp,
									"mobile": values.mobile || frm.doc.mobile
								}
							},
							"consent": {
								"code": "abha-enrollment",
								"version": "1.4"
							}
						}
						dialog.get_primary_btn().attr('disabled', true);
						frappe.call({
							method: 'healthcare.regional.india.abdm.utils.abdm_request',
							args: {
								'payload': payload,
								'url_key': 'create_abha_w_aadhaar',
								'req_type': 'Health ID',
								'to_be_enc': "otpValue"
							},
							freeze: true,
							freeze_message: __(`Creating Health ID <br>
								<small>Please note, this may take a while</small>`),
							callback: function (data) {
								if (data.message['txnId'] && data.message['ABHAProfile']) {
									let profile = data.message['ABHAProfile'];
									dialog.hide()
									frappe.run_serially([
										() =>frappe.db.get_value('Patient', {abha_number: profile['ABHANumber'],
												name: ['!=', frm.doc.name]	}, ['name', 'abha_card'])
											.then(r =>{
												if (r.message.name) {
													frappe.set_route("Form", "Patient", r.message.name);
													if (r.message.abha_card) {
														frappe.throw({
															message: __(`{0}`,
															["<img src='"+ r.message.abha_card + "'>"]),
															title: __("Patient already exist")
														});
													} else {
														frappe.throw({
															message: __(`{0}`,
															['<a href="/app/patient/'+r.message.name+'">' + r.message.name + '</a>']),
															title: __("Patient already exist")
														});
													}
												}
											}),
										() => {
											set_data_to_form(frm, profile, dialog, d)
											if (data.message['tokens']) {
												show_id_card_dialog(frm, data.message['tokens']['token'])
											}
											if (data.message['isNew'] == false) {
												frappe.show_alert({
													message: __('Fetched existing ABHA of aadhaar provided'),
													indicator: 'green' }, 5);
											} else {
												frappe.show_alert({
													message: __('ABHA ID created successfully'),
													indicator: 'green' }, 5);
											}
											// frm.save()
											dialog.hide();
										},
									])
								} else {
									dialog.get_primary_btn().attr('disabled', false);
									if (data.message && data.message.details[0]['message']) {
										show_message(dialog, data.message.message, 'red',
										data.message.details[0]['message'], 'otp')
									}
									frappe.show_alert({
										message: __('ABHA ID not Created'),
										indicator: 'red' }, 5);
								}
							}
						});
					}
				});

				setup_search_btn(dialog)
				setup_resend_otp_btn(dialog, txn_id)
				setup_send_otp_btn(dialog, txn_id)

				// clear response_message
				dialog.fields_dict['username'].df.onchange = () => {
					show_message(dialog, '', '', '', 'otp')
					dialog.get_primary_btn().attr('disabled', true);
				}
				dialog.show();
			} else {
				if (error_msg) {
					if (error_msg.details[0]['message']) {
						frappe.show_alert({
							message: __(error_msg.details[0]['message']),
							indicator: 'red' }, 5);
					} else if (error_msg.message) {
						frappe.show_alert({
							message: __(error_msg.message),
							indicator: 'red' }, 5);
					}
				}
			}
		}
	});
}


let setup_resend_otp_btn = function(dialog, txn_id) {
	dialog.fields_dict.otp.$wrapper.find('.control-input').append(
		`<span class="link-btn resend-btn" style="display:inline">
		<a class="icons" title="${__("Resend OTP")}">
			Resend OTP
			</a>
		</span>`
	);
	let search_btn = dialog.$body.find('.resend-btn');
	search_btn.toggle(true);

	search_btn.on('click', 'a', () => {
		if (txn_id) {
			show_message(dialog, 'Resending Aadhaar OTP ...', 'black', '', 'otp')
			frappe.call({
				method: 'healthcare.regional.india.abdm.utils.abdm_request',
				args: {
					'payload': {
						"txnId": txn_id
					},
					'url_key': 'resend_aadhaar_otp',
					'req_type': 'Health ID'
				},
				freeze: true,
				freeze_message: __('Resending Aadhaar OTP...'),
				callback: function (data) {
					if (data.message['txnId']) {
						show_message(dialog, 'Successfully Resent Aadhaar OTP', 'green', '', 'otp')
						dialog.get_primary_btn().attr('disabled', false);
						dialog.set_values({
							'resent_txn_id': data.message['txnId']
						});
					} else {
						show_message(dialog, 'Resending Aadhaar OTP Failed', 'red', '', 'otp')
						dialog.get_primary_btn().attr('disabled', true);
					}
				}
			});
		}
	});
}


let setup_send_otp_btn = function(dialog, txn_id = '') {
	dialog.fields_dict.mobile.$wrapper.find('.control-input').append(
		`<span class="link-btn send-a-m-otp" style="display:inline">
		<a class="icons" title="${__("Search")}">
			Verify
			</a>
		</span>`
	);
	let search_btn = dialog.$body.find('.send-a-m-otp');
	search_btn.toggle(true);

	search_btn.on('click', 'a', () => {
		if (dialog.get_value('mobile')) {
			let args = {};
			let url_key = '';
			if (txn_id) {
				args =  {
					'payload': {
						"mobile": dialog.get_value('mobile'),
						"txnId": txn_id
					},
					'url_key': 'generate_aadhaar_mobile_otp',
					'req_type': 'Health ID'
				}
				url_key = 'verify_aadhaar_mobile_otp'
			} else {
				args =  {
					'payload': {
						"mobile": dialog.get_value('mobile')
					},
					'url_key': 'generate_mobile_otp_for_linking',
					'req_type': 'Health ID'
				}
				url_key = 'verify_mobile_otp_for_linking'
			}
			dialog.fields_dict.mobile.$wrapper.find("span").remove();
			show_message(dialog, 'Sending Mobile OTP...', 'black', '', 'mobile')
			frappe.call({
				method: 'healthcare.regional.india.abdm.utils.abdm_request',
				args: args,
				freeze: true,
				freeze_message: __('Verifying...'),
				callback: function (data) {
					if (data.message['txnId']) {
						// setup_verify_otp_btn(dialog, data.message['txnId'])
						verify_mobile_otp_dialog(dialog, data.message['txnId'], url_key)
						show_message(dialog, 'Successfully Sent OTP', 'green', '', 'mobile')
					} else {
						// recreate send otp btn if otp sending fails
						setup_send_otp_btn(dialog, txn_id)
						if (data.message && data.message.details[0]['message']) {
							show_message(dialog, data.message.message, 'red',
								data.message.details[0]['message'], 'mobile')
						} else {
							show_message(dialog, 'Sending OTP Failed', 'red', '', 'mobile')
						}
					}
				}
			});
		} else {
			show_message(dialog, 'Please Enter Mobile Number', 'red', '', 'mobile')
		}
	});
}


let verify_mobile_otp_dialog = function(dialog, txn_id, url_key) {
	let otp_dialog = new frappe.ui.Dialog({
		title: 'Mobile Verification',
		fields: [
			{
				label: 'OTP',
				fieldname: 'otp',
				fieldtype: 'Data',
				reqd: 1
			}
		],
		primary_action_label: 'Verify',
		primary_action(values) {
			show_message(dialog, 'Verifying OTP...', 'black', '', 'mobile')
			let args = {};
			if (url_key == 'verify_aadhaar_mobile_otp') {
				args =  {
					'payload': {
						"otp": otp_dialog.get_value('otp'),
						"txnId": txn_id
					},
					'url_key': url_key,
					'req_type': 'Health ID'
				}
			} else if (url_key == 'verify_mobile_otp_for_linking'){
				args =  {
					'payload': {
						"to_encrypt": otp_dialog.get_value('otp'),
						"txnId": txn_id
					},
					'url_key': url_key,
					'req_type': 'Health ID',
					'to_be_enc': 'otp'
				}
			}
			frappe.call({
				method: 'healthcare.regional.india.abdm.utils.abdm_request',
				args: args,
				freeze: true,
				freeze_message: __('Verifying...'),
				callback: function (data) {
					show_message(dialog, '', '', '', 'mobile')
					if (data.message['txnId'] || data.message['token']) {
						dialog.fields_dict.mobile.$wrapper.find("span").remove();
						dialog.fields_dict.mobile.$wrapper.find('.control-input').append(
							`<span class="link-btn" style="display:inline">
								<a class="icons" title="${__("Verified")}">
									<i class="fa fa-check" aria-hidden="true"></i>
								</a>
							</span>`
						);
					} else {
						dialog.fields_dict.mobile.$wrapper.find("span").remove();
						dialog.fields_dict.mobile.$wrapper.find('.control-input').append(
							`<span class="link-btn p-x-btn" style="display:inline">
								<a class="icons" title="${__("Verification Failed")}">
									<i class="fa fa-times" aria-hidden="true"></i>
								</a>
							</span>`
						);
						let x_btn = dialog.$body.find('.p-x-btn');
						x_btn.toggle(true);

						x_btn.on('click', 'a', () => {
							dialog.fields_dict.mobile.$wrapper.find("span").remove();
							if (url_key == 'verify_aadhaar_mobile_otp') {
								setup_send_otp_btn(dialog, txn_id)
							} else if (url_key == 'verify_mobile_otp_for_linking'){
								setup_send_otp_btn(dialog)
							}
						});
					}
				}
			});
			otp_dialog.hide();
		}
	});
	otp_dialog.show();
}


let generate_link_token = function (frm) {
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
		"abha_address": frm.doc.abha_address,
		"abha_number": frm.doc.abha_number,
		"name": frm.doc.patient_name,
		"gender": frm.doc.sex,
		"year_of_birth": moment(frm.doc.dob, "YYYY-MM-DD").year()
	})
	dialog.show();
}

let show_message = function(dialog, message, color, details, field) {
	var field = dialog.get_field(field);
	field.df.description = `<div style="color:${color};
		padding:5px 5px 5px 5px">${message}<br>
		${details ? 'Details: '+details+'</div>': '</div>'}`
	field.refresh();
}