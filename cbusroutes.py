import time

import uasyncio as asyncio
from micropython import const

import canmessage
import cbus
import cbushistory
import cbusobjects
import cbuspubsub
import logger

ROUTE_STATE_ERROR = const(-1)
ROUTE_STATE_UNSET = const(0)
ROUTE_STATE_ACQUIRED = const(1)
ROUTE_STATE_SET = const(2)

ROUTE_RELEASE_TIMEOUT = const(30_000)
WAIT_TIME = const(10_000)


class routeobject:
    def __init__(self, robject: cbusobjects.base_cbus_layout_object, target_state: int,
                 when: int = cbusobjects.WHEN_DURING):
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
                 producer_events: tuple = None, sequential: bool = False, delay: int = 0, wait_for_feedback: bool = False):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.robjects = robjects
        self.sequential = sequential
        self.delay = delay
        self.wait_for_feedback = wait_for_feedback
        self.state = ROUTE_STATE_UNSET
        self.release_timeout_task_handle = None

        # acquire, set, release, occupied, unoccupied
        self.producer_events = producer_events

        self.occupancy_events = occupancy_events
        self.occupied = False
        self.occupied_evt = None
        self.occupancy_states = []
        self.occupancy_task_handle = None

        if self.occupancy_events:
            self.occupancy_states = [False] * len(self.occupancy_events)
            if len(self.occupancy_events) > 0:
                self.occupancy_sub = cbuspubsub.subscription(self.name + ':occ', self.cbus, query_type=canmessage.QUERY_UDF, query=self.udf)
                self.occupied_evt = asyncio.Event()
                self.occupancy_task_handle = asyncio.create_task(self.occupancy_task())

        self.lock = asyncio.Lock()
        self.locked_objects = []
        self.evt = asyncio.Event()
        self.set_time = None

    def dispose(self):
        if self.occupancy_events:
            self.occupancy_sub.unsubscribe()
            self.occupancy_task_handle.cancel()

    def __call__(self):
        return self.state

    def udf(self, msg):
        ev = tuple(msg)
        for ov in self.occupancy_events:
            if ev in ov:
                return True
        return False

    async def occupancy_task(self):
        last_state = False

        while True:
            msg = await self.occupancy_sub.wait()
            t = tuple(msg)
            # self.logger.log(f'route {self.name}: got occupancy event = {t}')

            for i, e in enumerate(self.occupancy_events):
                if t == e[0]:
                    # self.logger.log(f'route:{self.name}: event {i} is off')
                    self.occupancy_states[i] = False
                    break
                if t == e[1]:
                    # self.logger.log(f'route:{self.name}: event {i} is on')
                    self.occupancy_states[i] = True
                    break

            self.occupied = True in self.occupancy_states
            self.occupied_evt.set()
            self.occupied_evt.clear()

            if last_state != self.occupied:
                last_state = self.occupied
                self.logger.log(f'route:{self.name}: occupancy state changed to {self.occupied}')
                if t := canmessage.tuple_from_tuples(self.producer_events, OCCUPIED_EVENT):
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

        if t := canmessage.tuple_from_tuples(self.producer_events, ACQUIRE_EVENT):
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

    async def set_route_objects_group(self, route_objects: list[routeobject]) -> None:
        group = route_objects[0].when
        self.logger.log(f'set_route_objects_group: processing group = {group}')

        for robj in route_objects:
            self.logger.log(f'set_route_object: object = {robj.robject.name}, state = {robj.target_state}, when = {robj.when}')

            # if isinstance(robj.robject, cbusobjects.turnout):
            #     if robj.target_state == cbusobjects.TURNOUT_STATE_CLOSED:
            #         await robj.robject.close(wait_for_feedback=self.sequential)
            #     else:
            #         await robj.robject.throw(wait_for_feedback=self.sequential)
            # elif isinstance(robj.robject, cbusobjects.semaphore_signal):
            #     if robj.target_state == cbusobjects.SIGNAL_STATE_CLEAR:
            #         await robj.robject.clear(wait_for_feedback=self.sequential)
            #     else:
            #         await robj.robject.set(wait_for_feedback=self.sequential)
            # elif isinstance(robj.robject, cbusobjects.colour_light_signal):
            #     robj.robject.set_aspect(robj.target_state)

            await robj.robject.operate(robj.target_state, wait_for_feedback=self.sequential, force=True)

            if self.sequential and robj.robject.has_sensor:
                self.logger.log(f'set_route_objects_group: waiting for object, name = {robj.robject.name}')
                x = await robj.robject.sensor.wait(2_000)
                self.logger.log(f'set_route_objects_group: wait returns {x}')
            else:
                self.logger.log(f'set_route_objects_group: sleeping for delay = {self.delay}')
                await asyncio.sleep_ms(self.delay)
                self.logger.log(f'set_route_objects_group: sleep done')

        if not self.sequential and self.wait_for_feedback:
            self.logger.log(f'set_route_objects_group: collecting objects with sensors for group = {group}')
            wait_events = []
            for robj in route_objects:
                if robj.robject.has_sensor:
                    wait_events.append(robj.robject.feedback_events[robj.target_state])

            if len(wait_events) > 0:
                self.logger.log(f'set_route_objects_group: waiting for objects with sensors, for group = {group}')
                x = cbusobjects.WaitAllTimeout(tuple(wait_events), WAIT_TIME)
                if x is None:
                    self.logger.log(f'set_route_objects_group: wait timed out')
                else:
                    self.logger.log(f'set_route_objects_group: all objects responded')
            else:
                self.logger.log('set_route_objects_group: no objects with sensors')
        else:
            self.logger.log(f'set_route_objects_group: not waiting for feedback for group = {group}, seq = {self.sequential}, wait = {self.wait_for_feedback}')

    async def set(self) -> None:
        if not self.lock.locked():
            raise RuntimeError('route not acquired')

        self.logger.log('route set begins')

        for rgroup in (cbusobjects.WHEN_BEFORE, cbusobjects.WHEN_DURING, cbusobjects.WHEN_AFTER):
            self.logger.log(f'set: setting objects for group = {rgroup}')
            group_list = [obj for obj in self.robjects if obj.when == rgroup]
            await self.set_route_objects_group(group_list)

        self.logger.log('set: all groups set')

        self.logger.log('set: checking all object states')
        state_ok = False
        self.state = ROUTE_STATE_ACQUIRED

        for obj in self.robjects:
            self.logger.log(f'set: object = {obj.robject.name} state = {obj.robject.state}')
            state_ok = obj.robject.state > cbusobjects.OBJECT_STATE_UNKNOWN

        self.state = ROUTE_STATE_SET if state_ok else ROUTE_STATE_ERROR

        if self.state == ROUTE_STATE_SET:
            if t := canmessage.tuple_from_tuples(self.producer_events, SET_EVENT):
                msg = canmessage.event_from_tuple(self.cbus, t)
                msg.polarity = state_ok
                msg.send()

        self.evt.set()
        self.logger.log(f'route set complete, overall state = {self.state}')

    def release(self) -> None:
        for obj in self.locked_objects:
            if obj.robject.lock.locked():
                obj.robject.release()

        self.locked_objects = []
        self.lock.release()
        self.evt.clear()
        self.state = ROUTE_STATE_UNSET

        if t := canmessage.tuple_from_tuples(self.producer_events, RELEASE_EVENT):
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
    def __init__(self, name: str, cbus: cbus.cbus, nxroute: route, switch_events: tuple, producer_events: tuple):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.switch_events = switch_events
        self.nxroute = nxroute
        self.producer_events = producer_events

        self.switch_history = cbushistory.cbushistory(self.cbus, time_to_live=5_000, query_type=canmessage.QUERY_UDF,
                                                      query=self.udf)
        self.nx_run_task_handle = asyncio.create_task(self.nx_run_task())

    def dispose(self):
        self.switch_history.remove()
        self.nx_run_task_handle.cancel()
        self.nxroute.dispose()

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
                    if len(self.producer_events) > 0 and len(self.producer_events[0] == 3):
                        msg = canmessage.event_from_tuple(self.cbus, self.producer_events[0])
                        msg.polarity = int(b)
                        msg.send()
                else:
                    self.logger.log(f'nxroute:{self.name}: received one event')
                    if len(self.producer_events) > 1 and len(self.producer_events[1] == 3):
                        msg = canmessage.event_from_tuple(self.cbus, self.producer_events[1])
                        msg.send()
            else:
                if self.switch_history.any_received(self.switch_events):
                    self.logger.log(f'nxroute:{self.name}: releasing route')
                    self.nxroute.release()
                    self.nxroute.release_timeout_task_handle.cancel()
                    if len(self.producer_events) > 2 and len(self.producer_events[2] == 3):
                        msg = canmessage.event_from_tuple(self.cbus, self.producer_events[2])
                        msg.send()
