frappe.provide('frappe.healthcare');

frappe.pages['patient_wait_list'].on_page_show = function(wrapper){
	if (window.performance.getEntriesByName("refresh-wait-list", "mark").length) {
		performance.clearMarks("refresh-wait-list");
		frappe.healthcare.appointment.get_appointments();
	}
}
frappe.pages['patient_wait_list'].on_page_load = function(wrapper) {
	// FONT AWESOME from CDN
	var font_awesome_5 = document.createElement('link');
	font_awesome_5.rel = "stylesheet";
	font_awesome_5.href = "https://use.fontawesome.com/releases/v5.7.2/css/all.css";
	font_awesome_5.integrigty = "sha384-fnmOCqbTlWIlj8LyTjo7mOUStjsKC4pOpQbqyi7RrhN7udi9RwhKkMHpvLbHG9Sr";
	font_awesome_5.crossorigin = "anonymous";
	document.getElementsByTagName('head')[0].appendChild(font_awesome_5);
	//END FONT AWESOME from CDN
	frappe.healthcare.appointment = new frappe.healthcare.Appointment(wrapper);
	frappe.breadcrumbs.add("Healthcare");
};

frappe.healthcare.Appointment = Class.extend({
	init: function(parent) {
		this.parent = parent;
		this.make_page();
		this.make_toolbar();
		this.get_appointments();
	},
	get_appointments: function() {
		var me = this;
		me.wrapper.empty();
		var date = '', to_date = '';
		if (me.date.val() !=''){
			date = frappe.datetime.user_to_str(me.date.val());
		}
		if (me.to_date.val() !=''){
			to_date = frappe.datetime.user_to_str(me.to_date.val());
		}
		if(!me.date.val() && !me.practitioner.get_value() && !me.patient.get_value()){
			// frappe.msgprint({
			// 	message: __("No sufficient filters to query Appoinments"),
			// 	indicator: 'red'
			// });
			let msg_html = '<p class="text-muted" style="padding: 15px;" align="middle">Set Filters To Fetch Appoinment List</p>';
			$(msg_html).appendTo(me.wrapper);
			return;
		}
		if(!me.company.get_value()){
				frappe.msgprint(__("Company is Mandatory"));
			return;
		}
		return frappe.call({
			method: "healthcare.healthcare.page.patient_wait_list.patient_wait_list.get_appointments",
			args: {date: date, to_date: to_date, practitioner: me.practitioner.get_value(), status_values: me.status.get_value(),
				patient: me.patient.get_value(), company: me.company.get_value(), service_unit:me.service_unit.get_value(), appointment_type: me.appointment_type.get_value()
			},
			callback: function (r) {
				me.wrapper.empty();
				if(r.message.length > 0){
					me.make_list(r.message)
				}else{
					let msg_html = '<p class="text-muted" style="padding: 15px;">No '+ me.status.get_value() +' appointments  found for the day</p>';
					$(msg_html).appendTo(me.wrapper);
				}
			},
			freeze: true,
			freeze_message: 'Loading Patient Appointment List'
		});
	},
	make_list: function (appointments) {
		var me = this;
		// $(`<div class="col-sm-12" style='background-color:#D3D3D3;'><div class="col-sm-12"><b>
		// 	<div class="col-sm-2">Patient</div>
		// 	<div class="col-sm-1">Time</div>
		// 	<div class="col-sm-1">Status</div>
		// 	<div class="col-sm-3">Appointment</div>
		// 	<div class="col-sm-4"></div>
		// 	<div class="col-sm-1">Orders</div>
		// 	</b>
		$(`<div class="col-sm-12 start_cls"></div>`).appendTo(me.wrapper)
		$.each(appointments, function(i, appointment){
			let poc_string = '';
			if (appointment.plan_of_care){
				poc_string = appointment.plan_of_care.replace(/(<([^>]+)>)/ig,"");
			}
			let content = '';
			if (appointment.content){ // TODO: Move this to server side?
				content = appointment.content.replace(/(<([^>]+)>)/ig,"");
			}
			let app_content = '';
			if (appointment.app_content){ // TODO: Move this to server side?
				app_content = appointment.app_content.replace(/(<([^>]+)>)/ig,"");
			}
			$(frappe.render_template("patient_wait_list", {data: appointment, plan_of_care: poc_string, content: content, app_content: app_content})).appendTo(me.wrapper);
		});
		this.wrapper.find(".record-vitals").on("click", function() {
			me.create_vitals($(this).attr("data-patient"));
			window.performance.mark('refresh-wait-list');
		});
		this.wrapper.find(".attend").on("click", function() {
			// $(this).closest(".app-listing").hide();
			me.create_encounter($(this).attr("data-name"));
			window.performance.mark('refresh-wait-list');
		});
		this.wrapper.find(".cancel").on("click", function() {
			me.update_appointment_status($(this).attr("data-name"), me, "Cancelled");
		});
		this.wrapper.find(".arrived").on("click", function() {
			me.update_appointment_status($(this).attr("data-name"), me, "Arrived");
			me.make_invoice($(this).attr("data-name"), me);
			window.performance.mark('refresh-wait-list');
		});
		this.wrapper.find(".update-encounter").on("click", function() {
			me.update_encounter($(this).attr("data-name"));
		});
		this.wrapper.find(".reschedule").on("click", function() {
			me.check_availability($(this).attr("data-department"), $(this).attr("data-practitioner"), $(this).attr("data-name"), $(this).attr("data-appointment-date"), me);
		});
		this.wrapper.find(".start-procedure").on("click", function() {
			me.create_procedure($(this).attr("data-name"));
			window.performance.mark('refresh-wait-list');
		});
		this.wrapper.find(".update-procedure").on("click", function() {
			me.update_procedure($(this).attr("data-name"))
		});
		this.wrapper.find(".make-invoice").on("click", function() {
			me.make_invoice($(this).attr("data-name"), me);
			window.performance.mark('refresh-wait-list');
		});
		this.wrapper.find(".view-invoice").on("click", function() {
			me.view_invoice($(this).attr("data-name"), me);
		});
		this.wrapper.find(".open").on("click", function() {
			me.update_appointment_status($(this).attr("data-name"), me, "Open");
		});
		this.wrapper.find(".new_appointment").on("click", function() {
			me.check_availability($(this).attr(""), $(this).attr(""), $(this).attr(""), $(this).attr(""), me);
		});
		this.wrapper.find(".checkout").on("click", function() {
			me.update_appointment_status($(this).attr("data-name"), me, "Checked out");
		});
		this.wrapper.find(".noshow").on("click", function() {
			me.update_appointment_status($(this).attr("data-name"), me, "No show");
		});
		// this.wrapper.find(".payment_status").on("click", function() {
		// 	me.update_mca_payment_status($(this).attr("data-name"), $(this).attr("action"), me);
		// });
		// this.wrapper.find(".covid_test_status").on("click", function() {
		// 	me.update_covid_test_status($(this).attr("data-name"), $(this).attr("action"), me);
		// });
		this.wrapper.find(".patient_confirmed").on("click", function() {
			me.update_patient_confirmed($(this).attr("data-name"), $(this).attr("action"), me);
		});
	},
	update_appointment_status: function (appointment, me, status) {
		if(status=="Cancelled"){
			frappe.call({
				method: "frappe.client.get",
				args:{
					doctype: "Patient Appointment",
					name: appointment
				},
				callback: function(r) {
					if(r && r.message){
						var data = r.message;
						frappe.model.with_doctype("Patient Appointment", function() {
							cancellation_reasons(appointment, me, status, frappe.meta.get_docfield("Patient Appointment", "cancelled_by").options);
						});
					}
				}
			});
		}
		else{
			update_status(appointment,me,status)
		}
	},
	create_encounter: function (appointment) {
		frappe.call({
			method: "healthcare.healthcare.page.patient_wait_list.patient_wait_list.create_encounter",
			args: {appointment: appointment},
			callback: function (r) {
				if(r.message && !r.exc){
					var doclist = frappe.model.sync(r.message);
					frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
				}
				else{
					frappe.show_alert({
							message:__("Could not create Patient Encounter, please contact System Administrator"),
							indicator:'red'
						});
				}
			}
		});
	},
	update_encounter: function (appointment) {
		frappe.call({
			method: "healthcare.healthcare.page.patient_wait_list.patient_wait_list.update_encounter",
			args: {appointment: appointment},
			callback: function (r) {
				if(r.message && !r.exc){
					var doclist = frappe.model.sync(r.message);
					frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
				}
				else{
					frappe.show_alert({
							message:__("Patient Encounter reference not found, please contact System Administrator"),
							indicator:'red'
						});
				}
			}
		});
	},
	create_vitals:function (patient) {
		frappe.route_options = {
			"patient": patient,
		}
		frappe.new_doc("Vital Signs")
		// window.open('_blank');
	},
	create_procedure: function(appointment){
		frappe.call({
			method:"healthcare.healthcare.page.patient_wait_list.patient_wait_list.create_procedure",
			args: {appointment: appointment},
			callback: function(data){
				if(!data.exc && data.message){
					var doclist = frappe.model.sync(data.message);
					frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
				}
				else{
					frappe.show_alert({
							message:__("Could not create Clinical Procedure, please contact System Administrator"),
							indicator:'red'
						});
				}
			},
			freeze: true
		});
	},
	update_procedure: function(appointment){
		frappe.call({
			method:"healthcare.healthcare.page.patient_wait_list.patient_wait_list.update_procedure",
			args: {appointment: appointment},
			callback: function(data){
				if(!data.exc && data.message){
					var doclist = frappe.model.sync(data.message);
					frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
				}
				else{
					frappe.show_alert({
							message:__("Clinical Procedure reference not found, please contact System Administrator"),
							indicator:'red'
						});
				}
			},
			freeze: true
		});
	},
	make_invoice: function(appointment){
		// to check invoiced on status change
		frappe.db.get_value('Patient Appointment', {name: appointment}, 'invoiced').then(r => {
      let values = r.message;
			if (values.invoiced == 0){
				var me = this;
				frappe.call({
					method:"healthcare.healthcare.page.patient_wait_list.patient_wait_list.invoice_appointment",
					args: {appointment_id: appointment},
					callback: function(data){
						if(!data.exc && data.message){
							var doclist = frappe.model.sync(data.message);
							frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
						}
						else{
							frappe.show_alert({
									message:__("Could not create Sales Invoice, please contact System Administrator"),
									indicator:'red'
								});
						}
					}
				});
			}
		});
	},
	view_invoice: function(appointment){
		frappe.call({
			method:"healthcare.healthcare.page.patient_wait_list.patient_wait_list.view_invoice",
			args: {appointment_id: appointment},
			callback: function(data){
				if(!data.exc && data.message){
					var doclist = frappe.model.sync(data.message);
					frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
				}
				else{
					frappe.show_alert({message:__("No Sales Invoice Reference Found"), indicator:'yellow'});
				}
			}
		});
	},
	update_mca_payment_status: function(appointment, action, me){
		frappe.call({
			method:"healthcare.healthcare.page.patient_wait_list.patient_wait_list.update_mca_payment_status",
			args: {appointment_id: appointment, action: action},
			callback: function(r){
				if (!r.exc){
					me.get_appointments();
				}
			}
		});
	},
	update_covid_test_status: function(appointment, action, me){
		frappe.call({
			method:"healthcare.healthcare.page.patient_wait_list.patient_wait_list.update_covid_test_status",
			args: {appointment_id: appointment, action: action},
			callback: function(r){
				if (!r.exc){
					me.get_appointments();
				}
			}
		});
	},
	update_patient_confirmed: function(appointment, action, me){
		frappe.call({
			method:"healthcare.healthcare.page.patient_wait_list.patient_wait_list.update_patient_confirmed",
			args: {appointment_id: appointment, action: action},
			callback: function(r){
				if (!r.exc){
					me.get_appointments();
				}
			}
		});
	},
	check_availability:function(department, practitioner, appointment, appointment_date, me) {
		check_and_set_availability(department, practitioner, appointment, appointment_date, me)
	},
	make_toolbar: function () {
		var me = this;
		var selected_practitioner = '';
		var selected_patient = '';
		var selected_service_unit = '';
		var selected_company = '';
		var selected_appointment_type = '';
		selected_date = '';
		selected_to_date = '';
		this.practitioner = this.page.add_field({label: __("Healthcare Practitioner"), fieldtype: 'Link',
		options: 'Healthcare Practitioner',
		change: function(){
			if(me.practitioner.get_value() != selected_practitioner){
				selected_practitioner = me.practitioner.get_value();
				me.get_appointments();
			}
		}
		})
		if(frappe.user.has_role("Physician")){
			frappe.db.get_value("Healthcare Practitioner", {user_id: frappe.session.user}, 'name', function(r){
				if(r){
					me.practitioner.set_value(r.name)
				}
			});
		}
		this.date = this.page.add_date(__("Date"), frappe.datetime.get_today())
		this.date.on('change', function(){
			if(me.date.val() != selected_date){
				selected_date = me.date.val();
				me.get_appointments();
			}
		});
		this.to_date = this.page.add_date(__("To Date"), frappe.datetime.get_today())
		this.to_date.on('change', function(){
			if(me.to_date.val() != selected_date){
				selected_to_date = me.to_date.val();
				me.get_appointments();
			}
		});
		this.appointment_type = this.page.add_field({label: __("Appointment Type"), fieldtype: 'Link', options: 'Appointment Type',
		change: function(){
			if(me.appointment_type.get_value() != selected_appointment_type){
				selected_appointment_type = me.appointment_type.get_value();
				me.get_appointments();
			}
		}
		});
		this.status = this.page.add_field({label: __("Status"), fieldtype: 'MultiSelect', options: 'Scheduled\nOpen\nIn Progress\nClosed\nPending\nCancelled\nConfirmed\nNo show\nArrived\nChecked out'})
		this.status.$input.on('change', function(){
			me.get_appointments();
		});
		this.patient = this.page.add_field({label: __("Patient"), fieldtype: 'Link',
		options: 'Patient',
		change: function(){
			if(me.patient.get_value() != selected_patient){
				selected_patient = me.patient.get_value();
				me.get_appointments();
			}
		}
		});
		this.service_unit = this.page.add_field({label: __("Healthcare Service Unit"), fieldtype: 'Link',
			options: 'Healthcare Service Unit',
			get_query: function(){
				return {
					filters: {
						"is_group": false,
						"allow_appointments": true
					}
				};
			},
			change: function(){
				if(me.service_unit.get_value() != selected_service_unit){
					selected_service_unit = me.service_unit.get_value();
					me.get_appointments();
				}
				else if(!me.service_unit.get_value()){
					selected_service_unit = ''
					me.get_appointments();
				}
			}
		});
		this.company = this.page.add_field({label: __("Company"), fieldtype: 'Link',
		options: 'Company', default: frappe.defaults.get_user_default("Company"),
		change: function(){
			if(me.company.get_value() != selected_company){
				selected_company = me.company.get_value();
				me.get_appointments();
			}
		}
		});
		this.page.set_primary_action(__("Refresh"), function() {
			me.get_appointments();
		}, "fa fa-refresh");

		// this.view_desk = me.page.add_field({
		// 	fieldtype: 'Button',
		// 	label: 'Open Appoinment Desk',
		// 	click: function () {
		// 		frappe.set_route('patient-appointment-desk')
		// 	}
		// });
	},
	make_page: function() {
		if (this.page)
			return;

		frappe.ui.make_app_page({
			parent: this.parent,
			title: __('Patient Appointment List'),
			single_column: true
		});
		this.page = this.parent.page;
		this.wrapper = $('<div></div>').appendTo(this.page.main);
	},
});

