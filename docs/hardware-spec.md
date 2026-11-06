# Autonomous tea shop hardware spec

Draft, 6 Nov 2026. The editable version lives in Claude Docs: https://claude.ai/artifact/NEbT8XGmGy2NpswZawoaZ6 (this file is a snapshot).

## Summary

One unstaffed unit makes a 360 mL (small) or 500 mL (large) bubble tea in about 60 to 90 seconds, takes cashless payment, and hands the sealed cup to the customer after a QR scan or 6-digit PIN. Staff visit once or twice a day to restock, clean and empty waste.

Every requirement is tied to what the software already does: the Django backend, the kiosk touch UI, the phone app, and the edge service still to be written (issue #40).

The shop runs as five parts:

1. **Ordering station**: touchscreen, kiosk computer, QR scanner, payment terminal.
2. **Drink machine**: cup drop, tea brewing, liquid dosing, pearls, ice, sealing, delivery to pickup.
3. **Cold storage**: chiller with temperature probes that lock dairy drinks above 4 °C.
4. **Edge controller**: one computer running the edge service that drives the machine and talks to the backend.
5. **Site services**: power, water in and out, network, CCTV.

Prices, models and regulator details are from memory and approximate. Check each one with the supplier or agency before ordering.

## Open decisions

| # | Decision | Options | Suggestion |
| --- | --- | --- | --- |
| 1 | Buy or build the drink machine | Buy a commercial automated tea machine and integrate it; build from parts; hybrid | Buy a commercial dosing/sealing core with an open control interface, build the edge service around it |
| 2 | Site type | Indoor kiosk in a mall or MRT; standalone vending unit; small shopfront | Indoor kiosk |
| 3 | Pearls | Cook fresh on site; ready-to-use packaged pearls | Packaged ready-to-use pearls first |
| 4 | Fresh milk or UHT/creamer | Fresh dairy (needs the 4 °C lock); UHT or non-dairy creamer | Support fresh milk, keep a UHT fallback |
| 5 | Payment terminal | Acquirer terminal (NETS, card, PayNow, GrabPay); screen QR only | One unattended acquirer terminal plus on-screen SGQR; can wait |
| 6 | Pickup design | Single window; carousel or lockers | Window plus 4 to 6 holding slots |
| 7 | When a phone pre-order starts | As soon as paid; when the customer scans | Start on scan |
| 8 | Network backup | Fibre/Wi-Fi only; plus 4G/5G router | Add 4G failover |
| 9 | Shop name and branding | Still "Tea House" placeholder | Needed for cabinet wrap and licences |

## Ordering station

| Part | Requirement | Why the software needs it |
| --- | --- | --- |
| Touchscreen | 21.5" to 27", portrait, 1080 × 1920+, projected capacitive, 10-point, 350+ nits, anti-glare tempered glass (IK07+) | UI is laid out for a portrait kiosk |
| Kiosk computer | Fanless x86/ARM, 8 GB RAM, 128 GB SSD, Linux, Chromium kiosk mode, watchdog | Runs the React kiosk UI |
| QR scanner | 2D imager reading QR from phone screens, USB HID keyboard-wedge | Collect screen and Drink designer already accept keyboard-wedge scans |
| Payment terminal | Unattended card and QR terminal (see Payments) | Checkout uses one provider class per method |
| Speaker | Prompts and "drink ready" chime | Optional, accessibility |
| Enclosure | Lockable, ventilated, touch area about 0.9 to 1.2 m from floor | Accessibility, tamper resistance |

The 1-minute idle timeout is in software, so no presence sensor is needed.

## Drink machine

Makes any recipe the backend sends, one cup at a time, in 90 s or less, and reports each order as PREPARING, READY or FAILED. A drink is a list of ingredients in mL, worked out from size (360 or 500 mL liquid), sugar level and ice level (0/25/50/75/100%).

Stations in order: cup drop → ice → toppings → liquids → sealing → handoff to pickup.

| Module | Requirement |
| --- | --- |
| Cup dispenser | 2 sizes (about 500 and 700 mL PP cups, 90/95 mm rim), 150+ cups per size, cup-present sensor, jam detection |
| Tea brewing | Hot water 85 to 98 °C, 2 to 4 tea bases, batch brew to chilled holding tanks, holding time limit (e.g. 4 h) with auto discard |
| Liquid dosing | 8 to 16 channels, peristaltic or gear pumps with flow meters, ±3% or 2 mL, handles viscosity ratings 1 to 4 |
| Sweetener | Dedicated syrup channel, 30 mL (small) / 40 mL (large) at 100% sugar, linear to 0% |
| Toppings | 2 to 4 hoppers, portion by weight or volume |
| Pearl cooker (optional) | Auto cooker 1 to 2 kg/batch with timer and discard logging, only if decision 3 picks fresh cooking |
| Ice | Ice maker 80 to 150 kg/day, dispense by weight |
| Sealer | Auto film sealer, film-out and jam sensors, 3 to 5 s per cup |
| Cleaning | Clean-in-place cycle, logged (backend field `last_cip_cleaned_at`) |
| Waste | Drip tray, drain or waste tank with level sensor |

Every fault must stop that order and report FAILED with a reason; staff retry or refund from the admin.

## Cold storage and the dairy lock

The backend already locks the kiosk (`sfa_locked`) when a reading falls outside an ingredient's safe range.

- **Chiller**: built-in commercial fridge holding 1 to 4 °C; chilled dosing lines run from inside it.
- **Probes**: one food-grade probe per chilled container or zone, ±0.5 °C, digital (e.g. DS18B20 or PT100), in a liquid buffer next to the milk.
- **Reading rate**: at least once a minute locally, to the backend at least every 5 minutes, immediately when out of range.
- **Door sensor** on the chiller.
- **Failsafe**: no probe reading for 5 minutes = out of range; stop dairy drinks locally even without network.
- **Unlock**: staff only, from the admin.

Software gap: no API yet for the machine to send readings (issues #30, #42).

## Ingredient stock sensing

Sensors cross-check the backend's order-based stock count and warn before something runs dry.

| What | Sensor | Target |
| --- | --- | --- |
| Liquid containers | Load cell under each container | ±20 g |
| Topping hoppers | Load cell or ultrasonic level | ±5% |
| Cups | Stack sensor per size | warn at 20 cups |
| Sealing film | Roll-end sensor | warn at about 50 seals |
| Ice bin | Level sensor | low-ice warning |
| Water tank (if no mains) | Level sensor | low-water lock |
| Waste tank | Level sensor | full-tank lock |

## Payments

Payments are on hold in software; this fixes what to ask acquirers for.

- Unattended terminal: contactless card, NETS, SGQR (PayNow, GrabPay, wallets), PCI PTS unattended, with an API/SDK.
- Server-to-server webhooks (backend route `/checkout/webhooks/<method>/` exists).
- On-screen PayNow SGQR already works without a terminal.
- Refunds by API.
- No cash.

## Pickup

Customer scans the order QR or types the 6-digit PIN; backend marks COLLECTED; machine opens the right slot.

- Motorised window that opens only for the matching order, cup-taken sensor, pinch protection.
- 4 to 6 holding slots with cup-present sensors and lights.
- Scanner at the window.
- Uncollected cups moved to waste after a set time (issue #60).

## Edge controller, network and power

| Part | Requirement |
| --- | --- |
| Edge computer | Industrial fanless PC, 8 GB RAM, 64 GB+ SSD, Linux, hardware watchdog, 2+ Ethernet, 4+ USB |
| Machine control | PLC or microcontrollers over Modbus/CAN/serial; e-stop cuts motor power directly |
| Kiosk key | Sent as `Authorization: Kiosk <key>`, stored in a protected file |
| Clock | NTP sync |
| Network | Ethernet/Wi-Fi primary, 4G/5G failover, 10+ Mbit/s, outbound HTTPS only |
| Remote access | VPN or outbound-only management |
| Power | Separate 230 V circuits for cold, heat and electronics; estimate 4 to 8 kW peak |
| UPS | 10+ minutes for computers and network |
| Water | Mains with filter and regulator, or tank with level sensor |
| Security | Locked panels with door switches, CCTV, tamper alerts |

Offline: finish PAID orders, keep logging temperatures, send on reconnect; no new orders.

## Singapore rules to plan for (unverified, confirm with agencies)

| Area | Agency | Hardware impact |
| --- | --- | --- |
| Food licence | SFA | Food shop or vending machine licence; food-contact materials, cleaning access, temperature control |
| Food hygiene staff | SFA | Food Safety course for staff; possibly a Food Hygiene Officer |
| Nutri-Grade | HPB / MOH | C and D drinks show the mark at point of sale (kiosk already does this); D can't be advertised |
| Electrical work | EMA | Licensed electrical worker; RCD on wet circuits |
| Electrical products | Enterprise Singapore | Safety Mark for some appliances; IEC 60335 report for commercial units |
| Water fittings | PUB | Licensed plumber, approved fittings, backflow prevention |
| Fire safety | SCDF / landlord | Meet the building's fire safety plan |
| Payments | MAS | Use a licensed acquirer |
| CCTV and data | PDPC | CCTV notices, retention limits |

## What the machine must report to the backend

| Message | When | Backend today |
| --- | --- | --- |
| Order progress PREPARING / READY / FAILED + reason | Start, cup ready, fault | Built: `POST /ordering/orders/<id>/progress/` |
| Temperature per chilled ingredient | 1 to 5 min, at once when out of range | Model and lock built; API missing (#30, #42) |
| Heartbeat + machine status | Every minute | `last_heartbeat` field; API missing |
| Sensor stock levels | Every few minutes, after refills | Not built |
| Clean-in-place done | After each cycle | `last_cip_cleaned_at` field; API missing |
| Pickup slot opened, cup taken | After valid QR/PIN | Backend marks COLLECTED; machine confirm not built |
| Fault and tamper alerts | When they happen | Not built |

The machine also needs to fetch the next order's recipe; that queue is part of the edge service (#40).

## Next steps

- [ ] Answer the open decisions, starting with 1 and 2
- [ ] Ask SFA which licence fits the site
- [ ] Quotes from 2 or 3 automated tea machine makers with a control API
- [ ] Ask 2 acquirers for an unattended SGQR/card/NETS terminal with webhook and refund APIs
- [ ] Build temperature, heartbeat and CIP APIs (#30, #42)
- [ ] Start the edge service against a simulated machine (#40)
