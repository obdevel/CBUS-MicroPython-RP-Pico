# cbus_network_server.py
# a wireless CBUS interface

import json
import time

# import network
import uasyncio as asyncio
from machine import Pin

import aiorepl
import cbus
import cbusconfig
import cbusdefs
import cbusmodule
import logger
import mcp2515
import web

SSID = 'HUAWEI-B311-E39A'
PASSWORD = '33260100'

NTPSERVER = 'pool.ntp.org'
CONFIG_FILE = '/netconfig.dat'

webapp = web.App(host='0.0.0.0', port=80)

webpage = """
<html><body>
<h1>CBUS Network Server Wifi Configuration</h1>
Enter your wifi router SSID and password
</br>
<form action="/save" method="post">
      <label for="name">SSID:</label>
      <input type="text" id="ssid" name="ssid" />
      </br>
      <label for="password">Password:</label>
      <input type="password" id="password" name="password" />
      </br>
      <button type="submit">Submit</button>
</form>
</body></html>
"""


# root handler
@webapp.route('/')
async def handler(r, w):
    w.write(b'HTTP/1.0 200 OK\r\n')
    w.write(b'Content-Type: text/html; charset=utf-8\r\n')
    w.write(b'\r\n')
    # w.write(b'Hello world!')
    w.write(bytes(webpage, 'ascii'))
    await w.drain()


# POST handler
@webapp.route('/save', methods=['POST'])
async def handler(r, w):
    body = await r.read(1024)
    form = web.parse_qs(body.decode())
    ssid = form.get('ssid', 'world')
    pwd = form.get('password', 'xyz')
    print(f'ssid = {ssid}, pwd = {pwd}')
    w.write(b'HTTP/1.0 200 OK\r\n')
    w.write(b'Content-Type: text/html; charset=utf-8\r\n')
    w.write(b'\r\n')

    d = {'ssid': ssid, 'pwd': pwd}
    f = open(CONFIG_FILE, 'w')
    json.dump(d, f)
    f.close()

    w.write(b'Data saved ok - restarting')
    await w.drain()

    import machine
    machine.reset()


# ***
# *** CBUS module class
# ***

class mymodule(cbusmodule.cbusmodule):
    def __init__(self):
        super().__init__()
        self.cbus = None
        self.module_id = None
        self.module_name = None
        self.module_params = None
        self.logger = logger.logger()

        self.host = None
        self.is_picow = None
        self.gcserver = None

    def initialise(self) -> None:

        # ***
        # *** bare minimum module init
        # ***

        start_time = time.ticks_ms()

        self.cbus = cbus.cbus(mcp2515.mcp2515(), cbusconfig.cbusconfig())

        self.module_id = 110
        self.module_name = bytes('NETSVR ', 'ascii')
        self.module_params = [
            20,
            cbusdefs.MANU_MERG,
            0,
            self.module_id,
            self.cbus.config.num_events,
            self.cbus.config.num_evs,
            self.cbus.config.num_nvs,
            1,
            7,
            0,
            cbusdefs.PB_CAN,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ]

        self.cbus.set_leds(21, 20)
        self.cbus.set_switch(22)
        self.cbus.set_name(self.module_name)
        self.cbus.set_params(self.module_params)
        self.cbus.set_event_handler(self.event_handler)
        self.cbus.set_received_message_handler(self.received_message_handler)
        self.cbus.set_sent_message_handler(self.sent_message_handler)

        self.cbus.begin(max_msgs=1)

        # ***
        # *** end of bare minimum init
        # ***

        # read config file
        config_dict = None
        self.logger.log('reading config file')

        try:
            f = open(CONFIG_FILE, 'r')
            data = f.read()
            f.close()
            config_dict = json.loads(data)
        except OSError:
            self.logger.log('config file not found')
        except ValueError:
            self.logger.log('invalid config')

        if config_dict:
            self.logger.log(f'config: ssid = {config_dict["ssid"]}, password = {config_dict["pwd"]}')
            self.connect_to_wifi(config_dict['ssid'], config_dict['pwd'])
            self.run_gc_server()
        else:
            self.create_ap()

        # ***
        # *** module initialisation complete
        # ***

        self.logger.log(f'initialise complete, time = {time.ticks_diff(time.ticks_ms(), start_time)} ms')
        self.logger.log()
        self.logger.log(f'module: name = <{self.module_name}>, mode = {self.cbus.config.mode}, can id = {self.cbus.config.canid}, node number = {self.cbus.config.node_number}')
        self.logger.log(f'free memory = {self.cbus.config.free_memory()} bytes')
        self.logger.log()

        # ***
        # *** end of initialise method
        # ***

    # ***
    # *** network-related methods
    # ***

    def create_ap(self):
        try:
            import network
            self.logger.log('creating AP')
            self.wlan = network.WLAN(network.AP_IF)
            self.wlan.config(essid='CBUS', password='thereisnospoon')
            self.wlan.active(True)

            self.ip = self.wlan.ifconfig()[0]
            self.channel = self.wlan.config('channel')
            self.logger.log(f'created AP, channel = {self.channel}, address = {self.ip}')
            self.host = self.ip
        except ImportError:
            self.logger.log('import failed; device is not Pico W')
            self.is_picow = False

    def connect_to_wifi(self, ssid, pwd) -> None:
        try:
            import network
            self.logger.log('device is Pico W')
            self.wlan = network.WLAN(network.STA_IF)
            self.wlan.active(True)
            self.wlan.connect(ssid, pwd)
            self.logger.log('waiting for wifi...')
            tt = time.ticks_ms()

            while not self.wlan.isconnected() and time.ticks_diff(time.ticks_ms(), tt) < 5000:
                time.sleep_ms(500)

            if self.wlan.isconnected():
                self.ip = self.wlan.ifconfig()[0]
                self.channel = self.wlan.config('channel')
                self.logger.log(f'connected to wifi, channel = {self.channel}, address = {self.ip}')
                self.host = self.ip
            else:
                self.logger.log('unable to connect to wifi')

        except ImportError:
            self.logger.log('import failed; device is not Pico W')
            self.is_picow = False

    def run_gc_server(self) -> None:
        try:
            import gcserver
            self.gcserver = gcserver.gcserver(self.cbus, self.host, 5550)
            asyncio.create_task(
                asyncio.start_server(self.gcserver.client_connected_cb, self.gcserver.host, self.gcserver.port))
            self.logger.log('Gridconnect server is running')
        except ImportError:
            self.logger.log('import failed; device is not Pico W')

    # ***
    # *** coroutines that run in parallel
    # ***

    async def blink_led_coro(self) -> None:
        self.logger.log('blink_led_coro: start')

        try:
            led = Pin('LED', Pin.OUT)
        except TypeError:
            led = Pin(25, Pin.OUT)

        while True:
            led.value(1)
            await asyncio.sleep_ms(20)
            led.value(0)
            await asyncio.sleep_ms(980)

    # ***
    # *** module main entry point
    # ***

    async def run(self) -> None:

        _ = asyncio.create_task(self.blink_led_coro())
        _ = asyncio.create_task(webapp.serve())
        self.logger.log('asyncio is now running the module main loop and co-routines')

        # start async REPL and wait for exit
        repl = asyncio.create_task(aiorepl.task(globals()))
        await asyncio.gather(repl)

    # ***
    # *** end of module class
    # ***


# create an instance of our application class
mod = mymodule()
mod.initialise()

# *** start the scheduler and run the app class main method
asyncio.run(mod.run())

# *** the asyncio scheduler is now in control
# *** no code after this line is executed
