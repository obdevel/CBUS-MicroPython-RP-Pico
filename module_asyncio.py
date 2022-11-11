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
import cbuspubsub
import cbusobjects
import logger
import aiorepl
import primitives
# from primitives import WaitAny
# from primitives import WaitAll


# ***
# *** module class
# ***

class mymodule(cbusmodule.cbusmodule):
    def __init__(self):
        super().__init__()
        self.logger = logger.logger()

    def initialise(self, is_picow=False, start_gc_server=False) -> None:

        # ***
        # *** bare minimum module init
        # ***

        start_time = time.ticks_ms()

        self.cbus = cbus.cbus(
            mcp2515.mcp2515(),
            cbusconfig.cbusconfig(storage_type=cbusconfig.CONFIG_TYPE_FILES),
        )

        self.module_id = 103
        self.module_name = bytes("PYCO   ", "ascii")
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

        self.cbus.begin(freq=20, max_msgs=1)

        # ***
        # *** end of bare minimum init
        # ***

        # *** cbus long message handling

        self.lm = cbuslongmessage.cbuslongmessage(self.cbus)
        self.lm_ids = [1, 2, 3, 4, 5]
        self.lm.subscribe(self.lm_ids, self.long_message_handler, receive_timeout=30000)

        # cbus event history
        # self.history = cbushistory.cbushistory(self.cbus, max_size=1024, time_to_live=1000)

        # consume own messages
        self.cbus.set_consume_own_messages(False)

        self.is_picow = is_picow;
        self.start_gc_server = start_gc_server

        # start Gridconnect network server
        if self.is_picow and self.start_gc_server:
            try:
                import gcserver
                self.logger.log("device is Pico W")
                ssid = "HUAWEI-B311-E39A"
                password = "33260100"
                self.gcserver = gcserver.gcserver(self.cbus, ssid, password)
                self.gcserver.connect_wifi()
                self.is_picow = True
            except:
                self.logger.log("import failed; device is not Pico W")
                self.is_picow = False

        # get network time
        if self.is_picow:
            try:
                import ntptime
                self.logger.log("getting NTP time ...")
                ntptime.host = 'europe.pool.ntp.org'
                tt = ntptime.time()
                self.logger.log(f"NTP time = {tt}, {time.localtime(tt)}")
            except:
                print("ntptime module not present")

        # some test messages
        self.msg1 = canmessage.canmessage(99, 5, [0x90, 0, 22, 0, 25])
        self.msg2 = canmessage.canmessage(99, 5, [0xE9, 1, 0, 0, 24, 0, 0, 0])
        self.msg3 = canmessage.canmessage(4, 5, [0x91, 0, 22, 0, 23, 0, 0, 0])
        self.msg4 = canmessage.canmessage(4, 5, [0x90, 0, 22, 0, 23, 0, 0, 0])
        self.msg5 = canmessage.canmessage(126, 0, [], True, False)
        self.msg6 = canmessage.canmessage(126, 0, [], False, True)

        self.lm0 = canmessage.canmessage(126, 8, [0xE9, 9, 0, 0, 11, 0, 0, 0])
        self.lm1 = canmessage.canmessage(126, 8, [0xE9, 9, 1, 72, 101, 108, 108, 111])
        self.lm2 = canmessage.canmessage(126, 8, [0xE9, 9, 2, 32, 119, 111, 114, 108])
        self.lm3 = canmessage.canmessage(126, 8, [0xE9, 9, 3, 100, 0, 0, 0, 0])

        # *** module initialisation complete

        self.logger.log(f"initialise complete, time = {time.ticks_ms() - start_time} ms")
        self.logger.log()
        self.logger.log(f"module: name = <{self.module_name}>, mode = {self.cbus.config.mode}, can id = {self.cbus.config.canid}, node number = {self.cbus.config.node_number}")
        self.logger.log(f"free memory = {self.cbus.config.free_memory()} bytes")
        self.logger.log()

        # *** end of initialise method

    # ***
    # *** coroutines that run in parallel
    # ***

    async def blink_led_coro(self, lock) -> None:
        self.logger.log("blink_led_coro: start")
        self.led = machine.Pin("LED", machine.Pin.OUT)

        while True:
            await lock.acquire()
            self.led.value(1)
            lock.release()
            await asyncio.sleep_ms(20)
            self.led.value(0)
            await asyncio.sleep_ms(980)

    async def activity_coro(self, lock) -> None:
        self.logger.log("activity_coro: start")
        send_lm = False

        while True:
            await asyncio.sleep_ms(5000)
            await lock.acquire()

            if send_lm:
                self.cbus.can.rx_queue.enqueue(self.lm0)
                self.cbus.can.rx_queue.enqueue(self.lm1)
                self.cbus.can.rx_queue.enqueue(self.lm2)
                self.cbus.can.rx_queue.enqueue(self.lm3)
                send_lm = False
            else:
                self.cbus.can.rx_queue.enqueue(self.msg3)
                self.cbus.can.rx_queue.enqueue(self.msg4)
                send_lm = True

            lock.release()

    async def history_test_coro(self) -> None:
        self.logger.log("history_test_coro: start")
        event = asyncio.Event()
        self.history2 = cbushistory.cbushistory(self.cbus, max_size=1024, time_to_live=10000, event=event)

        while True:
            await event.wait()
            event.clear()
            if self.history2.sequence_received([(0, 22, 23), (1, 22, 23)], order=cbushistory.ORDER_GIVEN, within=2000, timespan=2000, which=cbushistory.WHICH_LATEST):
                self.logger.log(f"history_test_coro: found sequence in history")

    async def pubsub_test_coro(self, pevent=None) -> None:
        self.logger.log("pubsub_test_coro: start")
        self.sub = cbuspubsub.subscription('test sub', self.cbus, "hello", canmessage.QUERY_ALL)

        while True:
            msg = await self.sub.wait()
            self.logger.log(f"pubsub_test_coro: got subscribed item, msg = {msg.__str__()}")
            if pevent:
                pevent.set()

    async def sensor_test_coro(self, pevent=None) -> None:
        event = asyncio.Event()
        self.sn1 = cbusobjects.binarysensor("sensor1", mod.cbus, (0, 22, 23), event)
        self.logger.log(f"sensor_test_coro: start, {self.sn1.name} state = {cbusobjects.sensor_states.get(self.sn1.state)}")

        while True:
            await event.wait()
            event.clear()
            self.logger.log(f"sensor_test_coro: {self.sn1.name} changed state to {self.sn1.state} = {cbusobjects.sensor_states.get(self.sn1.state)}")
            if pevent:
                pevent.set()

    async def sequence_test_coro(self) -> None:
        evp = asyncio.Event()
        evs = asyncio.Event()
        evt = asyncio.Event()

        self.timer = cbusobjects.timeout(2_000, evt)
        tp = asyncio.create_task(self.pubsub_test_coro(evp))
        ts = asyncio.create_task(self.sensor_test_coro(evs))
        tt = asyncio.create_task(self.timer.one_shot())

        while True:
            evw = await primitives.WaitAny((evp, evs, evt)).wait()

            if evw is evp:
                self.logger.log("sequence_test_coro: pubsub_test_coro event was set")
                evp.clear()
            elif evw is evs:
                self.logger.log("sequence_test_coro: sensor_test_coro event was set")
                evs.clear()
            elif evw is evt:
                self.logger.log("sequence_test_coro: timed out")
                evt.clear()
                tt.cancel()

    # ***
    # *** module main entry point
    # ***

