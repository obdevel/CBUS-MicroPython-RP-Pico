#
# module_example.py
#
# simplest example CBUS module main class using asyncio library
#

import uasyncio as asyncio
from machine import Pin

import aiorepl
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
        # *** bare minimum module init
        # ***

        self.cbus = cbus.cbus(
            mcp2515.mcp2515(),
            cbusconfig.cbusconfig(storage_type=cbusconfig.CONFIG_TYPE_FILES),
        )

        # ** change the module name and ID if desired

        self.module_id = 103
        self.module_name = bytes('PYCO   ', 'ascii')
        self.module_params = [
            20,
            cbusdefs.MANU_MERG,
            0,
            self.module_id,
            self.cbus.config.num_events,
            self.cbus.config.num_evs,
            self.cbus.config.num_nvs,
            1,
            7,
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

        # change the CBUS switch and LED pin numbers if desired

        self.cbus.set_leds(21, 20)
        self.cbus.set_switch(22)
        self.cbus.set_name(self.module_name)
        self.cbus.set_params(self.module_params)
        self.cbus.set_event_handler(self.event_handler)
        self.cbus.set_received_message_handler(self.received_message_handler)
        self.cbus.set_sent_message_handler(self.sent_message_handler)

        self.cbus.begin()

        # ***
        # *** end of bare minimum init

        # ***
        # *** module initialisation complete

        self.logger.log(f'module: name = <{self.module_name}>, mode = {self.cbus.config.mode}, can id = {self.cbus.config.canid}, node number = {self.cbus.config.node_number}')
        self.logger.log(f'free memory = {self.cbus.config.free_memory()} bytes')
        self.logger.log()

        # *** end of initialise method

    # ***
    # *** coroutines that run in parallel
    # ***

    # *** task to blink the onboard LED
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
    async def module_main_loop_coro(self) -> None:
        self.logger.log('main loop coroutine start')
        while True:
            await asyncio.sleep_ms(25)

    # ***
    # *** module main entry point - like Arduino setup()
    # ***

    async def run(self) -> None:
        self.logger.log('run start')

        # start coroutines
        self.tb = asyncio.create_task(self.blink_led_coro())
        self.tm = asyncio.create_task(self.module_main_loop_coro())

        self.logger.log('asyncio is now running the module main loop and co-routines')

        # start async REPL and wait for exit
        repl = asyncio.create_task(aiorepl.task(globals()))
        await asyncio.gather(repl)


# create the module object and run it
mod = mymodule()
mod.initialise()
asyncio.run(mod.run())

# the asyncio scheduler is now in control
# no code after this line is executed
