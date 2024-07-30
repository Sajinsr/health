frappe.provide('frappe.dashboards.chart_sources');

frappe.dashboards.chart_sources["Department wise Patient Appointments"] = {
	method: "marley_health.marley_health.dashboard_chart_source.department_wise_patient_appointments.department_wise_patient_appointments.get",
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company")
		}
	]
};
