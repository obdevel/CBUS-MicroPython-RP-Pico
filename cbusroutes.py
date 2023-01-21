import time

import uasyncio as asyncio
from micropython import const

import canmessage
import cbus
import cbushistory
import cbusobjects
import cbuspubsub
import logger

ROUTE_STATE_UNSET = const(0)
ROUTE_STATE_ACQUIRED = const(1)
ROUTE_STATE_SET = const(2)

ROUTE_RELEASE_TIMEOUT = 30_000

STEP_NOOP = const(0)

STEP_LOCO_ACQUIRE = const(1)
STEP_LOCO_SPEED_DIR = const(2)
STEP_LOCO_FUNC = const(3)

STEP_SENSOR = const(4)
STEP_TURNOUT = const(5)
STEP_SIGNAL_HOME = const(6)
STEP_SIGNAL_DISTANT = const(7)
STEP_ROUTE = const(8)

STEP_TIME_WAITFOR = const(9)
STEP_CLOCK_WAITFOR = const(10)
STEP_TIME_WAITUNTIL = const(11)
STEP_CLOCK_WAITUNTIL = const(12)

STEP_EVENT_WAITFOR = const(13)
STEP_HISTORY_SEQUENCE_WAITFOR = const(14)

STEP_SEND_EVENT = const(15)
STEP_UNCOUPLER = const(16)
STEP_TURNTABLE = const(17)

STEP_LOOP = const(99)

MOVEMENT_STATE_NOT_RUNNING = const(-1)
MOVEMENT_STATE_PAUSED = const(0)
MOVEMENT_STATE_RUNNING = const(1)

current_sequences = {}


class routeobject:
    def __init__(self, robject: cbusobjects.base_cbus_layout_object, target_state: int,
                 when: int = cbusobjects.WHEN_DONT_CARE):
        self.robject = robject
        self.target_state = target_state
        self.when = when


ACQUIRE_EVENT = const(0)
SET_EVENT = const(1)
RELEASE_EVENT = const(2)
OCCUPIED_EVENT = const(3)
UNOCCUPIED_EVENT = const(4)


