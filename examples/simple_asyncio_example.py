#
# module_example.py
#
# simplest example CBUS module main class using asyncio library
#

import time

import machine
import uasyncio as asyncio

import aiorepl
import logger
import simple_server
from primitives import Queue


class mymodule():
    def __init__(self):
        self.logger = logger.logger()
        self.ip = None
        self.q = Queue()

    def initialise(self):
        pass

    # ***
    # *** end of bare minimum init

    # ***
    # *** module initialisation complete

    # *** end of initialise method

    # ***
    # *** coroutines that run in parallel
    # ***

    # *** task to blink the onboard LED
    async def blink_led_coro(self):
        self.logger.log('blink_led_coro start')
        try:
            led = machine.Pin('LED', machine.Pin.OUT)
        except TypeError:
            led = machine.Pin(25, machine.Pin.OUT)

        while True:
            led.value(1)
            await asyncio.sleep_ms(20)
            led.value(0)
            await asyncio.sleep_ms(980)

    # *** user module application task - like Arduino loop()
    async def module_main_loop_coro(self):
        self.logger.log('main loop coroutine start')

        while True:
            val = await self.q.get()
            self.logger.log(f'main loop: got from queue |{val}|')

    def connect_wifi(self) -> None:
        import network

        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        self.wlan.connect('HUAWEI-B311-E39A', '33260100')
        self.logger.log('waiting for wifi...')
        tt = time.ticks_ms()

        while not self.wlan.isconnected() and time.ticks_ms() - tt < 5000:
            time.sleep_ms(500)

        if self.wlan.isconnected():
            self.ip = self.wlan.ifconfig()[0]
            self.channel = self.wlan.config('channel')
            self.logger.log(f'connected to wifi, channel = {self.channel}, address = {self.ip}')
            self.host = self.ip
        else:
            self.logger.log('unable to connect to wifi')

    # ***
    # *** module main entry point - like Arduino setup()
    # ***

    async def run(self):
        self.logger.log('run start')

        # connect to wifi
        self.connect_wifi()

        # create server object
        self.server = simple_server.simple_server(self.q)

        # start coroutines
        self.tb = asyncio.create_task(self.blink_led_coro())
        self.tm = asyncio.create_task(self.module_main_loop_coro())
        self.ts = asyncio.create_task(asyncio.start_server(self.server.client_connected_cb, self.ip, 5550))

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
