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

OBJECT_STATE_AWAITING_SENSOR = const(-2)
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
    SIGNAL_STATE_SET: 'Set'
}

SIGNAL_TYPE_UNKNOWN = const(-1)
SIGNAL_TYPE_HOME = const(0)
SIGNAL_TYPE_DISTANT = const(1)
SIGNAL_TYPE_STARTER = const(2)

signal_types = {
    SIGNAL_TYPE_UNKNOWN: 'Unknown',
    SIGNAL_TYPE_HOME: 'Home',
    SIGNAL_TYPE_DISTANT: 'Distant',
    SIGNAL_TYPE_STARTER: 'Starter'
}

SIGNAL_COLOUR_RED = const(0)
SIGNAL_COLOUR_GREEN = const(1)
SIGNAL_COLOUR_YELLOW = const(2)
SIGNAL_COLOUR_DOUBLE_YELLOW = const(3)

TT_ROTATE_FASTEST = const(0)
TT_ROTATE_CLOCKWISE = const(1)
TT_ROTATE_ANTICLOCKWISE = const(2)

LOCK_BEFORE_OPERATION = False
MAX_TIMEOUT = const(2_147_483_647)  # sys.maxsize
OP_TIMEOUT = const(5_000)
RELEASE_TIMEOUT = const(10_000)


class timeout:
    def __init__(self, ms: int):
        self.ms = ms if ms >= 0 else MAX_TIMEOUT
        self.evt = asyncio.Event()

    async def one_shot(self) -> None:
        self.evt.clear()
        await asyncio.sleep_ms(self.ms)
        self.evt.set()
        self.evt.clear()

    async def recurrent(self) -> None:
        self.evt.clear()
        while True:
            await asyncio.sleep_ms(self.ms)
            self.evt.set()
            self.evt.clear()

    async def wait(self) -> None:
        await self.evt.wait()


class sensor:
    def __init__(self, name: str, cbus: cbus.cbus, sensor_events: tuple, query_message: tuple = None):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.sensor_events = sensor_events
        self.query_message = query_message
        self.state = SENSOR_STATE_UNKNOWN
        self.sub = None

        self.evt = asyncio.Event()
        self.evt.clear()
        self.timer = timeout(OP_TIMEOUT)
        self.sub = cbuspubsub.subscription(name + ':sub', self.cbus, canmessage.QUERY_UDF, self.udf)
        self.task = asyncio.create_task(self.run_task())

        self.sync_state()

    async def run_task(self) -> None:
        while True:
            msg = await self.sub.wait()
            self.interpret(msg)

    def interpret(self, msg):
        pass

    def udf(self, msg):
        pass

    def sync_state(self):
        if self.query_message:
            msg = canmessage.message_from_tuple(self.query_message)
            self.cbus.send_cbus_message(msg)

    def clear(self):
        self.evt.clear()

    def dispose(self):
        self.sub.unsubscribe()

    async def wait(self, waitfor: int = WAIT_FOREVER) -> int:
        self.clear()

        if waitfor != WAIT_FOREVER:
            self.timer.ms = waitfor
            tt = asyncio.create_task(self.timer.one_shot())
            r = await WaitAny((self.evt, self.timer.evt)).wait()

            if r is self.evt:
                tt.cancel()
                return self.state
            elif r is self.timer.evt:
                return -1
        else:
            await self.evt.wait()
            return self.state


class binary_sensor(sensor):
    def __init__(self, name: str, cbus: cbus.cbus, sensor_events: tuple, query_message: tuple = None):
        super(binary_sensor, self).__init__(name, cbus, sensor_events, query_message)

    def udf(self, msg):
        return tuple(msg) in self.sensor_events

    def interpret(self, msg: canmessage.cbusevent):
        t = tuple(msg)
        new_state = 0 if t == self.sensor_events[0] else 1

        if self.state != new_state:
            self.state = new_state
            self.logger.log(f'binary sensor {self.name}, new state = {self.state}')
            self.evt.set()

    def dispose(self):
        self.task.cancel()
        super().dispose()


