# cbuslongmessage.py

import time
import uasyncio as asyncio
import cbus
import cbusdefs
import canmessage
import logger

RECEIVE_TIMEOUT = 1000
TRANSMIT_DELAY = 10

CBUS_LONG_MESSAGE_INCOMPLETE = 0
CBUS_LONG_MESSAGE_COMPLETE = 1
CBUS_LONG_MESSAGE_SEQUENCE_ERROR = 2
CBUS_LONG_MESSAGE_TIMEOUT_ERROR = 3
CBUS_LONG_MESSAGE_CRC_ERROR = 4
CBUS_LONG_MESSAGE_TRUNCATED = 5


class lm_context:
    def __init__(self):
        self.logger = logger.logger()
        # self.logger.log("lm_context constructor")

        self.in_use = False
        self.streamid = 0
        self.buffer = bytearray()
        self.message_size = 0


class receive_context(lm_context):
    def __init__(self):
        self.logger = logger.logger()
        # self.logger.log("receive_context constructor")
        super().__init__()

        self.canid = 0
        self.last_fragment_received_at = 0
        self.crc = 0
        self.received = 0
        self.expected_next_receive_sequence_num = 0


class transmit_context(lm_context):
    def __init__(self):
        self.logger = logger.logger()
        # self.logger.log("transmit_context constructor")
        super().__init__()

        self.index = 0
        self.priority = 0
        self.sequence_num = 0
        self.using_crc = False
        self.flags = 0
        self.last_fragment_sent = 0