var check_and_set_availability = function(department, practitioner, appointment, appointment_date, me) {
	var selected_slot = null;
	var service_unit = null;
	var duration = null;
	let overlap_appointments = null;
	let appointment_based_on_check_in = false;

	show_availability()

	function show_empty_state(practitioner, appointment_date) {
		frappe.msgprint({
			title: __('Not Available'),
			message: __("Healthcare Practitioner {0} not available on {1}", [practitioner.bold(), appointment_date.bold()]),
			indicator: 'red'
		});
	}

	function show_availability(data) {
		let selected_practitioner = '';
		var d = new frappe.ui.Dialog({
			title: __("Available slots"),
			fields: [
				{ fieldtype: 'Link', options: 'Medical Department', reqd:1, fieldname: 'department', label: 'Medical Department'},
				{ fieldtype: 'Column Break'},
				{ fieldtype: 'Link', options: 'Healthcare Practitioner', reqd:1, fieldname: 'practitioner', label: 'Healthcare Practitioner'},
				{ fieldtype: 'Column Break'},
				{ fieldtype: 'Date', reqd:1, fieldname: 'appointment_date', label: 'Date', min_date: new Date(frappe.datetime.get_today()) },
				{ fieldtype: 'Section Break'},
				{ fieldtype: 'HTML', fieldname: 'available_slots'}
			],
			primary_action_label: __("Book"),
			primary_action: function() {
				frappe.call({
					method: "healthcare.healthcare.page.patient_wait_list.patient_wait_list.reschedule_appointment",
					args:{
						appointment_details: {
							practitioner: d.get_value('practitioner'),
							department: d.get_value('department'),
							appointment_date: d.get_value('appointment_date'),
							appointment_time: selected_slot,
							service_unit: service_unit || '',
							duration: duration
						},
						appointment_id: appointment
					},
					callback: function(r) {
						if(!r.exc){
							me.get_appointments();
						}
					},
					freeze: true
				})
				d.hide();
				d.get_primary_btn().attr('disabled', true);
			}
		});

		d.set_values({
			'department': department,
			'practitioner': practitioner,
			'appointment_date': appointment_date
		});

		let selected_department = department;

		d.fields_dict["department"].df.onchange = () => {
			if (selected_department != d.get_value('department')) {
				d.set_values({
					'practitioner': ''
				});
				selected_department = d.get_value('department');
			}
			if (d.get_value('department')) {
				d.fields_dict.practitioner.get_query = function() {
					return {
						filters: {
							'department': selected_department
						}
					};
				};
			}
		}

		// disable dialog action initially
		d.get_primary_btn().attr('disabled', true);

		// Field Change Handler

		var fd = d.fields_dict;

		d.fields_dict["appointment_date"].df.onchange = () => {
			show_slots(d, fd, appointment);
		}
		d.fields_dict["practitioner"].df.onchange = () => {
			if(d.get_value('practitioner') && d.get_value('practitioner') != selected_practitioner){
				selected_practitioner = d.get_value('practitioner');
				show_slots(d, fd, appointment);
			}
		}
		d.show();
	}

	async function show_slots(d, fd, appointment) {
		if (d.get_value('appointment_date') && d.get_value('practitioner')){
			fd.available_slots.html("")
			const appointment_doc = await (frappe.db.get_doc("Patient Appointment", appointment));

			frappe.call({
				method: 'healthcare.healthcare.doctype.patient_appointment.patient_appointment.get_availability_data',
				args: {
					practitioner: d.get_value('practitioner'),
					date: d.get_value('appointment_date'),
					appointment: appointment_doc
				},
				callback: (r) => {
					var data = r.message;
					if(data.slot_details.length > 0 || data.present_events.length > 0) {
						var $wrapper = d.fields_dict.available_slots.$wrapper;

						var slot_details = data.slot_details;
						var slot_html = "";
						for (let i = 0; i < slot_details.length; i++) {
							slot_html = slot_html + `<label>${slot_details[i].slot_name}</label>`;
							slot_html = slot_html + `<br/>` + slot_details[i].avail_slot.map(slot => {
								let disabled = '';
								let start_str = slot.from_time;
								let slot_start_time = moment(slot.from_time, 'HH:mm:ss');
								let slot_to_time = moment(slot.to_time, 'HH:mm:ss');
								let interval = (slot_to_time - slot_start_time)/60000 | 0;
								//iterate in all booked appointments, update the start time and duration
								slot_details[i].appointments.forEach(function(booked) {
									let booked_moment = moment(booked.appointment_time, 'HH:mm:ss');
									let end_time = booked_moment.clone().add(booked.duration, 'minutes');
									// Deal with 0 duration appointments
									if(booked_moment.isSame(slot_start_time) || booked_moment.isBetween(slot_start_time, slot_to_time)){
										if(booked.duration == 0){
											disabled = 'disabled="disabled"';
											return false;
										}
									}
									if(end_time.isSame(slot_start_time) || end_time.isBetween(slot_start_time, slot_to_time)){
										start_str = end_time.format("HH:mm")+":00";
										interval = (slot_to_time - end_time)/60000 | 0;
										return false;
									}
									// Check for overlaps considering appointment duration
									if(slot_start_time.isBefore(end_time) && slot_to_time.isAfter(booked_moment)){
										// There is an overlap
										disabled = 'disabled="disabled"';
										return false;
									}
								});
								return `<button class="btn btn-default"
									data-name=${start_str}
									data-duration=${interval}
									data-service-unit="${slot_details[i].service_unit || ''}"
									style="margin: 0 10px 10px 0; width: 72px;" ${disabled}>
									${start_str.substring(0, start_str.length - 3)}
								</button>`;
							}).join("");
							slot_html = slot_html + `<br/>`;
						}
						if(data.present_events && data.present_events.length > 0){
							slot_html = slot_html + `<br/>`;
							var present_events = data.present_events
							for (let i = 0; i < present_events.length; i++) {
									slot_html = slot_html + `<label>${present_events[i].slot_name}</label>`;
									slot_html = slot_html + `<br/>` + present_events[i].avail_slot.map(slot => {
										let disabled = '';
										let background_color = "#cef6d1";
										let start_str = slot.from_time;
										let slot_start_time = moment(slot.from_time, 'HH:mm:ss');
										let slot_to_time = moment(slot.to_time, 'HH:mm:ss');
										let interval = (slot_to_time - slot_start_time)/60000 | 0;
										//iterate in all booked appointments, update the start time and duration
										present_events[i].appointments.forEach(function(booked) {
											let booked_moment = moment(booked.appointment_time, 'HH:mm:ss');
											let end_time = booked_moment.clone().add(booked.duration, 'minutes');
											// Check for overlaps considering appointment duration
											if(slot_start_time.isBefore(end_time) && slot_to_time.isAfter(booked_moment)){
												// There is an overlap
												disabled = 'disabled="disabled"';
												background_color = "#d2d2ff";
												return false;
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
										return `<button class="btn btn-default"
											data-name=${start_str}
											data-duration=${interval}
											data-service-unit="${present_events[i].service_unit || ''}"
											flag-fixed-duration=${1}
											style="margin: 0 10px 10px 0; width: 72px; background-color:${background_color};" ${disabled}>
											${start_str.substring(0, start_str.length - 3)}
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
						});

					}else {
						//	fd.available_slots.html("Please select a valid date.".bold())
						show_empty_state(d.get_value('practitioner'), d.get_value('appointment_date'));
					}
				},
				freeze: true,
				freeze_message: __("Fetching records......")
			});
		}else{
			fd.available_slots.html("Appointment date and Healthcare Practitioner are Mandatory".bold())
		}
	}
}

var cancellation_reasons = function(appointment,me,status, cancelled_by_options) {
	var d_reasons = new frappe.ui.Dialog({
		title: __("Cancellation Reasons"),
		fields: [
			{ fieldtype: 'Select', options: '\nPatient\nPractitioner\nFacility', reqd:1, fieldname: 'cancellation_source', label: 'Cancellation Source'},
			// { fieldtype: 'Link', options: 'Appointment Cancellation Reason', reqd:1, fieldname: 'cancellation_reason', label: 'Cancellation Reason',
			// 	get_query:function () {
			// 		return {
			// 			filters: {
			// 				"cancellation_source": d_reasons.get_value('cancellation_source')
			// 			}
			// 		};
			// 	}
			// },
			// { fieldtype: 'Column Break'},
			{ fieldtype: 'Select', options: cancelled_by_options, fieldname: 'cancelled_by', label: 'Cancelled By'},
			{ fieldtype: 'Small Text', fieldname: 'cancellation_notes', label: 'Cancellation Notes'},
		],
		primary_action_label: __("Cancel"),
		primary_action: function() {
			frappe.call({
				method: "healthcare.healthcare.page.patient_wait_list.patient_wait_list.cancel_reason_appointment",
				args:{
					appointment_id: appointment,
					cancellation_source: d_reasons.get_value('cancellation_source'),
					cancelled_by: d_reasons.get_value('cancelled_by'),
					cancellation_notes: d_reasons.get_value('cancellation_notes')
				},
				callback: function(r) {
					if(!r.exc){
						update_status(appointment,me,status)
					}
				},
				freeze: true
			})
			d_reasons.hide();
			d_reasons.get_primary_btn().attr('disabled', true);
		}
	});
	// disable dialog action initially
	d_reasons.get_primary_btn().attr('disabled', true);
	d_reasons.fields_dict["cancellation_notes"].df.onchange = () => {
		d_reasons.get_primary_btn().attr('disabled', null);
	}
	d_reasons.show();
}
var update_status= function(appointment, me, status){
	frappe.call({
		method: "healthcare.healthcare.doctype.patient_appointment.patient_appointment.update_status",
		args: {appointment_id: appointment, status: status},
		callback: function (r) {
			if(!r.exc){
				me.get_appointments();
			}
		}
	});
}
