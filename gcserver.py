# gcserver.py
# GridConnect TCP/IP server for the Pico W

import network
import socket
import time
import uasyncio as asyncio
import logger
import cbus
import canio
import canmessage
import circularQueue


class qmsg:
    def __init__(self, source, gc):
        self.source = source
        self.gc = gc


class gcserver:

    #     def __new__(cls):
    #         if not hasattr(cls, "instance"):
    #             cls.instance = super(gcserver, cls).__new__(cls)
    #         return cls.instance

    def __init__(self, bus=None, ssid="", password="", port=5550):
        self.logger = logger.logger()
        # self.logger.log("gcserver: constructor")
        self.ssid = ssid
        self.password = password
        self.host = None
        self.port = port
        self.ip = None
        self.server = None
        self.gc = ""
        self.clients = []
        self.output_queue = circularQueue.circularQueue(16)
        self.peer_queue = circularQueue.circularQueue(4)

        if isinstance(bus, cbus.cbus):
            self.bus = bus
        else:
            raise TypeError("error: gcserver: cbus is not an instance of class cbus")

        bus.set_gcserver(self)

    def connect_wifi(self):
        # *** connect to wifi here

        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        self.wlan.connect(self.ssid, self.password)
        self.logger.log("gcserver: waiting for wifi...")
        t = time.ticks_ms()

        while not self.wlan.isconnected() and t > time.ticks_ms() - 5000:
            time.sleep_ms(500)

        if self.wlan.isconnected():
            self.ip = self.wlan.ifconfig()[0]
            self.channel = self.wlan.config('channel')
            self.logger.log(f"gcserver: connected to wifi, channel = {self.channel}, address = {self.ip}")
            self.host = self.ip
        else:
            self.logger.log("gcserver: failed to connect to wifi")

    async def client_connected_cb(self, reader, writer):
        peer = writer.get_extra_info("peername")
        cip = peer[0]
        cport = peer[1]
        self.logger.log(f"gcserver: new connection from client, ip = {cip}, port = {cport}")

        self.clients.append(writer)
        idx = len(self.clients) - 1
        self.logger.log(f"gcserver: using client idx = {idx}")

        data = None
        currgc = ""

        while True:
            try:
                data = await reader.read(64)
            except:
                self.logger.log("socket exception")
                break

            if data:
                data_decoded = data.decode()
                self.logger.log(f"gcserver: received |{data_decoded}| len = {len(data_decoded)} from {peer}")

                for ch in data_decoded:

                    if not ch.upper() in "XSNR0123456789ABCDEF;:":
                        continue

                    if ch == ":":
                        currgc = ch
                    else:
                        currgc += ch

                    if ch == ";":
                        m = self.GCtoCAN(currgc)
                        self.logger.log(f"gcserver: converted GC msg to {m.__str__()}")
                        self.bus.send_cbus_message_no_header_update(m)
                        # self.bus.can.rx_queue.enqueue(m)
                        self.peer_queue.enqueue(qmsg(cport, currgc))
                        await asyncio.sleep_ms(1)
            else:
                self.logger.log(f"gcserver: client idx = {idx} disconnected, closing stream")
                break

        for i in range(len(self.clients)):
            if self.clients[i] == writer:
                break

        writer.close()
        await writer.wait_closed()
        del self.clients[i]

    async def queue_manager(self):

        while True:
            while self.output_queue.available():
                self.logger.log("gcserver: message(s) available to send")
                msg = self.output_queue.dequeue()
                await self.send_message(msg)

            while self.peer_queue.available():
                pmsg = self.peer_queue.dequeue()
                for idx in range(len(self.clients) - 1):
                    cport = self.clients[idx].get_extra_info("peername")
                    if cport != pmsg.source:
                        self.clients[idx].write(pmsg.gc)
                        await self.clients[idx].drain()

            await asyncio.sleep_ms(20)

    async def send_message(self, msg):
        gc = self.CANtoGC(msg)
        count = 0

        for idx in range(len(self.clients)):
            if self.clients[idx] is not None:
                self.clients[idx].write(gc)
                await self.clients[idx].drain()
                count += 1

        self.logger.log(f"gcserver: sent message to {count} client(s)")

    def print_clients(self):
        for idx in range(len(self.clients)):
            if self.clients[idx] is not None:
                self.logger.log(
                    f"[{idx}] {self.clients[idx].get_extra_info('peername')}"
                )

    def CANtoGC(self, msg):

        tid = msg.id << 5

        gc = ":"
        gc += f"X{tid:04X}" if msg.ext else f"S{tid:04X}"
        gc += "R" if msg.rtr else "N"

        for i in range(msg.len):
            gc += f"{msg.data[i]:02X}"

        gc += ";"
        return gc

    def GCtoCAN(self, gc):

        msg = canmessage.canmessage()
        msg.ext = True if (gc[1] == "X") else False
        pos = gc.find("N")

        if pos == -1:
            msg.rtr = True
            pos = gc.find("R")
        else:
            msg.rtr = False

        id = "0X" + gc[2:pos]
        msg.id = int(id) >> 5

        data = gc[pos + 1 : -1]
        msg.len = int(len(data) / 2)

        for i in range(msg.len):
            j = int(i)
            t = "0x" + data[j * 2 : (j * 2) + 2]
            msg.data[i] = int(t)

        return msg
