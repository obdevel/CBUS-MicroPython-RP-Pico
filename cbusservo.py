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

a = (((0, 22, 30), (1, 22, 30)), ((0, 22, 31), (1, 22, 31)), ((0, 22, 32), (1, 22, 32)))


class cbusservo:
    def __init__(self, name: str, pin: int, close_limit: int = 0, open_limit: int = 0,
                 initial_state: int = STATE_IDLE) -> None:
        self.logger = logger.logger()
        self.name = name

        self._close_limit = close_limit
        self._open_limit = open_limit

        if self.open_limit <= self.close_limit:
            raise ValueError('servo open limit must be greater than close limit')

        self.midpoint = int(self._close_limit + ((self._open_limit - self._close_limit) / 2))

        self.cbus = None
        self.state = STATE_IDLE

        self.pos = self.midpoint
        self.run_freq = 100
        self.stride = 1
        self.midpoint_processed = True
        self.always_move = False

        self.consumer_events = None
        self.producer_events = None
        self.sub = None
        self.listener_task = None

        self.pwm = PWM(Pin(pin))
        self.pwm.freq(PWM_FREQ)
        self.run_task = asyncio.create_task(self.run())

        if initial_state != STATE_IDLE:
            self.operate(initial_state)

    @property
    def close_limit(self) -> int:
        return self._close_limit

    @close_limit.setter
    def close_limit(self, value: int) -> None:
        self._close_limit = value
        self.midpoint = int(self._close_limit + ((self._open_limit - self._close_limit) / 2))
        self.position_to(self.midpoint)

    @property
    def open_limit(self) -> int:
        return self._open_limit

    @open_limit.setter
    def open_limit(self, value: int) -> None:
        self._open_limit = value
        self.midpoint = int(self._close_limit + ((self._open_limit - self._close_limit) / 2))
        self.position_to(self.midpoint)

    def dispose(self) -> None:
        self.run_task.cancel()
        if self.listener_task is not None:
            self.listener_task.cancel()

    def position_to(self, pos: int) -> None:
        dc = map_duty_cycle(pos, 0, 255, 0, 65535)
        self.pwm.duty_u16(dc)
        self.pos = pos

    def operate(self, operation: int) -> None:
        self.state = STATE_OPENING if operation == SERVO_OPEN else STATE_CLOSING
        self.send_producer_event(HAPPENING_BEGIN, self.state)
        self.midpoint_processed = False

    def open(self) -> None:
        if self.pos < self.open_limit or self.always_move:
            self.operate(SERVO_OPEN)

    def close(self) -> None:
        if self.pos > self.close_limit or self.always_move:
            self.operate(SERVO_CLOSE)

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
        # TODO
        pass

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

    async def listener(self) -> None:
        self.sub = cbuspubsub.subscription('servo:' + self.name + ':listener', self.cbus, self.consumer_events,
                                           canmessage.QUERY_TUPLES)
        try:
            while True:
                msg = await self.sub.wait()
                if tuple(msg) == self.consumer_events[0]:
                    self.close()
                else:
                    self.open()
        except Exception as e:
            self.logger.log(f'listener task cancelled, exception = {e}')
        finally:
            self.sub.unsubscribe()


def map_duty_cycle(x: int, in_min: int, in_max: int, out_min: int, out_max: int) -> int:
    try:
        v = int((x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min)
    except ZeroDivisionError:
        v = 0
    finally:
        return v
