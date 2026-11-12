"""Turns a backend order into machine steps and runs them.

Each cup goes: cup drop -> ice -> toppings -> liquids -> seal -> pickup slot (the order in the
hardware spec). If a step fails, the cup goes to waste and the drink is tried once more with a new
cup, unless the fault says a retry can't help. If a cup still fails, cups already made for the order
go to waste too and the whole order is reported FAILED, so the backend refunds it.
"""
import logging
from dataclasses import dataclass, field

from .hardware import HardwareFault, Ingredient

logger = logging.getLogger('edge.maker')


def is_ice(line):
    """The backend's recipe doesn't flag ice, so it's found by name ("Ice", "Crushed ice")."""
    return 'ice' in (line.get('name') or '').lower().split() and line['kind'] != 'TOPPING'


def steps(item):
    """The machine steps for one cup of a backend job item, as (step, ingredient, amount)."""
    plan = [('cup', None, item['size'])]
    lines = [line for line in item['lines'] if float(line['amount']) > 0]
    for line in lines:
        if is_ice(line):
            plan.append(('ice', None, float(line['amount'])))
    for want in ('TOPPING', 'LIQUID'):
        for line in lines:
            # sweetener and other non-ice extras (kind OTHER) are pumped like liquids
            kind = 'LIQUID' if line['kind'] == 'OTHER' else line['kind']
            if kind == want and not is_ice(line):
                ingredient = Ingredient(line['ingredient'], line.get('code'), line['name'], line.get('unit') or 'mL')
                plan.append(('topping' if want == 'TOPPING' else 'liquid', ingredient, float(line['amount'])))
    plan.append(('seal', None, None))
    return plan


@dataclass
class Result:
    ok: bool
    reason: str = ''
    slots: list = field(default_factory=list)


class Maker:
    def __init__(self, hardware, retries=1):
        self.hw, self.retries = hardware, retries

    def run(self, step, ingredient, amount):
        hw = self.hw
        if step == 'cup':
            hw.cups.drop_cup(amount)
        elif step == 'ice':
            hw.ice.dispense_ice(amount)
        elif step == 'topping':
            hw.toppings.dispense_topping(ingredient, amount)
        elif step == 'liquid':
            hw.liquids.dose(ingredient, amount)
        elif step == 'seal':
            hw.sealer.seal()

    def make_cup(self, order_id, item):
        """Makes one cup into a pickup slot. Returns the slot. Raises HardwareFault after the retries."""
        plan = steps(item)
        for attempt in range(self.retries + 1):
            try:
                for step in plan:
                    self.run(*step)
                return self.hw.pickup.hold(order_id)
            except HardwareFault as fault:
                self.hw.cups.discard_cup()
                last = attempt == self.retries or not fault.retryable
                logger.warning("Order %s, %s: %s%s", order_id, item['name'], fault,
                               "" if last else "; retrying with a new cup")
                if last:
                    raise

    def make(self, job):
        """Makes every cup of a job from the backend's next-order reply."""
        slots = []
        for item in job['items']:
            try:
                slots.append(self.make_cup(job['id'], item))
            except HardwareFault as fault:
                self.hw.pickup.release_to_waste(job['id'])
                return Result(False, f"{item['name']}: {fault}"[:200])
        return Result(True, slots=slots)
