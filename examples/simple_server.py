# gcserver.py
# GridConnect TCP/IP server for the Pico W

import uasyncio as asyncio

import logger
from primitives import Queue


class simple_server:
    def __init__(self, q: Queue = None):
        self.logger = logger.logger()
        self.q = q
        self.ip = None
        self.server = None
        self.clients = []

    async def client_connected_cb(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info('peername')
        cip = peer[0]
        cport = peer[1]
        self.logger.log(f'server: new connection from client, ip = {cip}, port = {cport}')

        self.clients.append(writer)
        idx = len(self.clients) - 1
        self.logger.log(f'server: using client idx = {idx}')

        data = None
        msg = ''

        while True:
            try:
                data = await reader.read(64)
            except:
                self.logger.log('socket exception')
                break

            if data:
                data_decoded = data.decode()
                self.logger.log(f'server: received |{data_decoded}| len = {len(data_decoded)}')
                await self.q.put(data_decoded)
            else:
                self.logger.log(f'server: client idx = {idx} disconnected, closing stream')
                break

        for i in range(len(self.clients)):
            if self.clients[i] == writer:
                break

        writer.close()
        await writer.wait_closed()
        del self.clients[i]
