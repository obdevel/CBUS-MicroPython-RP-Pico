# example CBUS consumer module - controls 8 LEDs
# use FCU to teach events
# set EV1 to the number of the LED to control, values 0-7
# other EVs are not used
#

import uasyncio as asyncio
from machine import Pin

import aiorepl
import canmessage
import cbus
import cbusconfig
import cbusdefs
import cbusmodule
import logger
import mcp2515


class mymodule(cbusmodule.cbusmodule):
    def __init__(self):
        super().__init__()
        self.logger = logger.logger()

    def initialise(self):

        # ***
        # *** module init
        # ***

        # ** import a board definition from boards.py, or create a new one subclassed from boards.cbus_board
        # ** you should change the module ID to something unique on your layout
        # ** you can also change the module name if desired
        # ** and the number of events, EVs and NVs

        from boards import dgboard

        board = dgboard()
        config = cbusconfig.cbusconfig(storage_type=cbusconfig.CONFIG_TYPE_FILES, num_nvs=20, num_events=64, num_evs=4)
        self.cbus = cbus.cbus(board.can, config)

        self.module_id = 107
        self.module_name = bytes('PYCONS ', 'ascii')
        self.module_params = [
            20,
            cbusdefs.MANU_MERG,
            0,
            self.module_id,
            self.cbus.config.num_events,
            self.cbus.config.num_evs,
            self.cbus.config.num_nvs,
            1,
            cbusdefs.PF_CONSUMER | cbusdefs.PF_FLiM,  # 8 - flags
            0,
            cbusdefs.PB_CAN,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ]

        self.cbus.set_leds(board.green_led_pin_number, board.yellow_led_pin_number)
        self.cbus.set_switch(board.switch_pin_number)

        self.cbus.set_name(self.module_name)
        self.cbus.set_params(self.module_params)
        self.cbus.set_event_handler(self.event_handler)
        self.cbus.set_received_message_handler(self.received_message_handler)
        self.cbus.set_sent_message_handler(self.sent_message_handler)
        
        if self.module_params[8] & cbusdefs.PF_COE:
            self.cbus.consume_own_messages = True

        self.cbus.begin()

        # ***
        # *** end of bare minimum init

        # ***
        # *** setup output pins for LEDs
        # *** pin numbers could be configured using NVs rather than being hardcoded
        # ***

        self.pins = [None] * 8
        pin_numbers = (8, 9, 10, 11, 12, 13, 14, 15)

        for i, p in enumerate(pin_numbers):
            self.pins[i] = Pin(p, Pin.OUT)
            self.pins[i].off()

        # ***
        # *** module initialisation complete

        self.logger.log(f'module: name = <{self.module_name.decode()}>, mode = {self.cbus.config.mode}, can id = {self.cbus.config.canid}, node number = {self.cbus.config.node_number}')
        self.logger.log(f'free memory = {self.cbus.config.free_memory()} bytes')

        # *** end of initialise method

    # ***
    # *** CBUS event handler -- called whenever a previously taught event is received
    # *** when teaching, set the value of EV1 to select the LED to control (0-7)
    # ***

    def event_handler(self, msg: canmessage.canmessage, idx: int) -> None:
        self.logger.log(f'-- event handler: idx = {idx}: {msg}')

        # lookup the value of the 1st EV
        ev1 = self.cbus.config.read_event_ev(idx, 1)
        self.logger.log(f'** idx = {idx}, opcode = {msg.data[0]}, polarity = {"OFF" if msg.data[0] & 1 else "ON"}, ev1 = {ev1}')

        # switch the LED on or off according to the event opcode
        if ev1 < 8:
            if msg.data[0] & 1:        # off events are odd numbers
                self.logger.log(f'** LED {ev1} off')
                self.pins[ev1].off()
            else:                      # on events are even numbers
                self.logger.log(f'** LED {ev1} on')
                self.pins[ev1].on()

    # ***
    # *** coroutines that run in parallel
    # ***

    # *** task to blink the onboard LED
    # *** useful as an indication that the module is still alive

    async def blink_led_coro(self) -> None:
        self.logger.log('blink_led_coro start')
        try:
            led = Pin('LED', Pin.OUT)
        except TypeError:
            led = Pin(25, Pin.OUT)

        while True:
            led.value(1)
            await asyncio.sleep_ms(20)
            led.value(0)
            await asyncio.sleep_ms(980)

    # *** user module application task - like Arduino loop()
    # *** does nothing in this example

    async def module_main_loop_coro(self) -> None:
        self.logger.log('main loop coroutine start')

        while True:
            await asyncio.sleep_ms(25)

    # ***
    # *** module main entry point - like Arduino setup()
    # ***

    async def run(self) -> None:
        self.logger.log('run start')

        # module has been reset - do one-time config here
        if self.cbus.config.was_reset:
            self.logger.log('module was reset')
            self.cbus.config.set_reset_flag(False)

        # start coroutines
        self.tb = asyncio.create_task(self.blink_led_coro())
        self.tm = asyncio.create_task(self.module_main_loop_coro())

        # start async REPL and wait for exit
        repl = asyncio.create_task(aiorepl.task(globals()))

        self.logger.log('module startup complete')
        await asyncio.gather(repl)


# create the module object and run it
mod = mymodule()
mod.initialise()
asyncio.run(mod.run())

# the asyncio scheduler is now in control
# no code after this line is executed

print('*** application has ended ***')
