import binascii
from datetime import date
from decimal import Decimal
from unittest import TestCase

from .paynow import (PayNowConfig, PayNowError, PROXY_MOBILE, build_payload, crc16, parse_fields,
                     parse_payload, qr_png_data_url)

COMPANY = PayNowConfig(proxy_value="201912345K", merchant_name="Test Drinks Pte Ltd")


class Crc16Tests(TestCase):
    def test_known_check_value(self):
        # the published check value for CRC-16/CCITT-FALSE
        self.assertEqual(crc16("123456789"), "29B1")

    def test_matches_standard_library(self):
        payload = build_payload(COMPANY, amount=Decimal("4.50"), reference="ORDER1")[:-4]
        self.assertEqual(crc16(payload), f"{binascii.crc_hqx(payload.encode(), 0xFFFF):04X}")


class PayloadTests(TestCase):
    def test_order_payload_fields(self):
        payload = build_payload(COMPANY, amount=Decimal("4.5"), reference="ORDER12",
                                expires_on=date(2026, 9, 25))
        fields = parse_payload(payload)
        self.assertEqual(fields["00"], "01")
        self.assertEqual(fields["01"], "12")       # dynamic: pay once
        self.assertEqual(fields["53"], "702")      # SGD
        self.assertEqual(fields["54"], "4.50")
        self.assertEqual(fields["58"], "SG")
        self.assertEqual(fields["59"], "Test Drinks Pte Ltd")
        self.assertEqual(fields["60"], "Singapore")
        self.assertEqual(parse_fields(fields["62"]), {"01": "ORDER12"})
        self.assertEqual(parse_fields(fields["26"]), {
            "00": "SG.PAYNOW", "01": "2", "02": "201912345K", "03": "0", "04": "20260925"})
        self.assertTrue(payload.endswith("6304" + crc16(payload[:-4])))

    def test_static_code_lets_customer_enter_amount(self):
        fields = parse_payload(build_payload(COMPANY))
        self.assertEqual(fields["01"], "11")
        self.assertNotIn("54", fields)
        self.assertEqual(parse_fields(fields["26"])["03"], "1")

    def test_mobile_number_proxy(self):
        config = PayNowConfig(proxy_type=PROXY_MOBILE, proxy_value="+6591234567", merchant_name="Stall")
        merchant = parse_fields(parse_payload(build_payload(config, amount=3))["26"])
        self.assertEqual((merchant["01"], merchant["02"]), ("0", "+6591234567"))

    def test_amount_is_rounded_to_cents(self):
        self.assertEqual(parse_payload(build_payload(COMPANY, amount="3.005"))["54"], "3.01")

    def test_long_names_are_trimmed(self):
        config = PayNowConfig(proxy_value="201912345K", merchant_name="A" * 40, merchant_city="B" * 20)
        fields = parse_payload(build_payload(config, amount=1))
        self.assertEqual((len(fields["59"]), len(fields["60"])), (25, 15))

    def test_rejects_bad_input(self):
        bad = [
            (PayNowConfig(proxy_value="", merchant_name="X"), {}),
            (PayNowConfig(proxy_value="91234567", merchant_name="X", proxy_type=PROXY_MOBILE), {}),
            (PayNowConfig(proxy_value="201912345K", merchant_name="X", proxy_type="9"), {}),
            (COMPANY, {"amount": 0}),
            (COMPANY, {"amount": -1}),
            (COMPANY, {"reference": "R" * 26}),
            (COMPANY, {"reference": "ORDER#1"}),
        ]
        for config, kwargs in bad:
            with self.subTest(config=config, kwargs=kwargs), self.assertRaises(PayNowError):
                build_payload(config, **kwargs)

    def test_tampered_payload_fails_checksum(self):
        payload = build_payload(COMPANY, amount=1)
        with self.assertRaises(PayNowError):
            parse_payload(payload.replace("1.00", "9.00"))


class QrImageTests(TestCase):
    def test_png_data_url(self):
        self.assertTrue(qr_png_data_url(build_payload(COMPANY, amount=1)).startswith("data:image/png;base64,"))
