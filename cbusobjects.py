import uasyncio as asyncio
from micropython import const

import canmessage
import cbus
import cbuspubsub
import logger
from primitives import WaitAny, WaitAll

WAIT_FOREVER = const(-1)

STATE_UNKNOWN = const(-1)
STATE_OFF = const(0)
STATE_ON = const(1)

WHEN_BEFORE = const(0)
WHEN_DURING = const(1)
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
OBJECT_STATE_OFF = const(0)
OBJECT_STATE_ON = const(1)

TURNOUT_STATE_UNKNOWN = const(OBJECT_STATE_UNKNOWN)
TURNOUT_STATE_CLOSED = const(OBJECT_STATE_OFF)
TURNOUT_STATE_THROWN = const(OBJECT_STATE_ON)

turnout_states = {
    TURNOUT_STATE_UNKNOWN: 'Unknown',
    TURNOUT_STATE_CLOSED: 'Closed',
    TURNOUT_STATE_THROWN: 'Thrown'
}

SIGNAL_STATE_UNKNOWN = const(OBJECT_STATE_UNKNOWN)
SIGNAL_STATE_CLEAR = const(OBJECT_STATE_OFF)
SIGNAL_STATE_SET = const(OBJECT_STATE_ON)

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
MAX_TIMEOUT = const(1_000_000)
OP_TIMEOUT = const(5_000)
RELEASE_TIMEOUT = const(30_000)


def objects_must_be_locked(arg: bool = True):
    global LOCK_BEFORE_OPERATION
    LOCK_BEFORE_OPERATION = arg


class timeout:
    def __init__(self, ms: int):
        self.ms = ms if ms >= 0 else MAX_TIMEOUT
        self.evt = asyncio.Event()

    async def one_shot(self) -> None:
        self.evt.clear()
        await asyncio.sleep_ms(self.ms)
        self.evt.set()

    async def recurrent(self) -> None:
        while True:
            self.evt.clear()
            await asyncio.sleep_ms(self.ms)
            self.evt.set()

    async def wait(self) -> None:
        await self.evt.wait()


class WaitAnyTimeout:
    def __init__(self, objects: tuple, ms: int = 0) -> None:
        self.logger = logger.logger()
        # self.logger.log(f'WaitAnyTimeout: objects = {objects}, timeout = {ms}')

        self.objects = objects
        self.ms = ms
        self.timer = timeout(self.ms)
        self.timer_task_handle = asyncio.create_task(self.timer.one_shot())

    async def wait(self):
        if isinstance(self.objects, tuple):
            self.objects = self.objects + (self.timer,)
        else:
            self.objects = (self.objects, self.timer)

        # self.logger.log(f'WaitAnyTimeout: wait: objects = {self.objects}')
        e = await WaitAny(self.objects).wait()

        if e is self.timer:
            # self.logger.log(f'WaitAnyTimeout: wait: timed out, returning None')
            return None
        else:
            # self.logger.log(f'WaitAnyTimeout: wait: returning event = {e}')
            self.timer_task_handle.cancel()
            return e


class WaitAllTimeout:
    def __init__(self, objects: tuple, ms: int = 0) -> None:
        self.logger = logger.logger()
        # self.logger.log(f'WaitAllTimeout: objects = {objects}, timeout = {ms}')

        self.objects = objects
        self.ms = ms

    async def wait(self):
        if not isinstance(self.objects, tuple):
            self.objects = (self.objects,)

        # self.logger.log(f'WaitAllTimeout: wait objects = {self.objects}, timeout = {self.ms}')
        e = await WaitAnyTimeout(WaitAll(self.objects), self.ms).wait()
        # self.logger.log(f'WaitAllTimeout: returning = {e}')
        return e


# sn1 = cbusobjects.binary_sensor('sn1', mod.cbus, ((0,22,24),(1,22,24)))
# sn2 = cbusobjects.binary_sensor('sn2', mod.cbus, ((0,22,25),(1,22,25)))
# x = await cbusobjects.WaitAnyTimeout((sn1, sn2), 5_000).wait()
# x = await cbusobjects.WaitAllTimeout((sn1, sn2), 5_000).wait()

