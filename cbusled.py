# cbusled.py

import time

import uasyncio as asyncio
from machine import Pin
from micropython import const

import logger

BLINK_DURATION = const(500)
PULSE_DURATION = const(20)


class cbusled:
    def __init__(self, pin: int) -> None:
        self.logger = logger.logger()
        self.pin = Pin(pin, Pin.OUT)
        self.state = 0
        self.blinking = False
        self.pulsing = False
        self.last_change_time = 0
        self.pin.value(self.state)

        asyncio.create_task(self.run())

    async def run(self) -> None:
        while True:
            if self.pulsing:
                sleep_duration = PULSE_DURATION
            else:
                sleep_duration = BLINK_DURATION

            await asyncio.sleep_ms(sleep_duration)

            if self.blinking and time.ticks_diff(time.ticks_ms(), self.last_change_time) >= BLINK_DURATION:
                self.state = not self.state
                self.pin.value(self.state)
                self.last_change_time = time.ticks_ms()

            if self.pulsing and time.ticks_diff(time.ticks_ms(), self.last_change_time) >= PULSE_DURATION:
                self.state = 0
                self.pin.value(self.state)
                self.pulsing = False

    def on(self) -> None:
        self.blinking = False
        self.pulsing = False
        self.state = 1
        self.pin.value(self.state)
        pass

    def off(self) -> None:
        self.blinking = False
        self.pulsing = False
        self.state = 0
        self.pin.value(self.state)
        pass

    def blink(self) -> None:
        if not self.blinking:
            self.blinking = True
            self.pulsing = False
            self.last_change_time = time.ticks_ms()
            self.state = 0

    def pulse(self) -> None:
        if not self.pulsing:
            self.pulsing = True
            self.blinking = False
            self.state = 1
            self.pin.value(self.state)
            self.last_change_time = time.ticks_ms()
