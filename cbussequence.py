import time

import uasyncio as asyncio
from micropython import const

import canmessage
import cbus
import cbushistory
import cbusobjects
import cbuspubsub
import logger

STEP_NOOP = const(0)

STEP_LOCO_ACQUIRE = const(1)
STEP_LOCO_SPEED_DIR = const(2)
STEP_LOCO_FUNC = const(3)

STEP_SENSOR = const(4)
STEP_LAYOUT_OBJECT = const(5)
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
STEP_UDF = const(18)

STEP_LOOP = const(99)

step_types_lookup = {
    STEP_NOOP: "No op",
    STEP_LOCO_ACQUIRE: "Acquire loco",
    STEP_LOCO_SPEED_DIR: "Loco speed/dir",
    STEP_LOCO_FUNC: "Loco function",
    STEP_SENSOR: "Sensor",
    STEP_LAYOUT_OBJECT: "Layout object",
    STEP_TIME_WAITFOR: "Wait for time",
    STEP_TIME_WAITUNTIL: "Wait until time",
    STEP_EVENT_WAITFOR: "Wait for event",
    STEP_HISTORY_SEQUENCE_WAITFOR: "Wait for sequence",
    STEP_SEND_EVENT: "Send event",
    STEP_UNCOUPLER: "Uncoupler",
    STEP_TURNTABLE: "Turntable",
    STEP_UDF: "UDF"
}

SEQUENCE_STATE_NOT_RUNNING = const(-1)
SEQUENCE_STATE_PAUSED = const(0)
SEQUENCE_STATE_RUNNING = const(1)

SEQUENCE_BEGIN_EVENT = const(0)
SEQUENCE_COMPLETE_EVENT = const(1)
SEQUENCE_TIMEOUT_EVENT = const(2)
SEQUENCE_CANCELLED_EVENT = const(3)


class step:

    def __init__(self, object, type, data, target_state):
        self.object = object
        self.type = type
        self.data = data
        self.target_state = target_state