class sensor:
    def __init__(self, name: str, cbus: cbus.cbus, feedback_events: tuple, query_message: tuple = None):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.feedback_events = feedback_events
        self.query_message = query_message
        self.state = SENSOR_STATE_UNKNOWN
        self.sub = None

        self.evt = asyncio.Event()
        self.evt.clear()
        self.sub = cbuspubsub.subscription(name + ':sub', self.cbus, canmessage.QUERY_UDF, self.udf)
        self.task_handle = asyncio.create_task(self.run_task())

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

    def dispose(self):
        self.evt.set()
        self.sub.unsubscribe()
        self.task_handle.cancel()

    async def wait(self, timeout: int = WAIT_FOREVER) -> int:
        if timeout == WAIT_FOREVER:
            await self.evt.wait()
        else:
            x = await WaitAnyTimeout((self.evt,), timeout).wait()
            if not x:
                self.state = SENSOR_STATE_UNKNOWN

        self.evt.clear()
        return self.state


class binary_sensor(sensor):
    def __init__(self, name: str, cbus: cbus.cbus, feedback_events: tuple, query_message: tuple = None):
        super(binary_sensor, self).__init__(name, cbus, feedback_events, query_message)

    def udf(self, msg):
        return tuple(msg) in self.feedback_events

    def interpret(self, msg: canmessage.cbusevent):
        t = tuple(msg)

        if t == self.feedback_events[0]:
            new_state = SENSOR_STATE_OFF
        elif t == self.feedback_events[1]:
            new_state = SENSOR_STATE_ON
        else:
            new_state = SENSOR_STATE_UNKNOWN

        if self.state != new_state:
            self.logger.log(f'binary sensor {self.name}, changed state, from {self.state} to {new_state}')
            self.state = new_state
            self.evt.set()

    def dispose(self):
        super().dispose()


class multi_sensor(sensor):
    def __init__(self, name: str, cbus: cbus.cbus, feedback_events: tuple, query_message: tuple = None):
        super(multi_sensor, self).__init__(name, cbus, feedback_events, query_message)

    def udf(self, msg: canmessage.canmessage) -> bool:
        if tuple(msg) in self.feedback_events:
            return True

    def interpret(self, msg: canmessage.canmessage) -> None:
        t = tuple(msg)
        new_state = -1

        for x in self.feedback_events:
            if t == x:
                new_state = t[2]
                break

        if self.state != new_state:
            self.state = new_state
            self.logger.log(f'binary sensor {self.name}, new state = {self.state}')
            self.evt.set()

    def dispose(self) -> None:
        super().dispose()


class value_sensor(sensor):
    def __init__(self, name: str, cbus: cbus.cbus, feedback_events: tuple, query_message: tuple = None):
        super(value_sensor, self).__init__(name, cbus, feedback_events, query_message)
        self.value = -1
        self.state = SENSOR_STATE_UNKNOWN

    def interpret(self, msg):
        self.value = 99
        self.state = SENSOR_STATE_VALID
        self.evt.set()

    def udf(self, msg):
        return msg in self.feedback_events

    def dispose(self):
        super().dispose()


