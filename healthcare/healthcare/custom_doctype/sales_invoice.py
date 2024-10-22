import frappe

from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from erpnext.stock.get_item_details import get_item_details


class HealthcareSalesInvoice(SalesInvoice):
	@frappe.whitelist()
	def set_healthcare_services(self, checked_values):

		for checked_item in checked_values:
			item_line = self.append("items", {})
			price_list, price_list_currency = frappe.db.get_values(
				"Price List", {"selling": 1}, ["name", "currency"]
			)[0]
			args = {
				"doctype": "Sales Invoice",
				"item_code": checked_item["item"],
				"company": self.company,
				"customer": frappe.db.get_value("Patient", self.patient, "customer"),
				"selling_price_list": price_list,
				"price_list_currency": price_list_currency,
				"plc_conversion_rate": 1.0,
				"conversion_rate": 1.0,
			}
			item_details = get_item_details(args)
			item_line.item_code = checked_item["item"]
			item_line.qty = 1
			if checked_item["qty"]:
				item_line.qty = checked_item["qty"]
			if checked_item["rate"]:
				item_line.rate = checked_item["rate"]
			else:
				item_line.rate = item_details.price_list_rate
			item_line.amount = float(item_line.rate) * float(item_line.qty)
			if checked_item["income_account"]:
				item_line.income_account = checked_item["income_account"]
			if checked_item["dt"]:
				item_line.reference_dt = checked_item["dt"]
			if checked_item["dn"]:
				item_line.reference_dn = checked_item["dn"]
			if checked_item["description"]:
				item_line.description = checked_item["description"]
			if checked_item["dt"] == "Lab Test":
				lab_test = frappe.get_doc("Lab Test", checked_item["dn"])
				item_line.service_unit = lab_test.service_unit
				item_line.practitioner = lab_test.practitioner
				item_line.medical_department = lab_test.department

		self.set_missing_values(for_validate=True)

	@frappe.whitelist()
	def add_package_items(self, subscription):
		if not subscription:
			return

		subscription_doc = frappe.get_doc("Package Subscription", subscription)

		if subscription_doc.item_wise_invoicing:
			for row in subscription_doc.package_details:
				item_line = self.append("items", {})
				price_list, price_list_currency = frappe.db.get_values(
					"Healthcare Package", subscription_doc.healthcare_package, ["price_list", "currency"]
				)[0]
				args = {
					"doctype": "Sales Invoice",
					"item_code": row.item_code,
					"company": self.company,
					"customer": frappe.db.get_value("Patient", self.patient, "customer"),
					"selling_price_list": price_list,
					"price_list_currency": price_list_currency,
					"plc_conversion_rate": 1.0,
					"conversion_rate": 1.0,
				}
				item_details = get_item_details(args)
				item_line.item_code = row.item_code
				item_line.qty = 1
				if row.no_of_sessions:
					item_line.qty = row.no_of_sessions
				if row.rate:
					item_line.rate = row.rate
				else:
					item_line.rate = item_details.price_list_rate
				if row.amount_with_discount:
					item_line.amount = row.amount_with_discount
				item_line.rate = float(item_line.amount) / float(item_line.qty)
				if subscription_doc.income_account:
					item_line.income_account = subscription_doc.income_account
				if row.doctype:
					item_line.reference_dt = row.doctype
				if row.name:
					item_line.reference_dn = row.name

			self.set_missing_values(for_validate=True)
