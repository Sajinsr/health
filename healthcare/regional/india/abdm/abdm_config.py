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
	# "get_suggestions": {
	# 	"method": "GET",
	# 	"url": "/abha/api/v3/enrollment/enrol/suggestion",
	# 	"encrypted": False,
	# },
	# "resend_aadhaar_otp": {
	# 	"method": "POST",
	# 	"url": "/v2/registration/aadhaar/resendAadhaarOtp",
	# 	"encrypted": False,
	# },
	# "prefered_abha": {
	# 	"method": "POST",
	# 	"url": "/abha/api/v3/enrollment/enrol/abha-address",
	# 	"encrypted": False,
	# },
}


def get_url(key):
	return config.get(key)