class cbuslongmessage:
    def __init__(self, bus):
        self.logger = logger.logger()
        # self.logger.log("long message constructor")

        if not isinstance(bus, cbus.cbus):
            raise TypeError("error: bus arg is not an instance of class cbus")

        self.bus = bus
        self.using_crc = False
        self.subscribed_ids = None
        self.bus.set_long_message_handler(self)
        self.user_handler = None
        self.current_context = 0
        self.receive_contexts = [receive_context()]
        self.transmit_contexts = [transmit_context()]

        self.tl = asyncio.create_task(self.process())

    def subscribe(self, ids, handler, receive_timeout=RECEIVE_TIMEOUT):
        self.logger.log(f"lm subscribe: {ids}")
        self.subscribed_ids = ids
        self.user_handler = handler
        self.receive_timeout = receive_timeout

    def send_long_message(self, message, streamid, priority=0x0B):
        # self.logger.log(f'sending long message = {message}')

        if len(message) >= 2**16:
            self.logger.log("error: message is too long")
            return False

        for j in range(len(self.transmit_contexts)):
            if (
                self.transmit_contexts[j].in_use
                and self.transmit_contexts[j].streamid == streamid
            ):
                self.logger.log(
                    f"error: a message is already in progress with streamid = {streamid} in context {j}"
                )
                return False

        found_free_context = False

        for j in range(len(self.transmit_contexts)):
            if not self.transmit_contexts[j].in_use:
                found_free_context = True
                break

        if not found_free_context:
            self.transmit_contexts.append(transmit_context())
            j += 1

        self.transmit_contexts[j].in_use = True
        self.transmit_contexts[j].streamid = streamid
        self.transmit_contexts[j].buffer = bytearray(message)
        self.transmit_contexts[j].message_size = len(message)
        self.transmit_contexts[j].priority = priority
        self.transmit_contexts[j].sequence_num = 0
        self.transmit_contexts[j].index = 0
        self.transmit_contexts[j].flags = 0
        self.transmit_contexts[j].crc = (
            self.crc16(self.transmit_contexts[j].buffer) if self.using_crc else 0
        )

        msg = canmessage.canmessage(self.bus.config.canid, 8)

        msg.data[0] = cbusdefs.OPC_DTXC
        msg.data[1] = streamid
        msg.data[2] = self.transmit_contexts[j].sequence_num
        msg.data[3] = int(self.transmit_contexts[j].message_size / 256)
        msg.data[4] = self.transmit_contexts[j].message_size & 0xFF
        msg.data[5] = int(self.transmit_contexts[j].crc / 256)
        msg.data[6] = self.transmit_contexts[j].crc & 0xFF
        msg.data[7] = self.transmit_contexts[j].flags

        self.bus.can.send_message(msg)
        msg.print(False)

        self.transmit_contexts[j].sequence_num = 1
        self.transmit_contexts[j].last_fragement_sent = time.ticks_ms
        # self.logger.log('sent long message header packet')

    async def process(self):
        while True:

            for j in range(len(self.receive_contexts)):
                if (
                    self.receive_contexts[j].in_use
                    and time.ticks_ms() - self.receive_contexts[j].last_fragment_received_at
                    > self.receive_timeout
                ):
                    self.logger.log(f"error: receive context {j} timed out")
                    self.user_handler(
                        self.receive_contexts[j].buffer,
                        self.receive_contexts[j].streamid,
                        CBUS_LONG_MESSAGE_TIMEOUT_ERROR,
                    )
                    self.receive_contexts[j].in_use = False

            if (self.transmit_contexts[self.current_context].in_use and time.ticks_ms() - self.transmit_contexts[self.current_context].last_fragment_sent > TRANSMIT_DELAY):
                # print(f'sending next fragment in send context = {self.current_context}')

                msg = canmessage.canmessage(self.bus.config.canid, 8)
                msg.data[0] = cbusdefs.OPC_DTXC
                msg.data[1] = self.transmit_contexts[j].streamid
                msg.data[2] = self.transmit_contexts[j].sequence_num

                for c in range(5):
                    if (
                        self.transmit_contexts[self.current_context].index
                        >= self.transmit_contexts[self.current_context].message_size
                    ):
                        # print('send: end of data')
                        self.transmit_contexts[self.current_context].in_use = False
                        break

                    msg.data[c + 3] = self.transmit_contexts[self.current_context].buffer[
                        self.transmit_contexts[self.current_context].index
                    ]
                    # print(f'added char {chr(msg.data[c+3])}')
                    self.transmit_contexts[self.current_context].index += 1

                msg.print(False)
                self.bus.can.send_message(msg)
                self.transmit_contexts[self.current_context].sequence_num += 1
                self.transmit_contexts[
                    self.current_context
                ].last_fragement_sent = time.ticks_ms

            self.current_context = (self.current_context + 1) % len(self.transmit_contexts)

            await asyncio.sleep_ms(50)

    def handle_long_message_fragment(self, msg):
        # print('handling long message fragment')

        if msg.data[0] != cbusdefs.OPC_DTXC:
            self.logger.log(f"error: wrong opcode {msg.data[0]:x}")
            return

        if not msg.data[1] in self.subscribed_ids:
            self.logger.log(f"handle_long_message_fragment: not subscribed to stream id = {msg.data[1]}")
            return

        if msg.data[2] == 0:
            # self.logger.log(f'handling header packet, streamid = {msg.data[1]}, size = {msg.data[4]}')

            found_free_context = False

            for j in range(len(self.receive_contexts)):
                if not self.receive_contexts[j].in_use:
                    found_free_context = True
                    break

            if not found_free_context:
                # print('appending new receive context')
                self.transmit_contexts.append(receive_context())
                j += 1

            # self.logger.log(f'using receive context = {j}')
            self.receive_contexts[j].in_use = True
            self.receive_contexts[j].streamid = msg.data[1]
            self.receive_contexts[j].message_size = (msg.data[3] * 256) + msg.data[4]
            self.receive_contexts[j].crc = (msg.data[5] * 256) + msg.data[6]
            self.receive_contexts[j].buffer = bytearray()
            self.receive_contexts[j].expected_next_receive_sequence_num = 1
            self.receive_contexts[j].canid = msg.get_canid()
            self.receive_contexts[j].received = 0
            self.receive_contexts[j].last_fragment_received_at = time.ticks_ms()

        else:

            found_matching_context = False
            message_receive_complete = False

            for i in range(len(self.receive_contexts)):
                if (
                    self.receive_contexts[i].in_use
                    and self.receive_contexts[i].streamid == msg.data[1]
                    and self.receive_contexts[i].canid == msg.get_canid()
                ):
                    found_matching_context = True
                    break

            if not found_matching_context:
                self.logger.log(
                    "error: unable to find matching receive context for continuation packet"
                )
                return

            # print(f'using receive context = {i}')
            # print(f'handling continuation packet, streamid = {self.receive_contexts[i].streamid}')

            if (
                msg.data[2]
                != self.receive_contexts[i].expected_next_receive_sequence_num
            ):
                self.logger.log(
                    f"error: wrong sequence number, expected {self.receive_contexts[i].expected_next_receive_sequence_num}, got {msg.data[2]}"
                )
                self.user_handler(
                    self.receive_contexts[i].buffer,
                    self.receive_contexts[i].streamid,
                    CBUS_LONG_MESSAGE_SEQUENCE_ERROR,
                )
                self.receive_contexts[i].in_use = False
                return

            for c in range(5):
                # self.logger.log(f'processing next char = {chr(msg.data[c+3])}, len = {len(self.receive_contexts[i].buffer)}')
                self.receive_contexts[i].buffer.append(msg.data[c + 3])
                self.receive_contexts[i].received += 1
                self.receive_contexts[i].last_fragment_received_at = time.ticks_ms()
                self.receive_contexts[i].expected_next_receive_sequence_num = (
                    msg.data[2] + 1
                )

                if (
                    len(self.receive_contexts[i].buffer)
                    >= self.receive_contexts[i].message_size
                ):
                    message_receive_complete = True
                    break

            if (
                len(self.receive_contexts[i].buffer)
                >= self.receive_contexts[i].message_size
            ):
                message_receive_complete = True

            self.receive_contexts[i].expected_next_receive_sequence_num = (
                msg.data[2] + 1
            )

            if message_receive_complete:
                self.receive_contexts[i].in_use = False
                self.user_handler(
                    self.receive_contexts[i].buffer,
                    self.receive_contexts[i].streamid,
                    CBUS_LONG_MESSAGE_COMPLETE,
                )

    def use_crc(self, crc):
        self.using_crc = crc

    def crc16(self, data: bytes, poly=0x8408):
        data = bytearray(data)
        crc = 0xFFFF

        for b in data:
            cur_byte = 0xFF & b
            for _ in range(0, 8):
                if (crc & 0x0001) ^ (cur_byte & 0x0001):
                    crc = (crc >> 1) ^ poly
                else:
                    crc >>= 1
                cur_byte >>= 1

        crc = ~crc & 0xFFFF
        crc = (crc << 8) | ((crc >> 8) & 0xFF)

        return crc & 0xFFFF