class multi_sensor(sensor):
    def __init__(self, name: str, cbus: cbus.cbus, sensor_events: tuple, query_message: tuple = None):
        super(multi_sensor, self).__init__(name, cbus, sensor_events, query_message)

    def udf(self, msg: canmessage.canmessage) -> bool:
        if tuple(msg) in self.sensor_events:
            return True

    def interpret(self, msg: canmessage.canmessage) -> None:
        t = tuple(msg)
        new_state = -1

        for x in self.sensor_events:
            if t == x:
                new_state = t[2]
                break

        if self.state != new_state:
            self.state = new_state
            self.logger.log(f'binary sensor {self.name}, new state = {self.state}')
            self.evt.set()

    def dispose(self) -> None:
        pass


class value_sensor(sensor):
    def __init__(self, name: str, cbus: cbus.cbus, sensor_events: tuple, query_message: tuple = None):
        super(value_sensor, self).__init__(name, cbus, sensor_events, query_message)
        self.value = -1
        self.state = SENSOR_STATE_UNKNOWN

    def interpret(self, msg):
        self.value = 99
        self.state = SENSOR_STATE_VALID
        self.evt.set()

    def udf(self, msg):
        return msg in self.sensor_events

    def dispose(self):
        self.task.cancel()
        super().dispose()


class base_cbus_layout_object:
    def __init__(self, objtype: int, name: str, cbus: cbus.cbus, control_events: tuple,
                 initial_state: int = OBJECT_STATE_CLOSED, sensor_events: tuple = None, query_message: tuple = None,
                 init: bool = False, wait_for_sensor: bool = True):

        self.logger = logger.logger()
        self.objtype = objtype
        self.name = name
        self.cbus = cbus
        self.control_events = control_events
        self.query_message = query_message
        self.has_sensor = sensor_events and len(sensor_events) > 1
        self.sensor_events = sensor_events
        self.wait_for_sensor = wait_for_sensor
        self.state = initial_state
        self.evt = asyncio.Event()

        if self.objtype == OBJECT_TYPE_TURNOUT:
            self.objtypename = 'turnout'
        elif self.objtype == OBJECT_TYPE_SEMAPHORE_SIGNAL:
            self.objtypename = 'semaphore signal'
        else:
            self.objtypename = 'unknown'

        self.sensor = None
        self.sensor_name = None
        self.sensor_task_handle = None

        self.lock = asyncio.Lock()
        self.must_lock = LOCK_BEFORE_OPERATION
        self.auto_release = False
        self.release_timeout = RELEASE_TIMEOUT

        if self.has_sensor and sensor_events and len(sensor_events) == 2:
            self.sensor_name = self.objtypename + ':' + self.name + ':sensor'
            self.sensor = binary_sensor(self.sensor_name, cbus, self.sensor_events, self.query_message)
            self.sensor_task_handle = asyncio.create_task(self.sensor_run_task())
            self.timeout = timeout(OP_TIMEOUT)

        if init:
            self.operate(initial_state)

    def dispose(self) -> None:
        if self.has_sensor:
            self.sensor_task_handle.cancel()
            self.sensor.dispose()

    def __call__(self):
        return self.state

    async def acquire(self) -> bool:
        if self.lock.locked():
            return False
        else:
            await self.lock.acquire()
            if self.auto_release:
                _ = asyncio.create_task(self.lock_timeout_task(self.release_timeout))
            return True

    def release(self) -> None:
        if self.lock.locked():
            self.lock.release()

    async def operate(self, target_state, wait_for_feedback: bool = True, force: bool = False) -> bool:
        self.wait_for_sensor = wait_for_feedback
        self.evt.clear()
        ret = True

        if self.must_lock and not self.lock.locked():
            raise RuntimeError(f'object {self.name}: object must be acquired before operating')

        if (target_state != self.state) or force:

            if self.objtype == OBJECT_TYPE_TURNOUT or self.objtype == OBJECT_TYPE_SEMAPHORE_SIGNAL:
                self.state = OBJECT_STATE_UNKNOWN
                ev = canmessage.event_from_tuple(self.cbus, self.control_events[target_state])
                ev.send()
                self.state = target_state
            else:
                self.logger.log('operate unknown object type')
                ret = False

            if self.has_sensor:
                self.state = OBJECT_STATE_AWAITING_SENSOR

                if self.wait_for_sensor:
                    self.state = await self.sensor.wait(OP_TIMEOUT)

                    if self.state == SENSOR_STATE_UNKNOWN:
                        self.logger.log(f'{self.name}: operate timed out')
                        ret = False
                    else:
                        self.logger.log(f'{self.name}: operate feedback received, state = {self.state}')
                        self.evt.set()

        return ret

    async def sensor_run_task(self) -> None:
        while True:
            await self.sensor.wait()
            self.state = self.sensor.state
            self.logger.log(f'object sensor {self.sensor.name} triggered, new state = {self.sensor.state}')

    async def lock_timeout_task(self, timeout: int = 30_000):
        await asyncio.sleep_ms(timeout)
        self.lock.release()
        self.logger.log(f'object {self.name} lock released')


