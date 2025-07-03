frappe.listview_settings["ABDM Request"] = {
	get_indicator: function(doc) {
		var colors = {
			"Requested": "orange",
			"Expired": "grey",
			"Revoked": "red",
			"Expired": "grey",
            "Denied": "red",
            "Granted": "green"
		};
		return [__(doc.status), colors[doc.status], "status,=," + doc.status];
	}
};
