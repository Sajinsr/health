config = {
	"authorization": {"method": "POST", "url": "/api/hiecm/gateway/v3/sessions", "encrypted": False},
	"auth_cert": {
		"method": "GET",
		"url": "/abha/api/v3/profile/public/certificate",
		"encrypted": False,
	},
	"verify_abha_address": {
		"method": "POST",
		"url": "/abha/api/v3/phr/web/login/abha/search",
		"encrypted": False,
	},
	"verify_abha_number": {
		"method": "POST",
		"url": "/abha/api/v3/profile/login/request/otp",
		"encrypted": True,
	},
	"verify_abha_number_otp": {
		"method": "POST",
		"url": "/abha/api/v3/profile/login/verify",
		"encrypted": True,
	},
	"send_abha_address_otp": {
		"method": "POST",
		"url": "/abha/api/v3/phr/web/login/abha/request/otp",
		"encrypted": True,
	},
	"verify_abha_address_otp": {
		"method": "POST",
		"url": "/abha/api/v3/phr/web/login/abha/verify",
		"encrypted": True,
	},
	"generate_aadhaar_otp": {
		"method": "POST",
		"url": "/abha/api/v3/enrollment/request/otp",
		"encrypted": True,
	},
	"create_abha_w_aadhaar": {
		"method": "POST",
		"url": "/abha/api/v3/enrollment/enrol/byAadhaar",
		"encrypted": True,
	},
	"get_card": {
		"method": "GET",
		"url": "/abha/api/v3/phr/web/login/profile/abha/phr-card",
		"encrypted": False,
	},
	"get_account_card": {
		"method": "GET",
		"url": "/abha/api/v3/profile/account/abha-card",
		"encrypted": False,
	},
	"get_profile": {
		"method": "GET",
		"url": "/abha/api/v3/phr/web/login/profile/abha-profile",
		"encrypted": False,
	},
	"get_account_profile": {
		"method": "GET",
		"url": "/abha/api/v3/profile/account",
		"encrypted": False,
	},
	"hiecm_session": {"method": "POST", "url": "/gateway/v3/sessions", "encrypted": False},
	"update_bridge": {"method": "PATCH", "url": "/gateway/v3/bridge/url", "encrypted": False},
	"register_bridge": {
		"method": "POST",
		"url": "/v1/bridges/MutipleHRPAddUpdateServices",
		"encrypted": False,
	},
	"find_bridge_by_service_id": {
		"method": "GET",
		"url": "/gateway/v3/bridge-service/serviceId",
		"encrypted": False,
	},
	"find_services_by_bridge_id": {
		"method": "GET",
		"url": "/gateway/v3/bridge-services",
		"encrypted": False,
	},
	"hip_generate_token": {"method": "POST", "url": "/v3/token/generate-token", "encrypted": False},
	"link_carecontext": {"method": "POST", "url": "/hip/v3/link/carecontext", "encrypted": False},
	"link_carecontext_notify": {
		"method": "POST",
		"url": "hip/v3/link/context/notify",
		"encrypted": False,
	},
}


def get_url(key):
	return config.get(key)