#     def _handle_exception(self, loop, context):
#         print('Global handler')
#         sys.print_exception(context["exception"])
#         #loop.stop()
#         sys.exit()  # Drastic - loop.stop() does not work when used this way

    async def run(self) -> None:

        # loop = asyncio.get_event_loop()
        # loop.set_exception_handler(self._handle_exception)

        self.a_lock = Lock()
        self.b_lock = Lock()
        await self.a_lock.acquire()

        self.tb = asyncio.create_task(self.blink_led_coro(self.b_lock))
        self.ta = asyncio.create_task(self.activity_coro(self.a_lock))
        self.tm = asyncio.create_task(self.history_test_coro())
        # self.ts = asyncio.create_task(self.pubsub_test_coro())
        # self.tn = asyncio.create_task(self.sensor_test_coro())
        self.tq = asyncio.create_task(self.sequence_test_coro())

        # start gridconnect server coros if device is Pico W
        if self.is_picow and self.start_gc_server:
            self.tg = asyncio.create_task(asyncio.start_server(self.gcserver.client_connected_cb, self.gcserver.host, self.gcserver.port))

        self.logger.log("asyncio is now running the module main loop and co-routines")

        # start async REPL and wait for exit
        repl = asyncio.create_task(aiorepl.task(globals()))
        await asyncio.gather(repl)

    # ***
    # *** end of module class
    # ***


def control(state) -> None:
    if state:
        mod.a_lock.release()
    else:
        await mod.a_lock.acquire()

def conf() -> None:
    mod.cbus.config.set_mode(1)
    mod.cbus.config.set_canid(5)
    mod.cbus.config.set_node_number(333)

    mod.cbus.config.events[1] = 22
    mod.cbus.config.events[3] = 23
    mod.cbus.config.events[4] = 1
    mod.cbus.config.events[5] = 2
    mod.cbus.config.events[6] = 3
    mod.cbus.config.events[7] = 4
    mod.cbus.config.backend.store_events(mod.cbus.config.events)

def enq() -> None:
    mod.logger.log("test messages")
    mod.cbus.can.rx_queue.enqueue(mod.msg3)
    mod.cbus.can.rx_queue.enqueue(mod.msg4)

def enq3() -> None:
    mod.cbus.can.rx_queue.enqueue(mod.msg3)

def enq4() -> None:
    mod.cbus.can.rx_queue.enqueue(mod.msg4)

def lms() -> None:
    mod.logger.log("test long messages")
    mod.cbus.can.rx_queue.enqueue(mod.lm0)
    mod.cbus.can.rx_queue.enqueue(mod.lm1)
    mod.cbus.can.rx_queue.enqueue(mod.lm2)
    mod.cbus.can.rx_queue.enqueue(mod.lm3)


mod = mymodule()
# mod.initialise(is_picow=True, start_gc_server=False)
mod.initialise()

t = cbusobjects.turnout("t1", mod.cbus, ((0,22,23),(1,22,23)))
s = cbusobjects.semaphore_signal("s1", mod.cbus, ((0,22,23),(1,22,23)))
tobj = cbusobjects.routeobject(t, cbusobjects.STATE_ON, 0)
sobj = cbusobjects.routeobject(s, cbusobjects.STATE_OFF, 1)
r = cbusobjects.route("r1", mod.cbus, (tobj,), (sobj,))
r2 = cbusobjects.route("r2", mod.cbus, (tobj,), (sobj,))

asyncio.run(mod.run())

