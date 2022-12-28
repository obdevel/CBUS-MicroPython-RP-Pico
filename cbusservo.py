import uasyncio as asyncio
from machine import Pin, PWM
from micropython import const

import canmessage
import cbuspubsub
import logger

SERVO_NO_OP = const(-1)
SERVO_CLOSE = const(0)
SERVO_OPEN = const(1)

STATE_IDLE = const(-1)
STATE_CLOSING = const(0)
STATE_OPENING = const(1)

HAPPENING_BEGIN = const(0)
HAPPENING_MIDPOINT = const(1)
HAPPENING_COMPLETE = const(2)

PWM_FREQ = const(50)
RUN_FREQ = const(100)

a = (((0, 22, 30), (1, 22, 30)), ((0, 22, 31), (1, 22, 31)), ((0, 22, 32), (1, 22, 32)))


class cbusservo:
    def __init__(self, name: str, pin: int, close_limit: int = 0, open_limit: int = 0,
                 initial_state: int = STATE_IDLE) -> None:
        self.logger = logger.logger()
        self.name = name

        self.midpoint = 0
        self.stride = 0
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

        self.calc_stride()
        self.calc_midpoint()
        self.pos = self.midpoint

        self.pwm = PWM(Pin(pin))
        self.pwm.freq(PWM_FREQ)

        self.completion_event = None
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
        self.calc_stride()
        self.position_to(self.midpoint)

    @property
    def open_limit(self) -> int:
        return self._open_limit

    @open_limit.setter
    def open_limit(self, value: int) -> None:
        self._open_limit = value
        self.calc_midpoint()
        self.calc_stride()
        self.position_to(self.midpoint)

    @property
    def operate_time(self) -> int:
        return self._operate_time

    @operate_time.setter
    def operate_time(self, otime: int) -> None:
        self._operate_time = otime
        self.calc_stride()

    def calc_midpoint(self):
        self.midpoint = int(self._close_limit + ((self._open_limit - self._close_limit) / 2))

    def calc_stride(self):
        self.stride = max(1, int((self._open_limit - self._close_limit) / (self._operate_time / self.run_freq)))

    def dispose(self) -> None:
        self.run_task.cancel()
        if self.listener_task is not None:
            self.listener_task.cancel()

    def position_to(self, pos: int) -> None:
        dc = self.map_duty_cycle(pos, 0, 255, 0, 65535)
        self.pwm.duty_u16(dc)
        self.pos = pos

    async def operate(self, operation: int, wait_for_completion: bool = False) -> None:
        self.state = STATE_OPENING if operation == SERVO_OPEN else STATE_CLOSING
        self.send_producer_event(HAPPENING_BEGIN, self.state)
        self.midpoint_processed = False

        if wait_for_completion:
            self.logger.log('waiting for completion')
            await self.wait()
            self.logger.log('movement complete')

    async def open(self, wait_for_completion: bool = False) -> None:
        if self.pos < self.open_limit or self.always_move:
            await self.operate(SERVO_OPEN, wait_for_completion)

    async def close(self, wait_for_completion: bool = False) -> None:
        if self.pos > self.close_limit or self.always_move:
            await self.operate(SERVO_CLOSE, wait_for_completion)

    def set_consumer_events(self, cbus, events: tuple = None) -> None:
        self.cbus = cbus

        if events is not None and len(events) != 2:
            raise ValueError('expected one pair of consumer events')

        self.consumer_events = events

        if self.consumer_events is not None:
            self.listener_task = asyncio.create_task(self.listener())

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
            # t1 = time.ticks_us()
            pos_orig = self.pos
            for x in self.bounce_values:
                new_pos = pos_orig + x
                new_pos = min(self.open_limit, max(self.close_limit, new_pos))
                self.position_to(new_pos)
            self.position_to(pos_orig)
            # t2 = time.ticks_us()
            # self.logger.log(f'bounce took {time.ticks_diff(t2, t1)}')

    async def run(self) -> None:
        while True:
            await asyncio.sleep_ms(self.run_freq)

            if self.state != STATE_IDLE:
                if self.state == STATE_OPENING and self.pos < self._open_limit:
                    self.pos += self.stride
                    self.pos = min(self.pos, self._open_limit)
                elif self.state == STATE_CLOSING and self.pos > self._close_limit:
                    self.pos -= self.stride
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

                    if self.completion_event:
                        self.completion_event.set()

    async def listener(self) -> None:
        self.sub = cbuspubsub.subscription('servo:' + self.name + ':listener', self.cbus, self.consumer_events,
                                           canmessage.QUERY_TUPLES)
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

    async def wait(self):
        if not self.completion_event:
            self.completion_event = asyncio.Event()

        self.logger.log('waiting...')
        await self.completion_event.wait()
        self.completion_event.clear()
        self.logger.log('...done')

    @staticmethod
    def map_duty_cycle(x: int, in_min: int, in_max: int, out_min: int, out_max: int) -> int:
        v = 0
        try:
            v = int((x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min)
        except ZeroDivisionError:
            v = 0
        finally:
            return v
