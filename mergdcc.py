# mergdcc.py
# control MERG DCC system

import time

import uasyncio as asyncio
from micropython import const

import canmessage
import cbusdefs
import cbusobjects
import cbuspubsub
import logger
from primitives import WaitAny

FUNCTION_OFF = const(0)
FUNCTION_ON = const(1)

DIRECTION_REVERSE = const(0)
DIRECTION_FORWARD = const(1)

POWER_OFF = const(0)
POWER_ON = const(1)
COMMS_TIMEOUT = const(500)

LONG_ADDRESS = const(True)
SHORT_ADDRESS = const(False)


class loco:
    def __init__(self, decoder_id: int, long_address: bool = LONG_ADDRESS) -> None:
        if decoder_id > 127 and not long_address:
            raise ValueError('loco addresses >127 must be long')

        self.decoder_id = decoder_id
        self.long_address = long_address
        self.address_flag = '(L)' if self.long_address else '(S)'
        self.speed = 0
        self.direction = DIRECTION_FORWARD
        self.functions = [0] * 30
        self.active = False
        self.session = -1


class merg_cab:
    def __init__(self, cbus, timeout: int = 2000) -> None:
        self.logger = logger.logger()
        self.cbus = cbus
        self.timeout = timeout
        self.query = None
        self.sub = None
        self.msg = None
        self.active_sessions = {}  # decoder_id: loco object

        self.timeout_evt = asyncio.Event()
        self.timer = cbusobjects.timeout(self.timeout)
        self.sub = None

        self.ka = asyncio.create_task(self.keepalive())
        self.et = asyncio.create_task(self.err_task())

    async def dispose(self, stop=False):
        self.ka.cancel()
        self.et.cancel()
        for loco in self.active_sessions.values():
            if stop:
                await self.emergency_stop(loco)
            else:
                await self.dispatch(loco)
            del loco
            del self.active_sessions

    async def acquire(self, loco: loco) -> bool:
        if loco.session != -1:
            self.logger.log(f'merg_cab: loco already acquired')
            return True

        # For long addresses, bits 6 and 7 of the upper byte should be set by the CAB.
        nmra_id_upper = (loco.decoder_id >> 8)
        if loco.long_address:
            nmra_id_upper |= 0b11000000
        nmra_id_lower = loco.decoder_id & 0xff
        nmra_id = (nmra_id_upper << 8) + nmra_id_lower

        self.logger.log(f'merg_cab: requesting session for loco {loco.decoder_id}{loco.address_flag} ...')

        opcodes = (cbusdefs.OPC_PLOC, cbusdefs.OPC_ERR)
        self.sub = cbuspubsub.subscription('cab:sub', self.cbus, canmessage.QUERY_OPCODES, opcodes)

        # self.logger.log(f'acquire: id = {loco.decoder_id}{loco.address_flag}, upper = {nmra_id_upper}, lower = {nmra_id_lower}')
        msg = canmessage.canmessage(0, 3, (cbusdefs.OPC_RLOC, nmra_id_upper, nmra_id_lower))
        await self.cbus.send_cbus_message(msg)

        acquired_loco_ok = False
        start_time = time.ticks_ms()

        while time.ticks_diff(time.ticks_ms(), start_time) < self.timeout:
            response = await self.await_reply()

            if response:
                response_decoder_id = (response.data[2] << 8) + response.data[3]
                self.logger.log(f'acquire: processing response, id = {response_decoder_id}')

                if response.data[0] == cbusdefs.OPC_ERR:
                    self.logger.log(f'merg_cab: acquire returns error = {response.data[3]}')
                    break
                elif response.data[0] == cbusdefs.OPC_PLOC and (response_decoder_id == loco.decoder_id or response_decoder_id == nmra_id):
                    loco.active = True
                    loco.session = response.data[1]
                    loco.speed = response.data[4] & 0x7f
                    loco.dir = response.data[4] >> 7
                    loco.functions[0] = response.data[5]
                    loco.functions[1] = response.data[6]
                    loco.functions[2] = response.data[7]
                    self.active_sessions[loco.decoder_id] = loco
                    self.logger.log(f'merg_cab: loco {loco.decoder_id}{loco.address_flag} acquired successfully, session = {loco.session}')
                    acquired_loco_ok = True
                    break
                else:
                    self.logger.log(f'merg_cab: response for another loco, wanted = {loco.decoder_id}{loco.address_flag}, got = {response_decoder_id}')
            else:
                self.logger.log('merg_cab: request timed out')

        self.sub.unsubscribe()
        return acquired_loco_ok

    async def await_reply(self) -> canmessage.canmessage:
        response = None
        _ = asyncio.create_task(self.timer.one_shot())

        self.logger.log('await_reply: awaiting response ...')
        evw = await WaitAny((self.timeout_evt, self.sub.evt)).wait()

        if evw is self.sub.evt:
            self.logger.log('await_reply: received response')
            response = await self.sub.queue.get()
            # self.sub.evt.clear()
        elif evw is self.timeout_evt:
            self.logger.log('await_reply: timed out')

        return response

    async def dispatch(self, loco: loco) -> None:
        msg = canmessage.canmessage(0, 2, (cbusdefs.OPC_KLOC, loco.session))
        await self.cbus.send_cbus_message(msg)
        loco.session = -1
        try:
            del self.active_sessions[loco.decoder_id]
        except KeyError:
            pass
        finally:
            self.logger.log(f'dispatch: id = {loco.decoder_id}{loco.address_flag}')

    async def set_speed_and_direction(self, loco: loco) -> None:
        msg = canmessage.canmessage(0, 3, (cbusdefs.OPC_DSPD, loco.session, loco.speed + (loco.direction << 7)))
        await self.cbus.send_cbus_message(msg)
        self.logger.log(
            f'set_speed_and_direction: id = {loco.decoder_id}{loco.address_flag}, speed = {loco.speed}, direction = {loco.direction}')

    async def set_speed(self, loco: loco, speed: int) -> None:
        loco.speed = speed
        await self.set_speed_and_direction(loco)
        self.logger.log(f'set_speed, id = {loco.decoder_id}{loco.address_flag}, speed = {loco.speed}')

    async def set_direction(self, loco: loco, direction: int) -> None:
        loco.direction = direction
        await self.set_speed_and_direction(loco)
        self.logger.log(f'set_direction, id = {loco.decoder_id}{loco.address_flag}, direction = {loco.direction}')

    async def function(self, loco: loco, function: int, polarity: int) -> None:
        opc = cbusdefs.OPC_DFNON if polarity else cbusdefs.OPC_DFNOF
        msg = canmessage.canmessage(0, 3, (opc, loco.session, function))
        await self.cbus.send_cbus_message(msg)
        self.logger.log(f'set function, id = {loco.decoder_id}{loco.address_flag}, function {function} = {polarity}')

    async def emergency_stop(self, loco: loco) -> None:
        await self.set_speed(loco, 1)
        self.logger.log(f'e-stop, id = {loco.decoder_id}{loco.address_flag}')

    async def emergency_stop_all(self) -> None:
        msg = canmessage.canmessage(0, 1, (cbusdefs.OPC_RESTP,))
        await self.cbus.send_cbus_message(msg)
        self.logger.log('e-stop all')

    async def status(self) -> None:
        pass
    
    async def track_power(self, on: int) -> None:
        pass

    async def keepalive(self) -> None:
        try:
            while True:
                await asyncio.sleep(4)
                for loco in self.active_sessions.values():
                    msg = canmessage.canmessage(0, 2, (cbusdefs.OPC_DKEEP, loco.session))
                    await self.cbus.send_cbus_message(msg)
        except asyncio.CancelledError:
            self.logger.log('keepalive coro cancelled')

    async def err_task(self) -> None:
        sub = cbuspubsub.subscription('merg_cab:err_task', self.cbus, canmessage.QUERY_OPCODES, (cbusdefs.OPC_ERR,))
        try:
            while True:
                msg = await sub.wait()
                loco_id = (msg.data[1] << 8) + msg.data[2]
                self.logger.log(f'err_task: got error message, loco = {loco_id}, error = {msg.data[3]}')
        except asyncio.CancelledError:
            self.logger.log('err_task coro cancelled')
            sub.unsubscribe()
