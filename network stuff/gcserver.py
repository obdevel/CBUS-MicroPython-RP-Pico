# gcserver.py
# GridConnect TCP/IP server for the Pico W

import uasyncio as asyncio

import canmessage
import logger
from primitives import Queue


class qmsg:
    def __init__(self, source, gc):
        self.source = source
        self.gc = gc


class gcserver:
    def __init__(self, bus=None, host='', port=5550):
        self.logger = logger.logger()
        self.host = host
        self.port = port
        self.ip = None
        self.server = None
        self.gc = ''
        self.clients = []
        self.output_queue = Queue()
        self.peer_queue = Queue()
        self.bus = bus
        self.tq = asyncio.create_task(self.queue_manager())
        self.bus.set_gcserver(self)

    async def client_connected_cb(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info('peername')
        cip = peer[0]
        cport = peer[1]
        self.logger.log(f'gcserver: new connection from client, ip = {cip}, port = {cport}')

        self.clients.append(writer)
        idx = len(self.clients) - 1
        self.logger.log(f'gcserver: using client idx = {idx}')

        currgc = ''

        while True:
            try:
                data = await reader.read(64)
            except:
                self.logger.log('socket exception')
                break

            if data:
                data_decoded = data.decode()
                self.logger.log(f'gcserver: received |{data_decoded}| len = {len(data_decoded)}')

                for ch in data_decoded:
                    if not ch.upper() in 'XSNR0123456789ABCDEF;:':
                        continue

                    if ch == ':':
                        currgc = ''

                    currgc += ch

                    if ch == ';':
                        m = self.GCtoCAN(currgc)
                        self.logger.log(f'gcserver: converted GC msg to {m.__str__()}')
                        self.bus.send_cbus_message_no_header_update(m)
                        await self.peer_queue.put(qmsg(cport, currgc))
                        if self.bus.consume_own_messages:
                            await self.bus.can.rx_queue.enqueue(m)
            else:
                self.logger.log(f'gcserver: client idx = {idx} disconnected, closing stream')
                break

        for i, cl in enumerate(self.clients):
            if cl == writer:
                # del self.clients[i]
                break

        writer.close()
        await writer.wait_closed()
        del self.clients[i]

    async def queue_manager(self) -> None:
        while True:

            # output queue from main CBUS process
            while not self.output_queue.empty():
                self.logger.log('gcserver: output queue message(s) available to send')
                msg = await self.output_queue.get()
                # await self.send_message(msg)
                gc = self.CANtoGC(msg)
                count = 0

                for idx in range(len(self.clients)):
                    if self.clients[idx] is not None:
                        self.clients[idx].write(gc)
                        await self.clients[idx].drain()
                        count += 1
                        await asyncio.sleep_ms(5)

                self.logger.log(f'gcserver: sent message to {count} client(s)')
                await asyncio.sleep_ms(5)

            # peer-to-peer message queue
            while not self.peer_queue.empty():
                self.logger.log('gcserver: peer queue message(s) available to send')
                pmsg = await self.peer_queue.get()
                for idx in range(len(self.clients) - 1):
                    cport = self.clients[idx].get_extra_info('peername')
                    if cport != pmsg.source:
                        self.clients[idx].write(pmsg.gc)
                        await self.clients[idx].drain()
                        await asyncio.sleep_ms(5)

            await asyncio.sleep_ms(20)

    # async def send_message(self, msg: canmessage.canmessage) -> None:
    #     gc = self.CANtoGC(msg)
    #     count = 0
    #
    #     for idx in range(len(self.clients)):
    #         if self.clients[idx] is not None:
    #             self.clients[idx].write(gc)
    #             await self.clients[idx].drain()
    #             count += 1
    #             await asyncio.sleep_ms(5)
    #
    #     self.logger.log(f'gcserver: sent message to {count} client(s)')

    def print_clients(self) -> None:
        for i, c in enumerate(self.clients):
            if c is not None:
                self.logger.log(f'[{i} {c.get_extra_info("peername")}')

    def CANtoGC(self, msg: canmessage.canmessage) -> str:
        tid = msg.canid << 5

        gc = ':'
        gc += f'X{tid:04X}' if msg.ext else f'S{tid:04X}'
        gc += 'R' if msg.rtr else 'N'

        for i in range(msg.dlc):
            gc += f'{msg.data[i]:02X}'

        gc += ';'
        return gc

    def GCtoCAN(self, gc: str) -> canmessage.canmessage:
        msg = canmessage.canmessage()
        msg.ext = True if (gc[1] == 'X') else False
        pos = gc.find('N')

        if pos == -1:
            msg.rtr = True
            pos = gc.find('R')
        else:
            msg.rtr = False

        id = '0X' + gc[2:pos]
        msg.canid = int(id) >> 5

        data = gc[pos + 1: -1]
        msg.dlc = int(len(data) / 2)

        for i in range(msg.dlc):
            j = int(i)
            t = '0x' + data[j * 2: (j * 2) + 2]
            msg.data[i] = int(t)

        return msg
