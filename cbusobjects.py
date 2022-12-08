# cbussensor.py
# a CBUS sensor implementation
import uasyncio as asyncio
from micropython import const

import canmessage
import cbus
import cbusdefs
import cbuspubsub
import logger
from primitives import WaitAny

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
SENSOR_STATE_VALID = const(2)

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
SIGNAL_COLOUR_GREEN = const(1)
SIGNAL_COLOUR_YELLOW = const(2)
SIGNAL_COLOUR_DOUBLE_YELLOW = const(3)

TYPE_TURNOUT = const(0)
TYPE_SIGNAL = const(1)

ROUTE_STATE_UNKNOWN = const(0)
ROUTE_STATE_SET = const(1)

MAX_TIMEOUT = const(2_147_483_647)

presume_ok = True


class timeout:
    def __init__(self, ms: int, evt: asyncio.Event):
        self.ms = ms if ms >= 0 else MAX_TIMEOUT
        self.event = evt

    async def one_shot(self) -> None:
        await asyncio.sleep_ms(self.ms)
        self.event.set()
        self.event.clear()

    async def recurrent(self) -> None:
        while True:
            await asyncio.sleep_ms(self.ms)
            self.event.set()
            self.event.clear()


class sensor:
    def __init__(self, name, cbus: cbus.cbus, sensor_event: tuple, query_message: tuple, evt=None):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.sensor_event = sensor_event
        self.query_message = query_message
        self.evt = evt
        self.state = SENSOR_STATE_UNKNOWN
        self.sub = None

        if isinstance(self.evt, asyncio.Event):
            self.evt.clear()

    def dispose(self):
        self.sub.unsubscribe(self.sensor_event)


class binarysensor(sensor):
    def __init__(self, name, cbus: cbus.cbus, sensor_event: tuple, query_message: tuple, evt=None):
        super().__init__(name, cbus, sensor_event, query_message, evt)
        self.sync_state()
        self.task = asyncio.create_task(self.run())
        self.sub = cbuspubsub.subscription(name + ':sub', self.cbus, self.sensor_event, canmessage.QUERY_ALL)

    def sync_state(self):
        if self.query_message and len(self.query_message) == 2:
            self.sub = cbuspubsub.subscription(self.name + ':sub', self.cbus, self.query_message[1],
                                               canmessage.QUERY_TUPLES)
            msg = canmessage.event_from_tuple(self.cbus, self.query_message[0])
            msg.send()

            msg = await self.sub.wait()
            self.state = msg.data[0] == cbusdefs.OPC_ARON
            self.sub.unsubscribe(self.query_message)

    async def run(self) -> None:
        while True:
            msg = await self.sub.wait()
            if msg.dlc > 0:
                new_state = SENSOR_STATE_OFF if msg.data[0] & 1 else SENSOR_STATE_ON
                if self.state != new_state:
                    self.state = new_state
                    if isinstance(self.evt, asyncio.Event):
                        self.evt.set()

    def dispose(self):
        self.task.cancel()
        super().dispose()


class valuesensor(sensor):
    def __init__(self, name, cbus: cbus.cbus, sensor_event, init_message, evt=None):
        super().__init__(name, cbus, sensor_event, init_message, evt)
        self.value = -1
        self.task = asyncio.create_task(self.run())

    def sync(self):
        pass

    def interpret(self, msg):
        self.value = 99
        self.state = SENSOR_STATE_VALID

    async def run(self) -> None:
        while True:
            msg = await self.sub.wait()
            self.interpret(msg)
            if isinstance(self.evt, asyncio.Event):
                self.evt.set()

    def dispose(self):
        self.task.cancel()
        super().dispose()


