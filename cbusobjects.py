# cbussensor.py
# a CBUS sensor implementation

import uasyncio as asyncio
from micropython import const

import canmessage
import cbusdefs
import cbuspubsub
import logger
import primitives

WAIT_FOREVER = const(-1)

STATE_UNKNOWN = const(-1)
STATE_OFF = const(0)
STATE_ON = const(1)

WHEN_DONT_CARE = const(-1)
WHEN_BEFORE = const(0)
WHEN_AFTER = const(1)
WHEN_BOTH = const(2)

SENSOR_STATE_UNKNOWN = const(-1)
SENSOR_STATE_OFF = const(0)
SENSOR_STATE_ON = const(1)

sensor_states = {
    SENSOR_STATE_UNKNOWN: "Unknown",
    SENSOR_STATE_OFF: "Off",
    SENSOR_STATE_ON: "On"
}

TURNOUT_STATE_UNKNOWN = const(-1)
TURNOUT_STATE_CLOSED = const(0)
TURNOUT_STATE_THROWN = const(1)

turnout_states = {
    TURNOUT_STATE_UNKNOWN: "Unknown",
    TURNOUT_STATE_CLOSED: "Closed",
    TURNOUT_STATE_THROWN: "Thrown"
}

SIGNAL_STATE_UNKNOWN = const(-1)
SIGNAL_STATE_CLEAR = const(0)
SIGNAL_STATE_DANGER = const(1)

signal_states = {
    SIGNAL_STATE_UNKNOWN: "Unknown",
    SIGNAL_STATE_CLEAR: "Clear",
    SIGNAL_STATE_DANGER: "Danger"
}

SIGNAL_TYPE_UNKNOWN = const(-1)
SIGNAL_TYPE_STOP = const(0)
SIGNAL_TYPE_DISTANT = const(1)

signal_types = {
    SIGNAL_TYPE_UNKNOWN: "Unknown",
    SIGNAL_TYPE_STOP: "Stop",
    SIGNAL_TYPE_DISTANT: "Distant"
}

SIGNAL_COLOUR_RED = const(0)
SIGNAL_COLOUR_YELLOW = const(1)
SIGNAL_COLOUR_DOUBLE_YELLOW = const(2)
SIGNAL_COLOUR_GREEN = const(3)

TYPE_TURNOUT = const(0)
TYPE_SIGNAL = const(1)

ROUTE_STATE_UNKNOWN = const(0)
ROUTE_STATE_SET = const(1)

MAX_TIMEOUT = const(2_147_483_647)

presume_ok = True


class timeout:
    def __init__(self, ms, evt):
        self.ms = ms if ms >= 0 else MAX_TIMEOUT
        self.event = evt

    async def one_shot(self):
        await asyncio.sleep_ms(self.ms)
        self.event.set()

    async def recurrent(self):
        while True:
            await asyncio.sleep_ms(self.ms)
            self.event.set()


class sensor:
    def __init__(self, name, cbus, query_events, init_event, evt=None, default=SENSOR_STATE_UNKNOWN):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.query_events = query_events
        self.init_event = init_event
        self.evt = evt
        self.state = SENSOR_STATE_UNKNOWN

        if isinstance(self.evt, asyncio.Event):
            self.evt.clear()

        self.sub = cbuspubsub.subscription(self.name + ':sub', self.cbus, init_event, canmessage.QUERY_ALL)

        # send AREQ to get current state
        msg = canmessage.canmessage(0, 5)
        msg.data[0] = init_event[0]
        msg.data[1] = init_event[1]
        msg.data[2] = init_event[2]
        cbus.send_cbus_message(msg)

        # wait for ARON/AROF response
        msg = await self.sub.wait()

        self.state = msg.data[0] == cbusdefs.OPC_ARON
        self.sub.unsubscribe(init_event)

        # main sub
        self.sub = cbuspubsub.subscription(self.name + ':sub', self.cbus, query_events, canmessage.QUERY_ALL)

    def dispose(self):
        self.sub.unsubscribe(self.query_events)


class binarysensor(sensor):
    def __init__(self, name, cbus, query_event, init_event, evt=None, default=SENSOR_STATE_UNKNOWN):
        super().__init__(name, cbus, query_event, init_event, evt, default)
        self.state = default
        self.task = asyncio.create_task(self.run())

    async def run(self) -> None:
        while True:
            msg = await self.sub.wait()
            if msg.len > 0:
                new_state = SENSOR_STATE_OFF if msg.data[0] & 1 else SENSOR_STATE_ON
                if self.state != new_state:
                    self.state = new_state
                    if isinstance(self.evt, asyncio.Event):
                        self.evt.set()

    def dispose(self):
        self.task.cancel()
        super().dispose()