class route:
    def __init__(self, name, cbus: cbus.cbus, robjects: tuple[routeobject, ...], occupancy_events: tuple = None,
                 feedback_events: tuple = None, sequential: bool = False, delay: int = 0):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.robjects = robjects
        self.sequential = sequential
        self.delay = delay
        self.state = ROUTE_STATE_UNSET
        self.release_timeout_task_handle = None

        # acquire, set, release, occupied, unoccupied
        self.feedback_events = feedback_events

        self.occupancy_events = occupancy_events
        self.occupied = False
        self.occupied_evt = None
        self.occupancy_states = []

        if self.occupancy_events:
            self.occupancy_states = [False] * len(self.occupancy_events)
            if len(self.occupancy_events) > 0:
                self.occupancy_history = cbushistory.cbushistory(self.cbus, time_to_live=10_000,
                                                                 query_type=canmessage.QUERY_UDF,
                                                                 query=self.udf)
                self.occupied_evt = asyncio.Event()
                self.nx_run_task = asyncio.create_task(self.occupancy_task())

        self.lock = asyncio.Lock()
        self.locked_objects = []
        self.evt = asyncio.Event()
        self.set_time = None

    def __call__(self):
        return self.state

    def udf(self, msg):
        ev = tuple(msg)
        # self.logger.log(f'udf called with event = {ev}')
        return ev in self.occupancy_events

    async def occupancy_task(self):
        last_state = False

        while True:
            await self.occupancy_history.wait()
            t = tuple(self.occupancy_history.last_item_received.msg)
            self.logger.log(f'route {self.name}: got occupancy event')

            for i, e in enumerate(self.occupancy_events):
                if t == e[0]:
                    self.logger.log(f'route:{self.name}: event {i} is off')
                    self.occupancy_states[i] = False
                    break
                if t == e[1]:
                    self.logger.log(f'route:{self.name}: event {i} is on')
                    self.occupancy_states[i] = True
                    break

            self.occupied = True in self.occupancy_states
            self.logger.log(f'route:{self.name}: occupied = {self.occupied}')
            self.occupied_evt.set()

            if last_state != self.occupied:
                last_state = self.occupied
                if t := canmessage.tuple_from_tuples(self.feedback_events, OCCUPIED_EVENT):
                    evt = canmessage.event_from_tuple(self.cbus, t)
                    if self.occupied:
                        evt.send_on()
                    else:
                        evt.send_off()

    async def acquire(self) -> bool:
        if self.occupied:
            return False

        self.state = ROUTE_STATE_UNSET
        all_objects_locked = True

        if self.lock.locked():
            self.logger.log(f'route {self.name}: route is locked')
            all_objects_locked = False
        else:
            await self.lock.acquire()

            for obj in self.robjects:
                if obj.robject.lock.locked():
                    self.logger.log(f'route {self.name}: object {obj.robject.name} is locked')
                    all_objects_locked = False
                    break
                else:
                    await obj.robject.acquire()
                    self.locked_objects.append(obj)

            if not all_objects_locked:
                for obj in self.locked_objects:
                    obj.robject.release()
                self.lock.release()

        if t := canmessage.tuple_from_tuples(self.feedback_events, ACQUIRE_EVENT):
            msg = canmessage.event_from_tuple(self.cbus, t)
            msg.polarity = all_objects_locked
            msg.send()

        if all_objects_locked:
            self.state = ROUTE_STATE_ACQUIRED
            self.set_time = time.ticks_ms()
            self.release_timeout_task_handle = asyncio.create_task(self.release_timeout_task())
        else:
            self.state = ROUTE_STATE_UNSET

        return all_objects_locked

    async def set_route_objects(self, route_objects: list[routeobject]) -> None:
        for robj in route_objects:
            self.logger.log(
                f'set_route_object: object = {robj.robject.name}, state = {robj.target_state}, when = {robj.when}')

            if isinstance(robj.robject, cbusobjects.turnout):
                if robj.target_state == cbusobjects.TURNOUT_STATE_CLOSED:
                    await robj.robject.close()
                else:
                    await robj.robject.throw()
            elif isinstance(robj.robject, cbusobjects.semaphore_signal):
                if robj.target_state == cbusobjects.SIGNAL_STATE_CLEAR:
                    await robj.robject.clear()
                else:
                    await robj.robject.set()
            elif isinstance(robj.robject, cbusobjects.colour_light_signal):
                robj.robject.set_aspect(robj.target_state)

            if self.sequential and robj.robject.has_sensor:
                await robj.robject.sensor.wait()
            else:
                await asyncio.sleep_ms(self.delay)

    async def set(self) -> None:
        if not self.lock.locked():
            raise RuntimeError('route not acquired')

        for w in (cbusobjects.WHEN_BEFORE, cbusobjects.WHEN_DONT_CARE, cbusobjects.WHEN_AFTER):
            rlist = [obj for obj in self.robjects if obj.when == w]

            if len(rlist) > 0:
                await self.set_route_objects(rlist)

        self.state = ROUTE_STATE_SET

        state_ok = False
        for s in self.robjects:
            state_ok = s.robject.state > ROUTE_STATE_UNSET

        if t := canmessage.tuple_from_tuples(self.feedback_events, SET_EVENT):
            msg = canmessage.event_from_tuple(self.cbus, t)
            msg.polarity = state_ok
            msg.send()

        self.evt.set()

    def release(self) -> None:
        for obj in self.locked_objects:
            if obj.robject.lock.locked():
                obj.robject.release()

        self.locked_objects = []
        self.lock.release()
        self.evt.clear()
        self.state = ROUTE_STATE_UNSET

        if t := canmessage.tuple_from_tuples(self.feedback_events, RELEASE_EVENT):
            msg = canmessage.event_from_tuple(self.cbus, t)
            msg.send()

    def keepalive(self, delta: int = 60_000):
        self.set_time += delta

    def release_timeout_task(self):
        while True:
            await asyncio.sleep_ms(ROUTE_RELEASE_TIMEOUT)
            if time.ticks_diff(time.ticks_ms(), self.set_time) >= ROUTE_RELEASE_TIMEOUT:
                break
            else:
                self.logger.log('release_timeout_task: timeout was extended')

        if self.state != ROUTE_STATE_UNSET:
            self.logger.log('route release timeout')
            self.release()

    def wait(self, timeout=0):
        await self.evt.wait()


