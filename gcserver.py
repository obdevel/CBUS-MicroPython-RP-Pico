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

class gcserver:

#     def __new__(cls):
#         if not hasattr(cls, "instance"):
#             cls.instance = super(gcserver, cls).__new__(cls)
#         return cls.instance

    def __init__(self, bus=None, ssid="", password="", host="", port=5550):
        self.logger = logger.logger()
        # self.logger.log("gcserver: constructor")
        self.ssid = ssid
        self.password = password
        self.host = host
        self.port = port
        self.ip = None
        self.server = None
        self.wifi_is_connected = False
        self.num_active_clients = 0
        self.gc = ""
        self.clients = [None]
        self.output_queue = circularQueue.circularQueue(32)

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

        while not self.wlan.isconnected():
            print(".", end = "")
            time.sleep_ms(500)

        print()
        self.ip = self.wlan.ifconfig()[0]
        self.logger.log(f"gcserver: connected to wifi, address = {self.ip}")
        self.host = self.ip

    async def client_connected_cb(self, reader, writer):
        peer = writer.get_extra_info('peername')
        self.logger.log(f"gcserver: connection from ip = {peer[0]}, port = {peer[1]}")

        found = False

        for idx in range(len(self.clients)):
            if self.clients[idx] is None:
                found = True
                break

        if found:
            self.clients[idx] = writer
        else:
            self.clients.append(writer)
            idx += 1

        self.logger.log(f"gcserver: using client idx = {idx}")
        data = None

        while True:
            try:
                data = await reader.read(32)
            except:
                self.logger.log("socket exception")
                break

            if data:
                message = data.decode()
                self.logger.log(f"gcserver: received '{message}' len {len(message)} from {peer}")
                self.gc += message

                if self.gc[-1] == ";":
                    m = self.GCtoCAN(self.gc)
                    self.logger.log(f"converted = {m.__str__()}")
                    self.bus.send_cbus_message_no_header_update(m)
                    self.gc = ""
            else:
                self.logger.log(f"gcserver: client idx = {idx} has disappeared, closing socket")
                break

        writer.close()
        await writer.wait_closed()
        self.clients[idx] = None

    async def manage_output_queue(self):

        while True:
            while self.output_queue.available():
                self.logger.log("gcserver: message(s) available to send")
                msg = self.output_queue.dequeue()
                await self.send_message(msg)

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
                self.logger.log(f"[{idx}] {self.clients[idx].get_extra_info('peername')}")

    def stop(self):
        pass

    def CANtoGC(self, msg):

        gc = ":"
        gc += f"X{msg.id:X}" if msg.ext else f"S{msg.id:X}"
        gc += "R" if msg.rtr else "N"

        for i in range(msg.len):
            gc += f"{msg.data[i]:02X}"

        gc+= ";"
        return gc

    def GCtoCAN(self, gc):

        # gc = gc.decode()
        msg = canmessage.canmessage()
        msg.ext = True if (gc[1] == "X") else False
        pos = gc.find("R")

        if pos == -1:
            msg.rtr = False
            pos = gc.find("N")
        else:
            msg.rtr = True

        id = "0X" + gc[2:pos]
        msg.id = int(id)

        data = gc[pos+1:-1]
        msg.len = int(len(data)/2)
        # print(f"data = {data}, len = {len(data)}")

        for i in range(msg.len):
            j = int(i)
            t = "0x" + data[j*2:(j*2)+2]
            # print(f"item = {t}")
            msg.data[i] = int(t)

        return msg

