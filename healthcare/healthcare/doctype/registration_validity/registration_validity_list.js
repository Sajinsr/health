frappe.listview_settings['Registration Validity'] = {
	add_fields: ['patient', 'valid_from', 'valid_to'],
	get_indicator: function (doc) {
		var colors = {
			'Active': 'green',
			'Expired': 'red',
			'Cancelled': 'red'
		};
		return [__(doc.status), colors[doc.status], `status,=,${doc.status}`];
	}
};