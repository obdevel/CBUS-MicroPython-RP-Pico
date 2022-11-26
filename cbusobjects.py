# cbussensor.py
# a CBUS sensor implementation

import uasyncio as asyncio
from micropython import const

import canmessage
import cbuspubsub
import logger

WAIT_FOREVER = const(-1)

STATE_UNKNOWN = const(-1)
STATE_OFF = const(0)
STATE_ON = const(1)

WHEN_DONT_CARE = const(-1)
WHEN_BEFORE = const(0)
WHEN_AFTER = const(1)

SENSOR_STATE_UNKNOWN = const(-1)
SENSOR_STATE_OFF = const(0)
SENSOR_STATE_ON = const(1)

sensor_states = {
    SENSOR_STATE_UNKNOWN: "Unknown",
    SENSOR_STATE_OFF: "Off",
    SENSOR_STATE_ON: "On"
}

sensor_list = {}

TURNOUT_STATE_UNKNOWN = const(-1)
TURNOUT_STATE_CLOSED = const(0)
TURNOUT_STATE_THROWN = const(1)

turnout_states = {
    TURNOUT_STATE_UNKNOWN: "Unknown",
    TURNOUT_STATE_CLOSED: "Closed",
    TURNOUT_STATE_THROWN: "Thrown"
}

turnout_list = {}

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

TYPE_TURNOUT = const(0)
TYPE_SIGNAL = const(1)

signal_list = {}
route_list = {}

MAX_TIMEOUT = const(2_147_483_647)


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
    def __init__(self, name, cbus, query, event=None, default=SENSOR_STATE_UNKNOWN):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.query = query
        self.event = event
        self.sub = cbuspubsub.subscription(self.name + ':sub', self.cbus, query, canmessage.QUERY_ALL)
        sensor_list[name] = self

        if isinstance(self.event, asyncio.Event):
            self.event.clear()


class binarysensor(sensor):
    def __init__(self, name, cbus, query, event=None, default=SENSOR_STATE_UNKNOWN):
        super().__init__(name, cbus, query, event, default)
        self.state = default
        asyncio.create_task(self.run())

    async def run(self) -> None:
        while True:
            msg = await self.sub.wait()
            if msg.len > 0:
                new_state = SENSOR_STATE_OFF if msg.data[0] & 1 else SENSOR_STATE_ON
                if self.state != new_state:
                    self.state = new_state
                    if isinstance(self.event, asyncio.Event):
                        self.event.set()


class valuesensor(sensor):
    def __init__(self, name, cbus, query, event=None, default=-1):
        super().__init__(name, cbus, query, event, default)
        asyncio.create_task(self.run())
        self.value = default

    async def run(self) -> None:
        while True:
            msg = await self.sub.wait()
            if msg.len > 0:
                self.value = 99
                if isinstance(self.event, asyncio.Event):
                    self.event.set()


class turnout:
    def __init__(self, name, cbus, turnout_events, initial_state=TURNOUT_STATE_CLOSED, create_sensor=False,
                 sensor_events=None, init=False):
        self.logger = logger.logger()
        turnout_list[name] = self
        self.name = name
        self.cbus = cbus
        self.turnout_events = turnout_events
        self.state = initial_state
        self.create_sensor = create_sensor
        self.sensor_events = sensor_events

        self.sensor = None
        self.sensor_event = None
        self.sensor_task = None
        self.lock = None

        if init:
            if initial_state == TURNOUT_STATE_CLOSED:
                self.close()
            else:
                self.throw()

        if create_sensor and sensor_events is not None:
            self.sensor_evt = asyncio.Event()
            self.sensor = binarysensor(name + ":sensor", self.cbus, self.sensor_events, self.sensor_evt)
            self.sensor_task = asyncio.create_task(self.sensor_run())

    def get_state(self) -> int:
        return self.state

    def is_closed(self) -> bool:
        return self.state == TURNOUT_STATE_CLOSED

    def is_thrown(self) -> bool:
        return not self.is_closed()

    def throw(self) -> None:
        opc = self.turnout_events[0][0]
        nn = self.turnout_events[0][1]
        en = self.turnout_events[0][2]
        msg = canmessage.cbusevent(self.cbus, True, nn, en, canmessage.EVENT_ON)
        msg.send_on()
        self.state = TURNOUT_STATE_UNKNOWN if self.create_sensor else TURNOUT_STATE_THROWN

    def close(self) -> None:
        opc = self.turnout_events[1][0]
        nn = self.turnout_events[1][1]
        en = self.turnout_events[1][2]
        msg = canmessage.cbusevent(self.cbus, True, nn, en, canmessage.EVENT_ON)
        msg.send_off()
        self.state = TURNOUT_STATE_UNKNOWN if self.create_sensor else TURNOUT_STATE_CLOSED

    async def sensor_run(self) -> None:
        while True:
            await self.sensor_evt.wait()
            self.sensor_evt.clear()
            self.state = self.sensor.state
            self.logger.log(f"turnout sensor {self.sensor.name} triggered, state = {self.sensor.state}")


class turnoutgroup:
    def __init__(self, turnouts, states, init=False):
        self.logger = logger.logger()
        self.turnouts = turnouts
        self.states = states

        if init:
            self.set()

    def set(self) -> None:
        for i, t in enumerate(self.turnouts):
            t.throw() if self.states[i] else t.close()

    def unset(self) -> None:
        for i, t in enumerate(self.turnouts):
            t.close() if self.states[i] else t.throw()


class signal:
    def __init__(self, name, cbus, create_sensor=False, sensor_events=None):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.create_sensor = create_sensor
        self.create_sensor = create_sensor
        self.sensor_events = sensor_events
        self.sensor = None
        self.sensor_evt = None
        self.task = None
        self.lock = None

        if create_sensor:
            self.sensor_evt = asyncio.Event()
            self.sensor = binarysensor(name + ":sensor", self.cbus, self.sensor_events, self.sensor_evt)
            self.task = asyncio.create_task(self.sensor_run())

        signal_list[name] = self


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
        self.name = name
        self.cbus = cbus
        self.robjects = robjects
        self.lock_event = lock_event
        self.complete_event = complete_event
        self.sequential = sequential
        self.delay = delay

        self.lock = asyncio.Lock()
        self.locked_objects = []
        route_list[self.name] = self

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
        pass
