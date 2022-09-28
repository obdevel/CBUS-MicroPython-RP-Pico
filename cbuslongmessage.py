
# cbuslongmessage.py

import time
import cbus, cbusdefs, canmessage

RECEIVE_TIMEOUT = 5000
TRANSMIT_DELAY = 50

class receive_context:

    def __init__(self, buffer_size=64):
        self.in_use = False
        self.streamid = 0
        self.canid = 0
        self.buffer_size = buffer_size
        self.buffer = bytearray(buffer_size)
        self.index = 0
        self.last_fragment_received = 0
        self.message_size = 0
        self.crc = 0
        self.received = 0
        self.expected_next_receive_sequence_num = 0

class transmit_context:

    def __init__(self, buffer_size=64):
        self.in_use = False
        self.streamid = 0
        self.buffer_size = buffer_size
        self.priority = 0
        self.buffer = bytearray(buffer_size)
        self.index = 0
        self.sequence_num = 0
        self.crc = 0
        self.flags = 0
        self.last_fragment_sent = 0

class cbuslongmessage:

    def __init__(self, bus, buffer_size=64, num_contexts=4):

        print('** long message constructor')
        self.cbus = bus
        self.buffer_size = buffer_size
        self.num_contexts = num_contexts
        self.using_crc = False

        if not isinstance(bus, cbus.cbus):
            raise TypeError('cbus is not an instance of class cbus')

        self.subscribed_ids = None
        self.cbus.set_long_message_handler(self)
        self.user_handler = None
        self.buffer_size = buffer_size
        self.num_contexts = num_contexts
        self.current_context = 0
        self.receive_contexts = [receive_context(buffer_size)] * num_contexts
        self.transmit_contexts = [transmit_context(buffer_size)] * num_contexts

        for i in range(num_contexts):
            self.receive_contexts[i].in_use = False
            self.transmit_contexts[i].in_use = False

    def subscribe(self, ids, handler):
        print(f'subscribe: {ids}')
        self.subscribed_ids = ids
        self.user_handler = handler

    def send_long_message(self, message, streamid, priority=0x0b):
        print(f'sending long message = {message}')

        for j in range(self.num_contexts):
            if self.transmit_contexts[j].in_use and self.transmit_contexts[j].streamid == streamid:
                print(f'already sending streamid = {streamid} in context {i}')
                return False

        matched = False

        for j in range(self.num_contexts):
            if not self.transmit_contexts[j].in_use:
                matched = True
                break

        if not matched:
            print('unable to find a free transmit context')
            return False

        print(f'using transmit context = {j}')
        self.transmit_contexts[j].in_use = True
        self.transmit_contexts[j].streamid = streamid
        self.transmit_contexts[j].buffer = bytearray(message)
        self.transmit_contexts[j].message_size = len(message)
        self.transmit_contexts[j].priority = priority
        self.transmit_contexts[j].index = 0
        self.transmit_contexts[j].flags = 0

        if self.using_crc:
            self.transmit_contexts[j].crc = crc_16(self.transmit_contexts[j].message)
        else:
            self.transmit_contexts[j].crc = 0

        msg = canmessage.canmessage(self.cbus.config.canid, 8)
        msg.data[0] = cbusdefs.OPC_DTXC
        msg.data[1] = streamid
        msg.data[2] = 0
        msg.data[3] = int(self.transmit_contexts[j].message_size / 256)
        msg.data[4] = self.transmit_contexts[j].message_size & 0xff
        msg.data[5] = int(self.transmit_contexts[j].crc / 256)
        msg.data[6] = self.transmit_contexts[j].crc & 0xff
        msg.data[7] = self.transmit_contexts[j].flags

        # send fragment
        self.transmit_contexts[j].sequence_num = 1
        print('send fragment header')

    def process(self):

        for j in range(self.num_contexts):
            if self.receive_contexts[j].in_use and time.ticks_ms() - self.receive_contexts[j].last_fragment_received > RECEIVE_TIMEOUT:
                print(f'receive context {j} timed out')
                # call user handler with error code
                self.receive_contexts[j].in_use = False

        if self.transmit_contexts[self.current_context].in_use and time.ticks_ms() - self.transmit_contexts[self.current_context].last_fragment_sent > TRANSMIT_DELAY:
            print(f'sending next fragment in send context {self.current_context}')
            # send the fragment

        self.current_context = (self.current_context + 1) % self.num_contexts

    def handle_Long_message_fragment(self, msg):
        print('handling long message fragment')

        if msg.data[0] != cbusdefs.OPC_DTXC:
            print(f'wrong opcode {msg.data[0]:x')
            return

        if msg.data[2] == 0:
            print('handling header packet')

            matched = False

            for id in self.subscribed_ids:
                if id == msg.data[1]:
                    matched = True
                    break

            if not matched:
                print(f'not subscribed to id {msg.data[1]}')
                return

            matched = False

            for j in range(self.num_contexts):
                if not self.receive_contexts[j].in_use:
                    print(f'using context = {j}')
                    self.receive_contexts[j].in_use = True
                    self.receive_contexts[j].streamid = msg.data[1]
                    self.receive_contexts[j].message_size = (msg.data[3] * 256) + msg.data[4]
                    self.receive_contexts[j].crc = (msg.data[5] * 256) + msg.data[6]
                    self.receive_contexts[j].buffer = bytearray(self.receive_contexts[j].message_size)
                    self.receive_contexts[j].index = 0
                    self.receive_contexts[j].expected_next_receive_sequence_num = 1
                    self.receive_contexts[j].canid = self.cbus.message_canid(msg)
                    self.receive_contexts[j].received = 0
                    self.receive_contexts[j].last_fragment_received = time.ticks_ms()
                    matched = True
                    break

            if not matched:
                print('unable to find free receive context')
                return
        else:
            print('handling continuation packet')

            matched = False;

            for i in range(self.num_contexts):
                if self.receive_contexts[i].in_use and self.receive_contexts[i].streamid == msg.data[1] and self.receive_contexts[i].canid == self.cbus.message_canid(msg):
                    matched = True
                    break

            if not matched:
                print('unable to find matching receive context')
                return

            print(f'using context = {i}')

            if msg.data[2] != self.receive_contexts[i].expected_next_receive_sequence_num:
                print(f'wrong sequence number, expected {self.receive_contexts[i].expected_next_receive_sequence_num}, got {msg.data[2]}')
                # call user handler with error code
                self.receive_contexts[i].in_use = False
                return

            for j in range(5):
                self.receive_contexts[i].buffer[self.receive_contexts[i].index] = msg.data[j + 3]
                self.receive_contexts[i].index += 1
                self.receive_contexts[i].received += 1
                self.receive_contexts[j].last_fragment_received = time.ticks_ms()

                if self.receive_contexts[j].received >= self.receive_contexts[j].message_size:
                    # call user handler with success code
                    break

            if self.receive_contexts[j].received >= self.receive_contexts[j].message_size:
                # call user handler with success code
                pass

            self.receive_contexts[j].expected_next_receive_sequence_num = (self.receive_contexts[j].expected_next_receive_sequence_num + 1) % 256

    def use_crc(self, crc):
        self.using_crc = crc

def crc16(data: bytes, poly=0x8408):
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
    crc = (~crc & 0xFFFF)
    crc = (crc << 8) | ((crc >> 8) & 0xFF)
    
    return crc & 0xFFFF
