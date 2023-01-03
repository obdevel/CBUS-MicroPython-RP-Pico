import uasyncio as asyncio
from micropython import const

import canmessage
import cbus
import cbuspubsub
import logger
from primitives import WaitAny

WAIT_FOREVER = const(-1)

STATE_UNKNOWN = const(-1)
STATE_OFF = const(0)
STATE_ON = const(1)

WHEN_BEFORE = const(0)
WHEN_DONT_CARE = const(1)
WHEN_AFTER = const(2)

SENSOR_STATE_UNKNOWN = const(-1)
SENSOR_STATE_OFF = const(0)
SENSOR_STATE_ON = const(1)
SENSOR_STATE_VALID = const(2)

sensor_states = {
    SENSOR_STATE_UNKNOWN: 'Unknown',
    SENSOR_STATE_OFF: 'Off',
    SENSOR_STATE_ON: 'On'
}

OBJECT_TYPE_UNKNOWN = const(-1)
OBJECT_TYPE_TURNOUT = const(0)
OBJECT_TYPE_SEMAPHORE_SIGNAL = const(1)
OBJECT_TYPE_COLOUR_LIGHT_SIGNAL = const(2)
OBJECT_TYPE_SERVO = const(3)

OBJECT_STATE_UNKNOWN = const(-1)
OBJECT_STATE_CLOSED = const(0)
OBJECT_STATE_OPEN = const(1)

TURNOUT_STATE_UNKNOWN = const(OBJECT_STATE_UNKNOWN)
TURNOUT_STATE_CLOSED = const(OBJECT_STATE_CLOSED)
TURNOUT_STATE_THROWN = const(OBJECT_STATE_OPEN)

turnout_states = {
    TURNOUT_STATE_UNKNOWN: 'Unknown',
    TURNOUT_STATE_CLOSED: 'Closed',
    TURNOUT_STATE_THROWN: 'Thrown'
}

SIGNAL_STATE_UNKNOWN = const(OBJECT_STATE_UNKNOWN)
SIGNAL_STATE_CLEAR = const(OBJECT_STATE_CLOSED)
SIGNAL_STATE_SET = const(OBJECT_STATE_OPEN)

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

ROTATE_FASTEST = const(0)
ROTATE_CLOCKWISE = const(1)
ROTATE_ANTICLOCKWISE = const(2)

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

    async def wait(self) -> None:
        await self.event.wait()


class sensor:
    def __init__(self, name: str, cbus: cbus.cbus, sensor_events: tuple, query_message: tuple):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.sensor_events = sensor_events
        self.query_message = query_message
        self.state = SENSOR_STATE_UNKNOWN
        self.sub = None

        self.evt = asyncio.Event()
        self.evt.clear()

        self.sub = cbuspubsub.subscription(name + ':sub', self.cbus, canmessage.QUERY_UDF, self.udf)
        self.task = asyncio.create_task(self.run())
        self.sync_state()

    async def run(self) -> None:
        while True:
            msg = await self.sub.wait()
            self.interpret(msg)
            self.evt.set()

    def interpret(self, msg):
        pass

    def udf(self, msg):
        pass

    def sync_state(self):
        if self.query_message:
            msg = canmessage.event_from_tuple(self.cbus, self.query_message)
            msg.send()

    async def wait(self):
        await self.evt.wait()
        self.evt.clear()

    def dispose(self):
        self.sub.unsubscribe()


class binary_sensor(sensor):
    def __init__(self, name, cbus: cbus.cbus, sensor_events: tuple, query_message: tuple):
        super(binary_sensor, self).__init__(name, cbus, sensor_events, query_message)

    def udf(self, msg):
        # TODO update this
        t = tuple(msg)
        # self.logger.log(f'binary sensor {self.name}: udf: msg = {t}, sensor_events = {self.sensor_events}')
        return t in self.sensor_events

    def interpret(self, msg: canmessage.cbusevent):
        new_state = SENSOR_STATE_UNKNOWN
        t = tuple(msg)
        # self.logger.log(f'binary sensor {self.name}: interpret: msg = {t}, sensor_events = {self.sensor_events}')

        # TODO update for UDF
        new_state = not msg.data[0] & 1

        if self.state != new_state:
            self.state = new_state
            self.logger.log(f'binary sensor {self.name}, new state = {self.state}')
            self.evt.set()

    def dispose(self):
        self.task.cancel()
        super().dispose()


