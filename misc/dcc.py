# dcc.py
# control a DCC++ system / command station

import machine
import uasyncio as asyncio
from machine import UART, Pin
from micropython import const

import cbusobjects
import logger

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


class dccpp_connection:
    def __init__(self, host=None, port: int = None):
        self.logger = logger.logger()
        self.host = host
        self.port = port

    def connect(self):
        pass

    def disconnect(self):
        pass

    def write(self, data):
        pass

    async def read(self) -> bytes:
        pass


class dccpp_serial_connection(dccpp_connection):

    def __init__(self, host=None, port: int = 0, tx: int = 0, rx: int = 0):
        super().__init__(host=host, port=port)

        if host is not None and isinstance(host, machine.UART):
            self.uart = host
        else:
            self.uart = UART(port)
            self.uart.init(baudrate=115200, tx=Pin(tx), rx=Pin(rx), txbuf=32, rxbuf=128, timeout=COMMS_TIMEOUT)

        self.logger.log(self.uart)

    def write(self, data) -> None:
        self.uart.write(data)
        pass

    async def read(self) -> bytes:
        return self.uart.read(128)
        pass


class dccpp_network_connection(dccpp_connection):
    def __init__(self, host: str, port: int):
        super().__init__(host=host, port=port)

        self.sock = None
        self.writer = None
        self.reader = None

    def connect(self):
        try:
            import socket
        except ImportError:
            self.logger.log('import failed, device is not Pico W')
            return

        try:
            self.sock = socket.socket()
            addr_info = socket.getaddrinfo(self.host, self.port)
            addr = addr_info[0][-1]
            self.sock.settimeout(COMMS_TIMEOUT / 1000)
            self.sock.connect(addr)
        except OSError:
            self.logger.log('socket connect error')
            return

        self.writer = asyncio.StreamWriter(self.sock)
        self.reader = asyncio.StreamReader(self.sock)

    def write(self, data):
        self.writer.write(data)
        await self.writer.drain()

    async def read(self):
        return self.reader.read(128)

    def disconnect(self):
        self.sock.shutdown()
        self.sock.close()


class dccpp:
    def __init__(self, connection: dccpp_connection, timeout: int = 2000) -> None:
        self.logger = logger.logger()
        self.connection = connection
        self.request = ''
        self.response = ''
        self.timeout = timeout
        self.attempts = 1
        self.request = None
        self.response = None
        self.evc = asyncio.Event()
        self.evt = asyncio.Event()
        # self.timer = cbusobjects.timeout(self.timeout, self.evt)
        self.timer = cbusobjects.timeout(self.timeout)
        self.active_sessions = {}  # decoder_id: loco object

        self.connection.connect()

    async def send_request(self) -> None:
        self.logger.log(f'dccpp: send_request: request = {self.request}')
        self.response = ''

        self.connection.write(self.request)
        data = await self.connection.read()
        if data and len(data) > 0:
            self.response = data.decode()

    def acquire(self, loco: loco) -> bool:
        self.request = f'<t -1 {loco.decoder_id} 0 1>'
        await self.send_request()

        if self.response.startswith('<'):
            loco.session = 99
            loco.active = True
            self.logger.log(f'dccpp: loco {loco.decoder_id}, session = {loco.session}, active = {loco.active}')
            self.active_sessions[loco.decoder_id] = loco
        else:
            self.logger.log('dccpp: invalid response')

        return loco.active

    def dispatch(self, loco: loco) -> None:
        del self.active_sessions[loco.decoder_id]

    def set_speed(self, loco: loco, speed: int) -> None:
        self.request = f'<t -1 {loco.decoder_id} {speed} {loco.direction}>'
        await self.send_request()

        if self.response.startswith('<'):
            self.logger.log(f'dccpp: {self.response}')
            loco.speed = speed
        else:
            self.logger.log('dccpp: invalid response')

    def set_direction(self, loco: loco, direction: int) -> None:
        self.request = f'<t -1 {loco.decoder_id} {loco.speed} {direction}>'
        await self.send_request()

        if self.response.startswith('<'):
            self.logger.log(f'dccpp: {self.response}')
            loco.direction = direction
        else:
            self.logger.log('dccpp: invalid response')

    def function(self, loco: loco, function: int, polarity: int) -> None:
        self.request = f'<F {loco.decoder_id} {function} {polarity}>'
        await self.send_request()

        if self.response.startswith('<'):
            self.logger.log(f'dccpp: {self.response}')
            loco.functions[function] = polarity
        else:
            self.logger.log('dccpp: no response')

    def status(self) -> bool:
        self.request = '<s>'
        await self.send_request()

        if self.response.startswith('<'):
            self.logger.log(f'dccpp: {self.response}')
            return True
        else:
            self.logger.log('dccpp: no response')
            return False

    def track_power(self, state: int) -> None:
        self.request = f'<{state}>'
        await self.send_request()

        if self.response.startswith('<'):
            self.logger.log(f'dccpp: {self.response}')
        else:
            self.logger.log('dccpp: no response')

    def emergency_stop(self, loco: loco) -> None:
        self.set_speed(loco, 1)

    def emergency_stop_all(self) -> None:
        self.request = '<!>'
        await self.send_request()

        if self.response.startswith('<'):
            self.logger.log(f'dccpp: {self.response}')
        else:
            self.logger.log('dccpp: no response')
