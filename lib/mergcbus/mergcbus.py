import time
from machine import Pin
import mcp2515

_BLINK_RATE = 500
_PULSE_ON_TIME = 50

class cbus_switch:

    """a class to represent a module's CBUS switch"""

    def __init__(self, pin):
        self._switch = Pin(pin, Pin.IN, Pin.PULL_UP)
        self.reset()

    def run(self):
        """ allow the switch some processing time"""

        self._currentstate = self._switch.value()

        if self._current_state != self._last_state:
            self._previous_state_duration = self._last_state_duration
            self._last_state_duration = time.ticks_ms() - self._previous_state_duration
            self._last_state_change_time = time.ticks_ms()
            self._state_changed = True

            if self._current_state:
                self._prev_release_time = self._last_state_change_time

        else:
            self._state_changed = False

    def state_changed(self):
        """ return true if the state has changed"""
        return self._state_changed

    def get_state(self):
        """ return the current switch state"""
        return self._current_state

    def is_pressed(self):
        """ return true if the switch is currently pressed"""
        return (self._current_state == 0)

    def get_current_state_duration(self):
        """ return the number of ms the switch has been in its current state"""
        return time.ticks_ms() - self._last_state_change_time

    def get_last_state_duration(self):
        """ return the number of ms the switch was in its previous state"""
        return self._last_state_duration

    def get_last_state_change_time(self):
        """ return the time in ms when the switch last changed state"""
        return self._last_state_change_time

    def reset_current_duration(self):
        """ reset the current state duration"""
        self._last_state_change_time = time.ticks_ms()

    def reset(self):
        """ reset all state variables to default values"""
        self._current_state = 1
        self._last_state = self._current_state
        self._previous_state_duration = 0
        self._last_state_duration = 0
        self._last_state_change_time = 0
        self.state_changed = False


class cbus_led:

    """a class to represent one of a module's LEDs"""

    def __init__(self, pin):
        self._led = Pin(pin, Pin.OUT)
        self._state = 0
        self._blink = False
        self._pulse = False
        self._last_time = 0
        self._pulse_start = 0

        self.run()

    def off(self):
        """ switch the LED off"""
        self._state = 0
        self._blink = False

    def on(self):
        """ switch the LED on"""
        self._state = 1
        self._blink = False

    def toggle(self):
        """ toggle the LED state"""
        self._state = not self._state

    def blink(self):
        """ start the LED blinking"""
        self._blink = True

    def pulse(self):
        """ pulse the LED once"""
        self._pulse = True
        self._state = True
        self.pulse_start = time.ticks_ms()

    def run(self):
        """ allow the LED some processing time"""

        if self._blink:
            if time.ticks_ms() - self._last_time >= _BLINK_RATE:
                self.toggle()
                self._last_time = time.ticks_ms()

        if self._pulse:
            if time.ticks_ms() - self._pulse_start >= _PULSE_ON_TIME:
                self._pulse = False
                self._state = 0

        self._led(self._state)


class canframe:

    """ a class to represent a CAN 2.0b message frame"""

    def __init__(self):
        self.id = 0
        self.len = 0
        self.rtr = False
        self.ext = False
        self.data = bytearray(8)


class mergcbus:

    """ a class to represent a CBUS FLiM module"""

    def __init__(self, bus, switch=None, led1=None, led2=None):
        pass

    def set_event_handler(self):
        pass

    def set_frame_handler(self):
        pass

    def set_params(self):
        pass

    def set_name(self):
        pass

    def set_slim(self):
        pass

    def get_canid(self):
        pass

    def send_WRACK(self):
        pass

    def send_CMDERR(self):
        pass

    def is_ext(self):
        pass

    def is_rtr(self):
        pass

    def can_enumeration(self):
        pass

    def init_flim(self):
        pass

    def revert_slim(self):
        pass

    def renegotiate(self):
        pass

    def set_leds(self):
        pass

    def set_switch(self):
        pass

    def indicate_mode(self):
        pass

    def process(self, max_msgs=3):
        pass

    def check_can_enum(self):
        pass

    def process_accessory_event(self):
        pass

    def set_long_message_hanlder(self):
        pass

    def make_header(self):
        pass
