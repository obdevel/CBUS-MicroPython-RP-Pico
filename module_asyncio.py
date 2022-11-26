# module_asyncio.py

# example CBUS module main class using asyncio library

import time

import machine
import uasyncio as asyncio
from micropython import const

import aiorepl
import canmessage
import cbus
import cbusconfig
import cbusdefs
import cbushistory
import cbuslongmessage
import cbusmodule
import cbusobjects
import cbuspubsub
import logger
import mcp2515
import primitives

ntp_server = const('europe.pool.ntp.org')


# ***
# *** CBUS module class
# ***

class mymodule(cbusmodule.cbusmodule):
    def __init__(self):
        super().__init__()
        self.gcserver = None
        self.lm_ids = None
        self.cbus = None
        self.module_id = None
        self.module_name = None
        self.module_params = None
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

        # ***
        # *** optional configuration
        # ***

        # *** CBUS long message handling

        self.lm = cbuslongmessage.cbuslongmessage(self.cbus)
        self.lm_ids = [1, 2, 3, 4, 5]
        self.lm.subscribe(self.lm_ids, self.long_message_handler, receive_timeout=30000)

        # CBUS event history
        # self.history = cbushistory.cbushistory(self.cbus, max_size=256, time_to_live=1000)

        # consume own messages
        # self.cbus.set_consume_own_messages(False)

        # network-related
        self.is_picow = is_picow
        self.start_gc_server = start_gc_server

        if self.is_picow:
            self.connect_wifi()
            self.get_ntp_time()

            if self.start_gc_server:
                self.run_gc_server()

        # ***
        # *** module initialisation complete
        # ***

        self.logger.log(f"initialise complete, time = {time.ticks_diff(time.ticks_ms(), start_time)} ms")
        self.logger.log()
        self.logger.log(
            f"module: name = <{self.module_name}>, mode = {self.cbus.config.mode}, can id = {self.cbus.config.canid}, node number = {self.cbus.config.node_number}")
        self.logger.log(f"free memory = {self.cbus.config.free_memory()} bytes")
        self.logger.log()

        # ***
        # *** end of initialise method
        # ***

    # *** network-related methods

    def connect_wifi(self) -> None:
        try:
            import network
            self.logger.log("device is Pico W")
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
                self.logger.log("unable to connect to wifi")

        except ImportError:
            self.logger.log("import failed; device is not Pico W")
            self.is_picow = False

    def get_ntp_time(self) -> None:
        try:
            import ntptime
            ntptime.host = ntp_server
            self.logger.log(f"getting NTP time from {ntp_server} ...")
            nt = ntptime.time()
            lt = time.gmtime(nt)
            tt = (lt[0], lt[1], lt[2], 4, lt[3], lt[4], lt[5], lt[6])
            self.rtc = machine.RTC()
            self.rtc.datetime(tt)
            self.logger.log(f"NTP time = {tt}")
        except ImportError:
            print("ntptime module not present")
            self.is_picow = False

    def run_gc_server(self) -> None:
        try:
            import gcserver
            self.gcserver = gcserver.gcserver(self.cbus, self.host, 5550)
            asyncio.create_task(
                asyncio.start_server(self.gcserver.client_connected_cb, self.gcserver.host, self.gcserver.port))
        except ImportError:
            self.logger.log("import failed; gcserver module not found")

    # ***
    # *** coroutines that run in parallel
    # ***

    async def blink_led_coro(self) -> None:
        self.logger.log("blink_led_coro: start")
        led = machine.Pin("LED", machine.Pin.OUT)

        while True:
            led.value(1)
            await asyncio.sleep_ms(20)
            led.value(0)
            await asyncio.sleep_ms(980)

    async def history_test_coro(self) -> None:
        self.logger.log("history_test_coro: start")
        evt = asyncio.Event()
        self.history2 = cbushistory.cbushistory(self.cbus, max_size=1024, time_to_live=10000, event=evt)

        while True:
            await evt.wait()
            evt.clear()
            if self.history2.sequence_received([(0, 22, 23), (1, 22, 23)], order=cbushistory.ORDER_GIVEN, within=2000,
                                               timespan=2000, which=cbushistory.WHICH_LATEST):
                self.logger.log(f"history_test_coro: found sequence in history")

    async def pubsub_test_coro(self, pevent=None) -> None:
        self.logger.log("pubsub_test_coro: start")
        self.sub = cbuspubsub.subscription('test sub', self.cbus, None, canmessage.QUERY_ALL)

        while True:
            msg = await self.sub.wait()
            self.logger.log(f"pubsub_test_coro: got subscribed item, msg = {msg.__str__()}")
            if pevent:
                pevent.set()

    async def sensor_test_coro(self, pevent=None) -> None:
        event = asyncio.Event()
        self.sn1 = cbusobjects.binarysensor("sensor1", mod.cbus, (0, 22, 23), event)
        self.logger.log(
            f"sensor_test_coro: start, {self.sn1.name} state = {cbusobjects.sensor_states.get(self.sn1.state)}")

        while True:
            await event.wait()
            event.clear()
            self.logger.log(
                f"sensor_test_coro: {self.sn1.name} changed state to {self.sn1.state} = {cbusobjects.sensor_states.get(self.sn1.state)}")
            if pevent:
                pevent.set()

    async def any_test_coro(self) -> None:
        evp = asyncio.Event()
        evs = asyncio.Event()
        evt = asyncio.Event()

        timer = cbusobjects.timeout(5_000, evt)

        tp = asyncio.create_task(self.pubsub_test_coro(evp))
        ts = asyncio.create_task(self.sensor_test_coro(evs))
        tt = asyncio.create_task(timer.one_shot())

        while True:
            evw = await primitives.WaitAny((evp, evs, evt)).wait()

            if evw is evp:
                self.logger.log("any_test_coro: pubsub_test_coro event was set")
                evp.clear()
            elif evw is evs:
                self.logger.log("any_test_coro: sensor_test_coro event was set")
                evs.clear()
            elif evw is evt:
                self.logger.log("any_test_coro: timer expired")
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

        # test co-routines
        self.tb = asyncio.create_task(self.blink_led_coro())
        self.tm = asyncio.create_task(self.history_test_coro())
        self.tq = asyncio.create_task(self.any_test_coro())

        self.logger.log("asyncio is now running the module main loop and co-routines")

        # start async REPL and wait for exit
        repl = asyncio.create_task(aiorepl.task(globals()))
        await asyncio.gather(repl)

    def ttest(self):
        import cbusclocks
        self.wc = cbusclocks.cbusclock(mod.cbus, cbusclocks.WALLCLOCK, 0, True, 'pool.ntp.org')
        self.fc = cbusclocks.cbusclock(mod.cbus, cbusclocks.FASTCLOCK, 0, False)
        self.fc.set_multiplier(4)
        self.fc.resume()

    # ***
    # *** end of module class
    # ***


