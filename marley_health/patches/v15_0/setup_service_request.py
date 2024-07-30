from __future__ import unicode_literals

import frappe

from marley_health.setup import setup_service_request_masters


def execute():
	frappe.reload_doc("marley_health", "doctype", "Patient Care Type")

	setup_service_request_masters()

	frappe.reload_doc("accounts", "doctype", "sales_invoice")
	frappe.reload_doc("accounts", "doctype", "sales_invoice_item")
