import time

import uasyncio as asyncio
from micropython import const

import canmessage
import cbus
import cbusobjects
import cbuspubsub
import logger

ROUTE_STATE_ERROR = const(-1)
ROUTE_STATE_UNSET = const(0)
ROUTE_STATE_ACQUIRED = const(1)
ROUTE_STATE_AWAITING_FEEDBACK = const(2)
ROUTE_STATE_SET = const(3)

NO_AUTO_RELEASE = const(-1)


class routeobject:
    def __init__(self, robject: cbusobjects.base_cbus_layout_object, target_state: int, when: int = cbusobjects.WHEN_DURING):
        self.robject = robject
        # self.target_state = target_state
        self.robject.target_state = target_state
        self.when = when


ROUTE_ACQUIRE_EVENT = const(0)
ROUTE_SET_EVENT = const(1)
ROUTE_RELEASE_EVENT = const(2)
ROUTE_OCCUPIED_EVENT = const(3)
ROUTE_UNOCCUPIED_EVENT = const(4)
ROUTE_ERROR_EVENT = const(5)


class route:
    def __init__(self, name, cbus: cbus.cbus, robjects: tuple[routeobject, ...], occupancy_events: tuple = None,
                 producer_events: tuple = None, sequential: bool = False, delay: int = 0, wait_for_feedback: bool = False,
                 wait_time: int = 0, hold_time: int = NO_AUTO_RELEASE):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.robjects = robjects
        self.sequential = sequential
        self.delay = delay
        self.wait_for_feedback = wait_for_feedback
        self.wait_time = wait_time
        self.hold_time = hold_time
        self.state = ROUTE_STATE_UNSET
        self.release_timeout_task_handle = None

        for o in self.robjects:
            if not isinstance(o, routeobject):
                raise TypeError('route component is not of type routeobject')

        # acquire, set, release, occupied, unoccupied, error
        self.producer_events = producer_events

        self.occupancy_events = occupancy_events
        self.occupied = False
        self.occupied_evt = None
        self.occupancy_states = []
        self.occupancy_task_handle = None

        if self.occupancy_events:
            self.occupancy_states = [False] * len(self.occupancy_events)
            if len(self.occupancy_events) > 0:
                self.occupancy_sub = cbuspubsub.subscription('route:' + self.name + ':occ:sub', self.cbus, query_type=canmessage.QUERY_UDF, query=self.occ_sub_udf)
                self.occupied_evt = asyncio.Event()
                self.occupancy_task_handle = asyncio.create_task(self.occupancy_task())

        self.lock = asyncio.Lock()
        self.locked_objects = []
        self.evt = asyncio.Event()
        self.acquire_time = None

    def dispose(self) -> None:
        if self.occupancy_events:
            self.occupancy_sub.unsubscribe()
            self.occupancy_task_handle.cancel()

    def __call__(self) -> int:
        return self.state

    def occ_sub_udf(self, msg) -> bool:
        ev = tuple(msg)
        for ov in self.occupancy_events:
            if ev in ov:
                return True
        return False

    async def occupancy_task(self) -> None:
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
                if t := canmessage.tuple_from_tuples(self.producer_events, ROUTE_OCCUPIED_EVENT):
                    evt = canmessage.event_from_tuple(self.cbus, t)
                    if self.occupied:
                        evt.send_on()
                    else:
                        evt.send_off()

    async def acquire(self) -> bool:
        if self.occupied:
            self.logger.log(f'route {self.name}: acquire, route is occupied {self.occupancy_states}')
            return False

        self.state = ROUTE_STATE_UNSET
        all_objects_locked = True

        if self.lock.locked():
            self.logger.log(f'route {self.name}: route is already locked')
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

        if t := canmessage.tuple_from_tuples(self.producer_events, ROUTE_ACQUIRE_EVENT):
            msg = canmessage.event_from_tuple(self.cbus, t)
            msg.polarity = all_objects_locked
            msg.send()

        if all_objects_locked:
            self.state = ROUTE_STATE_ACQUIRED
            if self.hold_time != NO_AUTO_RELEASE:
                self.acquire_time = time.ticks_ms()
                self.release_timeout_task_handle = asyncio.create_task(self.release_timeout_task())
        else:
            self.state = ROUTE_STATE_UNSET

        return all_objects_locked

    async def set_route_objects_group(self, route_objects: list[routeobject]) -> None:
        if len(route_objects) == 0:
            self.logger.log('set_route_objects_group: no objects in this group')
            return

        group = route_objects[0].when
        self.logger.log(f'set_route_objects_group: processing group = {group}')

        for robj in route_objects:
            self.logger.log(f'set_route_object: object = {robj.robject.name}, state = {robj.robject.target_state}, when = {robj.when}')

            await robj.robject.operate(robj.robject.target_state, wait_for_feedback=self.sequential, force=True)

            if self.sequential and robj.robject.has_sensor:
                self.logger.log(f'set_route_objects_group: waiting for object, name = {robj.robject.name}')
                x = await robj.robject.wait(2_000)
                self.logger.log(f'set_route_objects_group: wait returns {x}')
            else:
                self.logger.log(f'set_route_objects_group: sleeping for delay = {self.delay}')
                await asyncio.sleep_ms(self.delay)

        if not self.sequential and self.wait_for_feedback:
            self.logger.log(f'set_route_objects_group: collecting objects with sensors for group = {group}')
            wait_objects = []
            for robj in route_objects:
                if robj.robject.has_sensor:
                    wait_objects.append(robj.robject)

            if len(wait_objects) > 0:
                self.logger.log(f'set_route_objects_group: waiting for objects with sensors, for group = {group}, objects = {wait_objects}')
                x = await cbusobjects.WaitAllTimeout(tuple(wait_objects), self.wait_time).wait()
                if x is None:
                    self.logger.log(f'set_route_objects_group: wait timed out after {self.wait_time}')
                else:
                    self.logger.log(f'set_route_objects_group: all objects responded')
            else:
                self.logger.log('set_route_objects_group: no objects with sensors')
        else:
            self.logger.log(f'set_route_objects_group: not waiting for feedback for group = {group}, sequential = {self.sequential}, wait_for_feedback = {self.wait_for_feedback}')

        self.logger.log()

    async def set(self) -> int:
        if not self.lock.locked():
            raise RuntimeError('route not acquired')

        self.logger.log('route set begins')

        for rgroup in (cbusobjects.WHEN_BEFORE, cbusobjects.WHEN_DURING, cbusobjects.WHEN_AFTER):
            self.logger.log(f'set: setting objects for group = {rgroup}')
            group_list = [obj for obj in self.robjects if obj.when == rgroup]

            if group_list and len(group_list) > 0:
                await self.set_route_objects_group(group_list)
            else:
                self.logger.log('set: no objects in this group')

        self.logger.log('set: all groups set')

        self.logger.log('set: checking all object states')
        state_ok = False
        self.state = ROUTE_STATE_ACQUIRED

        num_objects_unset, num_objects_with_sensor = self.calc_state()

        if num_objects_unset > 0:
            if num_objects_with_sensor > 0:
                self.state = ROUTE_STATE_AWAITING_FEEDBACK
            else:
                self.state = ROUTE_STATE_UNSET
        else:
            self.state = ROUTE_STATE_SET

        if self.state == ROUTE_STATE_SET:
            if t := canmessage.tuple_from_tuples(self.producer_events, ROUTE_SET_EVENT):
                msg = canmessage.event_from_tuple(self.cbus, t)
                msg.polarity = state_ok
                msg.send()

        self.evt.set()

        if self.state == ROUTE_STATE_SET:
            if t := canmessage.tuple_from_tuples(self.producer_events, ROUTE_SET_EVENT):
                msg = canmessage.event_from_tuple(self.cbus, t)
                msg.send()

        self.logger.log(f'route set complete, overall state = {self.state}')
        return self.state

    def calc_state(self) -> tuple[int, int]:
        num_objects_unset = 0
        num_objects_with_sensor = 0

        for obj in self.robjects:
            if obj.robject.state == obj.robject.target_state:
                self.logger.log(f'route wait: object {obj.robject.name} has correct state = {obj.robject.state}')
                self.state = ROUTE_STATE_SET
            else:
                self.logger.log(f'route wait: object {obj.robject.name} has incorrect state, {obj.robject.state} != {obj.robject.target_state}')
                num_objects_unset += 1
                if obj.robject.has_sensor:
                    num_objects_with_sensor += 1

        if num_objects_unset > 0:
            if num_objects_with_sensor > 0:
                self.state = ROUTE_STATE_AWAITING_FEEDBACK
            else:
                self.state = ROUTE_STATE_UNSET
        else:
            self.state = ROUTE_STATE_SET

        self.logger.log(f'route: calc_state: state = {self.state}')
        return num_objects_unset, num_objects_with_sensor

    def release(self) -> None:
        for obj in self.locked_objects:
            if obj.robject.lock.locked():
                obj.robject.release()

        self.locked_objects = []
        self.lock.release()
        self.evt.clear()
        self.state = ROUTE_STATE_UNSET

        if t := canmessage.tuple_from_tuples(self.producer_events, ROUTE_RELEASE_EVENT):
            msg = canmessage.event_from_tuple(self.cbus, t)
            msg.send()

    def release_timeout_task(self) -> None:
        self.logger.log(f'route: release_timeout_task: sleeping at {time.ticks_ms()}')
        await asyncio.sleep_ms(self.hold_time)

        if self.state != ROUTE_STATE_UNSET:
            self.logger.log('route: release_timeout_task: release timeout')
            self.release()

    async def wait(self, timeout: int = 0) -> int:
        if not self.lock.locked():
            raise RuntimeError('route not acquired')

        self.logger.log(f'route wait: current state = {self.state}')
        num_objects_unset, num_objects_with_sensor = self.calc_state()

        if timeout > 0 and num_objects_unset > 0:
            objs = []
            for obj in self.robjects:
                if obj.robject.has_sensor:
                    objs.append(obj.robject)

            if len(objs) > 0:
                self.state = ROUTE_STATE_UNSET
                self.logger.log(f'route wait: waiting for {len(objs)} objects = {objs}, current route state = {self.state}')
                e = await cbusobjects.WaitAllTimeout(tuple(objs), timeout).wait()
                self.logger.log(f'route wait: return is {e}')
                self.state = ROUTE_STATE_SET if e else ROUTE_STATE_ERROR

                num_objects_unset, num_objects_with_sensor = self.calc_state()
                self.logger.log(f'route wait: state now = {self.state}')

        if self.state == ROUTE_STATE_SET:
            if t := canmessage.tuple_from_tuples(self.producer_events, ROUTE_SET_EVENT):
                msg = canmessage.event_from_tuple(self.cbus, t)
                msg.send()

        return self.state
