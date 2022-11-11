# cbussensor.py
# a CBUS sensor implementation

import cbusdefs
import canmessage
import cbuspubsub
import logger
import uasyncio as asyncio
import sys
import time


WAIT_FOREVER = -1

STATE_UNKNOWN = -1
STATE_OFF = 0
STATE_ON = 1

WHEN_DONT_CARE = -1
WHEN_BEFORE = 0
WHEN_AFTER = 1

SENSOR_STATE_UNKNOWN = -1
SENSOR_STATE_OFF = 0
SENSOR_STATE_ON = 1

sensor_states = {
    SENSOR_STATE_UNKNOWN: "Unknown",
    SENSOR_STATE_OFF: "Off",
    SENSOR_STATE_ON: "On"
}

sensors = {}

TURNOUT_STATE_UNKNOWN = -1
TURNOUT_STATE_CLOSED = 0
TURNOUT_STATE_THROWN = 1

turnout_states = {
    TURNOUT_STATE_UNKNOWN: "Unknown",
    TURNOUT_STATE_CLOSED: "Closed",
    TURNOUT_STATE_THROWN: "Thrown"
}

turnouts = {}

SIGNAL_STATE_UNKNOWN = -1
SIGNAL_STATE_CLEAR = 0
SIGNAL_STATE_DANGER = 1

signal_states = {
    SIGNAL_STATE_UNKNOWN: "Unknown",
    SIGNAL_STATE_CLEAR: "Clear",
    SIGNAL_STATE_DANGER: "Danger"
}

SIGNAL_TYPE_UNKNOWN = -1
SIGNAL_TYPE_STOP = 0
SIGNAL_TYPE_DISTANT = 1

signal_types = {
    SIGNAL_TYPE_UNKNOWN: "Unknown",
    SIGNAL_TYPE_STOP: "Stop",
    SIGNAL_TYPE_DISTANT: "Distant"
}

signals = {}
routes = {}


class timeout:
    def __init__(self, ms, evt):
        self.ms = ms if ms >= 0 else sys.maxsize
        self.event = evt

    async def one_shot(self):
        await asyncio.sleep_ms(self.ms)
        self.event.set()


class sensor:
    def __init__(self, name, cbus, query, event=None, default=SENSOR_STATE_UNKNOWN):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.query = query
        self.event = event
        self.sub = cbuspubsub.subscription(self.name + ':sub', self.cbus, query, canmessage.QUERY_UNKNOWN)
        sensors[name] = self

        if isinstance(self.event, asyncio.Event):
            self.event.clear()

    def __del__(self):
        self.sub.unsubscribe(self.req)
        del sensor[self.name]

    def run(self) -> None:
        pass


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
    def __init__(self, name, cbus, turnout_events, initial_state=TURNOUT_STATE_CLOSED, create_sensor=False, sensor_events=None, init=False):
        self.logger = logger.logger()
        turnouts[name] = self
        self.name = name
        self.cbus = cbus
        self.turnout_events = turnout_events
        self.state = initial_state
        self.create_sensor = create_sensor
        self.sensor_events = sensor_events
        self.sensor = None
        self.event = None
        self.task = None
        self.lock = None

        if init:
            if initial_state == TURNOUT_STATE_CLOSED:
                self.close()
            else:
                self.throw()

        if create_sensor:
            self.event = asyncio.Event()
            self.sensor = binarysensor(name + ":sensor", self.cbus, self.sensor_events, self.event)
            self.task = asyncio.create_task(self.run())

    def __del__(self):
        if self.task is not None:
            self.task.cancel()
            del self.sensor
        del turnouts[self.name]

    def getstate(self) -> int:
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

    async def run(self) -> None:
        while True:
            await self.event.wait()
            self.event.clear()
            self.state = self.sensor.state
            self.logger.log(f"turnout sensor {self.sensor.name} triggered, state = {self.sensor.state}")


class turnoutgroup:
    def __init__(self, turnouts):
        self.logger = logger.logger()
        self.turnouts = turnouts

    def set(self, state) -> None:
        for t in self.turnouts:
            pass


class signal:
    def __init__(self, name, cbus, create_sensor=False, sensor_events=None):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.create_sensor = create_sensor
        self.create_sensor = create_sensor
        self.sensor_events = sensor_events
        self.sensor = None
        self.event = None
        self.task = None
        self.lock = None

        if create_sensor:
            self.event = asyncio.Event()
            self.sensor = binarysensor(name + ":sensor", self.cbus, self.sensor_events, self.event)
            self.task = asyncio.create_task(self.run())

        signals[name] = self


class semaphore_signal(signal):
    def __init__(self, name, cbus, signal_events, initial_state=SIGNAL_STATE_UNKNOWN, create_sensor=False, sensor_events=None, init=False):
        super().__init__(name, cbus, create_sensor, sensor_events)
        self.signal_events = signal_events
        self.initial_state = initial_state
        self.init = init
        self.state = SIGNAL_STATE_UNKNOWN

        if self.init and initial_state != SIGNAL_STATE_UNKNOWN:
            if initial_state == SIGNAL_STATE_CLEAR:
                self.clear()
            else:
                self.danger()

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

    async def run(self) -> None:
        while True:
            await self.event.wait()
            self.event.clear()
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
    def __init__(self, object, polarity, when):
        self.object = object
        self.polarity = polarity
        self.when = when


class route:
    def __init__(self, name, cbus, turnouts, signals, result_event=None, sequential=False):
        self.name = name
        self.cbus = cbus
        self.turnouts = turnouts
        self.signals = signals
        self.result_event = result_event
        self.lock = asyncio.Lock()
        self.locked_objects = []
        routes[self.name] = self

    def acquire(self) -> bool:
        all_objects_locked = True

        if self.lock.locked():
            all_objects_locked = False
        else:
            await self.lock.acquire()

            for obj in self.turnouts + self.signals:
                if isinstance(obj.object.lock, asyncio.Lock):
                    if obj.object.lock.locked():
                        all_objects_locked = False
                        break
                    else:
                        await obj.object.lock.acquire()
                        self.locked_objects.append(obj)
                else:
                    obj.object.lock = asyncio.Lock()
                    await obj.object.lock.acquire()
                    self.locked_objects.append(obj)

            if not all_objects_locked:
                for obj in self.locked_objects:
                    obj.object.lock.release()
                self.lock.release()

            if self.result_event:
                event_state = canmessage.EVENT_ON if all_objects_locked else canmessage.EVENT_ON
                msg = canmessage.cbusevent(self.cbus, True, self.result_event[1], self.result_event[2], event_state)
                if all_objects_locked:
                    msg.send_on()
                else:
                    msg.send_off()

        return all_objects_locked

    def release(self) -> None:

        for obj in self.locked_objects:
            if obj.object.lock.locked():
                try:
                    obj.object.lock.release()
                except:
                    pass

        self.locked_objects = []

        try:
            self.lock.release()
        except:
            pass

    def set(self) ->bool:
        pass