class turnout:
    def __init__(self, name, cbus: cbus.cbus, turnout_event, query_event, initial_state=TURNOUT_STATE_CLOSED,
                 has_sensor=False,
                 sensor_event=None, init=False):
        self.logger = logger.logger()
        self.cbus = cbus
        self.name = name
        self.turnout_event = turnout_event
        self.query_event = query_event
        self.state = initial_state
        self.has_sensor = has_sensor
        self.sensor_event = sensor_event

        self.sensor = None
        self.sensor_evt = None
        self.sensor_task = None
        self.lock = None
        self.timeout = None
        self.timeout_evt = None

        if has_sensor and sensor_event and len(sensor_event) == 2:
            self.sensor_evt = asyncio.Event()
            self.sensor = binarysensor(name + ':sensor', cbus, self.query_event, self.turnout_event,
                                       self.sensor_evt)
            self.sensor_task = asyncio.create_task(self.sensor_run())
            self.timeout_evt = asyncio.Event()
            self.timeout = timeout(2000, self.timeout_evt)

        if init:
            if initial_state == TURNOUT_STATE_CLOSED:
                self.close()
            else:
                self.throw()

    def dispose(self) -> None:
        if self.has_sensor:
            self.sensor_task.cancel()
            self.sensor.dispose()

    async def throw(self) -> bool:
        return await self.operate(TURNOUT_STATE_THROWN)

    async def close(self) -> bool:
        return await self.operate(TURNOUT_STATE_CLOSED)

    async def operate(self, target_state) -> bool:
        if target_state == TURNOUT_STATE_CLOSED and self.state != TURNOUT_STATE_CLOSED:
            ev = canmessage.event_from_tuple(self.cbus, self.turnout_event[0])
            ev.send_on()
            self.state = TURNOUT_STATE_UNKNOWN if self.has_sensor else TURNOUT_STATE_CLOSED
        elif target_state == TURNOUT_STATE_THROWN and self.state != TURNOUT_STATE_THROWN:
            ev = canmessage.event_from_tuple(self.cbus, self.turnout_event[1])
            ev.send_off()
            self.state = TURNOUT_STATE_UNKNOWN if self.has_sensor else TURNOUT_STATE_THROWN

        if self.has_sensor:
            t = asyncio.create_task((self.timeout.one_shot()))
            evw = await WaitAny((self.timeout_evt, self.sensor.evt)).wait()

            if evw is self.timeout_evt:
                # self.logger.log('timeout')
                self.state = TURNOUT_STATE_UNKNOWN
                return False
            else:
                self.state = self.sensor.state
                # self.logger.log(f'turnout state = {self.state}')

        return True

    async def sensor_run(self) -> None:
        while True:
            await self.sensor_evt.wait()
            self.sensor_evt.clear()
            self.state = self.sensor.state
            self.logger.log(f"turnout sensor {self.sensor.name} triggered, state = {self.sensor.state}")


class semaphore_signal:
    def __init__(self, name, cbus, signal_event, query_event, initial_state=SIGNAL_STATE_UNKNOWN,
                 has_sensor=False, sensor_event=None, init=False):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.signal_event = signal_event
        self.query_event = query_event
        self.has_sensor = has_sensor
        self.sensor_event = sensor_event
        self.state = SIGNAL_STATE_UNKNOWN

        self.sensor = None
        self.sensor_evt = None
        self.sensor_task = None
        self.lock = None
        self.timeout = None
        self.timeout_evt = None

        if init and initial_state != SIGNAL_STATE_UNKNOWN:
            if initial_state == SIGNAL_STATE_CLEAR:
                self.clear()
            else:
                self.set()

        if has_sensor and query_event and len(query_event) == 2:
            self.sensor_evt = asyncio.Event()
            self.sensor = binarysensor(name + ":sensor", self.cbus, self.sensor_event, self.query_event,
                                       self.sensor_evt)
            self.sensor_task = asyncio.create_task(self.sensor_run())

    def dispose(self):
        self.sensor_task.cancel()
        self.sensor.dispose()

    def set(self) -> None:
        nn = self.signal_event[1][1]
        en = self.signal_event[1][2]
        msg = canmessage.cbusevent(self.cbus, nn, en, canmessage.POLARITY_ON)
        msg.send_on()

        if self.has_sensor:
            self.state = SIGNAL_STATE_UNKNOWN
        else:
            self.state = SIGNAL_STATE_DANGER

    def clear(self) -> None:
        nn = self.signal_event[1][1]
        en = self.signal_event[1][2]
        msg = canmessage.cbusevent(self.cbus, nn, en, canmessage.POLARITY_OFF)
        msg.send_off()
        self.state = SIGNAL_STATE_CLEAR

        if self.has_sensor:
            self.state = SIGNAL_STATE_UNKNOWN
        else:
            self.state = SIGNAL_STATE_DANGER

    async def sensor_run(self) -> None:
        while True:
            await self.sensor_evt.wait()
            self.sensor_evt.clear()
            self.state = self.sensor.state
            self.logger.log(f"signal sensor {self.sensor.name} triggered, state = {self.sensor.state}")


class colour_light_signal:
    def __init__(self, name, cbus, num_aspects, signal_events, initial_state, init=False):
        self.name = name
        self.cbus = cbus
        self.num_aspects = num_aspects
        self.signal_events = signal_events
        self.state = initial_state if init else SIGNAL_STATE_UNKNOWN

    def set_aspect(self, aspect):
        if aspect < self.num_aspects:
            on = self.signal_events[aspect][0]
            nn = self.signal_events[aspect][1]
            en = self.signal_events[aspect][2]
            msg = canmessage.cbusevent(self.cbus, nn, en, on)
            msg.send_on() if on else msg.send_off()
            self.state = aspect
        else:
            raise ValueError('invalid state')


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
            event_state = canmessage.POLARITY_ON if all_objects_locked else canmessage.POLARITY_OFF
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
                # TODO: if object has sensor and is sequential, wait for feedback, with timeout
            elif isinstance(obj, semaphore_signal):
                if obj.state == SIGNAL_STATE_CLEAR:
                    obj.clear()
                else:
                    obj.set()
                # TODO: if object has sensor and is sequential, wait for feedback, with timeout
            elif isinstance(obj, colour_light_signal):
                obj.set_aspect(obj.state)

            await asyncio.sleep_ms(self.delay)
