# Copyright (c) 2025, earthians Health Informatics Pvt. Ltd. and contributors
# For license information, please see license.txt


def render_patient_html(resource: dict) -> str:
	"""html render for Patient resource by chatGPT"""
	if resource.get("resourceType") != "Patient":
		return "<div class='text-danger'>Unsupported resourceType for HTML rendering</div>"

	def badge(text, color):
		return f"<span class='badge badge-{color}'>{text}</span>"

	active = badge("Yes", "success") if resource.get("active") else badge("No", "secondary")
	gender = badge(resource.get("gender", "").lower(), "info")
	deceased = badge("Yes", "danger") if resource.get("deceasedBoolean") else badge("No", "secondary")
	multiple_birth = (
		badge("Yes", "info") if resource.get("multipleBirthBoolean") else badge("No", "secondary")
	)
	birth_date = resource.get("birthDate", "")

	# Contact
	contact = resource.get("contact", [])
	contact_html = ""
	for c in contact:
		name = c.get("name", {}).get("text") if isinstance(c.get("name"), dict) else c.get("name", "")
		gender_c = badge(c.get("gender", "").lower(), "info")
		contact_html += f"""
            <div class="ml-3 mb-2">
              <div><span class="text-gray-700">Name:</span> <span class="text-gray-800">{name}</span></div>
              <div><span class="text-gray-700">Gender:</span> {gender_c}</div>
            </div>
        """

	# Communication
	comm = resource.get("communication", [])
	comm_html = ""
	for c in comm:
		lang = (
			c.get("language", {}).get("coding", [{}])[0].get("code")
			if isinstance(c.get("language"), dict)
			else c.get("language", "")
		)
		comm_html += f"""<div class="ml-3"><span class="text-gray-700">Language:</span> {badge(lang, "primary")}</div>"""

	# Link
	link = resource.get("link", [])
	link_html = ""
	for l in link:
		ref = (
			l.get("other", {}).get("reference") if isinstance(l.get("other"), dict) else l.get("other", "")
		)
		typ = l.get("type", "")
		link_html += f"""
            <div class="ml-3">
              <div><span class="text-gray-700">Reference:</span> <span class="text-gray-800">{ref}</span></div>
              <div><span class="text-gray-700">Type:</span> {badge(typ, "warning")}</div>
            </div>
        """

	return f"""
    <div class="fhir-resource border rounded p-4 bg-gray-50 text-sm font-sans">
      <h2 class="text-lg font-semibold mb-3">Patient: <span class="text-gray-800">{resource.get("id")}</span></h2>
      <div class="mb-2"><span class="font-semibold text-gray-700">Active:</span> {active}</div>
      <div class="mb-2"><span class="font-semibold text-gray-700">Gender:</span> {gender}</div>
      <div class="mb-2"><span class="font-semibold text-gray-700">Birth Date:</span> <span class="text-gray-800">{birth_date}</span></div>
      <div class="mb-2"><span class="font-semibold text-gray-700">Deceased:</span> {deceased}</div>
      <div class="mb-2"><span class="font-semibold text-gray-700">Multiple Birth:</span> {multiple_birth}</div>

      <hr class="my-4 border-gray-300" />

      <div class="mb-4">
        <h3 class="font-semibold text-gray-600 mb-1">Contact</h3>
        {contact_html}
      </div>

      <div class="mb-4">
        <h3 class="font-semibold text-gray-600 mb-1">Communication</h3>
        {comm_html}
      </div>

      <div class="mb-2">
        <h3 class="font-semibold text-gray-600 mb-1">Link</h3>
        {link_html}
      </div>
    </div>
    """
