# module_asyncio.py

# example CBUS module main class using asyncio library

import time

import uasyncio as asyncio
from machine import RTC, Pin
from micropython import const

import aiorepl
import canmessage
import cbus
import cbusconfig
import cbusdefs
import cbushistory
# import cbuslongmessage
import cbusmodule
import cbusobjects
import cbuspubsub
import cbusroutes
import logger
import mcp2515
from primitives import WaitAny

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

    def initialise(self, is_picow: bool = False, start_gc_server: bool = False) -> None:

        # ***
        # *** bare minimum module init
        # ***

        start_time = time.ticks_ms()

        self.cbus = cbus.cbus(mcp2515.mcp2515(), cbusconfig.cbusconfig())

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

        self.cbus.set_leds(21, 20)
        self.cbus.set_switch(22)
        self.cbus.set_name(self.module_name)
        self.cbus.set_params(self.module_params)
        self.cbus.set_event_handler(self.event_handler)
        self.cbus.set_received_message_handler(self.received_message_handler)
        self.cbus.set_sent_message_handler(self.sent_message_handler)

        self.cbus.begin(freq=20, max_msgs=1)

        # ***
        # *** end of bare minimum init
        # ***

        # ***
        # *** optional configuration
        # ***

        # consume own messages
        self.cbus.consume_own_messages = False

        # *** CBUS long message handling
        # self.lm = cbuslongmessage.cbuslongmessage(self.cbus)
        # self.lm_ids = (1, 2, 3, 4, 5)
        # self.lm.subscribe(self.lm_ids, self.long_message_handler, receive_timeout=1_000)

        # CBUS event history
        # self.history = cbushistory.cbushistory(self.cbus, max_size=256, time_to_live=1000)

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

        self.logger.log(f'initialise complete, time = {time.ticks_diff(time.ticks_ms(), start_time)} ms')
        self.logger.log()
        self.logger.log(
            f'module: name = <{self.module_name}>, mode = {self.cbus.config.mode}, can id = {self.cbus.config.canid}, node number = {self.cbus.config.node_number}')
        self.logger.log(f'free memory = {self.cbus.config.free_memory()} bytes')
        self.logger.log()

        # ***
        # *** end of initialise method
        # ***

    # ***
    # *** network-related methods
    # ***

    def connect_wifi(self) -> None:
        try:
            import network
            self.logger.log('device is Pico W')
            self.wlan = network.WLAN(network.STA_IF)
            self.wlan.active(True)
            self.wlan.connect('HUAWEI-B311-E39A', '33260100')
            self.logger.log('waiting for wifi...')
            tt = time.ticks_ms()

            while not self.wlan.isconnected() and time.ticks_diff(time.ticks_ms(), tt) < 5000:
                time.sleep_ms(500)

            if self.wlan.isconnected():
                self.ip = self.wlan.ifconfig()[0]
                self.channel = self.wlan.config('channel')
                self.logger.log(f'connected to wifi, channel = {self.channel}, address = {self.ip}')
                self.host = self.ip
            else:
                self.logger.log('unable to connect to wifi')

        except ImportError:
            self.logger.log('import failed; device is not Pico W')
            self.is_picow = False

    def get_ntp_time(self) -> None:
        try:
            import ntptime
            ntptime.host = ntp_server
            self.logger.log(f'getting NTP time from {ntp_server} ...')
            nt = ntptime.time()
            lt = time.gmtime(nt)
            tt = (lt[0], lt[1], lt[2], 4, lt[3], lt[4], lt[5], lt[6])
            self.rtc = RTC()
            self.rtc.datetime(tt)
            self.logger.log(f'NTP time = {tt}')
        except ImportError:
            self.logger.log('import failed; device is not Pico W')
            self.is_picow = False

    def run_gc_server(self) -> None:
        try:
            import gcserver
            self.gcserver = gcserver.gcserver(self.cbus, self.host, 5550)
            asyncio.create_task(
                asyncio.start_server(self.gcserver.client_connected_cb, self.gcserver.host, self.gcserver.port))
        except ImportError:
            self.logger.log('import failed; device is not Pico W')

    # ***
    # *** coroutines that run in parallel
    # ***

    async def blink_led_coro(self) -> None:
        self.logger.log('blink_led_coro: start')

        try:
            led = Pin('LED', Pin.OUT)
        except TypeError:
            led = Pin(25, Pin.OUT)

        while True:
            led.value(1)
            await asyncio.sleep_ms(20)
            led.value(0)
            await asyncio.sleep_ms(980)

    async def history_test_coro(self, pevent: asyncio.Event) -> None:
        self.logger.log('history_test_coro: start')
        events = ((0, 22, 23), (1, 22, 23))
        hist = cbushistory.cbushistory(self.cbus, max_size=1024, time_to_live=5_000, query_type=canmessage.QUERY_TUPLES,
                                       query=events)
        while True:
            await hist.wait()
            if hist.sequence_received(events, order=cbushistory.ORDER_GIVEN, within=3_000, window=2_000,
                                      which=cbushistory.WHICH_LATEST):
                diff = hist.time_diff(events)
                self.logger.log(f'history_test_coro: sequence {events} found, time diff = {diff}')
                pevent.set()
            else:
                pass

    async def pubsub_test_coro(self, pevent: asyncio.Event) -> None:
        self.logger.log('pubsub_test_coro: start')
        sub = cbuspubsub.subscription('pubsub_test', self.cbus, query_type=canmessage.QUERY_OPCODES,
                                      query=canmessage.event_opcodes)
        while True:
            msg = await sub.wait()
            self.logger.log(f'pubsub_test_coro: got subscribed event = {tuple(msg)}')
            pevent.set()

    async def sensor_test_coro(self, pevent: asyncio.Event) -> None:
        event = asyncio.Event()
        self.sn1 = cbusobjects.binary_sensor('sensor1', mod.cbus, ((0, 22, 23), (1, 22, 23)), (0, 22, 33))
        self.logger.log(
            f'sensor_test_coro: start, {self.sn1.name} state = {cbusobjects.sensor_states.get(self.sn1.state)}')

        while True:
            await event.wait()
            event.clear()
            self.logger.log(
                f'sensor_test_coro: {self.sn1.name} changed state to {self.sn1.state} = {cbusobjects.sensor_states.get(self.sn1.state)}')
            pevent.set()

    async def any_test_coro(self) -> None:
        self.logger.log('any_test_coro: start')

        evt = asyncio.Event()
        timer = cbusobjects.timeout(5_000, evt)

        evp = asyncio.Event()
        evs = asyncio.Event()
        evh = asyncio.Event()

        tp = asyncio.create_task(self.pubsub_test_coro(evp))
        ts = asyncio.create_task(self.sensor_test_coro(evs))
        th = asyncio.create_task(self.history_test_coro(evh))
        tt = asyncio.create_task(timer.one_shot())

        while True:
            evw = await WaitAny((evt, evp, evs, evh)).wait()

            if evw is evt:
                self.logger.log('any_test_coro: timer expired')
                tt.cancel()
            elif evw is evp:
                self.logger.log('any_test_coro: pubsub_test_coro event was set')
            elif evw is evs:
                self.logger.log('any_test_coro: sensor_test_coro event was set')
            elif evw is evh:
                self.logger.log('any_test_coro: history_test_coro event was set')
            else:
                self.logger.log('any_test_coro: unknown event')

            evw.clear()

    async def module_main_loop(self):
        self.logger.log('module_main_loop: start')
        while True:
            await asyncio.sleep_ms(50)

    # ***
    # *** module main entry point
    # ***

    async def run(self) -> None:

        # loop = asyncio.get_event_loop()
        # loop.set_exception_handler(self._handle_exception)

        # module has been reset - do one-time config here
        if self.cbus.config.was_reset:
            self.logger.log('module was reset')
            self.cbus.config.set_reset_flag(False)

        # test co-routines
        t0 = asyncio.create_task(self.blink_led_coro())
        t1 = asyncio.create_task(self.any_test_coro())
        t2 = asyncio.create_task(self.module_main_loop())

        self.logger.log('asyncio is now running the module main loop and co-routines')

        # start async REPL and wait for exit
        repl = asyncio.create_task(aiorepl.task(globals()))
        await asyncio.gather(repl)

    # ***
    # *** end of module class
    # ***


