# cbuslongmessage.py

import time

import uasyncio as asyncio
from micropython import const

import canmessage
import cbus
import cbusdefs
import logger

RECEIVE_TIMEOUT = const(1000)
TRANSMIT_DELAY = const(10)
PROCESS_DELAY = const(50)
MAX_MSG_LEN = const(65_535)

CBUS_LONG_MESSAGE_INCOMPLETE = const(0)
CBUS_LONG_MESSAGE_COMPLETE = const(1)
CBUS_LONG_MESSAGE_SEQUENCE_ERROR = const(2)
CBUS_LONG_MESSAGE_TIMEOUT_ERROR = const(3)
CBUS_LONG_MESSAGE_CRC_ERROR = const(4)
CBUS_LONG_MESSAGE_TRUNCATED = const(5)


class lm_context:
    def __init__(self):
        self.logger = logger.logger()
        self.in_use = False
        self.stream_id = 0
        self.buffer = bytearray()
        self.message_size = 0
        self.crc = 0


class receive_context(lm_context):
    def __init__(self):
        super().__init__()
        self.logger = logger.logger()

        self.can_id = 0
        self.last_fragment_received_at = time.ticks_ms()
        self.received = 0
        self.expected_next_receive_sequence_num = 0


class transmit_context(lm_context):
    def __init__(self):
        super().__init__()
        self.logger = logger.logger()

        self.index = 0
        self.priority = 0
        self.sequence_num = 0
        self.using_crc = False
        self.flags = 0
        self.last_fragment_sent = time.ticks_ms()


