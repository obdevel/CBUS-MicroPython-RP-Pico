
## cbusswitch.py

import machine, time

class cbusswitch():

    def __init__(self, pin):
        print(f'** switch constructor, pin = {pin}')
        self.pin = machine.Pin(pin, machine.Pin.IN, machine.Pin.PULL_UP)
        self.state = self.pin.value()
        self.last_state = self.state
        self.last_change_time = 0
        self.last_state_duration = 0
        self.state_changed = False

    def run(self):
        self.state = self.pin.value()

        if self.state != self.last_state:
            self.state_changed = True
            self.last_state_duration = time.ticks_ms() - self.last_change_time
            self.last_change_time = time.ticks_ms()
            self.last_state = self.state
            print(f'switch state changed, state = {self.state}, last duration = {self.last_state_duration}')

    def is_pressed(self):
        return (self.state == 0)

    def current_state_duration(self):
        return (time.ticks_ms() - self.last_change_time)
    
