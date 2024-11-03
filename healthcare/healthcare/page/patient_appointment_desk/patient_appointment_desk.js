frappe.provide('erpnext.healthcare');
frappe.provide("frappe.views.calendar");
frappe.provide("frappe.views.calendars");
{% include 'healthcare/healthcare/utils.js' %}

var practitioner_filter = null;
frappe.pages['patient-appointment-desk'].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Patient Appointment Desk'),
		single_column: true
	});
	frappe.breadcrumbs.add("Healthcare");
	wrapper.pos = new erpnext.healthcare.AppointmentDesk(wrapper);
}

erpnext.healthcare.AppointmentDesk = Class.extend({
	init: function (wrapper) {
		this.page_len = 20;
		this.freeze = false;
		this.page = wrapper.page;
		this.practitioner_filter = null;
		this.wrapper = $(wrapper).find('.page-content');
		this.required_libs = [
			'assets/frappe/js/lib/fullcalendar/fullcalendar.min.css',
			'assets/frappe/js/lib/fullcalendar/fullcalendar.min.js',
			'assets/frappe/js/lib/fullcalendar/locale-all.js',
		];
		console.log(this.required_libs)
		// $(".page-form.row").after($('<div class="textintro-area">').html(`<p class="none_text text-muted text-center">
		// <i class="fa fa-play-circle" style="color:blue;"></i> Please select an Healthcare Practitioner to begin</p>`))
		
		this.prepare_render_view();
		this.render_calendar_view();
		this.make_toolbar();

	},
	make_toolbar: function (frm) {
		var me = this;
		var selected_practitioner = "";
		this.practitioner = this.page.add_field({
			fieldtype: 'Link',
			label: 'Healthcare Practitioner',
			options: 'Healthcare Practitioner',
			change: function () {
				if(!me.practitioner.get_value()){
					$(".fc.fc-unthemed.fc-ltr").css('visibility', 'hidden')
					$(".text-muted.footnote-area.level").css('visibility', 'hidden')
					selected_practitioner = "";
					// $(".page-form.row").after($('<div class="textintro-area">').html(`<p class="none_text text-muted text-center">
					// <i class="fa fa-play-circle" style="color:blue;"></i> Please select an Healthcare Practitioner to begin</p>`))
				}
				else if (me.practitioner.get_value() != selected_practitioner) {
					$(".fc.fc-unthemed.fc-ltr").css('visibility', 'visible')
					$(".text-muted.footnote-area.level").css('visibility', 'visible')
					$(".textintro-area").hide()
					selected_practitioner = me.practitioner.get_value();
					practitioner_filter = selected_practitioner;
					me.render_calendar_view();
				}
			}
		});
	},

	render_calendar_view: function () {
		if (this.calendar) {
			this.calendar.refresh();
			return;
		}

		this.load_lib = new Promise(resolve => {
			if (this.required_libs) {
				frappe.require(this.required_libs, resolve);
			}
		});

		this.load_lib
			.then(() => this.get_calendar_preferences())
			.then(options => {
				this.calendar = new erpnext.healthcare.HCalendar(options);
			});
	},

	get_calendar_preferences: function () {
		const options = {
			doctype: null,
			parent: this.wrapper, //this.$result,
			page: this.page,
			list_view: this,
		};
		return new Promise(resolve => {
			Object.assign(options, frappe.views.calendar["Practitioner Event"]);
			resolve(options);
		});
	},

	prepare_render_view: function () {
		var me = this;
		this._render_view = this.render_view;

		var lib_exists = (typeof this.required_libs === 'string' && this.required_libs) ||
			($.isArray(this.required_libs) && this.required_libs.length);

		this.render_view = function (values) {
			me.values_map = {};
			me.rows_map = {};
			values = values.map(me.prepare_data.bind(this));
			if (lib_exists) {
				me.load_lib(function () {
					me._render_view(values);
				});
			} else {
				me._render_view(values);
			}
		}.bind(this);
	},
});

