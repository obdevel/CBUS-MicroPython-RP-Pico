import uasyncio as asyncio
from micropython import const

import canmessage
import cbus
import cbuspubsub
import logger
from primitives import WaitAny, WaitAll

WAIT_FOREVER = const(-1)

OBJECT_STATE_AWAITING_SENSOR = const(-2)
OBJECT_STATE_UNKNOWN = const(-1)
OBJECT_STATE_OFF = const(0)
OBJECT_STATE_ON = const(1)
OBJECT_STATE_VALID = const(99)

OBJECT_TYPE_UNKNOWN = const(-1)
OBJECT_TYPE_TURNOUT = const(0)
OBJECT_TYPE_SEMAPHORE_SIGNAL = const(1)
OBJECT_TYPE_COLOUR_LIGHT_SIGNAL = const(2)
OBJECT_TYPE_SERVO = const(3)

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

SIGNAL_COLOUR_GREEN = const(0)
SIGNAL_COLOUR_RED = const(1)
SIGNAL_COLOUR_DOUBLE_YELLOW = const(2)
SIGNAL_COLOUR_YELLOW = const(3)

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
        self.objects = objects
        self.ms = ms
        self.timer = timeout(self.ms)
        self.timer_task_handle = asyncio.create_task(self.timer.one_shot())

    async def wait(self):
        if isinstance(self.objects, tuple):
            self.objects = self.objects + (self.timer,)
        else:
            self.objects = (self.objects, self.timer)

        e = await WaitAny(self.objects).wait()

        if e is self.timer:
            return None
        else:
            self.timer_task_handle.cancel()
            return e


class WaitAllTimeout:
    def __init__(self, objects: tuple, ms: int = 0) -> None:
        self.logger = logger.logger()
        self.objects = objects
        self.ms = ms

    async def wait(self):
        if not isinstance(self.objects, tuple):
            self.objects = (self.objects,)

        e = await WaitAnyTimeout(WaitAll(self.objects), self.ms).wait()
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
        self.state = OBJECT_STATE_AWAITING_SENSOR
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
                self.state = OBJECT_STATE_UNKNOWN

        self.evt.clear()
        return self.state


class binary_sensor(sensor):
    def __init__(self, name: str, cbus: cbus.cbus, feedback_events: tuple, query_message: tuple = None):
        super(binary_sensor, self).__init__(name, cbus, feedback_events, query_message)

    def udf(self, msg: canmessage.cbusevent):
        return tuple(msg) in self.feedback_events

    def interpret(self, msg: canmessage.cbusevent):
        t = tuple(msg)
        new_state = OBJECT_STATE_OFF if msg.data[0] & 1 else OBJECT_STATE_ON

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
            self.logger.log(f'multi sensor {self.name}, from {self.state} to state {new_state}')
            self.state = new_state
            self.evt.set()

    def dispose(self) -> None:
        super().dispose()


class value_sensor(sensor):
    def __init__(self, name: str, cbus: cbus.cbus, feedback_events: tuple, query_message: tuple = None):
        super(value_sensor, self).__init__(name, cbus, feedback_events, query_message)
        self.value = -1
        self.state = OBJECT_STATE_UNKNOWN

    def interpret(self, msg):
        self.value = 99
        self.state = OBJECT_STATE_VALID
        self.evt.set()

    def udf(self, msg):
        return msg in self.feedback_events

    def dispose(self):
        super().dispose()


