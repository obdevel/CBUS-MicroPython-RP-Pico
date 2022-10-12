
## cbusswitch.py

import machine, time

class cbusswitch():

    def __init__(self, pin):
        self.pin = machine.Pin(pin, machine.Pin.IN, machine.Pin.PULL_UP)
        self.state = self.pin.value()
        self.previous_state = self.state
        self.previous_state_change_at = 0
        self.previous_state_duration = 0
        self.state_changed = False

    def run(self):
        self.state = self.pin.value()

        if self.state != self.previous_state:
            self.state_changed = True
            self.previous_state = self.state
            self.previous_state_duration = time.ticks_ms() - self.previous_state_change_at
            self.previous_state_change_at = time.ticks_ms()
            print(f'switch state changed, state = {self.state}, last duration = {self.previous_state_duration}')
        else:
            self.state_changed = False

    def is_pressed(self):
        return (self.state == 0)

    def current_state_duration(self):
        return time.ticks_ms() - self.previous_state_change_at

    def reset(self):
        self.state = 1
        self.previous_state_change_at = 0
        self.previous_state_duration = 0
        self.state_changed = False