class entry_exit:
    def __init__(self, name: str, cbus: cbus.cbus, nxroute: route, switch_events: tuple, feedback_events: tuple):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.switch_events = switch_events
        self.nxroute = nxroute
        self.feedback_events = feedback_events

        self.switch_history = cbushistory.cbushistory(self.cbus, time_to_live=5_000, query_type=canmessage.QUERY_UDF,
                                                      query=self.udf)
        self.nx_run_task_handle = asyncio.create_task(self.nx_run_task())

    def udf(self, msg):
        if tuple(msg) in self.switch_events:
            return True

    async def nx_run_task(self):
        while True:
            await self.switch_history.add_evt.wait()
            self.switch_history.add_evt.clear()

            if self.nxroute.state == ROUTE_STATE_UNSET:
                if self.switch_history.sequence_received(self.switch_events):
                    self.logger.log(f'nxroute:{self.name}: received sequence')
                    b = await self.nxroute.acquire()
                    self.logger.log(f'nxroute:{self.name}: acquire returns {b}')
                    if b:
                        await self.nxroute.set()
                        self.logger.log(f'nxroute:{self.name}: route set')
                    if len(self.feedback_events) > 0 and len(self.feedback_events[0] == 3):
                        msg = canmessage.event_from_tuple(self.cbus, self.feedback_events[0])
                        msg.polarity = int(b)
                        msg.send()
                else:
                    self.logger.log(f'nxroute:{self.name}: received one event')
                    if len(self.feedback_events) > 1 and len(self.feedback_events[1] == 3):
                        msg = canmessage.event_from_tuple(self.cbus, self.feedback_events[1])
                        msg.send()
            else:
                if self.switch_history.any_received(self.switch_events):
                    self.logger.log(f'nxroute:{self.name}: releasing route')
                    self.nxroute.release()
                    self.nxroute.release_timeout_task_handle.cancel()
                    if len(self.feedback_events) > 2 and len(self.feedback_events[2] == 3):
                        msg = canmessage.event_from_tuple(self.cbus, self.feedback_events[2])
                        msg.send()


class step:
    def __init__(self, object, type, data, desired_state):
        self.object = object
        self.type = type
        self.data = data
        self.desired_state = desired_state


