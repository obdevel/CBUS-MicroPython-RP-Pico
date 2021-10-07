
## cbusswitch.py

import machine, time

class cbusswitch():

    def __init__(self, pin):
        print(f'** switch constructor, pin = {pin}')
        self.pin = machine.Pin(pin, machine.Pin.IN, machine.Pin.PULL_UP)
        self.state = self.pin.value()
        self.previous_state = self.state
        self.previous_change_time = 0
        self.previous_state_duration = 0
        self.state_changed = False

    def run(self):
        self.state = self.pin.value()

        if self.state != self.previous_state:
            self.state_changed = True
            self.previous_state_duration = time.ticks_ms() - self.previous_change_time
            self.previous_change_time = time.ticks_ms()
            self.previous_state = self.state
            print(f'switch state changed, state = {self.state}, last duration = {self.previous_state_duration}')

    def is_pressed(self):
        return (self.state == 0)

    def current_state_duration(self):
        return (time.ticks_ms() - self.previous_change_time)
    