erpnext.healthcare.HCalendar = class HCalendar extends frappe.views.Calendar {
	make_page(){
		var me = this;

		// add links to other calendars
		me.page.clear_user_actions();

		$(this.parent).on("show", function () {
			me.$cal.fullCalendar("refetchEvents");
		});
	}

	make() {
		this.$wrapper = this.parent;
		this.$cal = $("<div>").appendTo(this.page.main);
		this.footnote_area = frappe.utils.set_footnote(this.footnote_area, this.page.main,
			__("Please select Practitioner and click on slots to create a new appointment."));
		this.footnote_area.css({
			"border-top": "0px"
		});

		this.$cal.fullCalendar(this.cal_options);
		// this.set_css();

		// var me = this;
		// const btn_frd = `<button class="btn btn-default btn-xs btn-show-weekend-frd">${__('Show Friday')}</button>`;
		// me.footnote_area.append(btn_frd);
		// me.$wrapper.on("click", ".btn-show-weekend-frd", function() {
		// 	me.$cal.fullCalendar('option', 'hiddenDays', []);
		// 	$(me.footnote_area).find('.btn-show-weekend-frd').detach();
		// 	const btn_frd = `<button class="btn btn-default btn-xs btn-hide-weekend-frd">${__('Hide Friday')}</button>`;
		// 	me.footnote_area.append(btn_frd);
		// });
		// me.$wrapper.on("click", ".btn-hide-weekend-frd", function() {
		// 	me.$cal.fullCalendar('option', 'hiddenDays', [5]);
		// 	$(me.footnote_area).find('.btn-hide-weekend-frd').detach();
		// 	const btn_frd = `<button class="btn btn-default btn-xs btn-show-weekend-frd">${__('Show Friday')}</button>`;
		// 	me.footnote_area.append(btn_frd);
		// });
	}
	setup_options(defaults) {
		var me = this;
		this.go_to_date = this.page.add_field({
			fieldtype: 'Date',
			label: 'Go to Date',
			change: function () {
				me.$cal.fullCalendar('gotoDate', me.go_to_date.value);
				me.$cal.fullCalendar('changeView', 'agendaDay');
			}
		});
		this.check_availability_btn = me.page.add_field({
			fieldtype: 'Button',
			label: 'Check Availability',
			click: function () {
				if(practitioner_filter){
					frappe.db.get_value('Healthcare Practitioner', {name: practitioner_filter}, 'department', (r) => {
						if(r && r.department){
							check_and_set_availability(me, practitioner_filter, r.department, me.$cal.fullCalendar('getDate'))
						}
					});
				}
				else {
					check_and_set_availability(me, practitioner_filter, null, me.$cal.fullCalendar('getDate'))
				}
			}
		});
		this.create_event_btn = me.page.add_field({
			fieldtype: 'Button',
			label: 'Create New Event',
			click: function () {
				create_new_event(me);
			}
		});
		this.view_waitlist = me.page.add_field({
			fieldtype: 'Button',
			label: 'Open Appointment List',
			click: function () {
				frappe.set_route('patient-wait-list')
			}
		});
		this.page.set_primary_action(__("Refresh"), function() {
			frappe.msgprint(__("Refreshing..."));
			frappe.ui.toolbar.clear_cache();
		}, "fa fa-refresh");
		this.cal_options = {
			// schedulerLicenseKey: 'CC-Attribution-NonCommercial-NoDerivatives',
			locale: frappe.boot.user.language || "en",
			customButtons: {
		    hide_friday: {
		      text: 'Hide Friday',
		      click: function() {
							me.$cal.fullCalendar('option', 'hiddenDays', [5]);
							me.$wrapper.find('.fc-button').removeClass('fc-state-default');
							me.$wrapper.find('.fc-button').addClass('btn-info calen-btn');
							me.$wrapper.find('.fc-show_friday-button').removeClass('fc-state-active');
							me.$wrapper.find('.fc-hide_friday-button').addClass('fc-state-active');
		      }
		    },
				show_friday: {
		      text: 'Show Friday',
		      click: function() {
							me.$cal.fullCalendar('option', 'hiddenDays', []);
							me.$wrapper.find('.fc-button').removeClass('fc-state-default');
							me.$wrapper.find('.fc-button').addClass('btn-info calen-btn');
							me.$wrapper.find('.fc-hide_friday-button').removeClass('fc-state-active');
							me.$wrapper.find('.fc-show_friday-button').addClass('fc-state-active');
		      }
		    }
		  },
			header: {
				left: 'title',
				center: '',
				right: 'show_friday, hide_friday, prev,today,next month,agendaWeek,agendaDay,list'
			},
			views: {
				agendaFourDay: {
				  type: 'agenda',
				  duration: { days:  10}
				}
			},
			// editable: true,
			hiddenDays: [5],
			selectable: true,
			selectHelper: true,
			forceEventDuration: true,
			groupByResource: true,
			defaultView: 'list', // 'agendaDay',
			weekends: defaults.weekends,
			scrollTime: moment().format("HH")+ ":00:00", //frappe.datetime.now_time(), //current server time
			editable: false,
			eventStartEditable: false,
			eventDurationEditable: false,
			nowIndicator: true,
			events: function(start, end, timezone, callback) {
				// After field map
				// filters: [
					// 	['Patient Appointment', 'status', '=', 'Open', false]
					// ]
				me.$wrapper.find('.fc-hide_friday-button').addClass('fc-state-active');
				me.$wrapper.find('.fc-button').removeClass('fc-state-default');
				me.$wrapper.find('.fc-button').addClass('btn-info calen-btn');
				return frappe.call({
					method: "healthcare.healthcare.healthcare.utils.get_events",
					type: "GET",
					args: {
						start: frappe.datetime.get_datetime_as_string(start),
						end: frappe.datetime.get_datetime_as_string(end),
						filters: {
							practitioner: practitioner_filter,
							service_unit: false
						}
					},
					callback: function(r) {
						var events = r.message || [];
						events = me.prepare_events(events);
						callback(events);
					}
				});
			},
			eventDrop: function(event, delta, revertFunc) {
				// DISABLE DRAG N DROP
			},
			eventResize: function(event, delta, revertFunc) {
				// DISABLE RESIZE
			},
			select: function(startDate, endDate, jsEvent, view) {
				if (view.name==="month" && (endDate - startDate)===86400000) {
					// detect single day click in month view
					return;
				}

				var event = frappe.model.get_new_doc(me.doctype);

				event[me.field_map.start] = frappe.datetime.get_datetime_as_string(startDate);

				if(me.field_map.end)
					event[me.field_map.end] = frappe.datetime.get_datetime_as_string(endDate);

				if(me.field_map.allDay) {
					var all_day = (startDate._ambigTime && endDate._ambigTime) ? 1 : 0;

					event[me.field_map.allDay] = all_day;

					if (all_day)
						event[me.field_map.end] = frappe.datetime.get_datetime_as_string(moment(endDate).subtract(1, "s"));
				}
				// frappe.set_route("Form", me.doctype, event.name);
			},
			dayClick: function(date, jsEvent, view) {
				if(view.name === 'month') {
					const $date_cell = $('td[data-date=' + date.format('YYYY-MM-DD') + "]");

					if($date_cell.hasClass('date-clicked')) {
						me.$cal.fullCalendar('changeView', 'agendaDay');
						me.$cal.fullCalendar('gotoDate', date);
						me.$wrapper.find('.date-clicked').removeClass('date-clicked');

						// update "active view" btn
						me.$wrapper.find('.fc-month-button').removeClass('active');
						me.$wrapper.find('.fc-agendaDay-button').addClass('active');
					}

					me.$wrapper.find('.date-clicked').removeClass('date-clicked');
					$date_cell.addClass('date-clicked');
				}
				return false;
			},
			eventClick: function(event) {
				// edit event description or delete
				if(event.doctype == "Practitioner Event"){
					if(event.practitioner){
						frappe.db.get_value('Healthcare Practitioner', {name: event.practitioner}, 'department', (r) => {
							if(r && r.department){
								var department = r.department
								var event_date=event.start.format("YYYY-MM-DD");
								var today = frappe.datetime.nowdate();
								if(event.service_unit){
									frappe.db.get_value('Healthcare Service Unit', {name: event.service_unit}, 'overlap_appointments', (data) => {
										var allow_overlap = false;
										if(data && data.overlap_appointments){
											allow_overlap = true;
										}
										if(today > event_date){
											frappe.db.get_value("Healthcare Settings", "", "appointment_administrator", function(r) {
												if(r && r.appointment_administrator){
													if(frappe.user.has_role(r.appointment_administrator)){
														book_appointment(event, department, me, allow_overlap);
													}
													else{
														frappe.msgprint(__("You cannot book appointments for past date"));
													}
												}
												else{
													frappe.msgprint(__("You cannot book appointments for past date"));
												}
											});
										}
										else{
											book_appointment(event, department, me, allow_overlap);
										}
									});
								}
								else{
									if(today > event_date){
										frappe.db.get_value("Healthcare Settings", "", "appointment_administrator", function(r) {
											if(r && r.appointment_administrator){
												if(frappe.user.has_role(r.appointment_administrator)){
													book_appointment(event, department, me, false);
												}
												else{
													frappe.msgprint(__("You cannot book appointments for past date"));
												}
											}
											else{
												frappe.msgprint(__("You cannot book appointments for past date"));
											}
										});
									}
									else{
										book_appointment(event, department, me, false);
									}
								}
							}
						});
					}
				}
				else if(event.doctype == "Patient Appointment"){
					show_appointment(event, me);
					// frappe.set_route("Form", event.doctype, event.name);
				}
			},
		}
	};
	prepare_events(events) {
		var me = this;

		return (events || []).map(d => {
			d.id = d.name;
			d.editable = frappe.model.can_write(d.doctype || me.doctype);

			// do not allow submitted/cancelled events to be moved / extended
			if(d.docstatus && d.docstatus > 0) {
				d.editable = false;
			}

			$.each(me.field_map, function(target, source) {
				d[target] = d[source];
			});

			if(!me.field_map.allDay)
				d.allDay = 1;

			// convert to user tz
			d.start = frappe.datetime.get_datetime_as_string(d.start);
			d.end = frappe.datetime.get_datetime_as_string(d.end);

			// show event on single day if start or end date is invalid
			if (!frappe.datetime.validate(d.start) && d.end) {
				d.start = frappe.datetime.add_days(d.end, -1);
			}

			if (d.start && !frappe.datetime.validate(d.end)) {
				d.end = frappe.datetime.add_days(d.start, 1);
			}

			me.fix_end_date_for_event_render(d);
			me.prepare_colors(d);
			return d;
		});
	};
};

