# module.py
# cbus application base class

import uasyncio as asyncio

import logger


class cbusmodule:
    def __init__(self):
        self.logger = logger.logger()
        self.lm = None
        self.history = None
        self.start_gc_server = False
        asyncio.create_task(self.mem_coro())

    def initialise(self):
        pass

    def run(self):
        pass

    def event_handler(self, msg, idx: int) -> None:
        self.logger.log(f'-- event handler: idx = {idx}: {msg}')

    def received_message_handler(self, msg) -> None:
        self.logger.log(f'-- received message handler: {msg}')

    def sent_message_handler(self, msg) -> None:
        self.logger.log(f'-- sent message handler: {msg}')

    def long_message_handler(self, message: bytearray, streamid: int, status: int) -> None:
        self.logger.log('-- user long message handler:')
        self.logger.log(f'status = {status}, streamid = {streamid}, msg = <{message.decode()}>')

    async def mem_coro(self):
        import gc
        gc.enable()
        while True:
            gc.collect()
            gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())
            await asyncio.sleep(5)
