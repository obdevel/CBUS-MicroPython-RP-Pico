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
    SENSOR_STATE_UNKNOWN: 'Unknown',
    SENSOR_STATE_OFF: 'Off',
    SENSOR_STATE_ON: 'On'
}

TURNOUT_STATE_UNKNOWN = const(-1)
TURNOUT_STATE_CLOSED = const(0)
TURNOUT_STATE_THROWN = const(1)

turnout_states = {
    TURNOUT_STATE_UNKNOWN: 'Unknown',
    TURNOUT_STATE_CLOSED: 'Closed',
    TURNOUT_STATE_THROWN: 'Thrown'
}

SIGNAL_STATE_UNKNOWN = const(-1)
SIGNAL_STATE_CLEAR = const(0)
SIGNAL_STATE_SET = const(1)

signal_states = {
    SIGNAL_STATE_UNKNOWN: 'Unknown',
    SIGNAL_STATE_CLEAR: 'Clear',
    SIGNAL_STATE_SET: 'Danger'
}

SIGNAL_TYPE_UNKNOWN = const(-1)
SIGNAL_TYPE_STOP = const(0)
SIGNAL_TYPE_DISTANT = const(1)

signal_types = {
    SIGNAL_TYPE_UNKNOWN: 'Unknown',
    SIGNAL_TYPE_STOP: 'Stop',
    SIGNAL_TYPE_DISTANT: 'Distant'
}

SIGNAL_COLOUR_RED = const(0)
SIGNAL_COLOUR_GREEN = const(1)
SIGNAL_COLOUR_YELLOW = const(2)
SIGNAL_COLOUR_DOUBLE_YELLOW = const(3)

TYPE_TURNOUT = const(0)
TYPE_SIGNAL = const(1)

ROUTE_STATE_UNKNOWN = const(0)
ROUTE_STATE_ACQUIRED = const(1)
ROUTE_STATE_SET = const(2)

MAX_TIMEOUT = const(2_147_483_647)
OP_TIMEOUT = 2_000


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


# class WaitAnyTimeout(WaitAny):
#     def __init__(self, events, to):
#         self.tevt = asyncio.Event()
#         self.to = timeout(to, self.tevt).one_shot()
#         self.events = list(events)
#         self.events.append(self.tevt)
#         super().__init__(self.events)


class sensor:
    def __init__(self, name, cbus: cbus.cbus, sensor_events: tuple, query_message: tuple, evt=None):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.sensor_events = sensor_events
        self.query_message = query_message
        self.evt = evt
        self.state = SENSOR_STATE_UNKNOWN
        self.sub = None

        # self.logger.log(f'sensor: name = {name}, sensor events = {self.sensor_events}')

        if isinstance(self.evt, asyncio.Event):
            self.evt.clear()

    def dispose(self):
        self.sub.unsubscribe()


class binarysensor(sensor):
    def __init__(self, name, cbus: cbus.cbus, sensor_events: tuple, query_message: tuple, evt=None):
        super().__init__(name, cbus, sensor_events, query_message, evt)
        # self.logger.log(f'binarysensor: name = {name}, sensor events = {self.sensor_events}')
        self.sync_state()
        self.task = asyncio.create_task(self.run())
        self.sub = cbuspubsub.subscription(name + ':sub', self.cbus, self.sensor_events, canmessage.QUERY_TUPLES)

    def sync_state(self):
        if self.query_message and len(self.query_message) == 2:
            self.sub = cbuspubsub.subscription(self.name + ':sub', self.cbus, self.query_message[1],
                                               canmessage.QUERY_ALL)
            msg = canmessage.event_from_tuple(self.cbus, self.query_message[0])
            msg.send()

            msg = await self.sub.wait()
            self.state = msg.data[0] == cbusdefs.OPC_ARON
            self.sub.unsubscribe()

    async def run(self) -> None:
        while True:
            msg = await self.sub.wait()
            new_state = SENSOR_STATE_UNKNOWN
            t = tuple(msg)

            if t == self.sensor_events[0]:
                new_state = SENSOR_STATE_OFF
            elif t == self.sensor_events[1]:
                new_state = SENSOR_STATE_ON
            else:
                self.logger.log(f'sensor:{self.name}, unexpected event = {t}')

            if self.state != new_state:
                self.state = new_state
                if isinstance(self.evt, asyncio.Event):
                    self.evt.set()

    def dispose(self):
        self.task.cancel()
        super().dispose()