var show_appointment = function (event, page) {
	frappe.call({
		method: "frappe.client.get",
		args:{
			doctype: "Patient Appointment",
			name: event.appointment_name
		},
		callback: function(r) {
			if(r && r.message){
				var data = r.message;
				frappe.model.with_doctype("Patient Appointment", function() {
					show_appointment_dialoge(data, event, page, frappe.meta.get_docfield("Patient Appointment", "cancelled_by").options);
				});
			}
		}
	});
};

var show_appointment_dialoge = function(data, event, page, cancelled_by_options) {
	var fields = [
		{ fieldtype: 'Section Break'},
		{ fieldtype: 'Link', read_only:1, options: 'Patient', reqd:1, fieldname: 'patient', label: 'Patient'},
		{ fieldtype: 'Data', read_only:1, fieldname: 'patient_name', depends_on:'eval:doc.patient', label: 'Patient Name'},
		{ fieldtype: 'Link', options: 'Medical Department', read_only:1, fieldname: 'department', label: 'Medical Department'},
		{ fieldtype: 'Link', options: 'Healthcare Practitioner', read_only:1, fieldname: 'practitioner', label: 'Healthcare Practitioner'},
		{ fieldtype: 'Column Break'},
		{ fieldtype: 'Link', read_only:1, options: 'Patient Appointment', reqd:1, fieldname: 'patient_appointment', label: 'Appointment'},
		{ fieldtype: 'Link', read_only:1, options: 'Appointment Type', reqd:1, fieldname: 'appointment_type', label: 'Appointment Type'},
		{ fieldtype: 'Link', read_only:1, options: 'Healthcare Service Unit', fieldname: 'service_unit', label: 'Service Unit'},
		{ fieldtype: 'Int', read_only:1, fieldname: 'duration', label: 'Duration'},
		{ fieldtype: 'Column Break'},
		{ fieldtype: 'Date', read_only:1, fieldname: 'appointment_date', label: 'Date'},
		{ fieldtype: 'Time', read_only:1, fieldname: 'appointment_time', label: 'Time'},
		{ fieldtype: 'Select', read_only:1, options: '\nDirect\nReferral\nExternal Referral', reqd:1, fieldname: 'source', label: 'Source'},
		{ fieldtype: 'Link', read_only:1, options: 'Healthcare Practitioner',  fieldname: 'referring_practitioner', label: 'Referring Practitioner',
			depends_on:'eval:doc.source ==`Referral` || doc.source ==`External Referral`'
		},
		{ fieldtype: 'Select', options: 'Cancelled\nScheduled\nOpen\nIn Progress\nClosed\nPending\nConfirmed\nNo show\nArrived\nChecked out',
			fieldname: 'status', label: 'Status'},
		{ fieldtype: 'Section Break', depends_on:'eval:doc.status=="Cancelled"'},
		{ fieldtype: 'Select', fieldname: 'cancellation_source', options: '\nPatient\nPractitioner\nFacility',
			depends_on:'eval:doc.status=="Cancelled"', label: 'Cancellation Source'},
		{ fieldtype: 'Select', fieldname: 'cancelled_by', options: cancelled_by_options, depends_on:'eval:doc.status=="Cancelled"',
			label: 'Cancelled By'
		},
		{ fieldtype: 'Link', fieldname: 'cancellation_reason', options:"Appointment Cancellation Reason", depends_on:'eval:doc.status=="Cancelled"',
			label: 'Cancellation Reason',
			get_query:function () {
				return {
					filters: {
						"cancellation_source": d.get_value('cancellation_source')
					}
				};
			}
		},
		{ fieldtype: 'Column Break', depends_on:'eval:doc.status=="Cancelled"'},
		{ fieldtype: 'Small Text', fieldname: 'cancellation_note', depends_on:'eval:doc.status=="Cancelled"', label:'Cancellation Note'},
		{ fieldtype: 'Section Break', depends_on:'eval:doc.companion'},
		{ fieldtype: 'Link', read_only:1, options: 'Contact', fieldname: 'companion', label: 'Companion'},
		{ fieldtype: 'Column Break'},
		{ fieldtype: 'Data', read_only:1, fieldname: 'companion_name', depends_on:'eval:doc.companion', label: 'Companion Name'}
	]
	if(data.insurance){
		fields.push({ fieldtype: 'Section Break'});
		fields.push({ fieldtype: 'Link', read_only:1, options: 'Insurance Assignment', fieldname: 'insurance', label: 'Healthcare Insurance'});
		fields.push({ fieldtype: 'Data', read_only:1, fieldname: 'insurance_company_name', depends_on:'eval:doc.insurance', label: 'Insurance Company Name'});
		fields.push({ fieldtype: 'Data', read_only:1, fieldname: 'insurance_approval_number', depends_on:'eval:doc.insurance', label: 'Approval Number'});
		fields.push({ fieldtype: 'Column Break'});
		fields.push({ fieldtype: 'Small Text', read_only:1, fieldname: 'insurance_remarks', depends_on:'eval:doc.insurance', label: 'Insurance Remarks'});
	}
	else if(data.schc_package_assignment){
		fields.push({ fieldtype: 'Section Break'});
		fields.push({ fieldtype: 'Link', read_only:1, options: 'Healthcare Package Assignment', fieldname: 'schc_package_assignment', label: 'Healthcare Package'});
		fields.push({ fieldtype: 'Data', read_only:1, fieldname: 'schc_package_assignment_name', label: 'Package Name'});
	}

	var d = new frappe.ui.Dialog({
		title: __("Update Appointment - " + event.practitioner_name),
		fields: fields,
		primary_action_label: __("Update"),
		primary_action: function() {
			update_appointment(d);
			d.hide();
		}
	});

	d.set_values({
		'patient_appointment': data.name,
		'status': data.status,
		'patient': data.patient,
		'patient_name': data.patient_name,
		'appointment_date': event.start.toDate(),
		'appointment_time': event.start.format('HH:mm:ss'),
		'practitioner': data.practitioner,
		'service_unit':data.service_unit,
		'department': data.department,
		'duration': data.duration,
		'appointment_type': data.appointment_type,
		'source': data.source,
		'referring_practitioner': data.referring_practitioner,
		'schc_package_assignment' :data.schc_package_assignment,
		'schc_package_assignment_name': data.schc_package_assignment_name,
		'insurance' : data.insurance,
		'insurance_company_name': data.insurance_company_name,
		'insurance_approval_number':data.insurance_approval_number,
		'insurance_remarks': data.insurance_remarks,
		'companion': data.companion
	});

	// Field Change Handler
	var fd = d.fields_dict;
	d.fields_dict["source"].df.onchange = () => {
		if(d.get_value('source')=="Referral"){
			frappe.db.get_value("Healthcare Practitioner", d.get_value('practitioner'), 'healthcare_practitioner_type', function(r) {
				if(r && r.healthcare_practitioner_type && r.healthcare_practitioner_type=="Internal"){
					d.set_values({
						'referring_practitioner': event.practitioner
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
						'referring_practitioner': event.practitioner
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
	d.fields_dict["companion"].df.onchange = () => {
		frappe.db.get_value("Contact", d.get_value('companion'), 'first_name', function(r) {
			if(r && r.first_name){
				d.set_values({
					'companion_name': r.first_name
				});
			}
		});
	}
	d.show();
	d.$wrapper.find('.modal-dialog').css("width", "800px");
	var update_appointment = function(d){
		frappe.call({
			"method": "healthcare.healthcare.healthcare.utils.update_appointment_from_desk",
			"args": {dialog: d.get_values()},
			callback: function (data) {
				page.$cal.fullCalendar("refetchEvents");
			},
			freeze: true,
			freeze_message: __("Updating ...")
		});
	};
}

var book_appointment = function (event, department, page, allow_overlap) {
	var d = new frappe.ui.Dialog({
		title: __("Book Appointment -  " + event.practitioner_name),
		fields: [
			{ fieldtype: 'Section Break'},
			{ fieldtype: 'Link', options: 'Patient', reqd:1, fieldname: 'patient', label: 'Patient'},
			{ fieldtype: 'Data', read_only:1, fieldname: 'patient_name', depends_on:'eval:doc.patient', label: 'Patient Name'},
			{ fieldtype: 'Check', fieldname: 'patient_companion', label: 'Patient Companion', depends_on:'eval:doc.patient'},
			{ fieldtype: 'Column Break'},
			{ fieldtype: 'Link', options: 'Appointment Type', reqd:1, fieldname: 'appointment_type', label: 'Appointment Type',
				get_query:function () {
					return {
						query : "healthcare.healthcare.utils.get_practitioner_appointment_type",
						filters: {parent : d.get_value("practitioner")}
					}
				},
				read_only: event.appointment_type ? 1 :0
			},
			{ fieldtype: 'Column Break'},
			{ fieldtype: 'Int', fieldname: 'duration', label: 'Duration', read_only: allow_overlap ? 1 : 0},
			{ fieldtype: 'Section Break', depends_on:'eval:doc.patient_companion'},
			{ fieldtype: 'Data',  fieldname: 'companion_name', depends_on:'eval:doc.patient_companion', label: 'Companion Name'},
			{ fieldtype: 'Data', fieldname: 'companion_id',  depends_on:'eval:doc.patient_companion', label: 'Companion ID'},
			{ fieldtype: 'Column Break'},
			{ fieldtype: 'Data',  fieldname: 'companion_mobile', depends_on:'eval:doc.patient_companion', label: 'Companion Mobile '},
			{ fieldtype: 'Select', options:'\nFather\nMother\nSister\nBrother\nSpouse\nBairn\nRelative\nFriend\nColleague\nOther', depends_on:'eval:doc.patient_companion', fieldname: 'companion_relation',  label: 'Companion Relation'},
			{ fieldtype: 'Column Break'},
			{ fieldtype: 'Data', fieldname: 'companion_email', depends_on:'eval:doc.patient_companion',  label: 'Companion Email'},
			{ fieldtype: 'Section Break'},
			{ fieldtype: 'Link', options: 'Healthcare Service Unit', fieldname: 'service_unit', label: 'Service Unit',
				get_query: function () {
					return {
						filters: {
							"is_group": false,
							"allow_appointments": 1
						}
					};
				}, read_only: event.service_unit ? 1 :0
			},
			{ fieldtype: 'Column Break'},
			{ fieldtype: 'Select', options: '\nDirect\nReferral\nExternal Referral', reqd:1, fieldname: 'source', label: 'Source'},
			{ fieldtype: 'Column Break'},
			{ fieldtype: 'Link', options: 'Healthcare Practitioner',  fieldname: 'referring_practitioner', label: 'Referring Practitioner',
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
					let filters = {
						"patient": d.get_value('patient'),
						"from_date": ["<=", d.get_value('appointment_date')],
						"to_date": [">=", d.get_value('appointment_date')],
						"docstatus": 1,
						"status": ["in", ["Submitted", "Paid", "Partial"]]
					}
					if (d.get_value('sch_healthcare_practitioner_level')) {
						filters.healthcare_practitioner_level = d.get_value('sch_healthcare_practitioner_level')
					}
					if (d.get_value('department')) {
						filters.department = d.get_value('department')
					}
					return {
						filters: filters
					};
				}
			},
			{ fieldtype: 'Data', read_only:1, fieldname: 'schc_package_assignment_name', depends_on:'eval:doc.schc_package_assignment', label: 'Package Name'},
			{ fieldtype: 'Link', options: 'Item', fieldname: 'schc_package_item', label: 'Package Item',
				depends_on: 'eval: doc.schc_package_assignment',
				get_query: function () {
					return {
						query : "healthcare.queries.get_package_item_list",
						filters: {parent :d.get_value('schc_package_assignment')}
					};
				}
			},
			{ fieldtype: 'Data', read_only:1, fieldname: 'item_name', depends_on:'eval:doc.schc_package_item', label: 'Item Name'},
			{ fieldtype: 'Section Break'},
			{ fieldtype: 'Link', options: 'Medical Department', read_only:1, fieldname: 'department', label: 'Medical Department'},
			{ fieldtype: 'Link', options: 'Healthcare Practitioner', read_only:1, fieldname: 'practitioner', label: 'Healthcare Practitioner'},
			{ fieldtype: 'Link', options: 'Healthcare Practitioner Level', read_only:1, fieldname: 'sch_healthcare_practitioner_level', label: 'Healthcare Practitioner Level'},
			{ fieldtype: 'Column Break'},
			{ fieldtype: 'Date', read_only:1, fieldname: 'appointment_date', label: 'Date'},
			{ fieldtype: 'Time', read_only:1, fieldname: 'appointment_time', label: 'Time'}
		],
		primary_action_label: __("Book"),
		primary_action: function() {
			appointment_details = {
				'appointment_date': event.start.toDate(),
				'appointment_time': event.start.format('HH:mm:ss'),
				'practitioner': event.practitioner,
				'service_unit':d.get_value('service_unit'),
				'department': department,
				'duration': d.get_value('duration'),
				'appointment_type': d.get_value('appointment_type'),
				'source': d.get_value('source'),
				'patient': d.get_value('patient'),
				'insurance': d.get_value('insurance'),
				'schc_package_assignment': d.get_value('schc_package_assignment'),
				'practitioner_event': event.name,
				'sch_healthcare_practitioner_level': d.get_value('sch_healthcare_practitioner_level')
			};
			if(d.get_value('patient_companion') && d.get_value('companion_name') && d.get_value('companion_mobile')){
				appointment_details['companion_name'] = d.get_value('companion_name');
				appointment_details['companion_mobile'] = d.get_value('companion_mobile');
				appointment_details['companion_email'] = d.get_value('companion_email');
				appointment_details['companion_id'] = d.get_value('companion_id');
				appointment_details['companion_relation'] = d.get_value('companion_relation');
			}
			if(d.get_value('source') == "External Referral" || d.get_value('source') == "Referral"){
				appointment_details['referring_practitioner'] = d.get_value('referring_practitioner')
			}
			if(d.get_value('insurance')){
				appointment_details['insurance_company_name'] = d.get_value('insurance_company_name');
				appointment_details['insurance_approval_number'] = d.get_value('insurance_approval_number');
				appointment_details['insurance_remarks'] = d.get_value('insurance_remarks');
			}
			else if(d.get_value('schc_package_assignment')){
				appointment_details['schc_package_item'] = d.get_value('schc_package_item')
			}
			if(d.get_value('patient_companion') && (!d.get_value('companion_mobile') || !d.get_value('companion_name'))){
				frappe.msgprint("Companion Information - Name and Mobile Mandatory");
			}
			else{
				book_appointment_from_desk(appointment_details)
				d.hide();
			}
		}
	});

	d.set_values({
		'appointment_date': event.start.toDate(),
		'appointment_time': event.start.format('HH:mm:ss'),
		'practitioner': event.practitioner,
		'service_unit':event.service_unit,
		'department': department,
		'duration': event.duration,
		'appointment_type': event.appointment_type,
		'source': event.source,
		'referring_practitioner': event.referring_practitioner,
		'schc_package_assignment' :event.schc_package_assignment,
		'insurance' : event.insurance,
		'insurance_approval_number':event.insurance_approval_number,
		'insurance_remarks': event.insurance_remarks
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

	// Field Change Handler
	var fd = d.fields_dict;
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
		d.set_values({"schc_package_item": ''});
		if(d.get_value('schc_package_assignment')){
			d.set_values({
				'insurance': ''
			});
			frappe.call({
				method: "healthcare.healthcare.doctype.healthcare_package.healthcare_package.get_package_item_list",
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
			if(event.appointment_type){
				d.set_values({
					'appointment_type': event.appointment_type
				});
			}
			d.set_values({"schc_package_item": ''});
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
					var varble = 0;
					$.each(records, function(k, l){
						frappe.db.get_value("Patient Appointment", l.name, ['status','invoiced'], function(r) {
							if(r){
								if((r.status == 'No show' || r.status == 'Pending') && r.invoiced == 0){
									varble = varble+1
									d.set_values({
										booked_appointments: records.length-varble,
										remaining_appointments: item.no_of_session - (records.length-varble) - item.initial_completed_session
									});
								}
							}
						});
					});
						if (records.length >= (item.no_of_session - item.initial_completed_session)){
							d.set_values({
								remaining_appointments: __('Limit Exceeded')
							});
						d.get_primary_btn().attr('disabled', true);
						}
						else {
							d.get_primary_btn().attr('disabled', null);
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

	d.fields_dict["appointment_type"].df.onchange = () => {
		frappe.db.get_value("Appointment Type", d.get_value('appointment_type'), 'default_duration', function(r) {
			if(r && r.default_duration){
				d.set_values({
					'duration': r.default_duration
				});
			}
		});
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
	d.fields_dict["practitioner"].df.onchange = () => {
		frappe.db.get_value("Healthcare Practitioner", d.get_value('practitioner'), 'sch_healthcare_practitioner_level', function(r) {
			if(r && r.sch_healthcare_practitioner_level){
				d.set_values({
					'sch_healthcare_practitioner_level': r.sch_healthcare_practitioner_level
				});
			}
		});
	}
	d.fields_dict["source"].df.onchange = () => {
		if(d.get_value('source')=="Referral"){
			frappe.db.get_value("Healthcare Practitioner", d.get_value('practitioner'), 'healthcare_practitioner_type', function(r) {
				if(r && r.healthcare_practitioner_type && r.healthcare_practitioner_type=="Internal"){
					d.set_values({
						'referring_practitioner': event.practitioner
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
						'referring_practitioner': event.practitioner
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
			method: "healthcare.healthcare.healthcare.utils.get_contact_details",
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
	d.show();
	d.$wrapper.find('.modal-dialog').css("width", "800px");
	var book_appointment_from_desk = function(appointment_details){
		frappe.call({
			"method": "healthcare.healthcare.healthcare.utils.book_appointment_from_desk",
			"args": {appointment_details: appointment_details},
			callback: function (data) {
				page.$cal.fullCalendar("refetchEvents");
			},
			freeze: true,
			freeze_message: __("Booking ...")
		});
	};
};

var create_new_event = function (page) {
	var d = new frappe.ui.Dialog({
		title: __("Create Practitioner Event"),
		fields: [
			{ fieldtype: 'Section Break'},
			{ fieldtype: 'Link', options: 'Practitioner Event Type', fieldname: 'event_type', label: 'Event Type'},
			{ fieldtype: 'Data', reqd:1, fieldname: 'event', label: 'Event'},
			{ fieldtype: 'Link', options: 'Healthcare Practitioner', reqd:1, fieldname: 'practitioner', label: 'Healthcare Practitioner'},
			{ fieldtype: 'Data', read_only:1, fieldname: 'practitioner_name', depends_on:'eval:doc.practitioner', label: 'Practitioner Name'},
			{ fieldtype: 'Date', reqd:1, fieldname: 'from_date', label: 'From Date'},
			{ fieldtype: 'Column Break'},
			{ fieldtype: 'Time', reqd:1, fieldname: 'from_time', label: 'From Time'},
			{ fieldtype: 'Time', reqd:1, fieldname: 'to_time', label: 'To Time'},
			{ fieldtype: 'Check', fieldname: 'present', label: 'Present'},
			{ fieldtype: 'Link', options: 'Appointment Type', fieldname: 'appointment_type', label: 'Appointment Type', depends_on:'eval:doc.present'},
			{ fieldtype: 'Int', fieldname: 'duration', label: 'Duration', depends_on:'eval:doc.present'},
			{ fieldtype: 'Column Break'},
			{ fieldtype: 'Color', fieldname: 'color', label: 'Color'},
			{ fieldtype: 'Link', options: 'Healthcare Service Unit', fieldname: 'service_unit', label: 'Service Unit', depends_on:'eval:doc.present',
				get_query: function () {
					return {
						filters: {
							"is_group": false,
							"allow_appointments": 1
						}
					};
				}
			},
			{ fieldtype: 'Data', fieldname: 'total_service_unit_capacity', label: 'Total Service Unit Capacity',
				depends_on:'eval:doc.service_unit'},
			{ fieldtype: 'Check', fieldname: 'repeat_this_event', label: 'Repeat this Event'},
			{ fieldtype: 'Section Break' ,fieldname:'sb_repeat_event', depends_on:'eval:doc.repeat_this_event'},
			{ fieldtype: 'Select', fieldname: 'repeat_on', label: 'Repeat On', options:'\nEvery Day\nEvery Week\nEvery Month\nEvery Year'},
			{ fieldtype: 'Check', fieldname: 'monday', label: 'Monday', depends_on:'eval:doc.repeat_on==`Every Day`'},
			{ fieldtype: 'Check', fieldname: 'tuesday', label: 'Tuesday', depends_on:'eval:doc.repeat_on==`Every Day`'},
			{ fieldtype: 'Check', fieldname: 'wednesday', label: 'Wednesday', depends_on:'eval:doc.repeat_on==`Every Day`'},
			{ fieldtype: 'Check', fieldname: 'thursday', label: 'Thursday', depends_on:'eval:doc.repeat_on==`Every Day`'},
			{ fieldtype: 'Check', fieldname: 'friday', label: 'Friday', depends_on:'eval:doc.repeat_on==`Every Day`'},
			{ fieldtype: 'Check', fieldname: 'saturday', label: 'Saturday', depends_on:'eval:doc.repeat_on==`Every Day`'},
			{ fieldtype: 'Check', fieldname: 'sunday', label: 'Sunday', depends_on:'eval:doc.repeat_on==`Every Day`'},
			{ fieldtype: 'Column Break'},
			{ fieldtype: 'Date', fieldname: 'repeat_till', label: 'Repeat Till'},
		],
		primary_action_label: __("Create"),
		primary_action: function() {
			if(d.get_value('present') && d.get_value('service_unit')){
				frappe.db.get_value("Healthcare Service Unit", d.get_value('service_unit'), 'total_service_unit_capacity', function(r) {
					if(r && parseInt(r.total_service_unit_capacity) < parseInt(d.get_value('total_service_unit_capacity'))){
						let message = __("Not Allowed - Maximum Capacity of {0} is {1}",
							[d.get_value('service_unit').bold(), r.total_service_unit_capacity.bold()]);
						frappe.msgprint(message);
					}
					else{
						create_event_from_desk();
						d.hide();
					}
				});
			}
			else{
				create_event_from_desk();
				d.hide();
			}
		}
	});

	d.set_values({
		'from_date': page.$cal.fullCalendar('getDate'),
		'practitioner': practitioner_filter,
	});

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
	}
	d.fields_dict["practitioner"].df.onchange = () => {
		frappe.db.get_value("Healthcare Practitioner", d.get_value('practitioner'), 'practitioner_name', function(r) {
			if(r && r.practitioner_name){
				d.set_values({
					'practitioner_name': r.practitioner_name
				});
			}
		});
	}
	d.fields_dict["service_unit"].df.onchange = () => {
		frappe.db.get_value("Healthcare Service Unit", d.get_value('service_unit'), 'total_service_unit_capacity', function(r) {
			if(r && r.total_service_unit_capacity){
				d.set_values({
					'total_service_unit_capacity': r.total_service_unit_capacity
				});
			}
		});
	}
	d.fields_dict["event_type"].df.onchange = () => {
		if(d.get_value("event_type")){
			frappe.call({
				method: "frappe.client.get",
				args:{
					doctype: "Practitioner Event Type",
					name: d.get_value('event_type')
				},
				callback: function(r) {
					if(r.message){
						d.set_values({
							'event': r.message.name,
							'present': r.message.present,
							'appointment_type': r.message.present?r.message.appointment_type:'',
							'duration': r.message.present?r.message.duration:'',
							'color': r.message.color
						});
					}
				}
			});
		}
	}
	d.fields_dict["repeat_on"].df.onchange = () => {
		if(d.get_value('repeat_on')=="Every Day"){
			d.set_values({
				'monday': true,
				'tuesday': true,
				'wednesday': true,
				'thursday': true,
				'friday': true,
				'saturday': true,
				'sunday': true
			});
			d.set_values({
				'monday': true
			});
		}
	}
	d.show();
	d.$wrapper.find('.modal-dialog').css("width", "800px");
	var create_event_from_desk = function(){
		var details = {
			'event': d.get_value('event'), 'practitioner': d.get_value('practitioner'),
			'from_date': d.get_value('from_date'), 'from_time': d.get_value('from_time'),
			'to_time': d.get_value('to_time'), 'present': d.get_value('present'),
			'appointment_type': d.get_value('appointment_type'), 'duration': d.get_value('duration'),
			'service_unit': d.get_value('service_unit'), 'repeat_this_event': d.get_value('repeat_this_event'),
			'repeat_on': d.get_value('repeat_on'), 'repeat_till': d.get_value('repeat_till')||'',
			'monday': d.get_value('monday'), 'tuesday': d.get_value('tuesday'),
			'wednesday': d.get_value('wednesday'), 'thursday': d.get_value('thursday'),
			'friday': d.get_value('friday'), 'saturday': d.get_value('saturday'),
			'sunday': d.get_value('sunday'), 'event_type': d.get_value('event_type'),
			'total_service_unit_capacity': d.get_value('service_unit')?d.get_value('total_service_unit_capacity'):'',
			'color': d.get_value('color')
		}
		frappe.call({
			"method": "healthcare.healthcare.healthcare.utils.create_event_from_desk",
			"args": {details: details},
			callback: function (data) {
				page.$cal.fullCalendar("refetchEvents");
			},
			freeze: true,
			freeze_message: __("Creating Event ...")
		});
	};
};
