"""What the edge service needs from the machine, as one interface per module.

A real driver (PLC over Modbus, microcontrollers over serial, ...) implements these classes and is
picked with EDGE_DRIVER. The simulator in simulator.py implements them with logging and made-up
readings, so everything above this layer runs and is tested without hardware.

Rules every driver follows:

- A method returns when the step is done. Anything that goes wrong raises HardwareFault, with
  retryable=False when trying again with a new cup can't help (an empty cup stack, a door open).
- Amounts come in the ingredient's own unit from the backend recipe (mL or g).
- state() says how the module is right now: "ok", "low", "empty" or "fault". It goes to the backend
  with every check-in, so staff see it on the dashboard.
- Safety interlocks (e-stop, door switches, motor limits) live in the machine controller, not here.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

OK, LOW, EMPTY, FAULT = 'ok', 'low', 'empty', 'fault'


@dataclass(frozen=True)
class Ingredient:
    """One ingredient as the backend names it. Drivers map it to a channel or hopper, usually by code."""
    id: int
    code: str | None
    name: str
    unit: str = 'mL'


class HardwareFault(Exception):
    def __init__(self, module, message, retryable=True):
        super().__init__(f"{module}: {message}")
        self.module, self.message, self.retryable = module, message, retryable


class Module(ABC):  # noqa: B024 - state() has a default; the subclasses are abstract
    name = 'module'

    def state(self):
        return OK


class CupDispenser(Module):
    name = 'cups'

    @abstractmethod
    def drop_cup(self, size):
        """Put an empty cup of this size ("Small"/"Large") under the line. Raises if no cup arrived."""

    @abstractmethod
    def discard_cup(self):
        """Send the cup on the line (if any) to waste. Must not raise: it runs after faults."""


class IceDispenser(Module):
    name = 'ice'

    @abstractmethod
    def dispense_ice(self, grams):
        """Add this much ice, by weight."""


class ToppingDispenser(Module):
    name = 'toppings'

    @abstractmethod
    def dispense_topping(self, ingredient, amount):
        """Add a topping (pearls, jelly) in its unit, usually g."""


class LiquidDoser(Module):
    name = 'liquids'

    @abstractmethod
    def dose(self, ingredient, amount):
        """Pump a liquid (tea, milk, syrup) in its unit, usually mL. Raises if the measured dose is
        more than 5% off or the channel ran dry."""


class Sealer(Module):
    name = 'sealer'

    @abstractmethod
    def seal(self):
        """Seal the cup with film. Raises on film out or jam."""


class PickupSlots(Module):
    name = 'pickup'

    @abstractmethod
    def hold(self, order_id):
        """Move the finished cup into a free pickup slot kept for this order. Returns the slot number."""

    @abstractmethod
    def release_to_waste(self, order_id):
        """Send every cup held for this order to waste (the order failed part way)."""


class TemperatureSensor(Module):
    name = 'temperatures'

    @abstractmethod
    def read(self, ingredient):
        """Degrees C of the probe next to this chilled ingredient, or None if the probe didn't answer."""


@dataclass
class Hardware:
    """Everything the edge service drives. A driver's build() returns one of these."""
    cups: CupDispenser
    ice: IceDispenser
    toppings: ToppingDispenser
    liquids: LiquidDoser
    sealer: Sealer
    pickup: PickupSlots
    temperatures: TemperatureSensor

    def modules(self):
        return [self.cups, self.ice, self.toppings, self.liquids, self.sealer, self.pickup, self.temperatures]

    def module_states(self):
        states = {}
        for module in self.modules():
            try:
                states[module.name] = module.state()
            except Exception:  # a module that can't say how it is counts as broken
                states[module.name] = FAULT
        return states