# some test messages
msg1 = canmessage.canmessage(99, 5, [0x90, 0, 22, 0, 25])
msg2 = canmessage.canmessage(99, 5, [0xE9, 1, 0, 0, 24, 0, 0, 0])
msg3 = canmessage.canmessage(4, 5, [0x91, 0, 22, 0, 23, 0, 0, 0])
msg4 = canmessage.canmessage(4, 5, [0x90, 0, 22, 0, 23, 0, 0, 0])
msg5 = canmessage.canmessage(126, 0, [], True, False)
msg6 = canmessage.canmessage(126, 0, [], False, True)

lm0 = canmessage.canmessage(126, 8, [0xE9, 9, 0, 0, 11, 0, 0, 0])
lm1 = canmessage.canmessage(126, 8, [0xE9, 9, 1, 72, 101, 108, 108, 111])
lm2 = canmessage.canmessage(126, 8, [0xE9, 9, 2, 32, 119, 111, 114, 108])
lm3 = canmessage.canmessage(126, 8, [0xE9, 9, 3, 100, 0, 0, 0, 0])


def enq() -> None:
    mod.logger.log("test messages")
    mod.cbus.can.rx_queue.enqueue(msg3)
    mod.cbus.can.rx_queue.enqueue(msg4)


def enq3() -> None:
    mod.cbus.can.rx_queue.enqueue(msg3)


def enq4() -> None:
    mod.cbus.can.rx_queue.enqueue(msg4)


def lms() -> None:
    mod.logger.log("test long messages")
    mod.cbus.can.rx_queue.enqueue(lm0)
    mod.cbus.can.rx_queue.enqueue(lm1)
    mod.cbus.can.rx_queue.enqueue(lm2)
    mod.cbus.can.rx_queue.enqueue(lm3)


def wconnect() -> None:
    mod.connect_wifi()


mod = mymodule()
# mod.initialise(is_picow=True, start_gc_server=False)
mod.initialise()
# mod.initialise(True, False)

# t = cbusobjects.turnout("t1", mod.cbus, ((0, 22, 23), (1, 22, 23)), cbusobjects.STATE_ON, True,
#                         ((0, 22, 23), (1, 22, 23)))
# s = cbusobjects.semaphore_signal("s1", mod.cbus, ((0, 22, 23), (1, 22, 23)), cbusobjects.STATE_ON, True,
#                                  ((0, 22, 23), (1, 22, 23)))
# tobj = cbusobjects.routeobject(t, cbusobjects.STATE_ON, 0)
# sobj = cbusobjects.routeobject(s, cbusobjects.STATE_OFF, 1)
# r = cbusobjects.route("r1", mod.cbus, (tobj, sobj,))
# r2 = cbusobjects.route("r2", mod.cbus, (tobj, sobj,))
# c = None

# *** start the scheduler and run the app class's main method
asyncio.run(mod.run())

# *** the scheduler is now in control
# *** no code after this line is executed
