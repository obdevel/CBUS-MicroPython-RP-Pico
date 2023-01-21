import time

import uasyncio as asyncio
from micropython import const

import canmessage
import cbus
import cbushistory
import cbusobjects
import logger

ROUTE_STATE_UNSET = const(0)
ROUTE_STATE_ACQUIRED = const(1)
ROUTE_STATE_SET = const(2)

ROUTE_RELEASE_TIMEOUT = 30_000


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
