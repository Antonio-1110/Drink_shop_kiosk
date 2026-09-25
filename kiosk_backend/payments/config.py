from django.conf import settings
from .paynow import PayNowConfig, PROXY_MOBILE, PROXY_UEN

PROXY_TYPES = {"UEN": PROXY_UEN, "MOBILE": PROXY_MOBILE}


def paynow_config_from_settings():
    # the PAYNOW_* settings come from environment variables; see the README
    return PayNowConfig(
        # an unknown name is passed through so PayNowConfig.validate reports it
        proxy_type=PROXY_TYPES.get(settings.PAYNOW_PROXY_TYPE.upper(), settings.PAYNOW_PROXY_TYPE),
        proxy_value=settings.PAYNOW_PROXY_VALUE,
        merchant_name=settings.PAYNOW_MERCHANT_NAME,
        merchant_city=settings.PAYNOW_MERCHANT_CITY,
        merchant_category_code=settings.PAYNOW_MERCHANT_CATEGORY_CODE,
    )
