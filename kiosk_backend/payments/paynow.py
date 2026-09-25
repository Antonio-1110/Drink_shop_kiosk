"""PayNow QR codes (SGQR), following the EMVCo merchant-presented QR format.

Plain Python with no Django dependency, so the kiosk's edge service can use it too. The company's
PayNow details come in through PayNowConfig; the Django backend builds one from settings
(see payments/config.py).

A payload is a string of TLV fields: 2-digit tag, 2-digit length, value. Field 26 carries the PayNow
details and the last field (63) is a CRC-16 checksum of everything before it.
"""
import base64
import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

PROXY_MOBILE = "0"  # a +65 mobile number registered with PayNow
PROXY_UEN = "2"     # a company's Unique Entity Number

MAX_AMOUNT = Decimal("9999999999.99")  # 13 characters, the EMVCo limit


class PayNowError(ValueError):
    pass


@dataclass(frozen=True)
class PayNowConfig:
    """The account a QR code pays. These are company credentials: keep them out of the code."""
    proxy_value: str                  # the UEN, or the mobile number as +6591234567
    merchant_name: str                # shown in the customer's banking app, 25 characters max
    proxy_type: str = PROXY_UEN
    merchant_city: str = "Singapore"  # 15 characters max
    merchant_category_code: str = "0000"

    def validate(self):
        if self.proxy_type not in (PROXY_UEN, PROXY_MOBILE):
            raise PayNowError(f"Unknown PayNow proxy type {self.proxy_type!r}; use {PROXY_UEN} (UEN) or {PROXY_MOBILE} (mobile).")
        if not self.proxy_value:
            raise PayNowError("PayNow is not configured: no UEN or mobile number set.")
        if self.proxy_type == PROXY_MOBILE and not re.fullmatch(r"\+65[89]\d{7}", self.proxy_value):
            raise PayNowError("A PayNow mobile number must look like +6591234567.")
        if not self.merchant_name:
            raise PayNowError("PayNow merchant name is empty.")
        if not re.fullmatch(r"\d{4}", self.merchant_category_code):
            raise PayNowError("Merchant category code must be 4 digits.")


def tlv(tag, value):
    value = str(value)
    if len(value) > 99:
        raise PayNowError(f"Field {tag} is longer than 99 characters.")
    return f"{tag}{len(value):02d}{value}"


def crc16(data):
    """CRC-16/CCITT-FALSE, the checksum SGQR requires as the last field."""
    crc = 0xFFFF
    for byte in data.encode():
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return f"{crc:04X}"


def format_amount(amount):
    amount = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount <= 0 or amount > MAX_AMOUNT:
        raise PayNowError(f"Amount {amount} is out of range.")
    return f"{amount:.2f}"


def build_payload(config, amount=None, reference="", editable=False, expires_on=None):
    """Returns the text a PayNow QR code encodes.

    amount:     the price in SGD; None lets the customer type any amount (a static QR).
    reference:  shows in the payment record so it can be matched to an order, 25 characters max.
    editable:   whether the customer may change the amount.
    expires_on: a date after which banking apps refuse the code.
    """
    config.validate()
    if len(reference) > 25:
        raise PayNowError("Reference is longer than 25 characters.")
    if not re.fullmatch(r"[A-Za-z0-9 \-_.]*", reference):
        raise PayNowError("Reference may only use letters, digits, spaces and - _ .")

    merchant = (tlv("00", "SG.PAYNOW")
                + tlv("01", config.proxy_type)
                + tlv("02", config.proxy_value)
                + tlv("03", "1" if editable or amount is None else "0"))
    if expires_on is not None:
        merchant += tlv("04", expires_on.strftime("%Y%m%d"))

    payload = (tlv("00", "01")
               # 12 = dynamic (one payment, amount fixed), 11 = static (reusable)
               + tlv("01", "11" if amount is None else "12")
               + tlv("26", merchant)
               + tlv("52", config.merchant_category_code)
               + tlv("53", "702"))  # SGD
    if amount is not None:
        payload += tlv("54", format_amount(amount))
    payload += (tlv("58", "SG")
                + tlv("59", config.merchant_name[:25])
                + tlv("60", config.merchant_city[:15]))
    if reference:
        payload += tlv("62", tlv("01", reference))
    payload += "6304"
    return payload + crc16(payload)


def parse_payload(payload):
    """Splits a payload back into {tag: value}, checking the CRC. Field 26 and 62 stay as strings;
    pass them to parse_fields to read their sub-fields."""
    if len(payload) < 8 or crc16(payload[:-4]) != payload[-4:]:
        raise PayNowError("PayNow payload checksum does not match.")
    return parse_fields(payload)


def parse_fields(data):
    fields, i = {}, 0
    while i < len(data):
        tag, length = data[i:i + 2], int(data[i + 2:i + 4])
        fields[tag] = data[i + 4:i + 4 + length]
        i += 4 + length
    return fields


def qr_png_data_url(payload, box_size=10):
    """The QR code as a PNG data: URL, ready for an <img src>."""
    import qrcode  # only needed for images, so the payload functions work without it
    img = qrcode.make(payload, box_size=box_size)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
