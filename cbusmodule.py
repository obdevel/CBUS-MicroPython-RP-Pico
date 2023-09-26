# module.py
# cbus application base class

import uasyncio as asyncio

import canmessage
import logger


class cbusmodule:
    def __init__(self):
        self.logger = logger.logger()
        asyncio.create_task(self.gc_coro())

    def initialise(self):
        pass

    def run(self):
        pass

    def event_handler(self, msg: canmessage.canmessage, idx: int) -> None:
        self.logger.log(f'-- event handler: idx = {idx}: {msg}')

    def received_message_handler(self, msg: canmessage.canmessage) -> None:
        self.logger.log(f'-- received message handler: {msg}')

    def sent_message_handler(self, msg: canmessage.canmessage) -> None:
        self.logger.log(f'-- sent message handler: {msg}')

    def long_message_handler(self, data: bytearray, streamid: int, status: int) -> None:
        self.logger.log('-- user long message handler:')
        self.logger.log(f'status = {status}, streamid = {streamid}, msg = <{data.decode()}>')

    @staticmethod
    async def gc_coro():
        import gc
        gc.enable()
        while True:
            gc.collect()
            gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())
            await asyncio.sleep(5)
