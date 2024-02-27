frappe.listview_settings["Medication Administration"] = {
    add_fields: [
		"patient",
		"date",
		"performer",
		"inpatient_record",
		"medication_request",
	],
    has_indicator_for_draft: 1,
	get_indicator: function (doc) {
		if (doc.status === "Completed") {
			return [__("Completed"), "green", "status, =, Completed"];
		} else if (doc.status === "Stopped") {
			return [__("Stopped"), "red", "status, =, Stopped"];
        } else if (doc.status === "Entered in Error") {
			return [__("Entered in Error"), "red", "status, =, Entered in Error"];
		} else if (doc.status === "On Hold") {
			return [__("On Hold"), "gray", "status, =, On Hold"];
		} else if (doc.status === "In Progress") {
			return [__("In Progress"), "orange", "status, =, In Progress"];
		} else if (doc.status === "Not Done") {
			return [__("Not Done"), "orange", "status, =, Not Done"];
		} else if (doc.status === "Unknown") {
			return [__("Unknown"), "black", "status, =, Unknown"];
		}
	},
};
