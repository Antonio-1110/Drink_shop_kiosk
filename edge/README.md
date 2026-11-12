# Edge service

The Python program that runs on each shop's edge computer, between the cloud backend, the drink machine and the kiosk screen. It uses the standard library only (Python 3.11+), so there's nothing to install.

What it does, in a loop:

1. **Checks in** with the backend every minute with each module's state (`ok`, `low`, `empty`, `fault`). If check-ins stop, the backend closes the shop.
2. **Reads the fridge probes** every minute and sends the readings. A reading out of range, or a probe silent for 5 minutes, turns on the dairy lock here and at the backend. Only staff can clear it (untick **SFA locked** in `/admin`); the edge follows once the fridge is cold again.
3. **Takes paid orders** from the backend's work queue, makes each cup (cup drop, ice, toppings, liquids, seal, pickup slot), and reports READY, or FAILED with the reason so the order can be refunded. A failed cup goes to waste and is tried once more with a new cup, unless retrying can't help (no cups left).
4. **Serves the kiosk screen** on port 8080: the built UI from `kiosk-app/dist`, `/api/...` forwarded to the backend, and `GET /edge/status` (online, dairy lock, module states) for showing "temporarily closed".

When the backend can't be reached it finishes the drink in hand, keeps reading temperatures, and keeps every report in `edge-data/outbox.json` until the backend is back. If the edge stops in the middle of a drink, that order is reported FAILED when it starts again.

## Run it

With the backend running (`./dev.sh --backend --edge` does all of this for you):

```
cd kiosk_backend && python manage.py kiosk_key <machine ID>   # once; add the kiosk in /admin first
cd edge && KIOSK_KEY=<key> python -m edge_service
python -m edge_service --fault warm-fridge                    # try a fault (see below)
python -m edge_service --once                                 # one cycle, then stop
python -m edge_service --help                                 # every setting
```

Once a kiosk has a key, its shop only takes orders while the edge service is checking in.

| Setting | Default | |
| --- | --- | --- |
| `EDGE_BACKEND_URL` | `http://127.0.0.1:8000` | the cloud backend |
| `KIOSK_KEY` or `KIOSK_KEY_FILE` | | the machine's key; on a real kiosk use a file only root can read |
| `EDGE_DRIVER` | `simulator` | or a Python module with `build(**options)` returning a `Hardware` |
| `EDGE_FAULTS`, `EDGE_FAIL_RATE`, `EDGE_STEP_SECONDS` | none, 0, 0.5 | simulator only |
| `EDGE_DATA_DIR` | `./edge-data` | unsent reports |
| `EDGE_UI_DIR` | `../kiosk-app/dist` if built | the kiosk screen |
| `EDGE_HOST`, `EDGE_PORT` | `127.0.0.1`, `8080` | the screen's server |
| `EDGE_HEARTBEAT_SECONDS`, `EDGE_TEMPS_SECONDS`, `EDGE_POLL_SECONDS` | 60, 60, 3 | timings |

Simulator faults: `warm-fridge` (dairy lock), `probe-silent` (lock after 5 minutes), `out-of-cups` (every drink fails, no retry), `seal-jam` (each drink retried once, then fails).

## Plugging in real hardware

`edge_service/hardware/base.py` has one interface per module: `CupDispenser`, `IceDispenser`, `ToppingDispenser`, `LiquidDoser`, `Sealer`, `PickupSlots`, `TemperatureSensor`. A driver implements them and returns them as a `Hardware` from `build()`; `hardware/simulator.py` is the example. Then set `EDGE_DRIVER=your_package.driver`. Nothing else changes.

Each method returns when its step is done and raises `HardwareFault` when it isn't (with `retryable=False` when a new cup won't help). Amounts come in the ingredient's unit from the backend recipe (mL or g), and the driver maps each ingredient to its pump or hopper, usually by its code. Safety interlocks (e-stop, doors, motor limits) belong in the machine controller, not here.

## Code

| File | |
| --- | --- |
| `edge_service/service.py` | the loop: check-ins, temperatures, orders, status |
| `edge_service/maker.py` | turns a backend order into machine steps, with the retry |
| `edge_service/safety.py` | the local dairy lock |
| `edge_service/backend.py` | the backend's machine API |
| `edge_service/outbox.py` | reports kept on disk until sent |
| `edge_service/server.py` | kiosk screen, `/api` proxy, `/edge/status` |
| `edge_service/hardware/` | the interfaces and the simulator |

## Tests

```
cd edge && python -m unittest discover -s tests -t tests
```

These use the simulator and a pretend backend. `kiosk_backend/operation/test_edge_service.py` runs the real edge service against the real backend API. `./dev.sh --test` runs both, and so does CI.

## Not built yet

- Pickup: opening the right slot when a customer scans, and the cup-taken sensor (the backend marks COLLECTED; the machine confirm isn't built).
- Stock sensor levels, clean-in-place and waste reports (no backend API yet).
- Hiding single drinks when one module or ingredient is out (the backend gets module states but doesn't use them for the menu yet).
- Start-up self-test and the daily routine from the hardware spec.
- Running it as a service on the kiosk (systemd unit with a hardware watchdog).