class value_sensor(sensor):
    def __init__(self, name: str, cbus: cbus.cbus, sensor_events: tuple, query_message: tuple):
        super(value_sensor, self).__init__(name, cbus, sensor_events, query_message)
        self.value = -1
        self.state = SENSOR_STATE_UNKNOWN

    def interpret(self, msg):
        self.value = 99
        self.state = SENSOR_STATE_VALID

    def udf(self, msg):
        # self.logger.log('value_sensor: udf')
        return msg in self.sensor_events

    def dispose(self):
        self.task.cancel()
        super().dispose()


class base_cbus_layout_object:
    def __init__(self, objtype: int, name: str, cbus: cbus.cbus, control_events: tuple,
                 initial_state=OBJECT_STATE_CLOSED, sensor_events=None, query_message: tuple = None, init=False):

        self.logger = logger.logger()
        self.objtype = objtype
        self.name = name
        self.cbus = cbus
        self.control_events = control_events
        self.query_message = query_message
        self.has_sensor = sensor_events and len(sensor_events) > 1
        self.sensor_events = sensor_events
        self.state = initial_state

        if self.objtype == OBJECT_TYPE_TURNOUT:
            self.objtypename = 'turnout'
        elif self.objtype == OBJECT_TYPE_SEMAPHORE_SIGNAL:
            self.objtypename = 'semaphore signal'
        else:
            self.objtypename = 'unknown'

        self.sensor = None
        self.sensor_name = None
        self.sensor_task = None
        self.lock = None
        self.timeout = None
        self.timeout_evt = None

        if self.has_sensor and sensor_events and len(sensor_events) == 2:
            self.sensor_name = self.objtypename + ':' + self.name + ':sensor'
            self.sensor = binary_sensor(self.sensor_name, cbus, self.sensor_events, self.query_message)
            self.sensor_task = asyncio.create_task(self.sensor_run())
            self.timeout_evt = asyncio.Event()
            self.timeout = timeout(OP_TIMEOUT, self.timeout_evt)

        if init:
            self.operate(initial_state)

    def dispose(self) -> None:
        if self.has_sensor:
            self.sensor_task.cancel()
            self.sensor.dispose()

    def __call__(self):
        return self.state

    async def operate(self, target_state, force: bool = False) -> bool:
        if (target_state != self.state) or force:

            if self.objtype == OBJECT_TYPE_TURNOUT or self.objtype == OBJECT_TYPE_SEMAPHORE_SIGNAL:
                ev = canmessage.event_from_tuple(self.cbus, self.control_events[target_state])
                ev.send()
                self.state = target_state
            else:
                self.logger.log('operate unknown object type')

            if self.has_sensor:
                self.state = OBJECT_STATE_UNKNOWN
                t = asyncio.create_task((self.timeout.one_shot()))
                evw = await WaitAny((self.timeout_evt, self.sensor.evt)).wait()

                if evw is self.timeout_evt:
                    self.logger.log(f'object: name = {self.name}, timeout')
                    return False
                else:
                    self.state = self.sensor.state
                    self.logger.log(f'object: name = {self.name}, state = {self.state}')

        return True

    async def sensor_run(self) -> None:
        while True:
            await self.sensor.wait()
            self.state = self.sensor.state
            self.logger.log(f'sensor {self.sensor.name} triggered, state = {self.sensor.state}')


