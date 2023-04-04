import frappe


def execute():
	si = frappe.qb.DocType("Sales Invoice")
	sii = frappe.qb.DocType("Sales Invoice Item")
	patient = frappe.qb.DocType("Patient")

	registered_patients = (
		frappe.qb.from_(si)
		.left_join(sii)
		.on(si.name == sii.parent)
		.left_join(patient)
		.on(si.customer == patient.customer)
		.select((patient.name).as_("patient"), (si.posting_date).as_("valid_from"), (si.name).as_("sales_invoice"), (sii.amount).as_("amount"))
		.where((si.docstatus == 1) & (sii.item_name.like("%Registration Fee%")))
		.orderby(patient.name)
		.orderby(si.posting_date, order=frappe.qb.desc)
		.run(as_dict=True)
	)

	if registered_patients:
		for i in registered_patients:
			if not frappe.db.exists("Registration Validity", 
		       	{
					"patient": i.patient,
					"amount": i.amount,
					"docstatus": 1
				}
			):
				registration = frappe.new_doc("Registration Validity")
				registration.patient = i.patient
				registration.valid_from = i.valid_from
				registration.sales_invoice_reference = i.sales_invoice
				registration.amount = i.amount
				registration.status = "Active"
				registration.insert()
				registration.submit()