class valuesensor(sensor):
    def __init__(self, name, cbus, query_event, init_event, evt=None, default=SENSOR_STATE_UNKNOWN):
        super().__init__(name, cbus, query_event, init_event, evt, default)
        self.value = default
        self.task = asyncio.create_task(self.run())

    async def run(self) -> None:
        while True:
            msg = await self.sub.wait()
            if msg.len > 0:
                self.value = 99
                if isinstance(self.evt, asyncio.Event):
                    self.evt.set()

    def dispose(self):
        self.task.cancel()
        super().dispose()


class turnout:
    def __init__(self, name, cbus, turnout_events, query_event, initial_state=TURNOUT_STATE_CLOSED, create_sensor=False,
                 sensor_events=None, init=False):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.turnout_events = turnout_events
        self.state = initial_state
        self.create_sensor = create_sensor
        self.sensor_events = sensor_events

        self.sensor = None
        self.sensor_evt = None
        self.sensor_task = None
        self.lock = None
        self.timeout = None
        self.timeout_evt = None

        if create_sensor and sensor_events and len(sensor_events) == 2:
            self.sensor_evt = asyncio.Event()
            self.sensor = binarysensor(name + ":sensor", self.cbus, self.sensor_events, self.sensor_evt)
            self.sensor_task = asyncio.create_task(self.sensor_run())
            self.timeout_evt = asyncio.Event()
            self.timeout = timeout(2000, self.timeout_evt)

        if init:
            if initial_state == TURNOUT_STATE_CLOSED:
                self.close()
            else:
                self.throw()

    def dispose(self) -> None:
        self.sensor_task.cancel()
        self.sensor.dispose()

    def get_state(self) -> int:
        return self.state

    def is_closed(self) -> bool:
        return self.state == TURNOUT_STATE_CLOSED

    def is_thrown(self) -> bool:
        return not self.is_closed()

    def throw(self) -> None:
        self.operate(TURNOUT_STATE_THROWN)

    def close(self) -> None:
        self.operate(TURNOUT_STATE_CLOSED)

    def operate(self, state):
        if state == TURNOUT_STATE_THROWN:
            opc = self.turnout_events[0][0]
            nn = self.turnout_events[0][1]
            en = self.turnout_events[0][2]
            msg = canmessage.cbusevent(self.cbus, True, nn, en, canmessage.EVENT_ON)
            msg.send_on()
            self.state = TURNOUT_STATE_UNKNOWN if self.create_sensor else TURNOUT_STATE_THROWN
        else:
            opc = self.turnout_events[1][0]
            nn = self.turnout_events[1][1]
            en = self.turnout_events[1][2]
            msg = canmessage.cbusevent(self.cbus, True, nn, en, canmessage.EVENT_ON)
            msg.send_off()
            self.state = TURNOUT_STATE_UNKNOWN if self.create_sensor else TURNOUT_STATE_CLOSED

        if self.create_sensor:
            asyncio.create_task((self.timeout.one_shot()))
            evw = await primitives.WaitAny((self.timeout_evt, self.sensor.evt)).wait()

            if evw is self.timeout_evt:
                self.logger.log('timeout')
                self.state = TURNOUT_STATE_UNKNOWN
            else:
                self.state = self.sensor.state
                self.logger.log(f'turnout state = {self.state}')

    async def sensor_run(self) -> None:
        while True:
            await self.sensor_evt.wait()
            self.sensor_evt.clear()
            self.state = self.sensor.state
            self.logger.log(f"turnout sensor {self.sensor.name} triggered, state = {self.sensor.state}")


# class turnoutgroup:
#     def __init__(self, turnouts, states, init=False):
#         self.logger = logger.logger()
#         self.turnouts = turnouts
#         self.states = states
#
#         if init:
#             self.set()
#
#     def set(self) -> None:
#         for i, t in enumerate(self.turnouts):
#             t.throw() if self.states[i] else t.close()
#
#     def unset(self) -> None:
#         for i, t in enumerate(self.turnouts):
#             t.close() if self.states[i] else t.throw()


class signal:
    def __init__(self, name, cbus, create_sensor=False, sensor_events=None):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.create_sensor = create_sensor
        self.sensor_events = sensor_events
        self.sensor = None
        self.sensor_evt = None
        self.task = None
        self.lock = None

        if create_sensor and sensor_events and len(sensor_events) == 2:
            self.sensor_evt = asyncio.Event()
            self.sensor = binarysensor(name + ":sensor", self.cbus, self.sensor_events, self.sensor_evt)
            # self.task = asyncio.create_task(self.sensor_run())