class turnout(base_cbus_layout_object):
    def __init__(self, name, cbus: cbus.cbus, control_events: tuple, initial_state: int = TURNOUT_STATE_UNKNOWN,
                 sensor_events: tuple = None, query_message: tuple = None, init: bool = False,
                 wait_for_sensor: bool = True):
        super(turnout, self).__init__(OBJECT_TYPE_TURNOUT, name, cbus, control_events, initial_state,
                                      sensor_events, query_message, init, wait_for_sensor)

    async def close(self, wait_for_feedback: bool = True, force: bool = False) -> bool:
        return await self.operate(TURNOUT_STATE_CLOSED, wait_for_feedback, force)

    async def throw(self, wait_for_feedback: bool = True, force: bool = False) -> bool:
        return await self.operate(TURNOUT_STATE_THROWN, wait_for_feedback, force)


class semaphore_signal(base_cbus_layout_object):
    def __init__(self, name: str, cbus: cbus.cbus, control_events: tuple, query_message: tuple = None,
                 initial_state: int = SIGNAL_STATE_UNKNOWN, sensor_events: tuple = None, init: bool = False,
                 wait_for_sensor: bool = True):
        super(semaphore_signal, self).__init__(OBJECT_TYPE_SEMAPHORE_SIGNAL, name, cbus, control_events, initial_state,
                                               sensor_events, query_message, init, wait_for_sensor)

    async def clear(self, wait_for_feedback: bool = True, force: bool = False) -> bool:
        return await self.operate(SIGNAL_STATE_CLEAR, wait_for_feedback, force)

    async def set(self, wait_for_feedback: bool = True, force: bool = False) -> bool:
        return await self.operate(SIGNAL_STATE_SET, wait_for_feedback, force)


class colour_light_signal:
    def __init__(self, name: str, cbus: cbus.cbus, num_aspects: int, control_events: tuple[tuple], initial_state: int,
                 init: bool = False):
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
    def __init__(self, name: str, cbus: cbus.cbus, signals: tuple[semaphore_signal], initial_state: int,
                 init: bool = False):
        self.name = name
        self.cbus = cbus
        self.signals = signals
        self.initial_state = initial_state

        if init:
            pass

    # set aspect of first signal and others will cascade
    def clear(self):
        for sig in self.signals:
            await sig.clear()

    def set(self):
        for sig in self.signals:
            await sig.set()

    def dispose(self):
        for sig in self.signals:
            sig.dispose()