class base_cbus_layout_object:
    def __init__(self, objtype: int, name: str, cbus: cbus.cbus, control_events: tuple,
                 initial_state: int = OBJECT_STATE_UNKNOWN, feedback_events: tuple = None, query_message: tuple = None,
                 init: bool = False, wait_for_feedback: bool = True):

        self.logger = logger.logger()
        self.objtype = objtype
        self.name = name
        self.cbus = cbus
        self.control_events = control_events
        self.query_message = query_message
        self.has_sensor = feedback_events and len(feedback_events) > 1
        self.feedback_events = feedback_events
        self.wait_for_feedback = wait_for_feedback
        self.state = initial_state
        self.target_state = initial_state
        self.evt = asyncio.Event()

        if self.objtype == OBJECT_TYPE_TURNOUT:
            self.objtypename = 'turnout'
        elif self.objtype == OBJECT_TYPE_SEMAPHORE_SIGNAL:
            self.objtypename = 'semaphore signal'
        else:
            self.objtypename = 'unknown'

        self.sensor = None
        self.sensor_name = None
        self.sensor_monitor_task_handle = None
        # self.timer = timeout(OP_TIMEOUT)

        self.lock = asyncio.Lock()
        self.locked_by = None
        self.must_lock = LOCK_BEFORE_OPERATION
        self.auto_release = False
        self.lock_timeout_task_handle = None
        self.release_timeout = RELEASE_TIMEOUT

        if self.has_sensor and feedback_events and len(feedback_events) == 2:
            self.sensor_name = self.objtypename + ':' + self.name + ':sensor'
            self.sensor = binary_sensor(self.sensor_name, cbus, self.feedback_events, self.query_message)
            self.sensor_monitor_task_handle = asyncio.create_task(self.sensor_monitor_task())

        if init:
            self.operate(initial_state)

    def dispose(self) -> None:
        if self.has_sensor:
            self.sensor_monitor_task_handle.cancel()
            self.sensor.dispose()
        if self.lock_timeout_task_handle is not None:
            self.lock_timeout_task_handle.cancel()

    def __call__(self):
        return self.state

    async def acquire(self) -> bool:
        if self.lock.locked():
            return False
        else:
            await self.lock.acquire()
            if self.auto_release:
                self.lock_timeout_task_handle = asyncio.create_task(self.lock_timeout_task(self.release_timeout))
            return True

    def release(self) -> None:
        if self.lock_timeout_task_handle is not None:
            self.lock_timeout_task_handle.cancel()
        if self.lock.locked():
            self.lock.release()

    async def operate(self, target_state, wait_for_feedback: bool = True, force: bool = False) -> bool:
        self.target_state = target_state
        self.wait_for_feedback = wait_for_feedback
        self.evt.clear()
        ret = True

        self.logger.log(f'operate: current state = {self.state}, target state = {self.target_state}, wait for feedback = {self.wait_for_feedback} ')

        if self.must_lock and not self.lock.locked():
            raise RuntimeError(f'object {self.name}: object must be acquired before operating')

        if (target_state != self.state) or force:

            if self.objtype == OBJECT_TYPE_TURNOUT or self.objtype == OBJECT_TYPE_SEMAPHORE_SIGNAL:
                self.state = OBJECT_STATE_UNKNOWN
                ev = canmessage.event_from_tuple(self.cbus, self.control_events[target_state])
                ev.send()
            else:
                raise ValueError(f'operate: {self.name} unknown object type {self.objtype}')

            if self.has_sensor:
                self.state = OBJECT_STATE_AWAITING_SENSOR

                if self.wait_for_feedback:
                    self.logger.log(f'object {self.name} waiting for feedback sensor, current state = {self.state}')
                    # self.state = await self.sensor.wait(OP_TIMEOUT)
                    self.state = await self.wait()

                    if self.state == SENSOR_STATE_UNKNOWN:
                        self.logger.log(f'{self.name}: wait timed out, state = {self.state}')
                        ret = False
                    else:
                        if self.state == self.target_state:
                            self.logger.log(f'{self.name}: operate feedback received, new state = {self.state}')
                        else:
                            self.logger.log(f'{self.name}: operate feedback received, but unexpected state, new state = {self.state}')

                        self.evt.set()
            else:
                self.state = target_state
                self.evt.set()

        return ret

    async def sensor_monitor_task(self) -> None:
        if self.has_sensor:
            while True:
                self.evt.clear()
                await self.sensor.wait(WAIT_FOREVER)
                self.state = self.sensor.state
                if self.state == self.target_state:
                    self.logger.log(f'sensor_monitor_task: object sensor {self.sensor.name} triggered, new state = {self.sensor.state}')
                    self.evt.set()
                else:
                    self.logger.log(f'sensor_monitor_task: object sensor {self.sensor.name} triggered, but unexpected state, target state = {self.target_state}, new state = {self.sensor.state}')

    async def wait(self, waitfor: int = WAIT_FOREVER) -> int:
        # self.logger.log(f'object {self.name} wait: waitfor = {waitfor}')

        if self.has_sensor:
            if waitfor == WAIT_FOREVER:
                await self.evt.wait()
            else:
                r = await WaitAnyTimeout((self.evt,), waitfor).wait()

                if r is not self.evt:
                    return OBJECT_STATE_UNKNOWN

        return self.state

    async def lock_timeout_task(self, timeout: int = RELEASE_TIMEOUT):
        self.logger.log(f'lock_timeout_task: {self.name} sleeping for {timeout}')
        await asyncio.sleep_ms(timeout)
        self.lock.release()
        self.logger.log(f'lock_timeout_task: {self.name} lock released')