class semaphore_signal(signal):
    def __init__(self, name, cbus, signal_events, initial_state=SIGNAL_STATE_UNKNOWN, create_sensor=False,
                 sensor_events=None, init=False):
        super().__init__(name, cbus, create_sensor, sensor_events)
        self.signal_events = signal_events
        self.initial_state = initial_state
        self.init = init
        self.state = SIGNAL_STATE_UNKNOWN

        if self.init and initial_state != SIGNAL_STATE_UNKNOWN:
            if initial_state == SIGNAL_STATE_CLEAR:
                self.clear()
            else:
                self.set()

    def dispose(self):
        self.task.cancel()
        self.sensor.dispose()

    def set(self) -> None:
        opc = self.signal_events[1][0]
        nn = self.signal_events[1][1]
        en = self.signal_events[1][2]
        msg = canmessage.cbusevent(self.cbus, True, nn, en, canmessage.EVENT_ON)
        msg.send_on()

        if self.create_sensor:
            self.state = SIGNAL_STATE_UNKNOWN
        else:
            self.state = SIGNAL_STATE_DANGER

    def clear(self) -> None:
        opc = self.signal_events[1][0]
        nn = self.signal_events[1][1]
        en = self.signal_events[1][2]
        msg = canmessage.cbusevent(self.cbus, True, nn, en, canmessage.EVENT_OFF)
        msg.send_off()
        self.state = SIGNAL_STATE_CLEAR

        if self.create_sensor:
            self.state = SIGNAL_STATE_UNKNOWN
        else:
            self.state = SIGNAL_STATE_DANGER

    async def sensor_run(self) -> None:
        while True:
            await self.sensor_evt.wait()
            self.sensor_evt.clear()
            self.state = self.sensor.state
            self.logger.log(f"signal sensor {self.sensor.name} triggered, state = {self.sensor.state}")


class colour_signal_two(signal):
    def __init__(self):
        super().__init__()


class colour_signal_three(signal):
    def __init__(self):
        super().__init__()


class colour_signal_four(signal):
    def __init__(self):
        super().__init__()


class routeobject:
    def __init__(self, robject, state, when=WHEN_DONT_CARE):
        self.robject = robject
        self.state = state
        self.when = when


class route:
    def __init__(self, name, cbus, robjects, lock_event=None, complete_event=None, sequential=False, delay=0):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.robjects = robjects
        self.lock_event = lock_event
        self.complete_event = complete_event
        self.sequential = sequential
        self.delay = delay

        self.lock = asyncio.Lock()
        self.locked_objects = []

    def acquire(self) -> bool:
        all_objects_locked = True

        if self.lock.locked():
            all_objects_locked = False
        else:
            await self.lock.acquire()

            for obj in self.robjects:
                if isinstance(obj.robject.lock, asyncio.Lock):
                    if obj.robject.lock.locked():
                        all_objects_locked = False
                        break
                    else:
                        await obj.robject.lock.acquire()
                        self.locked_objects.append(obj)
                else:
                    obj.robject.lock = asyncio.Lock()
                    await obj.robject.lock.acquire()
                    self.locked_objects.append(obj)

            if not all_objects_locked:
                for obj in self.locked_objects:
                    obj.robject.lock.release()
                self.lock.release()

        if self.lock_event:
            event_state = canmessage.EVENT_ON if all_objects_locked else canmessage.EVENT_OFF
            msg = canmessage.cbusevent(self.cbus, True, self.lock_event[1], self.lock_event[2], event_state)
            if all_objects_locked:
                msg.send_on()
            else:
                msg.send_off()

        return all_objects_locked

    def release(self) -> None:

        for obj in self.locked_objects:
            if obj.robject.lock.locked():
                try:
                    obj.robject.lock.release()
                except RuntimeError:
                    pass

        self.locked_objects = []

        try:
            self.lock.release()
        except RuntimeError:
            pass

    def set(self) -> None:
        if not self.lock.locked():
            self.logger.log('route not locked')
            return

        for obj in self.robjects:
            if isinstance(obj, turnout):
                if obj.state == TURNOUT_STATE_CLOSED:
                    obj.close()
                else:
                    obj.throw()
                # TODO: if object has sensor, wait for feedback, with timeout
            elif isinstance(obj, semaphore_signal):
                if obj.state == SIGNAL_STATE_CLEAR:
                    obj.clear()
                else:
                    obj.set()
                # TODO: if object has sensor, wait for feedback, with timeout
