import frappe


def skip_auth_for_abdm_callbacks():
	path = frappe.request.path

	if path.startswith("/abdm/callback"):
		hip_id = frappe.request.headers.get("x-hip-id")
		exists = frappe.db.exists(
			"ABDM Settings",
			{
				"facility_id": hip_id,
				"default": 1,
				"user_api_key": ["is", "set"],
				"user_api_secret": ["is", "set"],
			},
		)
		if exists:
			api_key, api_secret = frappe.get_cached_value(
				"ABDM Settings", exists, ["user_api_key", "user_api_secret"]
			)
			frappe.request.environ["HTTP_AUTHORIZATION"] = f"token {api_key}:{api_secret}"
