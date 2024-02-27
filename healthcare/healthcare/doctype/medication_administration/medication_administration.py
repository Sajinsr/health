# Copyright (c) 2023, healthcare and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from healthcare.healthcare.doctype.healthcare_settings.healthcare_settings import get_account
from healthcare.healthcare.utils import get_warehouse_from_service_unit


class MedicationAdministration(Document):
	def on_submit(self):
		if self.status == "Completed":
			make_stock_entry_for_nursing_task(self)

	def on_cancel(self):
		if self.medication_request and frappe.db.exists("Stock Entry Detail", {"medication_administration": self.name, "docstatus": 1}):
			stock_entry = frappe.db.get_value("Stock Entry Detail", {"medication_administration": self.name, "docstatus": 1}, "parent")
			if stock_entry:
				entry_doc = frappe.get_doc("Stock Entry", stock_entry)
				entry_doc.cancel()


def make_stock_entry_for_nursing_task(doc):
	""""
	Insert a material issue stock entry to consume items used in medication request with that date
	:params doc: Medication Administration doc to get relevent details
	"""
	if doc.inpatient_record and doc.medication_request:
		medication_request = frappe.get_doc("Medication Request", doc.medication_request)
		cost_center = frappe.get_cached_value("Company", doc.company, "cost_center")
		expense_account = get_account(None, "expense_account", "Healthcare Settings", doc.company)
		to_warehouse = get_warehouse_from_service_unit(
			medication_request.inpatient_record, doc.company
		)
		stock_entry = frappe.new_doc("Stock Entry")
		stock_entry.purpose = "Material Issue"
		stock_entry.set_stock_entry_type()
		stock_entry.from_warehouse = to_warehouse
		stock_entry.company = doc.company

		se_child = stock_entry.append("items")
		se_child.item_code = medication_request.medication_item
		se_child.item_name = frappe.db.get_value(
			"Item", medication_request.medication_item, "stock_uom"
		)
		se_child.uom = frappe.db.get_value(
			"Item", medication_request.medication_item, "stock_uom"
		)
		se_child.stock_uom = se_child.uom
		se_child.qty = doc.quantity
		se_child.t_warehouse = to_warehouse
		se_child.to_inpatient_record = doc.inpatient_record
		se_child.medication_request = medication_request.name
		# in stock uom
		se_child.conversion_factor = 1
		se_child.cost_center = cost_center
		se_child.expense_account = expense_account
		se_child.medication_administration = doc.name
		stock_entry.insert(ignore_permissions=True)
		stock_entry.submit()

		if stock_entry.name:
			frappe.msgprint(_(f"Stock Entry {frappe.bold(stock_entry.name)} created"), alert=True)
