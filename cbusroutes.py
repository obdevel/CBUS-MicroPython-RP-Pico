import time

import uasyncio as asyncio
from micropython import const

import canmessage
import cbus
import cbusobjects
import cbuspubsub
import logger

WHEN_BEFORE = const(0)
WHEN_DURING = const(1)
WHEN_AFTER = const(2)

ROUTE_STATE_ERROR = const(-1)
ROUTE_STATE_UNSET = const(0)
ROUTE_STATE_ACQUIRED = const(1)
ROUTE_STATE_AWAITING_FEEDBACK = const(2)
ROUTE_STATE_SET = const(3)

ROUTE_ACQUIRE_EVENT = const(0)
ROUTE_SET_EVENT = const(1)
ROUTE_RELEASE_EVENT = const(2)
ROUTE_OCCUPIED_EVENT = const(3)
ROUTE_ERROR_EVENT = const(4)

NO_AUTO_RELEASE = const(-1)


class routeobject:
    def __init__(self, robject: cbusobjects.base_cbus_layout_object, target_state: int, when: int = WHEN_DURING):
        self.robject = robject
        self.target_state = target_state
        self.robject.target_state = target_state
        self.when = when


class route:
    def __init__(self, name, cbus: cbus.cbus, robjects: tuple[routeobject, ...], occupancy_events: tuple = None,
                 producer_events: tuple = None, sequential: bool = False, delay: int = 0, wait_for_feedback: bool = False,
                 wait_time: int = 0, hold_time: int = NO_AUTO_RELEASE):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.robjects = robjects
        self.original_target_states = tuple([ro.target_state for ro in self.robjects])
        self.sequential = sequential
        self.delay = delay
        self.wait_for_feedback = wait_for_feedback
        self.wait_time = wait_time
        self.hold_time = hold_time
        self.state = ROUTE_STATE_UNSET
        self.release_timeout_task_handle = None

        for i, obj in enumerate(self.robjects):
            if not isinstance(obj, routeobject):
                raise TypeError(f'route component {i} is not of type routeobject')

        # acquired, set, released, (un)occupied, error
        self.producer_events = producer_events

        self.occupancy_events = occupancy_events
        self.occupied = False
        self.occupied_evt = None
        self.occupancy_states = []
        self.occupancy_task_handle = None

        if self.occupancy_events:
            if len(self.occupancy_events) > 0:
                self.occupancy_states = [False] * len(self.occupancy_events)
                self.occupancy_sub = cbuspubsub.subscription('route:' + self.name + ':occ:sub', self.cbus, query_type=canmessage.QUERY_UDF, query=self.occ_sub_udf)
                self.occupancy_task_handle = asyncio.create_task(self.occupancy_task())

        self.lock = asyncio.Lock()
        self.acquired_by = None
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

            for i, e in enumerate(self.occupancy_events):
                if t == e[0]:
                    self.occupancy_states[i] = False
                    break
                if t == e[1]:
                    self.occupancy_states[i] = True
                    break

            self.occupied = True in self.occupancy_states

            if last_state != self.occupied:
                last_state = self.occupied
                self.logger.log(f'route:{self.name}: occupancy state changed to {self.occupied}')
                if t := canmessage.tuple_from_tuples(self.producer_events, ROUTE_OCCUPIED_EVENT):
                    evt = canmessage.event_from_tuple(self.cbus, t)
                    if self.occupied:
                        evt.send_on()
                    else:
                        evt.send_off()

    async def acquire(self, acquirer: str = None) -> bool:
        if self.occupied:
            self.logger.log(f'route {self.name}: acquire, route is occupied {self.occupancy_states}')
            return False

        self.state = ROUTE_STATE_UNSET
        self.acquired_by = acquirer
        all_objects_locked = True

        if self.lock.locked():
            self.logger.log(f'route {self.name}: route is already locked by {self.acquired_by}')
            all_objects_locked = False
        else:
            await self.lock.acquire()

            for obj in self.robjects:
                if obj.robject.lock.locked():
                    self.logger.log(f'route {self.name}: object {obj.robject.name} is locked by {obj.robject.acquired_by}')
                    all_objects_locked = False
                    break
                else:
                    await obj.robject.acquire()
                    obj.robject.acquired_by = self.acquired_by
                    self.locked_objects.append(obj)

            if not all_objects_locked:
                for obj in self.locked_objects:
                    obj.robject.release()
                    obj.robject.acquired_by = None
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

    async def set_route_group_objects(self, route_group_objects: list[routeobject]) -> None:
        if len(route_group_objects) == 0:
            self.logger.log('set_route_group_objects: no objects in this group')
            return

        group = route_group_objects[0].when
        self.logger.log(f'set_route_group_objects: processing group = {group}')

        for robj in route_group_objects:
            self.logger.log(f'set_route_object: object = {robj.robject.name}, target state = {robj.target_state}, object state = {robj.robject.state}, when = {robj.when}')

            await robj.robject.operate(robj.robject.target_state, wait_for_feedback=self.sequential, force=False)

            if self.sequential and robj.robject.has_sensor:
                self.logger.log(f'set_route_group_objects: waiting for object, name = {robj.robject.name}')
                x = await robj.robject.wait(cbusobjects.WAIT_FOREVER)
                self.logger.log(f'set_route_group_objects: wait returns {x}')
            else:
                self.logger.log(f'set_route_group_objects: sleeping for delay = {self.delay}')
                await asyncio.sleep_ms(self.delay)

        if not self.sequential and self.wait_for_feedback:
            self.logger.log(f'set_route_group_objects: collecting objects with sensors for group = {group}')
            wait_objects = []
            for robj in route_group_objects:
                if robj.robject.has_sensor and (robj.robject.state != robj.robject.target_state) or (robj.robject.state != robj.target_state):
                    wait_objects.append(robj.robject)

            if len(wait_objects) > 0:
                self.logger.log(f'set_route_group_objects: waiting for objects with sensors, for group = {group}, objects = {wait_objects}')
                x = await cbusobjects.WaitAllTimeout(tuple(wait_objects), self.wait_time).wait()
                if x is None:
                    self.logger.log(f'set_route_group_objects: wait timed out after {self.wait_time}')
                else:
                    self.logger.log(f'set_route_group_objects: all objects responded')
            else:
                self.logger.log('set_route_group_objects: no objects to wait for')
        else:
            self.logger.log(f'set_route_group_objects: not waiting for feedback for group = {group}, sequential = {self.sequential}, wait_for_feedback = {self.wait_for_feedback}')

    async def set(self, correct_states: bool = True) -> int:
        if not self.lock.locked():
            raise RuntimeError('route not acquired')

        self.logger.log('route set begins')

        self.check_target_states(correct_states)

        for rgroup in (WHEN_BEFORE, WHEN_DURING, WHEN_AFTER):
            self.logger.log(f'set: setting objects for group = {rgroup}')
            group_list = [obj for obj in self.robjects if obj.when == rgroup]

            if group_list and len(group_list) > 0:
                await self.set_route_group_objects(group_list)
            else:
                self.logger.log('set: no objects in this group')

        self.logger.log('set: all groups set')

        self.logger.log('set: checking all object states')
        state_ok = False
        self.state = ROUTE_STATE_ACQUIRED

        num_objects_unset, num_objects_with_sensor = self.reset_target_states()

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

        self.logger.log(f'route set complete, overall route state = {self.state}')
        return self.state

    def check_target_states(self, correct_states: bool = False):
        self.logger.log('route: checking object target states')
        target_states_unchanged = True

        for i, s in enumerate(self.original_target_states):
            if self.robjects[i].robject.target_state != self.original_target_states[i]:
                self.logger.log(f'route: target state changed for object = {i}')
                target_states_unchanged = False

        if target_states_unchanged:
            self.logger.log('route: all target states unchanged')

        if not target_states_unchanged and correct_states:
            self.logger.log('route: correcting target states')
            for i, s in enumerate(self.original_target_states):
                self.robjects[i].robject.target_state = s
                self.robjects[i].target_state = s
            self.logger.log('route: target states corrected')

    def reset_target_states(self) -> tuple[int, int]:
        num_objects_unset = 0
        num_objects_with_sensor = 0

        for obj in self.robjects:
            obj.robject.target_state = obj.target_state

        for obj in self.robjects:
            if obj.robject.state == obj.target_state:
                self.logger.log(f'route: reset_target_states: object {obj.robject.name} has correct state = {obj.robject.state}')
                self.state = ROUTE_STATE_SET
            else:
                self.logger.log(f'route: reset_target_states: object {obj.robject.name} has incorrect state, {obj.robject.state} != {obj.target_state}')
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

        self.logger.log(f'route: reset_target_states: overall route state = {self.state}')
        return num_objects_unset, num_objects_with_sensor

    def reverse(self):
        for x in self.robjects:
            if x.when == WHEN_BEFORE:
                x.when = WHEN_AFTER
            elif x.when == WHEN_AFTER:
                x.when = WHEN_BEFORE

            if x.target_state == cbusobjects.OBJECT_STATE_OFF:
                x.target_state = x.robject.target_state = cbusobjects.OBJECT_STATE_ON
            elif x.target_state == cbusobjects.OBJECT_STATE_ON:
                x.target_state = x.robject.target_state = cbusobjects.OBJECT_STATE_OFF

        self.state = ROUTE_STATE_UNSET

    def release(self) -> None:
        for obj in self.locked_objects:
            if obj.robject.lock.locked():
                obj.robject.release()
                obj.robject.acquired_by = None

        self.locked_objects = []
        self.acquired_by = None
        self.evt.clear()
        self.state = ROUTE_STATE_UNSET

        if self.lock.locked():
            self.lock.release()

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
        num_objects_unset, num_objects_with_sensor = self.reset_target_states()

        if timeout > 0 and num_objects_unset > 0:
            objs = []
            for obj in self.robjects:
                if obj.robject.has_sensor:
                    objs.append(obj.robject)

            if len(objs) > 0:
                self.state = ROUTE_STATE_UNSET
                self.logger.log(f'route wait: waiting for {len(objs)} objects = {objs}, current route state = {self.state}')
                e = await cbusobjects.WaitAllTimeout(tuple(objs), timeout).wait()
                self.logger.log(f'route wait: wait returns, e = {e}')
                self.state = ROUTE_STATE_SET if e else ROUTE_STATE_ERROR

                self.reset_target_states()
                self.logger.log(f'route wait: state now = {self.state}')

        if self.state == ROUTE_STATE_SET:
            if t := canmessage.tuple_from_tuples(self.producer_events, ROUTE_SET_EVENT):
                msg = canmessage.event_from_tuple(self.cbus, t)
                msg.send()

        return self.state
