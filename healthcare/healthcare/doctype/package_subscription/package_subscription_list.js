frappe.listview_settings["Package Subscription"] = {
	get_indicator: function (doc) {
		if (doc.status === "Paid") {
			return [__("Paid"), "green", "status,=," + doc.status];
		} else if (doc.status === "Partially Paid") {
			return [__("Partially Paid"), "orange", "status,=," + doc.status];
		} else if (doc.status === "Unpaid") {
			return [__("Unpaid"), "red", "status,=," + doc.status];
		} else if (doc.status === "Discontinued") {
			return [__("Discontinued"), "red", "status,=," + doc.status];
		}
	},
}