class turnout(base_cbus_layout_object):
    def __init__(self, name, cbus: cbus.cbus, control_events: tuple, initial_state: int = TURNOUT_STATE_UNKNOWN,
                 feedback_events: tuple = None, query_message: tuple = None, init: bool = False,
                 wait_for_feedback: bool = True):
        super(turnout, self).__init__(OBJECT_TYPE_TURNOUT, name, cbus, control_events, initial_state,
                                      feedback_events, query_message, init, wait_for_feedback)

    async def close(self, wait_for_feedback: bool = True, force: bool = False) -> bool:
        return await self.operate(TURNOUT_STATE_CLOSED, wait_for_feedback, force)

    async def throw(self, wait_for_feedback: bool = True, force: bool = False) -> bool:
        return await self.operate(TURNOUT_STATE_THROWN, wait_for_feedback, force)


class semaphore_signal(base_cbus_layout_object):
    def __init__(self, name: str, cbus: cbus.cbus, control_events: tuple, query_message: tuple = None,
                 initial_state: int = SIGNAL_STATE_UNKNOWN, feedback_events: tuple = None, init: bool = False,
                 wait_for_feedback: bool = True):
        super(semaphore_signal, self).__init__(OBJECT_TYPE_SEMAPHORE_SIGNAL, name, cbus, control_events, initial_state,
                                               feedback_events, query_message, init, wait_for_feedback)

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
        self.has_sensor = False

        if init:
            self.set_aspect(initial_state)

    def __call__(self):
        return self.state

    def set_aspect(self, aspect: int):
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
    def __init__(self, name: str, cbus: cbus.cbus, signals: tuple[colour_light_signal], initial_aspects: tuple[int] = None, init: bool = False):
        self.name = name
        self.cbus = cbus
        self.signals = signals

        if init:
            self.set_aspect(initial_aspects)

    def set_aspect(self, aspects: tuple[int]):
        for i, s in enumerate(self.signals):
            s.set_aspect(aspects[i])

    def dispose(self):
        pass


class turntable:
    def __init__(self, name: str, cbus: cbus.cbus, position_events: tuple, stop_event: tuple = None,
                 feedback_events: tuple = None, query_message: tuple = None, init: bool = False, init_pos: int = 0):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.position_events = position_events
        self.stop_event = stop_event
        self.has_sensor = feedback_events is not None
        self.feedback_events = feedback_events
        self.query_message = query_message
        self.sensor = None
        self.current_position = 0
        self.target_position = 0
        self.evt = asyncio.Event()

        if self.has_sensor:
            self.sensor_name = 'turntable:' + self.name + ':sensor'
            self.sensor = multi_sensor(self.sensor_name, cbus, self.feedback_events, self.query_message)
            self.sensor_monitor_task_handle = asyncio.create_task(self.sensor_monitor_task())
            self.timeout = timeout(OP_TIMEOUT)

            if self.query_message is not None:
                self.sync_state()

        if init:
            self.position_to(init_pos)

    def dispose(self) -> None:
        if self.has_sensor:
            self.sensor_monitor_task_handle.cancel()
            self.sensor.dispose()

    def sync_state(self) -> None:
        msg = canmessage.message_from_tuple(self.query_message)
        self.cbus.send_cbus_message(msg)

    def sensor_monitor_task(self) -> None:
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
        self.evt.clear()
        await self.sensor.wait()
        self.evt.set()


class uncoupler:
    def __init__(self, name: str, cbus: cbus.cbus, event: tuple, auto_off: bool = False, timeout: int = RELEASE_TIMEOUT) -> None:
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.timeout = timeout
        self.event = canmessage.event_from_tuple(self.cbus, event)
        self.auto_off = auto_off

    def on(self) -> None:
        self.event.send_on()
        self.logger.log(f'uncoupler {self.name} on')

        if self.auto_off:
            _ = asyncio.create_task(self.auto_off_timer())

    def off(self):
        self.event.send_off()
        self.logger.log(f'uncoupler {self.name} off')

    async def auto_off_timer(self):
        self.logger.log(f'uncoupler {self.name} waiting for timeout')
        await asyncio.sleep_ms(self.timeout)
        self.logger.log(f'uncoupler {self.name} timed out')
        self.off()