class sequence:
    def __init__(self, name: str, cbus: cbus.cbus, steps: tuple[step, ...], autorun: bool = False, operate_objects=False, cab=None, loco: int = 0, clock=None) -> None:
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.steps = steps
        self.operate_objects = operate_objects

        self.cab = cab
        self.loco = loco

        self.evt = asyncio.Event()
        self.evt.clear()
        self.sub = cbuspubsub.subscription('ps', self.cbus, 0, 0)

        self.clock = None

        self.state = MOVEMENT_STATE_NOT_RUNNING
        self.current_index = -1
        current_sequences[self.name] = self

        if autorun:
            self.state = MOVEMENT_STATE_PAUSED
            self.run_task_handle = asyncio.create_task(self.run_sequence())

    def init(self) -> None:
        pass

    # @staticmethod
    # def create_from_list(step_objects: tuple[tuple, ...]) -> tuple:
    #     steps_list = []
    #     for step_object in step_objects:
    #         st = step(step_object[0], step_object[1], step_object[2], step_object[3])
    #         steps_list.append(st)
    #     return tuple(steps_list)

    def run(self):
        self.state = MOVEMENT_STATE_PAUSED
        self.run_task_handle = asyncio.create_task(self.run_sequence())

    async def run_sequence(self) -> None:
        try:
            self.logger.log('sequence running...')

            for self.current_index in range(len(self.steps)):
                if not self.evt.is_set():
                    self.logger.log('sequence, awaiting event set')
                    self.state = MOVEMENT_STATE_PAUSED
                    await self.evt.wait()
                    self.state = MOVEMENT_STATE_RUNNING
                    self.logger.log('sequence, event is set, continuing')
                else:
                    self.state = MOVEMENT_STATE_RUNNING

                current_step = self.steps[self.current_index]
                self.logger.log(f'sequence:{self.name} processing step {self.current_index} = {current_step.type}')

                if current_step.type == STEP_LOCO_ACQUIRE:
                    self.logger.log('acquire loco')
                    if not await self.cab.acquire(self.loco):
                        self.logger.log('failed to acquire loco')
                        break

                elif current_step.type == STEP_LOCO_SPEED_DIR:
                    self.logger.log('set loco speed')
                    self.loco.speed = current_step.data[0]
                    self.loco.direction = current_step.data[1]
                    self.cab.set_speed_and_direction(self.loco)

                elif current_step.type == STEP_LOCO_FUNC:
                    self.logger.log('set loco function')
                    self.cab.function(self.loco, current_step.data[0], current_step.data[1])

                elif current_step.type == STEP_SENSOR:
                    self.logger.log(f'sensor {current_step.object.name}, state = {current_step.object.state}')

                elif current_step.type == STEP_SIGNAL_DISTANT:
                    self.logger.log(f'distant signal {current_step.object.name}, state = {current_step.object.state}')
                    if self.operate_objects:
                        pass
                    await current_step.object.wait()

                elif current_step.type == STEP_SIGNAL_HOME:
                    self.logger.log(f'home signal {current_step.object.name}, state = {current_step.object.state}')
                    if self.operate_objects:
                        pass
                    await current_step.object.wait()

                elif current_step.type == STEP_TURNOUT:
                    self.logger.log(f'turnout {current_step.object.name}, state = {current_step.object.state}')
                    if self.operate_objects:
                        pass
                    await current_step.object.wait()

                elif current_step.type == STEP_ROUTE:
                    self.logger.log(f'route {current_step.object.name}, state = {current_step.object.state}')
                    if self.operate_objects:
                        pass
                    await current_step.object.wait()

                elif current_step.type == STEP_TIME_WAITFOR:
                    self.logger.log(f'time wait for {current_step.data}')
                    await asyncio.sleep_ms(current_step.data)

                elif current_step.type == STEP_CLOCK_WAITFOR:
                    self.logger.log('clock wait for')

                elif current_step.type == STEP_TIME_WAITUNTIL:
                    self.logger.log(f'time wait until {current_step.desired_state}')
                    while time.ticks_ms() != current_step.desired_state:
                        await asyncio.sleep_ms(500)

                elif current_step.type == STEP_CLOCK_WAITUNTIL:
                    self.logger.log('clock wait until')

                elif current_step.type == STEP_EVENT_WAITFOR:
                    self.logger.log(f'wait for event {current_step.data}')
                    sub = cbuspubsub.subscription('m1', self.cbus, canmessage.QUERY_TUPLES, tuple(current_step.data))
                    await sub.wait()
                    sub.unsubscribe()

                elif current_step.type == STEP_HISTORY_SEQUENCE_WAITFOR:
                    self.logger.log(f'wait for sequence {current_step.data[0]}')
                    history = cbushistory.cbushistory(self.cbus, 1_000, 10_000, canmessage.QUERY_TUPLES, tuple(current_step.data))
                    while True:
                        await history.wait()
                        if history.sequence_received(current_step.data[0]):
                            history.remove()
                            break

                elif current_step.type == STEP_SEND_EVENT:
                    self.logger.log('send event')
                    evt = canmessage.event_from_tuple(self.cbus, current_step.data)
                    evt.send()

                elif current_step.type == STEP_UNCOUPLER:
                    current_step.object.on()

                elif current_step.type == STEP_TURNTABLE:
                    current_step.object.position_to(current_step.data, True)

                elif current_step.type == STEP_LOOP:
                    self.logger.log(f'loop back to step {current_step.data[0]}')
                    idx = current_step.data[0]

                else:
                    self.logger.log(f'unknown sequence step type {current_step.type}')

        except asyncio.CancelledError:
            self.logger.log(f'sequence cancelled')
            if self.cab:
                self.cab.emergency_stop(self.loco)
        finally:
            self.logger.log(f'end of sequence')
            self.sub.unsubscribe()
            del current_sequences[self.name]

    def pause(self) -> None:
        self.evt.clear()

    def resume(self):
        self.evt.set()

    def cancel(self) -> None:
        self.run_task_handle.cancel()