def _handle_exception(self, loop, context):
    import sys
    print('Global handler')
    sys.print_exception(context['exception'])


#         #loop.stop()
#         sys.exit()  # Drastic - loop.stop() does not work when used this way

wc = None
fc = None


def ttest() -> None:
    import cbusclocks
    global wc, fc
    wc = cbusclocks.cbusclock(mod.cbus, cbusclocks.WALLCLOCK, 0, mod.is_picow, ntp_server)
    fc = cbusclocks.cbusclock(mod.cbus, cbusclocks.FASTCLOCK, 0, False)
    fc.set_multiplier(4)
    fc.resume()


sv = None
sg = None


def servo_test() -> None:
    import cbusservo
    global sv, sg
    sv = cbusservo.cbusservo('sv', 10, 0, 255)
    sv.set_consumer_events(mod.cbus, ((0, 22, 28), (1, 22, 28)))
    sv.set_producer_events(mod.cbus,
                           (((0, 22, 30), (1, 22, 30)), ((0, 22, 31), (1, 22, 31)), ((0, 22, 32), (1, 22, 32))))
    sg = cbusservo.cbusservogroup('sg', (sv, sv), (0, 1))


# some test messages
msg1 = canmessage.canmessage(99, 5, [0x90, 0, 22, 0, 25])
msg2 = canmessage.canmessage(99, 5, [0xE9, 1, 0, 0, 24, 0, 0, 0])
msg3 = canmessage.canmessage(4, 5, [0x91, 0, 22, 0, 23, 0, 0, 0])
msg4 = canmessage.canmessage(4, 5, [0x90, 0, 22, 0, 23, 0, 0, 0])
msg5 = canmessage.canmessage(126, 0, [], True, False)
msg6 = canmessage.canmessage(126, 0, [], False, True)

