# gcserver.py
# GridConnect TCP/IP server for the Pico W

import uasyncio as asyncio

import logger


class simple_server:

    #     def __new__(cls):
    #         if not hasattr(cls, 'instance'):
    #             cls.instance = super(gcserver, cls).__new__(cls)
    #         return cls.instance

    def __init__(self, host='', port=5550):
        self.logger = logger.logger()
        self.host = host
        self.port = port
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

                for ch in data_decoded:
                    if not ch.upper() in 'XSNR0123456789ABCDEF;:':
                        continue

                    if ch == ':':
                        msg = ''

                    msg += ch

                    if ch == ';':
                        self.logger.log(f'server: complete message = {msg}')
            else:
                self.logger.log(f'server: client idx = {idx} disconnected, closing stream')
                break

        for i in range(len(self.clients)):
            if self.clients[i] == writer:
                break

        writer.close()
        await writer.wait_closed()
        del self.clients[i]
