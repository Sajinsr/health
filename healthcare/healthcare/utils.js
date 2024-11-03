// Copyright (c) 2018, earthians and contributors
// For license information, please see license.txt

var check_and_set_availability = function(page, practitioner, department, appointment_date) {
	var selected_slot = null;
	var service_unit = null;
	var duration = null;
	show_availability();

	function show_empty_state(practitioner, appointment_date) {
		frappe.msgprint({
			title: __('Not Available'),
			message: __("Healthcare Practitioner {0} not available on {1}", [practitioner.bold(), appointment_date.bold()]),
			indicator: 'red'
		});
	}

	function show_availability() {
		let selected_practitioner = '';
		let selected_appointment_date = '';
		let selected_appointment_type = '';
		var d = new frappe.ui.Dialog({
			title: __("Available slots"),
			fields: [
				{ fieldtype: 'Link', options: 'Patient', reqd:1, fieldname: 'patient', label: 'Patient'},
				{ fieldtype: 'Data', read_only:1, fieldname: 'patient_name', depends_on:'eval:doc.patient', label: 'Patient Name'},
				{ fieldtype: 'Link', options: 'Medical Department', reqd:1, fieldname: 'department', label: 'Medical Department'},
				{ fieldtype: 'Column Break'},
				{ fieldtype: 'Link', options: 'Healthcare Practitioner', reqd:1, fieldname: 'practitioner', label: 'Healthcare Practitioner'},
				{ fieldtype: 'Data', read_only:1, fieldname: 'practitioner_name',depends_on:'eval:doc.practitioner', label: 'Practitioner Name'},
				{ fieldtype: 'Link', options: 'Appointment Type', reqd:1, fieldname: 'appointment_type', label: 'Appointment Type'},
				{ fieldtype: 'Column Break'},
				{ fieldtype: 'Int', fieldname: 'duration', label: 'Duration'},
				{ fieldtype: 'Date', reqd:1, fieldname: 'appointment_date', label: 'Date'},
				{ fieldtype: 'Check',  fieldname: 'patient_companion', label: 'Patient Companion', depends_on:'eval:doc.patient'},
				{ fieldtype: 'Section Break', depends_on:'eval:doc.patient_companion'},
				{ fieldtype: 'Data',  fieldname: 'companion_name', depends_on:'eval:doc.patient_companion', label: 'Companion Name'},
				{ fieldtype: 'Data', fieldname: 'companion_id',  depends_on:'eval:doc.patient_companion', label: 'Companion ID'},
				{ fieldtype: 'Column Break'},
				{ fieldtype: 'Data',  fieldname: 'companion_mobile', depends_on:'eval:doc.patient_companion', label: 'Companion Mobile '},
				{ fieldtype: 'Select', options:['Father','Mother','Sister','Brother','Spouse','Bairn','Relative','Friend','Colleague','Other'], depends_on:'eval:doc.patient_companion', fieldname: 'companion_relation',  label: 'Companion Relation'},
				{ fieldtype: 'Column Break'},
				{ fieldtype: 'Data', fieldname: 'companion_email', depends_on:'eval:doc.patient_companion',  label: 'Companion Email'},
				{ fieldtype: 'Section Break'},
				{ fieldtype: 'Select', options: ['Direct', 'Referral', 'External Referral'], reqd:1, fieldname: 'source', label: 'Source'},
				{ fieldtype: 'Column Break'},
				{ fieldtype: 'Link', options: 'Healthcare Practitioner',  fieldname: 'referring_practitioner', label: 'Healthcare Practitioner',
					depends_on:'eval:doc.source ==`Referral` || doc.source ==`External Referral`',
					get_query: function(){
						if(d.get_value('source')=="External Referral"){
							return {
								filters: {
									"healthcare_practitioner_type": "External"
								}
							};
						}
						else{
							return {
								filters: {
									"healthcare_practitioner_type": "Internal"
								}
							};
						}
					}
				},
				{ fieldtype: 'Link', options: 'Healthcare Practitioner Level', read_only:1, fieldname: 'sch_healthcare_practitioner_level', label: 'Healthcare Practitioner Level'},
				{ fieldtype: 'Section Break'},
				{ fieldtype: 'Link', options: 'Insurance Assignment', fieldname: 'insurance', label: 'Healthcare Insurance',
					depends_on: 'eval: !doc.schc_package_assignment',
					get_query: function () {
						return {
							filters: {
								"patient" : d.get_value('patient'),
								"end_date":[">=", d.get_value('appointment_date')],
								"docstatus" :1
							}
						};
					}
				},
				{ fieldtype: 'Data', read_only:1, fieldname: 'insurance_company_name', depends_on:'eval:doc.insurance', label: 'Insurance Company Name'},
				{ fieldtype: 'Data', fieldname: 'insurance_approval_number', depends_on:'eval:doc.insurance', label: 'Approval Number'},
				{ fieldtype: 'Small Text', fieldname: 'insurance_remarks', depends_on:'eval:doc.insurance', label: 'Insurance Remarks'},
				{ fieldtype: 'Int', read_only:1, fieldname: 'booked_appointments', label: 'Booked Appointments', depends_on: 'eval: doc.schc_package_item'},
				{ fieldtype: 'Data', read_only:1, fieldname: 'remaining_appointments', label: 'Remaining Appointments', depends_on: 'eval: doc.schc_package_item'},
				{ fieldtype: 'Column Break'},
				{ fieldtype: 'Link', options: 'Healthcare Package Assignment', fieldname: 'schc_package_assignment', label: 'Healthcare Package',
					depends_on: 'eval: !doc.insurance',
					get_query: function () {
						return {
							filters: {
								"patient" : d.get_value('patient'),
								"from_date": ["<=", d.get_value('appointment_date')],
								"to_date": [">=", d.get_value('appointment_date')],
								"docstatus": 1,
								"healthcare_practitioner_level":d.get_value('sch_healthcare_practitioner_level'),
								"department":d.get_value('department')
							}
						};
					}
				},
				{ fieldtype: 'Data', read_only:1, fieldname: 'schc_package_assignment_name', depends_on:'eval:doc.schc_package_assignment', label: 'Package Name'},
				{ fieldtype: 'Link', options: 'Item', fieldname: 'schc_package_item', label: 'Package Item',
					depends_on: 'eval: doc.schc_package_assignment',
					get_query: function () {
						return {
							query : "sehacloud_healthcare.queries.get_package_item_list",
							filters: {parent :d.get_value('schc_package_assignment')}
						};
					}
				},
				{ fieldtype: 'Data', read_only:1, fieldname: 'item_name', depends_on:'eval:doc.schc_package_item', label: 'Item Name'},
				{ fieldtype: 'Section Break'},
				{ fieldtype: 'HTML', fieldname: 'available_slots'}
			],
			primary_action_label: __("Book"),
			primary_action: function() {
				var args = {
					practitioner: d.get_value('practitioner'),
					patient: d.get_value('patient'),
					department: d.get_value('department'),
					appointment_date: d.get_value('appointment_date'),
					appointment_time: selected_slot,
					service_unit: service_unit || '',
					duration: d.get_value('duration'),
					appointment_type: d.get_value('appointment_type'),
					source:d.get_value('source'),
					referring_practitioner:d.get_value('referring_practitioner')||'',
					schc_package_assignment:d.get_value('schc_package_assignment'),
					insurance :d.get_value('insurance'),
					insurance_approval_number: d.get_value('insurance_approval_number')||'',
					insurance_remarks:d.get_value('insurance_remarks')||'',
					sch_healthcare_practitioner_level:d.get_value('sch_healthcare_practitioner_level')||''
				};
				if(d.get_value('patient_companion') && d.get_value('companion_name') && d.get_value('companion_mobile')){
					args['companion_name'] = d.get_value('companion_name'),
					args['companion_mobile'] = d.get_value('companion_mobile'),
					args['companion_email'] = d.get_value('companion_email'),
					args['companion_id'] = d.get_value('companion_id'),
					args['companion_relation'] = d.get_value('companion_relation')
				}
				if(d.get_value('patient_companion') && (!d.get_value('companion_mobile') || !d.get_value('companion_name'))){
					frappe.msgprint("Companion Information - Name and Mobile Mandatory");
				}
				else if (d.get_value('schc_package_assignment') && d.get_value('remaining_appointments') == "Limit Exceeded"){
						frappe.msgprint("Session Limit Exceeded");
				}
				else{
					frappe.call({
						method: "sehacloud_healthcare.sehacloud_healthcare.utils.book_appointment_from_desk",
						args:{
							appointment_details:args
						},
						callback: function(r) {
							if(!r.exc){
								page.$cal.fullCalendar("refetchEvents");
							}
						},
						freeze: true,
						freeze_message: __("Booking ...")
					})
					d.hide();
					d.get_primary_btn().attr('disabled', true);
				}
			}
		});

		d.set_values({
			'department': department,
			'practitioner': practitioner,
			'appointment_date': appointment_date
		});

		frappe.db.get_value("Healthcare Settings", "", "default_practitioner_source", function(r) {
			if(r && r.default_practitioner_source){
				d.set_values({
					'source': r.default_practitioner_source
				});
			}
			else{
				d.set_values({
					'source': ""
				});
			}
		});

		d.fields_dict["department"].df.onchange = () => {
			d.set_values({
				'practitioner': ''
			});
			var department = d.get_value('department');
			if(department){
				d.fields_dict.practitioner.get_query = function() {
					return {
						filters: {
							"department": department
						}
					};
				};
			}
		};

		d.fields_dict["insurance"].df.onchange = () => {
			if(d.get_value('insurance')){
				d.set_values({
					'schc_package_assignment': ''
				});
			}
			frappe.db.get_value("Insurance Assignment", d.get_value('insurance'), 'insurance_company_name', function(r) {
				if(r && r.insurance_company_name){
					d.set_values({
						'insurance_company_name': r.insurance_company_name
					});
				}
			});
		};

		d.fields_dict["schc_package_assignment"].df.onchange = () => {
			if(d.get_value('schc_package_assignment')){
				d.set_values({
					'insurance': ''
				});
				frappe.call({
					method: "sehacloud_healthcare.sehacloud_healthcare.doctype.healthcare_package.healthcare_package.get_package_item_list",
					args: {"package": d.get_value('schc_package_assignment')},
					callback: function(r) {
						if(r && r.message && r.message.length == 1){
							d.set_values({"schc_package_item": r.message[0][0]});
						}
					}
				});
				frappe.db.get_value("Healthcare Package Assignment", d.get_value('schc_package_assignment'), 'package_name', function(r) {
					if(r && r.package_name){
						d.set_values({
							'schc_package_assignment_name': r.package_name
						});
					}
				});
				frappe.db.get_value("Healthcare Package Assignment", d.get_value('schc_package_assignment'), 'appointment_type', function(r) {
					if(r && r.appointment_type){
						d.set_values({
							'appointment_type': r.appointment_type
						});
					}
				});
			}
			else{
				d.set_values({"schc_package_item": ''});
				d.set_values({
					'appointment_type': ''
				});
			}
		};

		// disable dialog action initially
		d.get_primary_btn().attr('disabled', true);

		// Field Change Handler

		var fd = d.fields_dict;
		d.fields_dict["appointment_type"].df.onchange = () => {
			frappe.db.get_value("Appointment Type", d.get_value('appointment_type'), 'default_duration', function(r) {
				if(r && r.default_duration){
					d.set_values({
						'duration': r.default_duration
					});
				}
			});
			if(d.get_value('appointment_type') && d.get_value('appointment_type') != selected_appointment_type){
				selected_appointment_type = d.get_value('appointment_type');
				var today = frappe.datetime.nowdate();
				if(today > d.get_value('appointment_date')){
					frappe.db.get_value("Healthcare Settings", "", "appointment_administrator", function(r) {
						if(r && r.appointment_administrator){
							if(frappe.user.has_role(r.appointment_administrator)){
								show_slots(d, fd);
							}
							else{
								frappe.msgprint(__("You cannot book appointments for past date"));
								fd.available_slots.html(__("You cannot book appointments for past date").bold());
							}
						}
						else{
							frappe.msgprint(__("You cannot book appointments for past date"));
							fd.available_slots.html(__("You cannot book appointments for past date").bold());
						}
					});
				}
				else
				{
					show_slots(d, fd);
				}
			}
		}
		d.fields_dict["appointment_date"].df.onchange = () => {
			if(d.get_value('appointment_date') && d.get_value('appointment_date') != selected_appointment_date){
				selected_appointment_date = d.get_value('appointment_date');
				var today = frappe.datetime.nowdate();
				if(today > selected_appointment_date){
					frappe.db.get_value("Healthcare Settings", "", "appointment_administrator", function(r) {
						if(r && r.appointment_administrator){
							if(frappe.user.has_role(r.appointment_administrator)){
								show_slots(d, fd);
							}
							else{
								frappe.msgprint(__("You cannot book appointments for past date"));
								fd.available_slots.html(__("You cannot book appointments for past date").bold());
							}
						}
						else{
							frappe.msgprint(__("You cannot book appointments for past date"));
							fd.available_slots.html(__("You cannot book appointments for past date").bold());
						}
					});
				}
				else
				{
					show_slots(d, fd);
				}
			}
			else if(!d.get_value("appointment_date")){
				selected_appointment_date = '';
			}
		}
		d.fields_dict["patient"].df.onchange = () => {
			frappe.db.get_value("Patient", d.get_value('patient'), 'patient_name', function(r) {
				if(r && r.patient_name){
					d.set_values({
						'patient_name': r.patient_name
					});
				}
			});
		}
		d.fields_dict["source"].df.onchange = () => {
			if(d.get_value('source')=="Referral"){
				frappe.db.get_value("Healthcare Practitioner", d.get_value('practitioner'), 'healthcare_practitioner_type', function(r) {
					if(r && r.healthcare_practitioner_type && r.healthcare_practitioner_type=="Internal"){
						d.set_values({
							'referring_practitioner': d.get_value("practitioner")
						});
					}
					else{
						d.set_values({
							'referring_practitioner': ""
						});
					}
				});
			}
			else if(d.get_value('source')=="External Referral"){
				frappe.db.get_value("Healthcare Practitioner", d.get_value('practitioner'), 'healthcare_practitioner_type', function(r) {
					if(r && r.healthcare_practitioner_type && r.healthcare_practitioner_type=="External"){
						d.set_values({
							'referring_practitioner': d.get_value("practitioner")
						});
					}
					else{
						d.set_values({
							'referring_practitioner': ""
						});
					}
				});
			}
			else{
				d.set_values({
					'referring_practitioner': ""
				});
			}
		}
		d.fields_dict["companion_mobile"].df.onchange = () => {
			frappe.call({
				method: "sehacloud_healthcare.sehacloud_healthcare.utils.get_contact_details",
				args: {
						'mobile_no': d.get_value('companion_mobile')
				},
				callback: function(r) {
					if(r && r.message){
						d.set_values({
							'companion_name': r.message.first_name,
							'companion_email': r.message.email_id,
							'companion_id':r.message.companion_id,
							'companion_relation': r.message.companion_relation,
						});
					}
				}
			});
		}
		d.fields_dict["practitioner"].df.onchange = () => {
			if(d.get_value('practitioner') && d.get_value('practitioner') != selected_practitioner){
				selected_practitioner = d.get_value('practitioner');
				d.set_values({
					'appointment_type': ''
				});
				frappe.db.get_value("Healthcare Practitioner", d.get_value('practitioner'), 'practitioner_name', function(r) {
					if(r && r.practitioner_name){
						d.set_values({
							'practitioner_name': r.practitioner_name
						});
					}
				});
				d.fields_dict.appointment_type.get_query = function () {
					return {
						query : "erpnext.healthcare.utils.get_practitioner_appointment_type",
						filters: {parent : d.get_value("practitioner")}
					}
				}
				frappe.db.get_value("Healthcare Practitioner", d.get_value('practitioner'), 'sch_healthcare_practitioner_level', function(r) {
					if(r && r.sch_healthcare_practitioner_level){
						d.set_values({
							'sch_healthcare_practitioner_level': r.sch_healthcare_practitioner_level
						});
					}
				});
				show_slots(d, fd);
			}
		};
		d.fields_dict["schc_package_item"].df.onchange = () => {
			if (d.get_value('schc_package_item')){
				frappe.db.get_doc('Healthcare Package Assignment',  d.get_value('schc_package_assignment')).then(doc => {
					$.each(doc.items, function(j, item){
							if(item.item_code == d.get_value('schc_package_item')){
							}
					if(item.item_code == d.get_value('schc_package_item')){
					frappe.db.get_list('Patient Appointment', {
						filters: {
							schc_package_assignment: d.get_value('schc_package_assignment'),
							schc_package_item: d.get_value('schc_package_item'),
							status: ['!=', "Cancelled"]
						}
					}).then(records => {
						d.set_values({
							booked_appointments: records.length ,
							remaining_appointments: item.no_of_session - records.length - item.initial_completed_session
						})
							if (records.length >= (item.no_of_session - item.initial_completed_session)){
								d.set_values({
									remaining_appointments: __('Limit Exceeded')
								});
							}
						});
					}
					});
				});
				frappe.db.get_value("Item", d.get_value('schc_package_item'), 'item_name', function(r) {
					if(r && r.item_name){
						d.set_values({
							'item_name': r.item_name
						});
					}
				});
			}
			else{
				d.set_values({
					booked_appointments: '',
					remaining_appointments: ''
				});
			}
		};
		d.show();
		d.$wrapper.find('.modal-dialog').css("width", "800px");
	}

	function show_slots(d, fd) {
		// If appointment_type is there in frm then dialoge shoud needs that appointment_type - Rescehduling
		// If appointment_type is NOT there in frm then dialoge shoud NOT need appointment_type - Booking
		if (d.get_value('appointment_date') && d.get_value('practitioner') && d.get_value("appointment_type")){
			fd.available_slots.html("");
			exists_appointment(d.get_value('patient'), d.get_value('practitioner'), d.get_value('appointment_date'), (exists)=>{
				if(exists){
					fd.available_slots.html("");
					frappe.call({
						method: 'erpnext.healthcare.doctype.patient_appointment.patient_appointment.get_availability_data',
						args: {
							practitioner: d.get_value('practitioner'),
							date: d.get_value('appointment_date')
						},
						callback: (r) => {
							var data = r.message;
							if(data.slot_details.length > 0 || data.present_events.length > 0) {
								var $wrapper = d.fields_dict.available_slots.$wrapper;

								// make buttons for each slot
								var slot_details = data.slot_details;
								var slot_html = "";
								var have_atleast_one_schedule = false;
								for (let i = 0; i < slot_details.length; i++) {
									if(slot_details[i].appointment_type == d.get_value("appointment_type") || slot_details[i].appointment_type == null){
										have_atleast_one_schedule = true;
										slot_html = slot_html + `<label>${slot_details[i].slot_name}</label>`;
										slot_html = slot_html + `<br/>` + slot_details[i].avail_slot.map(slot => {
											var appointment_count=0;
											let disabled = '';
											let background_color = "#cef6d1";
											let capacity = slot_details[i].service_unit_capacity||'';
											let start_str = slot.from_time;
											let slot_start_time = moment(slot.from_time, 'HH:mm:ss');
											let slot_to_time = moment(slot.to_time, 'HH:mm:ss');
											let interval = (slot_to_time - slot_start_time)/60000 | 0;
											//checking current time in solt
											var today = frappe.datetime.nowdate();
											if(today == d.get_value('appointment_date')){
												// disable before  current  time in current date
												var curr_time= moment(frappe.datetime.now_time(), 'HH:mm:ss');
												if(slot_start_time.isBefore(curr_time)){
													disabled = 'disabled="disabled"';
													background_color = "#A1A1A1";
												}
											}
											//iterate in all booked appointments, update the start time and duration
											slot_details[i].appointments.forEach(function(booked) {
												let booked_moment = moment(booked.appointment_time, 'HH:mm:ss');
												let end_time = booked_moment.clone().add(booked.duration, 'minutes');
												if(slot_details[i].fixed_duration != 1){
													if(end_time.isSame(slot_start_time) || end_time.isBetween(slot_start_time, slot_to_time)){
														start_str = end_time.format("HH:mm")+":00";
														interval = (slot_to_time - end_time)/60000 | 0;
														return false;
													}
												}
												// Check for overlaps considering appointment duration
												if(slot_details[i].allow_overlap != 1){
													if(slot_start_time.isBefore(end_time) && slot_to_time.isAfter(booked_moment)){
														// There is an overlap
														disabled = 'disabled="disabled"';
														background_color = "#d2d2ff";
														return false;
													}
												}
												else{
													if(slot_start_time.isBefore(end_time) && slot_to_time.isAfter(booked_moment)){
														appointment_count++
													}
													if(appointment_count>=slot_details[i].service_unit_capacity){
														// There is an overlap
														disabled = 'disabled="disabled"';
														background_color = "#d2d2ff";
														return false;
													}
												}
											});
											//iterate in all absent events and disable the slots
											slot_details[i].absent_events.forEach(function(event) {
												let event_from_time = moment(event.from_time, 'HH:mm:ss');
												let event_to_time = moment(event.to_time, 'HH:mm:ss');
												// Check for overlaps considering event start and end time
												if(slot_start_time.isBefore(event_to_time) && slot_to_time.isAfter(event_from_time)){
													// There is an overlap
													disabled = 'disabled="disabled"';
													background_color = "#ffd7d7";
													return false;
												}
											});
											let count=''
											if(slot_details[i].allow_overlap==1){
												count="("+appointment_count+"/"+capacity+")"
											}
											return `<button class="btn btn-default"
												data-name=${start_str}
												data-duration=${interval}
												data-service-unit="${slot_details[i].service_unit || ''}"
												flag-fixed-duration=${slot_details[i].fixed_duration || 0}
												style="margin: 0 10px 10px 0; background-color:${background_color};" ${disabled}>
												${start_str.substring(0, start_str.length - 3)} ${count}
											</button>`;
										}).join("");
										slot_html = slot_html + `<br/>`;
									}
								}

								if(!have_atleast_one_schedule && !data.present_events){
									slot_html = __("There are no schedules for appointment type {0}", [d.get_value("appointment_type")||'']).bold();
								}

								if(data.present_events && data.present_events.length > 0){
									slot_html = slot_html + `<br/>`;
									var present_events = data.present_events
									for (let i = 0; i < present_events.length; i++) {
										slot_html = slot_html + `<label>${present_events[i].slot_name}</label>`;
										slot_html = slot_html + `<br/>` + present_events[i].avail_slot.map(slot => {
											var appointment_count=0;
											let disabled = '';
											let background_color = "#cef6d1";
											let capacity = present_events[i].service_unit_capacity
											let start_str = slot.from_time;
											let slot_start_time = moment(slot.from_time, 'HH:mm:ss');
											let slot_to_time = moment(slot.to_time, 'HH:mm:ss');
											let interval = (slot_to_time - slot_start_time)/60000 | 0;
											//checking current time in solt
												var today = frappe.datetime.nowdate();
												if(today == d.get_value('appointment_date')){
													// disable before  current  time in current date
													var curr_time= moment(frappe.datetime.now_time(), 'HH:mm:ss');
													if(slot_start_time.isBefore(curr_time)){
														disabled = 'disabled="disabled"';
														background_color = "#A1A1A1";
													}
												}
											//iterate in all booked appointments, update the start time and duration
											present_events[i].appointments.forEach(function(booked) {
												let booked_moment = moment(booked.appointment_time, 'HH:mm:ss');
												let end_time = booked_moment.clone().add(booked.duration, 'minutes');
												// Check for overlaps considering appointment duration
												if(present_events[i].allow_overlap != 1){
													if(slot_start_time.isBefore(end_time) && slot_to_time.isAfter(booked_moment)){
														// There is an overlap
														disabled = 'disabled="disabled"';
														background_color = "#d2d2ff";
														return false;
													}
												}
												else{
													if(slot_start_time.isBefore(end_time) && slot_to_time.isAfter(booked_moment)){
														appointment_count++
													}
													if(appointment_count>=present_events[i].service_unit_capacity){
														// There is an overlap
														disabled = 'disabled="disabled"';
														background_color = "#d2d2ff";
														return false;
													}
												}
											});
											//iterate in all absent events and disable the slots
											present_events[i].absent_events.forEach(function(event) {
												let event_from_time = moment(event.from_time, 'HH:mm:ss');
												let event_to_time = moment(event.to_time, 'HH:mm:ss');
												// Check for overlaps considering event start and end time
												if(slot_start_time.isBefore(event_to_time) && slot_to_time.isAfter(event_from_time)){
													// There is an overlap
													disabled = 'disabled="disabled"';
													background_color = "#ffd7d7";
													return false;
												}
											});
											let count=''
											if(present_events[i].allow_overlap==1){
												count="("+appointment_count+"/"+capacity+")"
											}
											return `<button class="btn btn-default"
												data-name=${start_str}
												data-duration=${interval}
												data-service-unit="${present_events[i].service_unit || ''}"
												flag-fixed-duration=${1}
												style="margin: 0 10px 10px 0; background-color:${background_color};" ${disabled}>
												${start_str.substring(0, start_str.length - 3)} ${count}
											</button>`;
										}).join("");
										slot_html = slot_html + `<br/>`;
									}
								}

								$wrapper
									.css('margin-bottom', 0)
									.addClass('text-center')
									.html(slot_html);

								// blue button when clicked
								$wrapper.on('click', 'button', function() {
									var $btn = $(this);
									$wrapper.find('button').removeClass('btn-primary active');
									$btn.addClass('btn-primary active');
									selected_slot = $btn.attr('data-name');
									service_unit = $btn.attr('data-service-unit')
									duration = $btn.attr('data-duration')
									// enable dialog action
									d.get_primary_btn().attr('disabled', null);
									if($btn.attr('flag-fixed-duration') == 1){
										d.set_values({
											'duration': $btn.attr('data-duration')
										});
									}
								});

							}else {
								//	fd.available_slots.html("Please select a valid date.".bold())
								show_empty_state(d.get_value('practitioner'), d.get_value('appointment_date'));
							}
						},
						freeze: true,
						freeze_message: __("Fetching records......")
					});
				}
				else{
					fd.available_slots.html("");
				}
			});
		}
		else{
			fd.available_slots.html("Appointment date and Healthcare Practitioner are Mandatory".bold());
		}
	}

	function exists_appointment(patient, practitioner, appointment_date, callback) {
		frappe.call({
			method: "erpnext.healthcare.utils.exists_appointment",
			args:{
				appointment_date: appointment_date,
				practitioner: practitioner,
				patient: patient
			},
			callback: function(data) {
				if(data.message){
					var message  = __("Appointment is already booked on {0} for {1} with {2}, Do you want to book another appointment on this day?",
						[appointment_date.bold(), patient.bold(), practitioner.bold()]);
					frappe.confirm(
						message,
						function(){
							callback(true);
						},
						function(){
							frappe.show_alert({
								message:__("Select new date and slot to book appointment if you wish."),
								indicator:'yellow'
							});
							callback(false);
						}
					);
				}
				else{
					callback(true);
				}
			}
		});
	}
}