class sequence:
    def __init__(self, name: str, cbus: cbus.cbus, steps: tuple[step, ...], producer_events: tuple = None, autorun: bool = False, operate_objects=False, cab=None, loco: int = 0) -> None:
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.steps = steps
        self.producer_events = producer_events
        self.operate_objects = operate_objects

        self.cab = cab
        self.loco = loco

        self.evt = asyncio.Event()
        self.evt.clear()
        self.sub = None
        self.history = None
        self.wait_timeout = 30_000
        self.timed_out = False

        self.clock = None

        self.state = SEQUENCE_STATE_NOT_RUNNING
        self.current_index = -1
        self.current_step = -1

        if autorun:
            self.state = SEQUENCE_STATE_PAUSED
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
        self.state = SEQUENCE_STATE_PAUSED
        self.run_task_handle = asyncio.create_task(self.run_sequence())

    async def run_sequence(self) -> None:
        try:
            self.logger.log('sequence running...')
            self.timed_out = False

            if t := canmessage.tuple_from_tuples(self.producer_events, SEQUENCE_BEGIN_EVENT):
                msg = canmessage.event_from_tuple(self.cbus, t)
                msg.send()

            for self.current_index, self.current_step in enumerate(self.steps):
                if self.timed_out:
                    if t := canmessage.tuple_from_tuples(self.producer_events, SEQUENCE_TIMEOUT_EVENT):
                        msg = canmessage.event_from_tuple(self.cbus, t)
                        msg.send()
                    break

                if not self.evt.is_set():
                    self.logger.log('sequence, awaiting event set')
                    self.state = SEQUENCE_STATE_PAUSED
                    await self.evt.wait()
                    self.state = SEQUENCE_STATE_RUNNING
                    self.logger.log('sequence, event is set, continuing')
                else:
                    self.state = SEQUENCE_STATE_RUNNING

                self.logger.log(
                    f'sequence:{self.name} processing step {self.current_index}, type = {self.current_step.type} {step_types_lookup.get(self.current_step.type)}, data = {self.current_step.data}')

                if self.current_step.type == STEP_LOCO_ACQUIRE:
                    self.logger.log('acquire loco')
                    if not await self.cab.acquire(self.loco):
                        self.logger.log('failed to acquire loco')
                        break

                elif self.current_step.type == STEP_LOCO_SPEED_DIR:
                    self.logger.log('set loco speed')
                    self.loco.speed = self.current_step.data[0]
                    self.loco.direction = self.current_step.data[1]
                    self.cab.set_speed_and_direction(self.loco)

                elif self.current_step.type == STEP_LOCO_FUNC:
                    self.logger.log('set loco function')
                    self.cab.function(self.loco, self.current_step.data[0], self.current_step.data[1])

                elif self.current_step.type == STEP_SENSOR:
                    self.logger.log(f'sensor {self.current_step.object.name}, current state = {self.current_step.object.state}, target = {self.current_step.target_state}')
                    while self.current_step.object.state != self.current_step.target_state:
                        x = await cbusobjects.WaitAllTimeout((self.current_step.object,), self.wait_timeout).wait()
                        if not x:
                            self.timed_out = True
                            self.logger.log('timed out')
                            break

                elif self.current_step.type == STEP_LAYOUT_OBJECT:
                    self.logger.log(f'layout object {self.current_step.object.name}, current state = {self.current_step.object.state}, target = {self.current_step.target_state}')
                    if self.operate_objects:
                        pass
                    while self.current_step.object.state != self.current_step.target_state:
                        x = await cbusobjects.WaitAnyTimeout((self.current_step.object,), self.wait_timeout).wait()
                        if not x:
                            self.timed_out = True
                            self.logger.log('timed out')
                            break

                elif self.current_step.type == STEP_ROUTE:
                    self.logger.log(f'route {self.current_step.object.name}, state = {self.current_step.object.state}, target = {self.current_step.target_state}')
                    if self.operate_objects:
                        pass
                    while self.current_step.object.state != self.current_step.target_state:
                        x = await cbusobjects.WaitAnyTimeout((self.current_step.object.evt,), self.wait_timeout).wait()
                        if not x:
                            self.timed_out = True
                            self.logger.log('timed out')
                            break

                elif self.current_step.type == STEP_TIME_WAITFOR:
                    self.logger.log(f'time wait for {self.current_step.data}')
                    await asyncio.sleep_ms(self.current_step.data)

                elif self.current_step.type == STEP_CLOCK_WAITFOR:
                    self.logger.log('clock wait for')

                elif self.current_step.type == STEP_TIME_WAITUNTIL:
                    self.logger.log(f'time wait until {self.current_step.target_state}')
                    while time.ticks_ms() != self.current_step.target_state:
                        await asyncio.sleep_ms(500)

                elif self.current_step.type == STEP_CLOCK_WAITUNTIL:
                    self.logger.log('clock wait until')

                elif self.current_step.type == STEP_EVENT_WAITFOR:
                    self.logger.log(f'wait for event {self.current_step.data}')
                    self.sub = cbuspubsub.subscription('m1', self.cbus, canmessage.QUERY_TUPLES, tuple(self.current_step.data))
                    x = await cbusobjects.WaitAnyTimeout((self.sub,), self.wait_timeout).wait()
                    if not x:
                        self.timed_out = True
                        self.logger.log('timed out')
                        break
                    self.sub.unsubscribe()
                    self.sub = None

                elif self.current_step.type == STEP_HISTORY_SEQUENCE_WAITFOR:
                    self.logger.log(f'wait for sequence {self.current_step.data}')
                    self.history = cbushistory.cbushistory(self.cbus, -1, 5_000, canmessage.QUERY_TUPLES, tuple(self.current_step.data))
                    while True:
                        x = await cbusobjects.WaitAnyTimeout((self.history,), self.wait_timeout).wait()
                        if not x:
                            self.timed_out = True
                            self.logger.log('timed out')
                            break
                        if self.history.sequence_received(self.current_step.data, order=cbushistory.ORDER_GIVEN, which=cbushistory.WHICH_LATEST):
                            self.history.remove()
                            self.history = None
                            break

                elif self.current_step.type == STEP_SEND_EVENT:
                    self.logger.log('send event')
                    evt = canmessage.event_from_tuple(self.cbus, self.current_step.data)
                    evt.send()

                elif self.current_step.type == STEP_UNCOUPLER:
                    self.current_step.object.on()

                elif self.current_step.type == STEP_TURNTABLE:
                    self.current_step.object.position_to(self.current_step.data, True)

                elif self.current_step.type == STEP_LOOP:
                    self.logger.log(f'loop back to step {self.current_step.data[0]}')
                    idx = self.current_step.data[0]

                else:
                    self.logger.log(f'unknown sequence step type {self.current_step.type}')

        except asyncio.CancelledError:
            self.logger.log(f'sequence cancelled')
            if self.cab and self.loco:
                self.cab.emergency_stop(self.loco)

                if t := canmessage.tuple_from_tuples(self.producer_events, SEQUENCE_CANCELLED_EVENT):
                    msg = canmessage.event_from_tuple(self.cbus, t)
                    msg.send()
        finally:
            self.logger.log(f'end of sequence')
            self.state = SEQUENCE_STATE_RUNNING

            if t := canmessage.tuple_from_tuples(self.producer_events, SEQUENCE_COMPLETE_EVENT):
                msg = canmessage.event_from_tuple(self.cbus, t)
                msg.send()

    def pause(self) -> None:
        self.evt.clear()

    def resume(self):
        self.evt.set()

    def cancel(self) -> None:
        self.run_task_handle.cancel()
