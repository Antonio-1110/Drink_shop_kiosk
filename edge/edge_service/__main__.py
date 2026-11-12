"""Run the edge service:  python -m edge_service  (from the edge/ folder)

Settings come from environment variables, and the flags below override them:

    EDGE_BACKEND_URL     the cloud backend (default http://127.0.0.1:8000)
    KIOSK_KEY            this machine's key from `manage.py kiosk_key <machine_id>`, or
    KIOSK_KEY_FILE       a file holding it (better on a real kiosk: chmod 600)
    EDGE_DRIVER          "simulator" (default) or a module with build(**options) returning a Hardware
    EDGE_FAULTS          simulator faults, comma separated (see hardware/simulator.py)
    EDGE_FAIL_RATE       simulator: chance any step fails, 0 to 1
    EDGE_STEP_SECONDS    simulator: how long each step takes (default 0.5)
    EDGE_DATA_DIR        where unsent reports are kept (default ./edge-data)
    EDGE_UI_DIR          the built kiosk UI (default ../kiosk-app/dist when it exists)
    EDGE_HOST, EDGE_PORT the kiosk screen's server (default 127.0.0.1:8080)
    EDGE_HEARTBEAT_SECONDS, EDGE_TEMPS_SECONDS, EDGE_POLL_SECONDS   timings (60, 60, 3)
"""
import argparse
import logging
import os
import sys
import threading

from .backend import BackendClient
from .hardware import load_driver
from .outbox import Outbox
from .server import serve
from .service import EdgeService

HERE = os.path.dirname(os.path.abspath(__file__))


def env(name, default=None):
    value = os.environ.get(name, '')
    return value if value != '' else default


def read_key(args):
    if args.key:
        return args.key.strip()
    if env('KIOSK_KEY_FILE'):
        with open(env('KIOSK_KEY_FILE')) as f:
            return f.read().strip()
    return ''


def parse(argv):
    default_ui = os.path.join(HERE, '..', '..', 'kiosk-app', 'dist')
    p = argparse.ArgumentParser(prog='edge_service', description="The kiosk's edge service: drives the drink machine "
                                "from the backend's work queue and serves the kiosk screen.")
    p.add_argument('--backend', default=env('EDGE_BACKEND_URL', 'http://127.0.0.1:8000'))
    p.add_argument('--key', default=env('KIOSK_KEY', ''), help="The kiosk key (or KIOSK_KEY / KIOSK_KEY_FILE).")
    p.add_argument('--driver', default=env('EDGE_DRIVER', 'simulator'))
    p.add_argument('--fault', action='append', default=[f for f in env('EDGE_FAULTS', '').split(',') if f],
                   help="Simulator fault; repeat for more.")
    p.add_argument('--fail-rate', type=float, default=float(env('EDGE_FAIL_RATE', 0)))
    p.add_argument('--step-seconds', type=float, default=float(env('EDGE_STEP_SECONDS', 0.5)))
    p.add_argument('--data-dir', default=env('EDGE_DATA_DIR', 'edge-data'))
    p.add_argument('--ui-dir', default=env('EDGE_UI_DIR', default_ui if os.path.isdir(default_ui) else None))
    p.add_argument('--host', default=env('EDGE_HOST', '127.0.0.1'))
    p.add_argument('--port', type=int, default=int(env('EDGE_PORT', 8080)))
    p.add_argument('--no-ui', action='store_true', help="Don't serve the kiosk screen.")
    p.add_argument('--heartbeat-seconds', type=float, default=float(env('EDGE_HEARTBEAT_SECONDS', 60)))
    p.add_argument('--temps-seconds', type=float, default=float(env('EDGE_TEMPS_SECONDS', 60)))
    p.add_argument('--poll-seconds', type=float, default=float(env('EDGE_POLL_SECONDS', 3)))
    p.add_argument('--maintenance', action='store_true', help="Check in as MAINTENANCE: the shop closes, nothing is made.")
    p.add_argument('--once', action='store_true', help="Run one cycle (check in, temperatures, make what's waiting) and stop.")
    p.add_argument('-v', '--verbose', action='store_true')
    return p.parse_args(argv)


def main(argv=None):
    args = parse(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format='%(asctime)s %(levelname)-7s %(name)s: %(message)s')
    log = logging.getLogger('edge')
    key = read_key(args)
    if not key:
        log.error("No kiosk key. Make one with `python manage.py kiosk_key <machine_id>` and pass --key, "
                  "KIOSK_KEY or KIOSK_KEY_FILE.")
        return 2
    options = {}
    if args.driver == 'simulator':
        options = {'faults': args.fault, 'fail_rate': args.fail_rate, 'step_seconds': args.step_seconds}
    hardware = load_driver(args.driver, **options)
    os.makedirs(args.data_dir, exist_ok=True)
    outbox = Outbox(os.path.join(args.data_dir, 'outbox.json'))
    service = EdgeService(BackendClient(args.backend, key), hardware, outbox, heartbeat_every=args.heartbeat_seconds,
                          temps_every=args.temps_seconds)
    service.maintenance = args.maintenance
    log.info("Edge service: backend %s, driver %s%s", args.backend, args.driver,
             f" (faults: {', '.join(args.fault)})" if args.fault else "")
    if args.once:
        made = service.tick()
        log.info("Made %d order(s): %s", len(made), made)
        return 0 if service.online else 1
    if not args.no_ui:
        httpd = serve(args.host, args.port, args.backend, args.ui_dir, service.status)
        threading.Thread(target=httpd.serve_forever, daemon=True, name='kiosk-ui').start()
        log.info("Kiosk screen: http://%s:%d%s", args.host, args.port,
                 "" if args.ui_dir else " (no built UI found: /api and /edge/status only)")
    stop = threading.Event()
    try:
        service.run(stop, poll_every=args.poll_seconds)
    except KeyboardInterrupt:
        log.info("Stopping")
    return 0


if __name__ == '__main__':
    sys.exit(main())
