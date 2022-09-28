
## cbusled.py

import machine, time

BLINK_DELAY = 500
PULSE_DELAY = 50

class cbusled():

    def __init__(self, pin):
        # print(f'** LED constructor, pin = {pin}')
        self.pin = machine.Pin(pin, machine.Pin.OUT)
        self.state = 0
        self.blinking = 0
        self.pulsing = 0
        self.last_change_time = 0
        self.pin.value(self.state)

    def run(self):
        if self.blinking and time.ticks_ms() - self.last_change_time >= BLINK_DELAY:
            self.state = not self.state
            self.pin.value(self.state)
            self.last_change_time = time.ticks_ms()

        if self.pulsing and time.ticks_ms() - self.last_change_time >= PULSE_DELAY:
            self.state = 0
            self.pin.value(self.state)
            self.pulsing = 0

    def on(self):
        self.blinking = 0
        self.pulsing = 0
        self.state = 1
        self.pin.value(self.state)
        pass

    def off(self):
        self.blinking = 0
        self.pulsing = 0
        self.state = 0
        self.pin.value(self.state)
        pass

    def blink(self):
        self.blinking = 1
        self.pulsing = 0
        self.last_change_time = time.ticks_ms()
        self.state = 0

    def pulse(self):
        self.pulsing = 1
        self.blinking = 0
        self.state = 1
        self.pin.value(self.state)
        self.last_change_time = time.ticks_ms()
