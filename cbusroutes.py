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

STEP_TURNOUT = const(0)
STEP_SIGNAL_HOME = const(1)
STEP_SIGNAL_DISTANT = const(2)
STEP_ROUTE = const(3)
STEP_LOCO = const(4)
STEP_SPEED_DIR = const(5)
STEP_FUNC = const(6)
STEP_SENSOR = const(7)
STEP_TIME_WAITFOR = const(8)
STEP_CLOCK_WAITFOR = const(9)
STEP_TIME_WAITUNTIL = const(10)
STEP_CLOCK_WAITUNTIL = const(11)
STEP_EVENT_WAITFOR = const(12)
STEP_LOOP = const(13)


class routeobject:
    def __init__(self, robject: cbusobjects.base_cbus_layout_object, target_state: int,
                 when: int = cbusobjects.WHEN_DONT_CARE):
        self.robject = robject
        self.target_state = target_state
        self.when = when


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

        # acquire, set, release
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
        self.set_time = None

    def __call__(self):
        return self.state

    def udf(self, msg):
        ev = tuple(msg)
        for ev1 in self.occupancy_events:
            if ev in ev1:
                return True
        return False

    async def occupancy_task(self):
        while True:
            await self.occupancy_history.wait()
            self.logger.log(f'route:{self.name}: got occupancy event')
            t = tuple(self.occupancy_history.last_item_received.msg)

            for i, e in enumerate(self.occupancy_events):
                if t == e[0]:
                    self.logger.log(f'route:{self.name}: event is 0')
                    self.occupancy_states[i] = False
                    break
                if t == e[1]:
                    self.logger.log(f'route:{self.name}: event is 1')
                    self.occupancy_states[i] = True
                    break

            self.occupied = True in self.occupancy_states
            self.logger.log(f'route:{self.name}: occupied = {self.occupied}')
            self.occupied_evt.set()

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

        if self.feedback_events and len(self.feedback_events) > 0:
            msg = canmessage.event_from_tuple(self.cbus, self.feedback_events[0])
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

        if self.feedback_events and len(self.feedback_events) > 1:
            msg = canmessage.event_from_tuple(self.cbus, self.feedback_events[1])
            msg.polarity = state_ok
            msg.send()

    def release(self) -> None:
        for obj in self.locked_objects:
            if obj.robject.lock.locked():
                obj.robject.release()

        self.locked_objects = []
        self.lock.release()
        self.state = ROUTE_STATE_UNSET

        if self.feedback_events and len(self.feedback_events) > 2:
            msg = canmessage.event_from_tuple(self.cbus, self.feedback_events[2])
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


class movement:
    def __init__(self, name: str, cbus: cbus.cbus, objects: tuple[step, ...], operate_objects=False, cab=None,
                 loco: int = 0) -> None:
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.objects = objects
        self.operate_objects = operate_objects

        self.cab = cab
        self.loco = loco

        self.evt = asyncio.Event()
        self.evt.clear()
        self.sub = cbuspubsub.subscription('ps', self.cbus, 0, 0)

        self.run_task_handle = asyncio.create_task(self.run())

    def init(self) -> None:
        pass

    @staticmethod
    def create_from_list(step_objects: tuple[tuple, ...]) -> tuple:
        steps_list = []
        for step_object in step_objects:
            st = step(step_object[0], step_object[1], step_object[2], step_object[3])
            steps_list.append(st)
        return tuple(steps_list)

    async def run(self) -> None:
        try:
            self.logger.log('movement running...')

            for i, obj in enumerate(self.objects):
                if not self.evt.is_set():
                    self.logger.log('movement, awaiting event set')
                    await self.evt.wait()
                    self.logger.log('movement, event is set, continuing')

                self.logger.log(f'movement:{self.name} processing step {i} = {obj.type}')

                if obj.type == STEP_SENSOR:
                    self.logger.log('movement, step is sensor')
                elif obj.type == STEP_SIGNAL_HOME:
                    self.logger.log('movement, step is signal home')
                elif obj.type == STEP_TURNOUT:
                    self.logger.log('movement, step is turnout')
                elif obj.type == STEP_ROUTE:
                    pass
                elif obj.type == STEP_LOCO:
                    pass
                elif obj.type == STEP_SPEED_DIR:
                    pass
                elif obj.type == STEP_FUNC:
                    pass
                elif obj.type == STEP_LOOP:
                    self.logger.log(f'movement: loop back to step {obj.data[0]}')
                    i = obj.data
                else:
                    self.logger.log(f'unknown movement {obj.type}')

        except asyncio.CancelledError:
            self.logger.log(f'movement cancelled')
        finally:
            self.logger.log(f'end of movement')
            self.sub.unsubscribe()

    def pause(self) -> None:
        self.evt.clear()

    def resume(self):
        self.evt.set()

    def cancel(self) -> None:
        self.run_task_handle.cancel()