lm0 = canmessage.canmessage(126, 8, [0xE9, 2, 0, 0, 11, 0, 0, 0])
lm1 = canmessage.canmessage(126, 8, [0xE9, 2, 1, 72, 101, 108, 108, 111])
lm2 = canmessage.canmessage(126, 8, [0xE9, 2, 2, 32, 119, 111, 114, 108])
lm3 = canmessage.canmessage(126, 8, [0xE9, 2, 3, 100, 0, 0, 0, 0])


def enq() -> None:
    mod.logger.log('test messages')
    # mod.cbus.can.rx_queue.enqueue(msg3)
    # mod.cbus.can.rx_queue.enqueue(msg4)
    mod.cbus.send_cbus_message(msg3)
    mod.cbus.send_cbus_message(msg4)


def enq3() -> None:
    # mod.cbus.send_cbus_message(msg3)
    mod.cbus.can.rx_queue.enqueue(msg3)


def enq4() -> None:
    # mod.cbus.send_cbus_message(msg4)
    mod.cbus.can.rx_queue.enqueue(msg4)


def out(n) -> None:
    tstart = time.ticks_ms()

    for x in range(n):
        mod.cbus.send_cbus_message(msg3)
        mod.cbus.send_cbus_message(msg4)

    print(time.ticks_diff(time.ticks_ms(), tstart))


# def lms() -> None:
#     mod.logger.log('test long messages')
#     mod.cbus.can.rx_queue.enqueue(lm0)
#     mod.cbus.can.rx_queue.enqueue(lm1)
#     mod.cbus.can.rx_queue.enqueue(lm2)
#     mod.cbus.can.rx_queue.enqueue(lm3)

def wconnect() -> None:
    mod.connect_wifi()


mod = mymodule()
# mod.initialise(is_picow=True, start_gc_server=False)
mod.initialise()
# mod.initialise(True, False)

evt3 = canmessage.event_from_message(mod.cbus, msg3)
evt4 = canmessage.event_from_tuple(mod.cbus, tuple(msg3))
evt5 = canmessage.event_from_table(mod.cbus, 0)

t1 = cbusobjects.turnout('t1',
                         mod.cbus,
                         control_events=((0, 22, 25), (1, 22, 25)),
                         initial_state=cbusobjects.TURNOUT_STATE_UNKNOWN,
                         sensor_events=((0, 22, 26), (1, 22, 26)))

s1 = cbusobjects.semaphore_signal('s1',
                                  mod.cbus,
                                  control_events=((0, 22, 27), (1, 22, 27)),
                                  initial_state=cbusobjects.SIGNAL_STATE_UNKNOWN)

s2 = cbusobjects.semaphore_signal('s2',
                                  mod.cbus,
                                  control_events=((0, 22, 28), (1, 22, 28)),
                                  initial_state=cbusobjects.SIGNAL_STATE_UNKNOWN)

tobj1 = cbusroutes.routeobject(t1, cbusobjects.TURNOUT_STATE_CLOSED)
sobj1 = cbusroutes.routeobject(s1, cbusobjects.SIGNAL_STATE_SET, cbusobjects.WHEN_BEFORE)
sobj2 = cbusroutes.routeobject(s2, cbusobjects.SIGNAL_STATE_CLEAR, cbusobjects.WHEN_AFTER)

r = cbusroutes.route('r1', mod.cbus, (tobj1, sobj1, sobj2,), None, None, False, 0)
r2 = cbusroutes.route('r2', mod.cbus, (tobj1, sobj1, sobj2,), None, None, False, 0)

nx = None
load_data = []


def nxtest() -> None:
    global nx
    nx = cbusroutes.entry_exit('nx', mod.cbus, r, ((0, 22, 50), (0, 22, 51)), ())


def load(num: int, with_sensor: bool = False) -> None:
    global load_data
    load_data = []
    for x in range(num):
        if with_sensor:
            load_data.append(
                cbusobjects.turnout(f't{x}', mod.cbus, ((0, 22, x), (1, 22, x)), -1, ((0, 23, x), (1, 23, x))))
        else:
            load_data.append(cbusobjects.turnout(f't{x}', mod.cbus, ((0, 22, x), (1, 22, x)), -1, ))


def op(which):
    for t in load_data:
        if which:
            await t.throw()
        else:
            await t.close()


mov = 0


def move_test():
    global mov

    st1 = cbusroutes.step(t1, cbusroutes.STEP_TURNOUT, 0)
    st2 = cbusroutes.step(s1, cbusroutes.STEP_SIGNAL_HOME, 0)
    st3 = cbusroutes.step(mod.sn1, cbusroutes.STEP_SENSOR, 0)

    steps = (st1, st2, st3)
    mov = cbusroutes.movement('mov', mod.cbus, steps)


# *** start the scheduler and run the app class main method
asyncio.run(mod.run())

# *** the asyncio scheduler is now in control
# *** no code after this line is executed
