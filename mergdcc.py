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


class loco:
    def __init__(self, decoder_id) -> None:
        self.decoder_id = decoder_id
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

        self.evt = asyncio.Event()
        self.timer = cbusobjects.timeout(self.timeout, self.evt)
        self.sub = None

        self.ka = asyncio.create_task(self.keepalive())
        self.et = asyncio.create_task(self.err_task())

    def dispose(self, stop=False):
        self.ka.cancel()
        self.et.cancel()
        for loco in self.active_sessions.values():
            if stop:
                self.emergency_stop(loco)
            else:
                self.dispatch(loco)
            del loco
            del self.active_sessions

    def acquire(self, loco: loco) -> bool:
        self.logger.log(f'merg_cab: requesting session for loco {loco.decoder_id} ...')

        if loco.session != -1:
            self.logger.log(f'merg_cab: loco already acquired')
            return True

        opcodes = (cbusdefs.OPC_PLOC, cbusdefs.OPC_ERR)
        self.sub = cbuspubsub.subscription('cab:sub', self.cbus, canmessage.QUERY_OPCODES, opcodes)

        msg = canmessage.canmessage(0, 3, (cbusdefs.OPC_RLOC, loco.decoder_id >> 7, loco.decoder_id & 0x7f))
        self.cbus.send_cbus_message(msg)

        ok = False
        t1 = time.ticks_ms()

        while time.ticks_diff(time.ticks_ms(), t1) < self.timeout:
            resp = await self.await_reply()

            if resp:
                if resp.data[0] == cbusdefs.OPC_ERR:
                    self.logger.log(f'merg_cab: acquire returns error = {resp.data[3]}')
                    break
                elif resp.data[0] == cbusdefs.OPC_PLOC and (resp.data[2] << 8) + resp.data[3] == loco.decoder_id:
                    loco.active = True
                    loco.session = resp.data[1]
                    loco.speed = resp.data[4] & 0x7f
                    loco.dir = resp.data[4] >> 7
                    loco.functions[0] = resp.data[5]
                    loco.functions[1] = resp.data[6]
                    loco.functions[2] = resp.data[7]
                    self.active_sessions[loco.decoder_id] = loco
                    self.logger.log(f'merg_cab: loco {loco.decoder_id} acquired successfully, session = {loco.session}')
                    ok = True
                    break
                else:
                    id = (resp.data[2] << 8) + resp.data[3]
                    self.logger.log(f'merg_cab: response for another loco = {id}')
            else:
                self.logger.log('merg_cab: request failed')

        self.sub.unsubscribe()
        return ok

    async def await_reply(self) -> canmessage.canmessage:
        resp = None
        _ = asyncio.create_task(self.timer.one_shot())

        self.logger.log('merg_cab: awaiting response ...')
        evw = await WaitAny((self.evt, self.sub.evt)).wait()

        if evw is self.sub.evt:
            self.logger.log('merg_cab: received response')
            resp = await self.sub.queue.get()
            self.sub.evt.clear()
        elif evw is self.evt:
            self.logger.log('merg_cab: timed out')

        self.sub.unsubscribe()
        return resp

    def dispatch(self, loco: loco) -> None:
        msg = canmessage.canmessage(0, 2, (cbusdefs.OPC_KLOC, loco.session))
        self.cbus.send_cbus_message(msg)
        loco.session = -1
        try:
            del self.active_sessions[loco.decoder_id]
        except KeyError:
            pass
        self.logger.log(f'dispatch: id = {loco.decoder_id}')

    def set_speed_and_direction(self, loco: loco) -> None:
        msg = canmessage.canmessage(0, 3, (cbusdefs.OPC_DSPD, loco.session, loco.speed + (loco.direction * 128)))
        self.cbus.send_cbus_message(msg)
        self.logger.log(
            f'set_speed_and_direction: id = {loco.decoder_id}, speed = {loco.speed}, direction = {loco.direction}')

    def set_speed(self, loco: loco, speed: int) -> None:
        loco.speed = speed
        self.set_speed_and_direction(loco)
        self.logger.log(f'set_speed, id = {loco.decoder_id}, speed = {loco.speed}')

    def set_direction(self, loco: loco, direction: int) -> None:
        loco.direction = direction
        self.set_speed_and_direction(loco)
        self.logger.log(f'set_direction, id = {loco.decoder_id}, direction = {loco.direction}')

    def function(self, loco: loco, function: int, polarity: int) -> None:
        opc = cbusdefs.OPC_DFNON if polarity else cbusdefs.OPC_DFNOF
        msg = canmessage.canmessage(0, 3, (opc, loco.session, function))
        self.cbus.send_cbus_message(msg)
        self.logger.log(f'set function, id = {loco.decoder_id}, function {function} = {polarity}')

    def emergency_stop(self, loco: loco) -> None:
        self.set_speed(loco, 1)
        self.logger.log('e stop')

    def emergency_stop_all(self) -> None:
        msg = canmessage.canmessage(0, 1, (cbusdefs.OPC_RESTP,))
        self.cbus.send_cbus_message(msg)
        self.logger.log('e stop all')

    async def keepalive(self) -> None:
        while True:
            await asyncio.sleep(4)
            for loco in self.active_sessions.values():
                msg = canmessage.canmessage(0, 2, (cbusdefs.OPC_DKEEP, loco.session))
                self.cbus.send_cbus_message(msg)

    async def err_task(self) -> None:
        sub = cbuspubsub.subscription('merg_cab:err_task', self.cbus, canmessage.QUERY_TUPLES, (cbusdefs.OPC_ERR,))
        while True:
            msg = await sub.wait()
            loco_id = msg.data[1] << 8 + msg.data[2]
            self.logger.log(f'err_task: got error message, loco = {loco_id}, error = {msg.data[3]}')
