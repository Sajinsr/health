import frappe


def execute():
	company = frappe.get_all("Company", filters={"country": "India"})
	if not company:
		return

	from marley_health.regional.india.abdm.setup import setup

	setup()
