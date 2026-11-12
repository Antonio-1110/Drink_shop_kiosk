"""Hardware drivers. EDGE_DRIVER picks one:

- "simulator" (the default): pretend modules, see simulator.py.
- "package.module": any importable module with a build(**options) function returning a Hardware.
  That's how a real driver plugs in without changing the edge service.
"""
import importlib

from .base import (EMPTY, FAULT, LOW, OK, CupDispenser, Hardware, HardwareFault, IceDispenser, Ingredient,
                   LiquidDoser, PickupSlots, Sealer, TemperatureSensor, ToppingDispenser)

__all__ = ['EMPTY', 'FAULT', 'LOW', 'OK', 'CupDispenser', 'Hardware', 'HardwareFault', 'IceDispenser', 'Ingredient',
           'LiquidDoser', 'PickupSlots', 'Sealer', 'TemperatureSensor', 'ToppingDispenser', 'load_driver']


def load_driver(name='simulator', **options):
    if name == 'simulator':
        name = 'edge_service.hardware.simulator'
    module = importlib.import_module(name)
    hardware = module.build(**options)
    if not isinstance(hardware, Hardware):
        raise TypeError(f"{name}.build() must return a Hardware, got {type(hardware).__name__}")
    return hardware
