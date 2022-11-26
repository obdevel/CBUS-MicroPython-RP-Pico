# cbusled.py

from micropython import const
import machine
import time
import logger

BLINK_DURATION = const(500)
PULSE_DURATION = const(10)


class cbusled:
    def __init__(self, pin):
        self.logger = logger.logger()
        self.pin = machine.Pin(pin, machine.Pin.OUT)
        self.state = 0
        self.blinking = False
        self.pulsing = False
        self.last_change_time = 0
        self.pin.value(self.state)

    def run(self):
        if self.blinking and time.ticks_ms() - self.last_change_time >= BLINK_DURATION:
            self.state = not self.state
            self.pin.value(self.state)
            self.last_change_time = time.ticks_ms()

        if self.pulsing and time.ticks_ms() - self.last_change_time >= PULSE_DURATION:
            self.state = 0
            self.pin.value(self.state)
            self.pulsing = 0

    def on(self):
        self.blinking = False
        self.pulsing = False
        self.state = 1
        self.pin.value(self.state)
        pass

    def off(self):
        self.blinking = False
        self.pulsing = False
        self.state = 0
        self.pin.value(self.state)
        pass

    def blink(self):
        if not self.blinking:
            self.blinking = True
            self.pulsing = False
            self.last_change_time = time.ticks_ms()
            self.state = 0

    def pulse(self):
        if not self.pulsing:
            self.pulsing = True
            self.blinking = False
            self.state = 1
            self.pin.value(self.state)
            self.last_change_time = time.ticks_ms()