class colour_light_signal_group:
    def __init__(self, name: str, cbus: cbus.cbus, signals: tuple[colour_light_signal], initial_aspect: int = 0,
                 init: bool = False):
        self.name = name
        self.cbus = cbus
        self.signals = signals
        self.aspects = ((SIGNAL_COLOUR_RED, SIGNAL_COLOUR_GREEN),
                        (SIGNAL_COLOUR_RED, SIGNAL_COLOUR_YELLOW, SIGNAL_COLOUR_GREEN),
                        (SIGNAL_COLOUR_RED, SIGNAL_COLOUR_YELLOW, SIGNAL_COLOUR_DOUBLE_YELLOW, SIGNAL_COLOUR_GREEN,)
                        )

        if init:
            self.set_aspect(initial_aspect)

    # set aspect of first signal and others will cascade
    def set_aspect(self, aspect):
        num_signals = len(self.signals)
        for i in self.aspects:
            if i == num_signals:
                break

    def dispose(self):
        pass


class turntable:
    def __init__(self, name: str, cbus: cbus.cbus, position_events: tuple, stop_event: tuple = None,
                 sensor_events: tuple = None, query_message: tuple = None, init: bool = False, init_pos: int = 0):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.position_events = position_events
        self.stop_event = stop_event
        self.has_sensor = sensor_events is not None
        self.sensor_events = sensor_events
        self.query_message = query_message
        self.sensor = None
        self.current_position = 0
        self.target_position = 0
        self.evt = asyncio.Event()

        if self.has_sensor:
            self.sensor_name = 'turntable:' + self.name + ':sensor'
            self.sensor = multi_sensor(self.sensor_name, cbus, self.sensor_events, self.query_message)
            self.sensor_task_handle = asyncio.create_task(self.sensor_run_task())
            self.timeout = timeout(OP_TIMEOUT)

            if self.query_message is not None:
                self.sync_state()

        if init:
            self.position_to(init_pos)

    def dispose(self) -> None:
        if self.has_sensor:
            self.sensor_task_handle.cancel()
            self.sensor.dispose()

    def sync_state(self) -> None:
        msg = canmessage.message_from_tuple(self.query_message)
        self.cbus.send_cbus_message(msg)

    def sensor_run_task(self) -> None:
        while True:
            await self.sensor.wait()
            self.current_position = self.sensor.state

    async def position_to(self, position: int, wait: bool = False) -> bool:
        ret = False
        msg = canmessage.event_from_tuple(self.cbus, self.position_events[position])
        msg.send()

        if wait and self.has_sensor:
            self.current_position = -1
            t = asyncio.create_task((self.timeout.one_shot()))
            evw = await WaitAny((self.timeout.evt, self.sensor.evt)).wait()

            if evw is self.timeout.evt:
                self.logger.log(f'turntable: name = {self.name}, timeout')
                ret = False
            else:
                self.current_position = self.sensor.state
                self.logger.log(f'turntable: name = {self.name}, position = {self.current_position}')
                t.cancel()
                ret = True

        return ret

    def stop(self) -> None:
        if self.stop_event:
            msg = canmessage.event_from_tuple(self.cbus, self.stop_event)
            msg.send()

    def wait(self) -> None:
        await self.sensor.wait()
        self.evt.set()


class uncoupler:
    def __init__(self, name: str, cbus: cbus.cbus, event: tuple, auto_off: bool = False, timeout: int = RELEASE_TIMEOUT) -> None:
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.timeout = timeout
        self.evt = canmessage.event_from_tuple(self.cbus, event)
        self.auto_off = auto_off

    async def uncouple(self) -> None:
        self.logger.log(f'uncoupler {self.name} uncoupling')
        self.evt.send_on()

        if not self.auto_off:
            self.logger.log(f'uncoupler {self.name} waiting')
            await asyncio.sleep_ms(self.timeout)
            self.evt.send_off()
            self.logger.log(f'uncoupler {self.name} uncoupled')

        self.logger.log(f'uncoupler {self.name} complete')