class base_cbus_layout_object:
    def __init__(self, name: str, cbus: cbus.cbus, control_events: tuple,
                 initial_state: int = OBJECT_STATE_UNKNOWN, feedback_events: tuple = None, query_message: tuple = None,
                 init: bool = False, wait_for_feedback: bool = True):

        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.control_events = control_events
        self.query_message = query_message
        self.has_sensor = feedback_events and len(feedback_events) == 2
        self.feedback_events = feedback_events
        self.wait_for_feedback = wait_for_feedback
        self.state = initial_state
        self.target_state = initial_state
        self.evt = asyncio.Event()

        if isinstance(self, turnout):
            self.objtypename = 'turnout'
        elif isinstance(self, semaphore_signal):
            self.objtypename = 'semaphore signal'
        elif isinstance(self, colour_light_signal):
            self.objtypename = 'colour light signal'
        else:
            self.objtypename = 'unknown'

        self.sensor = None
        self.sensor_name = None
        self.sensor_monitor_task_handle = None

        self.lock = asyncio.Lock()
        self.acquired_by = None
        self.must_lock = LOCK_BEFORE_OPERATION
        self.auto_release = False
        self.lock_timeout_task_handle = None
        self.release_timeout = RELEASE_TIMEOUT

        if self.has_sensor:
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
            self.acquired_by = None

    async def operate(self, target_state, wait_for_feedback: bool = True, force: bool = False) -> bool:
        self.target_state = target_state
        self.wait_for_feedback = wait_for_feedback
        self.evt.clear()
        ret = True

        self.logger.log(f'{self.name}: operate: current state = {self.state}, target state = {self.target_state}, wait for feedback = {self.wait_for_feedback} ')

        if self.must_lock and not self.lock.locked():
            raise RuntimeError(f'object {self.name}: object must be acquired before operating')

        if (self.target_state != self.state) or force:
            self.state = OBJECT_STATE_UNKNOWN
            ev = canmessage.event_from_tuple(self.cbus, self.control_events[target_state])
            ev.send()

            if self.has_sensor:
                self.state = OBJECT_STATE_AWAITING_SENSOR

                if self.wait_for_feedback:
                    self.logger.log(f'object {self.name} waiting for feedback sensor, current state = {self.state}')
                    self.state = await self.wait()

                    if self.state == OBJECT_STATE_UNKNOWN:
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
                    self.logger.log(f'sensor_monitor_task: object sensor {self.sensor.name} triggered, to target state, new state = {self.sensor.state}')
                    self.evt.set()
                else:
                    self.logger.log(f'sensor_monitor_task: object sensor {self.sensor.name} triggered, but not target state, target state = {self.target_state}, new state = {self.sensor.state}')

    async def wait(self, waitfor: int = WAIT_FOREVER) -> int:
        if self.has_sensor and self.state != self.target_state:
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
    def __init__(self, name, cbus: cbus.cbus, control_events: tuple, initial_state: int = OBJECT_STATE_UNKNOWN,
                 feedback_events: tuple = None, query_message: tuple = None, init: bool = False,
                 wait_for_feedback: bool = True):
        super(turnout, self).__init__(name, cbus, control_events, initial_state,
                                      feedback_events, query_message, init, wait_for_feedback)

    async def close(self, wait_for_feedback: bool = True, force: bool = False) -> bool:
        return await self.operate(OBJECT_STATE_OFF, wait_for_feedback, force)

    async def throw(self, wait_for_feedback: bool = True, force: bool = False) -> bool:
        return await self.operate(OBJECT_STATE_ON, wait_for_feedback, force)


class semaphore_signal(base_cbus_layout_object):
    def __init__(self, name: str, cbus: cbus.cbus, control_events: tuple, query_message: tuple = None,
                 initial_state: int = OBJECT_STATE_UNKNOWN, feedback_events: tuple = None, init: bool = False,
                 wait_for_feedback: bool = True):
        super(semaphore_signal, self).__init__(name, cbus, control_events, initial_state, feedback_events, query_message, init, wait_for_feedback)

    async def clear(self, wait_for_feedback: bool = True, force: bool = False) -> bool:
        return await self.operate(OBJECT_STATE_OFF, wait_for_feedback, force)

    async def set(self, wait_for_feedback: bool = True, force: bool = False) -> bool:
        return await self.operate(OBJECT_STATE_ON, wait_for_feedback, force)


class colour_light_signal(base_cbus_layout_object):
    def __init__(self, name: str, cbus: cbus.cbus, num_aspects: int, control_events: tuple, initial_state: int = OBJECT_STATE_UNKNOWN, init: bool = False):
        super(colour_light_signal, self).__init__(name, cbus, control_events, initial_state)
        self.num_aspects = num_aspects
        self.control_events = control_events
        self.state = initial_state if init else OBJECT_STATE_UNKNOWN
        self.has_sensor = False
        self.target_state = initial_state
        self.lock = asyncio.Lock()

        if init:
            self.operate(initial_state)

    def __call__(self):
        return self.state

    async def operate(self, target_state, wait_for_feedback: bool = True, force: bool = False) -> bool:
        self.target_state = target_state

        if target_state < self.num_aspects:
            ev = canmessage.event_from_tuple(self.cbus, self.control_events[target_state])
            ev.send()
            self.state = target_state
        else:
            raise ValueError('invalid aspect')

        return True

    async def wait(self, waitfor: int = WAIT_FOREVER) -> int:
        return True