class valuesensor(sensor):
    def __init__(self, name, cbus: cbus.cbus, sensor_events: tuple, query_message: tuple, evt=None):
        super().__init__(name, cbus, sensor_events, query_message, evt)
        self.value = -1
        self.state = SENSOR_STATE_UNKNOWN
        self.task = asyncio.create_task(self.run())

    def sync(self):
        self.state = SENSOR_STATE_VALID

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
    def __init__(self, name, cbus: cbus.cbus, control_events: tuple, query_message: tuple = None,
                 initial_state=TURNOUT_STATE_CLOSED,
                 has_sensor=False,
                 sensor_events=None,
                 init=False):
        self.logger = logger.logger()
        self.cbus = cbus
        self.name = name
        self.control_events = control_events
        self.query_message = query_message
        self.state = initial_state
        self.has_sensor = has_sensor
        self.sensor_events = sensor_events

        self.sensor = None
        self.sensor_name = None
        self.sensor_evt = None
        self.sensor_task = None
        self.lock = None
        self.timeout = None
        self.timeout_evt = None

        if has_sensor and sensor_events and len(sensor_events) == 2:
            self.sensor_evt = asyncio.Event()
            self.sensor_name = 'turnout:' + self.name + ':sensor'
            self.sensor = binarysensor(self.sensor_name, cbus, self.sensor_events, self.query_message, self.sensor_evt)
            self.sensor_task = asyncio.create_task(self.sensor_run())
            self.timeout_evt = asyncio.Event()
            self.timeout = timeout(OP_TIMEOUT, self.timeout_evt)

        if init:
            if initial_state == TURNOUT_STATE_CLOSED:
                self.close()
            else:
                self.throw()

    def dispose(self) -> None:
        if self.has_sensor:
            self.sensor_task.cancel()
            self.sensor.dispose()

    async def throw(self, force: bool = False) -> bool:
        return await self.operate(TURNOUT_STATE_THROWN, force)

    async def close(self, force: bool = False) -> bool:
        return await self.operate(TURNOUT_STATE_CLOSED, force)

    async def operate(self, target_state, force: bool = False) -> bool:
        if (target_state != self.state) or force:
            ev = canmessage.event_from_tuple(self.cbus, self.control_events[target_state])
            ev.send()
            self.state = target_state

            if self.has_sensor:
                self.state = TURNOUT_STATE_UNKNOWN
                t = asyncio.create_task((self.timeout.one_shot()))
                self.sensor_evt.clear()
                evw = await WaitAny((self.timeout_evt, self.sensor.evt)).wait()

                if evw is self.timeout_evt:
                    self.logger.log(f'turnout: name = {self.name}, timeout')
                    return False
                else:
                    self.state = self.sensor.state
                    self.logger.log(f'turnout: name = {self.name}, state = {self.state}')

        return True

    async def sensor_run(self) -> None:
        while True:
            await self.sensor_evt.wait()
            self.sensor_evt.clear()
            self.state = self.sensor.state
            self.logger.log(f'turnout sensor {self.sensor.name} triggered, state = {self.sensor.state}')


