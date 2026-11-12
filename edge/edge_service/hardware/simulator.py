"""Pretend hardware: every module logs what it would do, and the fridge probes make up temperatures.

Faults to try (EDGE_FAULTS, comma separated):
    warm-fridge    probes read about 7 C, so the dairy lock comes on
    probe-silent   probes stop answering; after 5 minutes the edge locks dairy itself
    out-of-cups    no cup drops, so every drink fails without a retry
    seal-jam       every seal fails, so each drink is retried once and then fails
EDGE_FAIL_RATE (0 to 1) makes any step fail at random, as a retryable fault.
"""
import logging
import random
import time

from .base import (EMPTY, FAULT, OK, CupDispenser, Hardware, HardwareFault, IceDispenser, LiquidDoser,
                   PickupSlots, Sealer, TemperatureSensor, ToppingDispenser)

logger = logging.getLogger('edge.simulator')
FAULTS = {'warm-fridge', 'probe-silent', 'out-of-cups', 'seal-jam'}


class Sim:
    """Shared settings for the pretend modules."""
    def __init__(self, faults=(), fail_rate=0.0, step_seconds=0.0, rng=None, sleep=time.sleep):
        unknown = set(faults) - FAULTS
        if unknown:
            raise ValueError(f"Unknown simulator faults: {', '.join(sorted(unknown))}. Try {', '.join(sorted(FAULTS))}.")
        self.faults, self.fail_rate, self.step_seconds = set(faults), fail_rate, step_seconds
        self.rng, self.sleep = rng or random.Random(), sleep
        self.actions = []  # what happened, in order; tests read this

    def step(self, module, action):
        self.sleep(self.step_seconds)
        if self.fail_rate and self.rng.random() < self.fail_rate:
            raise HardwareFault(module, f"random fault during {action}")
        self.actions.append(f"{module}: {action}")
        logger.info("%s: %s", module, action)


class SimCups(CupDispenser):
    def __init__(self, sim):
        self.sim, self.on_line = sim, False

    def drop_cup(self, size):
        if 'out-of-cups' in self.sim.faults:
            raise HardwareFault(self.name, "no cups left", retryable=False)
        self.sim.step(self.name, f"drop {size} cup")
        self.on_line = True

    def discard_cup(self):
        if self.on_line:
            self.sim.actions.append("cups: cup to waste")
            logger.info("cups: cup to waste")
        self.on_line = False

    def state(self):
        return EMPTY if 'out-of-cups' in self.sim.faults else OK


class SimIce(IceDispenser):
    def __init__(self, sim):
        self.sim = sim

    def dispense_ice(self, grams):
        self.sim.step(self.name, f"{grams:g} g ice")


class SimToppings(ToppingDispenser):
    def __init__(self, sim):
        self.sim = sim

    def dispense_topping(self, ingredient, amount):
        self.sim.step(self.name, f"{amount:g} {ingredient.unit} {ingredient.name}")


class SimLiquids(LiquidDoser):
    def __init__(self, sim):
        self.sim = sim

    def dose(self, ingredient, amount):
        self.sim.step(self.name, f"{amount:g} {ingredient.unit} {ingredient.name}")


class SimSealer(Sealer):
    def __init__(self, sim):
        self.sim = sim

    def seal(self):
        if 'seal-jam' in self.sim.faults:
            raise HardwareFault(self.name, "seal failed")
        self.sim.step(self.name, "seal")

    def state(self):
        return FAULT if 'seal-jam' in self.sim.faults else OK


class SimPickup(PickupSlots):
    def __init__(self, sim, slots=6):
        self.sim, self.slots, self.held = sim, slots, {}  # slot -> order id

    def hold(self, order_id):
        free = next((s for s in range(1, self.slots + 1) if s not in self.held), None)
        if free is None:
            raise HardwareFault(self.name, "every pickup slot is full", retryable=False)
        self.held[free] = order_id
        self.sim.step(self.name, f"order {order_id} cup in slot {free}")
        return free

    def release_to_waste(self, order_id):
        for slot in [s for s, o in self.held.items() if o == order_id]:
            del self.held[slot]
            self.sim.actions.append(f"pickup: slot {slot} to waste")

    def collected(self, order_id):
        """The simulator has no cup-taken sensor, so this stands in for a customer taking the cups."""
        self.held = {s: o for s, o in self.held.items() if o != order_id}


class SimTemperatures(TemperatureSensor):
    def __init__(self, sim):
        self.sim = sim

    def read(self, ingredient):
        if 'probe-silent' in self.sim.faults:
            return None
        base = 7.0 if 'warm-fridge' in self.sim.faults else 3.0
        return round(base + self.sim.rng.uniform(-0.4, 0.4), 1)

    def state(self):
        return FAULT if 'probe-silent' in self.sim.faults else OK


def build(faults=(), fail_rate=0.0, step_seconds=0.0, rng=None, sleep=time.sleep):
    sim = Sim(faults, fail_rate, step_seconds, rng, sleep)
    hardware = Hardware(cups=SimCups(sim), ice=SimIce(sim), toppings=SimToppings(sim), liquids=SimLiquids(sim),
                        sealer=SimSealer(sim), pickup=SimPickup(sim), temperatures=SimTemperatures(sim))
    hardware.sim = sim
    return hardware
