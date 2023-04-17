/*
(c) ESS 2015-16
*/
frappe.listview_settings['Patient Appointment'] = {
	filters: [["status", "=", "Open"]],
	get_indicator: function(doc) {
		var colors = {
			"Open": "orange",
			"Scheduled": "yellow",
			"No Show": "grey",
			"In Progress": "orange",
			"Closed": "green",
			"Cancelled": "red",
		};
		return [__(doc.status), colors[doc.status], "status,=," + doc.status];
	}
};