class cbuslongmessage:
    def __init__(self, bus: cbus.cbus):
        self.logger = logger.logger()

        self.bus = bus
        self.using_crc = False
        self.subscribed_ids = []
        self.bus.set_long_message_handler(self)
        self.user_handler = None
        self.current_context = 0
        self.receive_timeout = 0
        self.receive_contexts = [receive_context()]
        self.transmit_contexts = [transmit_context()]
        asyncio.create_task(self.process())

    def subscribe(self, ids: tuple, handler, receive_timeout: int = RECEIVE_TIMEOUT) -> None:
        self.subscribed_ids = ids
        self.user_handler = handler
        self.receive_timeout = receive_timeout

    def send_long_message(self, message: str, stream_id: int, priority: int = 0x0b) -> bool:
        if len(message) >= MAX_MSG_LEN:
            raise ValueError('error: message is too long')

        j = 0
        ctx = None

        for j, ctx in enumerate(self.transmit_contexts):
            if ctx.in_use and self.transmit_contexts[j].stream_id == stream_id:
                raise ValueError(f'error: a message is already in progress with stream_id = {stream_id} in context {j}')

        found_free_context = False

        for j, ctx in enumerate(self.transmit_contexts):
            if not ctx.in_use:
                found_free_context = True
                break

        if not found_free_context:
            self.transmit_contexts.append(transmit_context())
            j += 1
            ctx = self.transmit_contexts[j]

        ctx.in_use = True
        ctx.stream_id = stream_id
        ctx.buffer = bytearray(message)
        ctx.message_size = len(message)
        ctx.priority = priority
        ctx.sequence_num = 0
        ctx.index = 0
        ctx.flags = 0
        ctx.crc = (self.crc16(ctx.buffer) if self.using_crc else 0)

        msg = canmessage.canmessage(self.bus.config.canid, 8)

        msg.data[0] = cbusdefs.OPC_DTXC
        msg.data[1] = stream_id
        msg.data[2] = ctx.sequence_num
        msg.data[3] = int(ctx.message_size >> 8)
        msg.data[4] = ctx.message_size & 0xff
        msg.data[5] = int(ctx.crc >> 8)
        msg.data[6] = ctx.crc & 0xff
        msg.data[7] = ctx.flags

        self.bus.can.send_message(msg)

        ctx.sequence_num = 1
        ctx.last_fragment_sent = time.ticks_ms
        return True

    async def process(self) -> None:
        while True:

            for j, ctx in enumerate(self.receive_contexts):
                if ctx.in_use and time.ticks_diff(time.ticks_ms(), ctx.last_fragment_received_at) > self.receive_timeout:
                    self.logger.log(f'error: receive context {j} timed out')
                    self.user_handler(ctx.buffer, ctx.stream_id, CBUS_LONG_MESSAGE_TIMEOUT_ERROR)
                    ctx.in_use = False

            cctx = self.transmit_contexts[self.current_context]

            if cctx.in_use and time.ticks_diff(time.ticks_ms(), cctx.last_fragment_sent) > TRANSMIT_DELAY:
                msg = canmessage.canmessage(self.bus.config.canid, 8)
                msg.data[0] = cbusdefs.OPC_DTXC
                msg.data[1] = cctx.stream_id
                msg.data[2] = cctx.sequence_num

                for c in range(5):
                    if cctx.index >= cctx.message_size:
                        cctx.in_use = False
                        break

                    msg.data[c + 3] = cctx.buffer[cctx.index]
                    cctx.index += 1

                self.bus.can.send_message(msg)
                cctx.sequence_num += 1
                cctx.last_fragment_sent = time.ticks_ms

            self.current_context = (self.current_context + 1) % len(self.transmit_contexts)
            await asyncio.sleep_ms(PROCESS_DELAY)

    def handle_long_message_fragment(self, msg: canmessage.canmessage) -> None:
        if not msg.data[1] in self.subscribed_ids:
            return

        if msg.data[2] == 0:
            found_free_context = False
            j = 0
            ctx = None

            for j, ctx in enumerate(self.receive_contexts):
                if not ctx.in_use:
                    found_free_context = True
                    break

            if not found_free_context:
                self.receive_contexts.append(receive_context())
                j += 1
                ctx = self.receive_contexts[j]

            ctx.in_use = True
            ctx.stream_id = msg.data[1]
            ctx.message_size = (msg.data[3] << 8) + msg.data[4]
            ctx.crc = (msg.data[5] << 8) + msg.data[6]
            ctx.buffer = bytearray()
            ctx.expected_next_receive_sequence_num = 1
            ctx.can_id = msg.get_canid()
            ctx.received = 0
            ctx.last_fragment_received_at = time.ticks_ms()

        else:
            found_matching_context = False
            message_receive_complete = False
            i = 0
            ctx = None

            for i, ctx in enumerate(self.receive_contexts):
                if ctx.in_use and ctx.stream_id == msg.data[1] and ctx.can_id == msg.get_canid():
                    found_matching_context = True
                    break

            if not found_matching_context:
                self.logger.log('error: unable to find matching receive context for continuation packet')
                return

            if msg.data[2] != ctx.expected_next_receive_sequence_num:
                self.logger.log(f'error: wrong sequence number, expected {self.receive_contexts[i].expected_next_receive_sequence_num}, got {msg.data[2]}')
                self.user_handler(ctx.buffer, ctx.stream_id, CBUS_LONG_MESSAGE_SEQUENCE_ERROR, )
                ctx.in_use = False
                return

            for c in range(5):
                ctx.buffer.append(msg.data[c + 3])
                ctx.received += 1
                ctx.last_fragment_received_at = time.ticks_ms()
                ctx.expected_next_receive_sequence_num = (msg.data[2] + 1)

                if len(ctx.buffer) >= ctx.message_size:
                    message_receive_complete = True
                    break

            if len(ctx.buffer) >= ctx.message_size:
                message_receive_complete = True

            ctx.expected_next_receive_sequence_num = msg.data[2] + 1

            if message_receive_complete:
                ctx.in_use = False
                self.user_handler(ctx.buffer, ctx.stream_id, CBUS_LONG_MESSAGE_COMPLETE)

    def use_crc(self, crc) -> None:
        self.using_crc = crc

    @staticmethod
    def crc16(data: bytes, poly=0x8408) -> int:
        data = bytearray(data)
        crc = 0xffff

        for b in data:
            cur_byte = 0xff & b
            for _ in range(8):
                if (crc & 0x0001) ^ (cur_byte & 0x0001):
                    crc = (crc >> 1) ^ poly
                else:
                    crc >>= 1
                cur_byte >>= 1

        crc = ~crc & 0xffff
        crc = (crc << 8) | ((crc >> 8) & 0xff)

        return crc & 0xffff
