# cbusswitch.py

import time

import uasyncio as asyncio
from machine import Pin

import logger


class cbusswitch:
    def __init__(self, pin_number):
        self.logger = logger.logger()
        self.pin = Pin(pin_number, Pin.IN, Pin.PULL_UP)
        self.state = self.pin.value()
        self.previous_state = self.state
        self.previous_state_change_at = time.ticks_ms()
        self.previous_state_duration = 0
        self.state_changed = False
        self.num_interrupts = 0

        self.tsf = asyncio.ThreadSafeFlag()
        self.pin.irq(trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING, handler=lambda x: self.tsf.set())
        asyncio.create_task(self.run())

    def run(self):
        await self.tsf.wait()
        self.num_interrupts += 1
        self.state = self.pin.value()

        if self.state != self.previous_state:
            self.state_changed = True
            self.previous_state = self.state
            self.previous_state_duration = time.ticks_diff(time.ticks_ms(), self.previous_state_change_at)
            self.previous_state_change_at = time.ticks_ms()
            # self.logger.log(f"switch state changed, state = {self.state}, last duration = {self.previous_state_duration}")
        else:
            self.state_changed = False
            self.logger.log('switch: spurious interrupt?')

    def is_pressed(self):
        return self.state == 0

    def current_state_duration(self):
        return time.ticks_diff(time.ticks_ms(), self.previous_state_change_at)

    def reset(self):
        self.state = 1
        self.previous_state_change_at = 0
        self.previous_state_duration = 0
        self.state_changed = False