class turnout(base_cbus_layout_object):
    def __init__(self, name, cbus: cbus.cbus, control_events: tuple, initial_state=TURNOUT_STATE_CLOSED,
                 sensor_events=None, query_message: tuple = None, init=False):
        super(turnout, self).__init__(OBJECT_TYPE_TURNOUT, name, cbus, control_events, initial_state,
                                      sensor_events, query_message, init)

    async def close(self, force: bool = False) -> bool:
        return await self.operate(TURNOUT_STATE_CLOSED, force)

    async def throw(self, force: bool = False) -> bool:
        return await self.operate(TURNOUT_STATE_THROWN, force)


class semaphore_signal(base_cbus_layout_object):
    def __init__(self, name: str, cbus: cbus.cbus, control_events: tuple, query_message: tuple = None,
                 initial_state=SIGNAL_STATE_UNKNOWN,
                 sensor_events=None,
                 init=False):
        super(semaphore_signal, self).__init__(OBJECT_TYPE_SEMAPHORE_SIGNAL, name, cbus, control_events, initial_state,
                                               sensor_events, query_message, init)

    async def clear(self, force: bool = False) -> bool:
        return await self.operate(SIGNAL_STATE_CLEAR, force)

    async def set(self, force: bool = False) -> bool:
        return await self.operate(SIGNAL_STATE_SET, force)


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

    def __call__(self):
        return self.state

    def set_aspect(self, aspect):
        if aspect < self.num_aspects:
            ev = canmessage.event_from_tuple(self.cbus, self.control_events[aspect])
            ev.send()
            self.state = aspect
        else:
            raise ValueError('invalid aspect')


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


class colour_light_signal_group:
    def __init__(self, name: str, cbus: cbus.cbus, signals: tuple[colour_light_signal], initial_aspect: int = 0,
                 init: bool = False):
        self.name = name
        self.cbus = cbus
        self.signals = signals

        if init:
            self.set_aspect(initial_aspect)

    # set aspect of first signal and others will cascade
    def set_aspect(self, aspect):
        pass

    def dispose(self):
        pass


class turntable:
    def __init__(self, name: str, cbus: cbus.cbus, position_events: tuple[int, ...], stop_event: tuple = None,
                 sensor_event: tuple = None, query_message: tuple = None, init: bool = False, init_pos: int = 0):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.position_events = position_events
        self.stop_event = stop_event
        self.has_sensor = sensor_event is not None
        self.sensor_event = sensor_event
        self.query_message = query_message
        self.sensor = None
        self.current_position = 0
        self.target_position = 0

        if self.has_sensor:
            self.sensor_name = 'turntable:' + self.name + ':sensor'
            self.sensor = value_sensor(self.sensor_name, cbus, self.sensor_event, self.query_message)
            self.sensor_task = asyncio.create_task(self.sensor_run())
            self.timeout_evt = asyncio.Event()
            self.timeout = timeout(OP_TIMEOUT, self.timeout_evt)

            if self.query_message is not None:
                self.sync_state()

        if init:
            self.position_to(init_pos)

    def dispose(self) -> None:
        if self.has_sensor:
            self.sensor_task.cancel()
            self.sensor.dispose()

    def sync_state(self) -> None:
        msg = canmessage.message_from_tuple(self.query_message)
        self.cbus.send_cbus_message(msg)

    def sensor_run(self) -> None:
        while True:
            await self.sensor.wait()
            self.current_position = self.sensor.state

    async def position_to(self, position: int, wait: bool = False) -> bool:
        ret = None
        msg = canmessage.event_from_tuple(self.cbus, self.position_events[position])
        msg.send()

        if wait and self.has_sensor:
            self.current_position = -1
            t = asyncio.create_task((self.timeout.one_shot()))
            evw = await WaitAny((self.timeout_evt, self.sensor.evt)).wait()

            if evw is self.timeout_evt:
                self.logger.log(f'turntable: name = {self.name}, timeout')
                ret = False
            else:
                self.current_position = self.sensor.state
                self.logger.log(f'turntable: name = {self.name}, position = {self.current_position}')
                ret = True

            t.cancel()
        return ret

    def stop(self) -> None:
        if self.stop_event:
            msg = canmessage.event_from_tuple(self.cbus, self.stop_event)
            msg.send()
