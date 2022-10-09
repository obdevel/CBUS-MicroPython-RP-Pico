
## cbusled.py

import machine, time

BLINK_DURATION = 500
PULSE_DURATION = 10

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
        if self.blinking and time.ticks_ms() - self.last_change_time >= BLINK_DURATION:
            self.state = not self.state
            self.pin.value(self.state)
            self.last_change_time = time.ticks_ms()

        if self.pulsing and time.ticks_ms() - self.last_change_time >= PULSE_DURATION:
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
        if not self.blinking:
            self.blinking = 1
            self.pulsing = 0
            self.last_change_time = time.ticks_ms()
            self.state = 0

    def pulse(self):
        if not self.pulsing:
            self.pulsing = 1
            self.blinking = 0
            self.state = 1
            self.pin.value(self.state)
            self.last_change_time = time.ticks_ms()
