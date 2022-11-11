#
# module_example.py
#
# simplest example CBUS module main class using asyncio library
#

import machine
import time
import uasyncio as asyncio
import aiorepl

import cbusmodule
import cbus
import mcp2515
import cbusdefs
import cbusconfig
import canmessage
import logger


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

        self.module_id = 103
        self.module_name = "PYCO   "
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

        self.cbus.set_leds(21, 20)
        self.cbus.set_switch(22)
        self.cbus.set_name(self.module_name)
        self.cbus.set_params(self.module_params)
        self.cbus.set_event_handler(self.event_handler)
        self.cbus.set_frame_handler(self.frame_handler)

        self.cbus.begin()

        # ***
        # *** end of bare minimum init

        # ***
        # *** module initialisation complete

        self.logger.log(f"module: name = <{self.module_name}>, mode = {self.cbus.config.mode}, can id = {self.cbus.config.canid}, node number = {self.cbus.config.node_number}")
        self.logger.log(f"free memory = {self.cbus.config.free_memory()} bytes")
        self.logger.log()

        # *** end of initialise method

    # ***
    # *** coroutines that run in parallel
    # ***

    # *** task to blink the onboard LED
    async def blink_led_coro(self):
        self.logger.log("blink_led_coro start")
        self.led = machine.Pin("LED", machine.Pin.OUT)

        while True:
            self.led.value(1)
            await asyncio.sleep_ms(20)
            self.led.value(0)
            await asyncio.sleep_ms(980)

    # *** user module application task
    async def module_main_loop_coro(self):
        self.logger.log("main loop coroutine start")

        while True:
            await asyncio.sleep_ms(25)


    # ***
    # *** module main entry point
    # ***

    async def run(self):
        self.logger.log("run start")

        self.tb = asyncio.create_task(self.blink_led_coro())
        self.tm = asyncio.create_task(self.module_main_loop_coro())

        self.logger.log("asyncio is now running the module main loop and co-routines")

        # start async REPL and wait for exit
        repl = asyncio.create_task(aiorepl.task(globals()))
        await asyncio.gather(repl)


# create the module object and run it
mod = mymodule()
mod.initialise()
asyncio.run(mod.run())
