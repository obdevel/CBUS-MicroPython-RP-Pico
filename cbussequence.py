import time

import uasyncio as asyncio
from micropython import const

import canmessage
import cbus
import cbushistory
import cbuspubsub
import logger

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
STEP_UDF = const(18)

STEP_LOOP = const(99)

step_types_lookup = {
    STEP_NOOP: "No op",
    STEP_LOCO_ACQUIRE: "Acquire loco",
    STEP_LOCO_SPEED_DIR: "Loco speed/dir",
    STEP_LOCO_FUNC: "Loco function",
    STEP_SENSOR: "Sensor",
    STEP_TURNOUT: "Turnout",
    STEP_SIGNAL_HOME: "Home signal",
    STEP_SIGNAL_DISTANT: "Distant signal",
    STEP_TIME_WAITFOR: "Wait for time",
    STEP_TIME_WAITUNTIL: "Wait until time",
    STEP_EVENT_WAITFOR: "Wait for event",
    STEP_HISTORY_SEQUENCE_WAITFOR: "Wait for sequence",
    STEP_SEND_EVENT: "Send event",
    STEP_UNCOUPLER: "Uncoupler",
    STEP_TURNTABLE: "Turntable",
    STEP_UDF: "UDF"
}

MOVEMENT_STATE_NOT_RUNNING = const(-1)
MOVEMENT_STATE_PAUSED = const(0)
MOVEMENT_STATE_RUNNING = const(1)

current_sequences = {}


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
                self.logger.log(f'sequence:{self.name} processing step {self.current_index}, type = {current_step.type} {step_types_lookup.get(current_step.type)}, data = {current_step.data}')

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
