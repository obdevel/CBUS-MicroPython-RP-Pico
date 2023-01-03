import uasyncio as asyncio
from machine import Pin, PWM
from micropython import const

import canmessage
import cbusobjects
import cbuspubsub
import logger
from primitives import WaitAny

PWM_FREQ = const(50)
RUN_FREQ = const(100)

OP_NO_OP = const(-1)
OP_CLOSE = const(0)
OP_OPEN = const(1)

STATE_IDLE = const(-1)
STATE_CLOSING = const(0)
STATE_OPENING = const(1)

HAPPENING_BEGIN = const(0)
HAPPENING_MIDPOINT = const(1)
HAPPENING_COMPLETE = const(2)

FEEDBACK_PIN_NONE = const(-1)
FEEDBACK_STATE_UNKNOWN = const(-1)

FEEDBACK_TYPE_INTERNAL = const(0)
FEEDBACK_TYPE_SENSOR = const(1)
FEEDBACK_TYPE_PIN = const(2)
FEEDBACK_TYPE_PIN_INVERTED = const(3)

MODE_SYNC = const(0)
MODE_ASYNC = const(1)


class cbusservo:
    def __init__(self, name: str, pin: int, close_limit: int = 0, open_limit: int = 0,
                 initial_state: int = STATE_IDLE) -> None:
        self.logger = logger.logger()
        self.name = name
        self.feedback_type = FEEDBACK_TYPE_INTERNAL
        self.feedback_pin = FEEDBACK_PIN_NONE
        self.interrupt_pin = None
        self.feedback_state = FEEDBACK_STATE_UNKNOWN
        self.tsf = None
        self.sensor = None
        self.sensor_event = None
        self.sensor_events = None
        self.sensor_query_message = None

        self.midpoint = 0
        self.steps_per_run = 0
        self.run_freq = RUN_FREQ
        self._operate_time = 5000

        self._close_limit = close_limit
        self._open_limit = open_limit

        if self.open_limit <= self.close_limit:
            raise ValueError('servo open limit must be greater than close limit')

        self.cbus = None
        self.state = STATE_IDLE

        self.midpoint_processed = True
        self.always_move = False
        self.do_bounce = False
        self.bounce_values = [-10, 5, -2, 1, -1]

        self.consumer_events = None
        self.producer_events = None
        self.sub = None
        self.listener_task = None

        self.calc_steps_per_run()
        self.calc_midpoint()
        self.pos = self.midpoint

        self.pwm = PWM(Pin(pin))
        self.pwm.freq(PWM_FREQ)

        self.completion_event = asyncio.Event()
        self.run_task = asyncio.create_task(self.run())

        if initial_state != STATE_IDLE:
            asyncio.create_task(self.operate(initial_state))

    @property
    def close_limit(self) -> int:
        return self._close_limit

    @close_limit.setter
    def close_limit(self, value: int) -> None:
        self._close_limit = value
        self.calc_midpoint()
        self.calc_steps_per_run()
        self.position_to(self.midpoint)

    @property
    def open_limit(self) -> int:
        return self._open_limit

    @open_limit.setter
    def open_limit(self, value: int) -> None:
        self._open_limit = value
        self.calc_midpoint()
        self.calc_steps_per_run()
        self.position_to(self.midpoint)

    @property
    def operate_time(self) -> int:
        return self._operate_time

    @operate_time.setter
    def operate_time(self, otime: int) -> None:
        self._operate_time = otime
        self.calc_steps_per_run()

    def calc_midpoint(self):
        self.midpoint = int(self._close_limit + ((self._open_limit - self._close_limit) / 2))

    def calc_steps_per_run(self):
        self.steps_per_run = max(1, int((self._open_limit - self._close_limit) / (self._operate_time / self.run_freq)))

    def dispose(self) -> None:
        self.run_task.cancel()
        if self.listener_task is not None:
            self.listener_task.cancel()
        # TODO more to clear up here

    def set_feedback(self, feedback_type: int, pin: int, sensor_events: tuple = (),
                     sensor_query_message: tuple = None) -> None:
        self.feedback_type = feedback_type
        self.feedback_pin = pin

        if self.feedback_type == FEEDBACK_TYPE_PIN or self.feedback_type == FEEDBACK_TYPE_PIN_INVERTED:
            self.interrupt_pin = Pin(self.feedback_pin, Pin.IN, Pin.PULL_UP)
            state = self.interrupt_pin.value()
            self.feedback_state = state if self.feedback_type == FEEDBACK_TYPE_PIN else not state
            self.tsf = asyncio.ThreadSafeFlag()
            self.interrupt_pin.irq(trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING, handler=lambda t: self.tsf.set())
            asyncio.create_task(self.feedback_irq_handler())

        elif self.feedback_type == FEEDBACK_TYPE_SENSOR:
            self.sensor_events = sensor_events
            self.sensor_query_message = sensor_query_message
            self.sensor_event = asyncio.Event()
            self.sensor = cbusobjects.binary_sensor(self.name, self.cbus, self.sensor_events, (),
                                                    self.sensor_query_message)
            asyncio.create_task(self.feedback_sensor_handler())

    async def feedback_irq_handler(self) -> None:
        while True:
            await self.tsf.wait()
            state = self.interrupt_pin.value()
            self.feedback_state = state if self.feedback_type == FEEDBACK_TYPE_PIN else not state
            self.state = self.feedback_state
            self.completion_event.set()

    async def feedback_sensor_handler(self) -> None:
        while True:
            await self.sensor_event.wait()
            self.sensor_event.clear()
            self.state = self.sensor.state
            self.completion_event.set()

    async def wait(self, timeout: int = 10_000) -> bool:
        timeout_event = asyncio.Event()
        self.completion_event.clear()
        timeout_event.clear()
        timeout = cbusobjects.timeout(timeout, timeout_event)
        tt = asyncio.create_task(timeout.one_shot())
        evw = await WaitAny((self.completion_event, timeout_event)).wait()
        self.completion_event.clear()

        if evw == timeout_event:
            tt.cancel()
            self.logger.log('wait timed out')
            return False
        else:
            return True

    def position_to(self, pos: int) -> None:
        dc = self.map_duty_cycle(pos, 0, 255, 0, 65535)
        self.pwm.duty_u16(dc)
        self.pos = pos

    async def operate(self, operation: int, wait_for_completion: bool = False, timeout: int = 10_000) -> None:
        self.state = STATE_OPENING if operation == OP_OPEN else STATE_CLOSING
        self.send_producer_event(HAPPENING_BEGIN, self.state)
        self.midpoint_processed = False

        if wait_for_completion:
            self.logger.log('waiting for completion')
            await self.wait(timeout)
            self.logger.log('movement complete')

    async def open(self, wait_for_completion: bool = False, timeout: int = 10_000) -> None:
        if self.pos < self.open_limit or self.always_move:
            await self.operate(OP_OPEN, wait_for_completion, timeout)

    async def close(self, wait_for_completion: bool = False, timeout: int = 10_000) -> None:
        if self.pos > self.close_limit or self.always_move:
            await self.operate(OP_CLOSE, wait_for_completion, timeout)

    def set_consumer_events(self, cbus, events: tuple = None) -> None:
        self.cbus = cbus

        if events is not None and len(events) != 2:
            raise ValueError('expected one pair of consumer events')

        self.consumer_events = events

        if self.consumer_events is not None:
            self.listener_task = asyncio.create_task(self.listener())
        else:
            if self.listener_task:
                self.listener_task.cancel()

    def set_producer_events(self, cbus, events: tuple = None) -> None:
        self.cbus = cbus

        if events is not None and len(events) != 3:
            raise ValueError('expected three pairs of producer events')

        self.producer_events = events

    def send_producer_event(self, happening_type: int, direction: int) -> None:
        if self.producer_events and len(self.producer_events) == 3:
            try:
                t = self.producer_events[happening_type][direction]
                if t != (0, 0, 0):
                    msg = canmessage.event_from_tuple(self.cbus, t)
                    msg.send()
            except IndexError:
                self.logger.log('producer events tuple improperly formed')

    def bounce(self):
        if self.do_bounce:
            pos_orig = self.pos
            for x in self.bounce_values:
                new_pos = pos_orig + x
                new_pos = min(self.open_limit, max(self.close_limit, new_pos))
                self.position_to(new_pos)
            self.position_to(pos_orig)

    async def run(self) -> None:
        while True:
            await asyncio.sleep_ms(self.run_freq)

            if self.state != STATE_IDLE:
                if self.state == STATE_OPENING and self.pos < self._open_limit:
                    self.pos += self.steps_per_run
                    self.pos = min(self.pos, self._open_limit)
                elif self.state == STATE_CLOSING and self.pos > self._close_limit:
                    self.pos -= self.steps_per_run
                    self.pos = max(self.pos, self._close_limit)

                self.position_to(self.pos)

                if not self.midpoint_processed and ((self.state == STATE_CLOSING and self.pos <= self.midpoint) or (
                        self.state == STATE_OPENING and self.pos >= self.midpoint)):
                    self.send_producer_event(HAPPENING_MIDPOINT, self.state)
                    self.midpoint_processed = True

                if self.pos == self._close_limit or self.pos == self._open_limit:
                    self.bounce()
                    self.send_producer_event(HAPPENING_COMPLETE, self.state)
                    self.state = STATE_IDLE

                    if self.feedback_type == FEEDBACK_TYPE_INTERNAL:
                        self.completion_event.set()

    async def listener(self) -> None:
        self.sub = cbuspubsub.subscription('servo:' + self.name + ':listener', self.cbus, canmessage.QUERY_TUPLES,
                                           self.consumer_events)
        try:
            while True:
                msg = await self.sub.wait()
                if tuple(msg) == self.consumer_events[0]:
                    await self.close()
                else:
                    await self.open()
        except Exception as e:
            self.logger.log(f'listener task cancelled, exception = {e}')
        finally:
            self.sub.unsubscribe()

    @staticmethod
    def map_duty_cycle(x: int, in_min: int, in_max: int, out_min: int, out_max: int) -> int:
        v = 0
        try:
            v = int((x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min)
        except ZeroDivisionError:
            v = 0
        finally:
            return v


class cbusservogroup:
    def __init__(self, name: str, servos: tuple[cbusservo, ...], order: tuple[int, ...], mode: int = MODE_SYNC):
        self.name = name
        self.servos = servos
        self.order = order
        self.mode = mode

        if len(order) != len(servos):
            raise ValueError('mismatched arg lengths')

    async def operate(self, operations: tuple[int, ...]):
        if len(operations) != len(self.servos):
            raise ValueError('mismatched arg length')

        wait = True if self.mode == MODE_SYNC else False
        for s in self.order:
            await self.servos[s].operate(operations[s], wait)
