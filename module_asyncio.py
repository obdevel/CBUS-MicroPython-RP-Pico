# module_asyncio.py

# example CBUS module main class using asyncio library

import machine
import time
import uasyncio as asyncio
from uasyncio import Lock
import cbusmodule
import cbus
import mcp2515
import cbusdefs
import cbusconfig
import canmessage
import cbuslongmessage
import cbushistory
import logger
import aiorepl


class mymodule(cbusmodule.cbusmodule):
    def __init__(self):
        super().__init__()
        self.logger = logger.logger()
        # self.logger.log("mymodule constructor")

    def initialise(self):
        # ***
        # *** bare minimum module init
        # ***

        start_time = time.ticks_ms()

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
        self.cbus.set_consume_own_messages(False)

        self.cbus.begin()

        # ***
        # *** end of bare minimum init
        # ***

        # *** cbus long message handling

        self.lm = cbuslongmessage.cbuslongmessage(self.cbus)
        self.lm_ids = [1, 2, 3, 4, 5]
        self.lm.subscribe(self.lm_ids, self.long_message_handler)

        # cbus event history
        self.history = cbushistory.cbushistory(self.cbus, max_size=1024, time_to_live=120_000)

        # consume own messages
        self.cbus.set_consume_own_messages(False)

        # some test messages
        self.msg1 = canmessage.canmessage(99, 5, [0x90, 0, 22, 0, 25])
        self.msg2 = canmessage.canmessage(99, 5, [0xE9, 1, 0, 0, 24, 0, 0, 0])
        self.msg3 = canmessage.canmessage(4, 5, [0x91, 0, 22, 0, 23, 0, 0, 0])
        self.msg4 = canmessage.canmessage(555, 0, [], True, False)
        self.msgx = canmessage.canmessage(444, 33, [], False, True)

        self.lm0 = canmessage.canmessage(333, 8, [0xE9, 2, 0, 0, 11, 0, 0, 0])
        self.lm1 = canmessage.canmessage(333, 8, [0xE9, 2, 1, 72, 101, 108, 108, 111])
        self.lm2 = canmessage.canmessage(333, 8, [0xE9, 2, 2, 32, 119, 111, 114, 108])
        self.lm3 = canmessage.canmessage(333, 8, [0xE9, 2, 3, 100, 0, 0, 0, 0])

        # *** module initialisation complete

        self.logger.log(
            f"initialise complete, time = {time.ticks_ms() - start_time} ms"
        )
        self.logger.log()
        self.logger.log(
            f"module: name = <{self.module_name}>, mode = {self.cbus.config.mode}, can id = {self.cbus.config.canid}, node number = {self.cbus.config.node_number}"
        )
        self.logger.log(f"free memory = {self.cbus.config.free_memory()} bytes")
        self.logger.log()

        # *** end of initialise method

    # ***
    # *** coroutines that run in parallel
    # ***

    async def cbus_coro(self):
        self.logger.log("cbus_coro start")

        while True:
            c = self.cbus.process()
            await asyncio.sleep_ms(1)

    async def long_message_coro(self):
        self.logger.log("long_message_coro start")

        while True:
            self.lm.process()
            await asyncio.sleep_ms(10)

    async def history_coro(self):
        self.logger.log("event history coro start")

        while True:
            self.history.reap()
            await asyncio.sleep_ms(100)

    async def blink_led_coro(self, lock):
        self.logger.log("blink_led_coro start")
        self.led = machine.Pin(25, machine.Pin.OUT)

        while True:
            await lock.acquire()
            self.led.value(1)
            lock.release()
            await asyncio.sleep_ms(20)
            self.led.value(0)
            await asyncio.sleep_ms(980)

    async def activity_coro(self, lock):
        self.logger.log("activity coro start")
        send_lm = True

        while True:
            await asyncio.sleep_ms(2000)
            await lock.acquire()

            if send_lm:
                self.cbus.can.rx_queue.enqueue(self.lm0)
                self.cbus.can.rx_queue.enqueue(self.lm1)
                self.cbus.can.rx_queue.enqueue(self.lm2)
                self.cbus.can.rx_queue.enqueue(self.lm3)
                send_lm = False
            else:
                self.cbus.can.rx_queue.enqueue(self.msg3)
                send_lm = True

            lock.release()

    async def main_loop_coro(self):
        self.logger.log("main loop coro start")
        
        while True:
            await asyncio.sleep_ms(50)

            if self.history.find_event(22, 23, 2, 50):
                self.logger.log("** found event in history")

    # ***
    # *** module main entry point
    # ***

    async def main(self):
        self.logger.log("main start")

        self.a_lock = Lock()
        self.b_lock = Lock()

        await self.a_lock.acquire()

        self.tc = asyncio.create_task(self.cbus_coro())
        self.tl = asyncio.create_task(self.long_message_coro())
        self.th = asyncio.create_task(self.history_coro())
        self.tb = asyncio.create_task(self.blink_led_coro(self.b_lock))
        self.ta = asyncio.create_task(self.activity_coro(self.a_lock))
        self.tm = asyncio.create_task(self.main_loop_coro())

        repl = asyncio.create_task(aiorepl.task(globals()))

        self.logger.log("asyncio is now running the module main loop and co-routines")

        await asyncio.gather(repl)


def control(state):
    if state:
        mod.a_lock.release()
    else:
        await mod.a_lock.acquire()


mod = mymodule()
mod.initialise()
asyncio.run(mod.main())
