# dcc.py
# control a DCC system / command station

import uasyncio as asyncio
from machine import UART, Pin
from micropython import const

import canmessage
import cbusdefs
import cbusobjects
import cbuspubsub
import logger
import primitives

uart1 = UART(1, baudrate=115200, tx=Pin(8), rx=Pin(9))

FUNCTION_OFF = const(0)
FUNCTION_ON = const(1)

DIRECTION_REVERSE = const(0)
DIRECTION_FORWARD = const(1)

POWER_OFF = const(0)
POWER_ON = const(1)

active_sessions = {}  # decoder_id: loco object


class loco:
    def __init__(self, decoder_id):
        self.decoder_id = decoder_id
        self.speed = 0
        self.direction = DIRECTION_FORWARD
        self.functions = [0] * 30
        self.active = False
        self.session = 0

    def __del(self):
        del active_sessions[self.decoder_id]


class merg_cab:
    def __init__(self, cbus, timeout=2000):
        self.logger = logger.logger()
        self.cbus = cbus
        self.timeout = timeout
        asyncio.create_task(self.keepalive())

    def acquire(self, loco) -> bool:
        self.logger.log("merg_cab: requesting session ...")
        self.query = (cbusdefs.OPC_PLOC, cbusdefs.OPC_ERR)
        self.sub = cbuspubsub.subscription('cab:sub', self.cbus, self.query, canmessage.QUERY_OPCODES)
        self.msg = canmessage.canmessage()
        ok = False

        if await self.send_request(self.msg):
            loco.session = 99
            loco.active = True
            active_sessions[loco.decoder_id] = loco
            ok = True
        else:
            self.logger.log("merg_cab: request failed")

        self.logger.log(f"merg_cab: loco {loco.decoder_id}, session = {loco.session}, active = {loco.active}")
        return ok

    def send_request(self, msg) -> bool:
        ok = False
        evt = asyncio.Event()
        evc = asyncio.Event()
        timer = cbusobjects.timeout(self.timeout, evt)
        tc = asyncio.create_task(timer.one_shot())
        sc = asyncio.create_task(self.wait_for_response(evc))

        self.logger.log("merg_cab: awaiting response ...")
        evw = await primitives.WaitAny((evt, evc)).wait()

        if evw is evc:
            self.logger.log("merg_cab: received response")
            ok = True
        elif evw is evt:
            self.logger.log("merg_cab: timed out")

        tc.cancel()
        sc.cancel()
        self.sub.unsubscribe()
        return ok

    async def wait_for_response(self, evt) -> None:
        self.msg = await self.sub.wait()
        evt.set()

    def dispatch(self, decoder_id) -> None:
        del active_sessions[decoder_id]

    def set_speed(self, decoder_id, speed) -> None:
        self.logger.log("set speed")

    def set_direction(self, decoder_id, direction) -> None:
        self.logger.log("set direction")

    def function(self, decoder_id, function, polarity) -> None:
        self.logger.log("set function")

    def emergency_stop(self, decoder_id) -> None:
        self.logger.log("e stop")

    def emergency_stop_all(self) -> None:
        self.logger.log("e stop all")

    async def keepalive(self) -> None:
        while True:
            await asyncio.sleep(4)
            for decoder_id in active_sessions:
                session = active_sessions[decoder_id]


class dccpp:
    def __init__(self, port, timeout=2000):
        self.logger = logger.logger()
        self.port = uart1
        self.writer = asyncio.StreamWriter(self.port)
        self.reader = asyncio.StreamReader(self.port)
        self.request = ""
        self.response = ""
        self.timeout = timeout
        self.attempts = 1

    def acquire(self, loco) -> bool:
        self.request = f"<t -1 {loco.decoder_id} 0 1>"
        self.response = ""
        await self.send_request()

        if self.response.startswith("<"):
            loco.session = 99
            loco.active = True
            self.logger.log(f"dccpp: loco {loco.decoder_id}, session = {loco.session}, active = {loco.active}")
            active_sessions[loco.decoder_id] = loco
        else:
            self.logger.log("dccpp: invalid response")

        return loco.active

    def dispatch(self, decoder_id):
        pass

    def set_speed(self, loco, speed):
        self.request = f"<t -1 {loco.decoder_id} {speed} {loco.direction}>"
        self.response = ""
        await self.send_request()

        if self.response.startswith("<"):
            self.logger.log(f"dccpp: {self.response}")
            loco.speed = speed
        else:
            self.logger.log("dccpp: invalid response")

    def set_direction(self, loco, direction):
        self.request = f"<t -1 {loco.decoder_id} {loco.speed} {direction}>"
        self.response = ""
        await self.send_request()

        if self.response.startswith("<"):
            self.logger.log(f"dccpp: {self.response}")
            loco.direction = direction
        else:
            self.logger.log("dccpp: invalid response")

    def function(self, loco, function, polarity) -> None:
        self.request = f"<F {loco.decoder_id} {function} {polarity}>"
        self.response = ""
        await self.send_request()

        if self.response.startswith("<"):
            self.logger.log(f"dccpp: {self.response}")
            loco.functions[function] = polarity
        else:
            self.logger.log("dccpp: no response")

    def status(self) -> bool:
        self.request = "<s>"
        self.response = ""
        await self.send_request()

        if self.response.startswith("<"):
            self.logger.log(f"dccpp: {self.response}")
        else:
            self.logger.log("dccpp: no response")

    def track_power(self, state):
        self.request = f"<{state}>"
        self.response = ""
        await self.send_request()

        if self.response.startswith("<"):
            self.logger.log(f"dccpp: {self.response}")
        else:
            self.logger.log("dccpp: no response")

    def emergency_stop(self, decoder_id):
        pass

    def emergency_stop_all(self):
        self.request = "<!>"
        self.response = ""
        await self.send_request()

        if self.response.startswith("<"):
            self.logger.log(f"dccpp: {self.response}")
        else:
            self.logger.log("dccpp: no response")

    def send_request(self):
        self.logger.log(f"dccpp: send_request: request = {self.request}")
        evt = asyncio.Event()
        evc = asyncio.Event()

        timer = cbusobjects.timeout(self.timeout, evt)
        self.writer.write(self.request)
        await self.writer.drain()

        tc = asyncio.create_task(timer.one_shot())
        sc = asyncio.create_task(self.wait_for_response(evc))

        self.logger.log("dccpp: waiting for response ...")
        evw = await primitives.WaitAny((evt, evc)).wait()

        if evw is evc:
            self.logger.log("dccpp: received response")
        elif evw is evt:
            self.logger.log("dccpp: timed out")

        tc.cancel()
        sc.cancel()

    async def wait_for_response(self, evt):
        data = await self.reader.read(128)
        self.response = data.decode()
        self.logger.log(f"dccpp: got response |{self.response}|, len = {len(self.response)}")
        evt.set()