class semaphore_signal:
    def __init__(self, name, cbus, control_events: tuple, query_message: tuple = None,
                 initial_state=SIGNAL_STATE_UNKNOWN,
                 has_sensor=False,
                 sensor_events=None,
                 init=False):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.control_events = control_events
        self.query_message = query_message
        self.has_sensor = has_sensor
        self.sensor_events = sensor_events
        self.state = SIGNAL_STATE_UNKNOWN

        self.sensor = None
        self.sensor_name = None
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

        if has_sensor and query_message and len(query_message) == 2:
            self.sensor_evt = asyncio.Event()
            self.sensor_name = 'signal:' + self.name + ':sensor'
            self.sensor = binarysensor(self.sensor_name, self.cbus, self.sensor_events, self.query_message,
                                       self.sensor_evt)
            self.sensor_task = asyncio.create_task(self.sensor_run())
            self.timeout_evt = asyncio.Event()
            self.timeout = timeout(OP_TIMEOUT, self.timeout_evt)

    def dispose(self):
        self.sensor_task.cancel()
        self.sensor.dispose()

    async def clear(self, force: bool = False) -> bool:
        return await self.operate(SIGNAL_STATE_CLEAR, force)

    async def set(self, force: bool = False) -> bool:
        return await self.operate(SIGNAL_STATE_SET, force)

    async def operate(self, target_state, force: bool = False) -> bool:
        if (target_state != self.state) or force:
            ev = canmessage.event_from_tuple(self.cbus, self.control_events[target_state])
            ev.send()
            self.state = target_state

            if self.has_sensor:
                self.state = SIGNAL_STATE_UNKNOWN
                t = asyncio.create_task((self.timeout.one_shot()))
                self.sensor_evt.clear()
                evw = await WaitAny((self.timeout_evt, self.sensor.evt)).wait()

                if evw is self.timeout_evt:
                    self.logger.log(f'signal: name = {self.name}, timeout')
                    return False
                else:
                    self.state = self.sensor.state
                    self.logger.log(f'signal: name = {self.name}, state = {self.state}')

        return True

    async def sensor_run(self) -> None:
        while True:
            await self.sensor_evt.wait()
            self.sensor_evt.clear()
            self.state = self.sensor.state
            self.logger.log(f'signal sensor {self.sensor.name} triggered, state = {self.sensor.state}')


class semaphore_signal_group:
    def __init__(self, name: str, cbus: cbus.cbus, signals: tuple[semaphore_signal], initial_state: int, init=False):
        self.name = name
        self.cbus = cbus
        self.signals = signals
        self.initial_state = initial_state

        if init:
            pass

    # set aspect of first signal and others will cascade
    def clear(self):
        pass

    def set(self):
        pass

    def dispose(self):
        pass


class colour_light_signal:
    def __init__(self, name: str, cbus: cbus.cbus, num_aspects: int, control_events: tuple[tuple], initial_state: int,
                 init=False):
        self.name = name
        self.cbus = cbus
        self.num_aspects = num_aspects
        self.control_events = control_events
        self.state = initial_state if init else SIGNAL_STATE_UNKNOWN

        if init:
            self.set_aspect(initial_state)

    def set_aspect(self, aspect):
        if aspect < self.num_aspects:
            ev = canmessage.event_from_tuple(self.cbus, self.control_events[aspect])
            ev.send()
            self.state = aspect
        else:
            raise ValueError('invalid aspect')


class colour_light_signal_group:
    def __init__(self, name: str, cbus: cbus.cbus, signals: tuple[colour_light_signal], initial_state: int):
        self.name = name
        self.cbus = cbus
        self.signals = signals
        self.initial_state = initial_state

    # set aspect of first signal and others will cascade
    def set_aspect(self, aspect):
        pass

    def dispose(self):
        pass


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
        self.state = ROUTE_STATE_UNKNOWN

        self.lock = asyncio.Lock()
        self.locked_objects = []

    ## TODO: auto timeout and release ?

    def acquire(self) -> bool:
        self.state = ROUTE_STATE_UNKNOWN
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

        self.state = ROUTE_STATE_ACQUIRED if all_objects_locked else ROUTE_STATE_UNKNOWN
        return all_objects_locked

    def release(self) -> None:
        for obj in self.locked_objects:
            if obj.robject.lock.locked():
                try:
                    obj.robject.lock.release()
                except RuntimeError:
                    pass

        self.locked_objects = []
        self.lock.release()
        self.state = ROUTE_STATE_UNKNOWN

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

        self.state = ROUTE_STATE_SET
