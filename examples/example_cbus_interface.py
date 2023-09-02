# example serial Gridconnect module
# performs same functionality as CANUSB4
#

import uasyncio as asyncio
from machine import Pin

# import aiorepl
import canmessage
import cbus
import cbusconfig
import cbusdefs
import cbusmodule
import logger
import mcp2515

import gcserver
import sys


class mymodule(cbusmodule.cbusmodule):
    def __init__(self):
        super().__init__()
        self.logger = logger.logger()

    def initialise(self):

        # ***
        # *** module init
        # ***

        self.logger.log('*** Gridconnect CBUS interface ***')

        # ** change these pin numbers to suit your CAN interface hardware
        # ** also the switch and LED pins further down
        # ** you can also change the module name and ID if desired
        # ** and the number of events, EVs and NVs

        from machine import SPI
        bus = SPI(0, baudrate=10_000_000, polarity=0, phase=0, bits=8, firstbit=SPI.MSB, sck=Pin(2), mosi=Pin(3), miso=Pin(4))
        can = mcp2515.mcp2515(osc=16_000_000, cs_pin=5, interrupt_pin=1, bus=bus)
        config = cbusconfig.cbusconfig(storage_type=cbusconfig.CONFIG_TYPE_FILES, num_nvs=20, num_events=64, num_evs=4)
        self.cbus = cbus.cbus(can, config)

        self.module_id = 109
        self.module_name = bytes('PYGCSVR', 'ascii')
        self.module_params = [
            20,
            cbusdefs.MANU_MERG,
            0,
            self.module_id,
            self.cbus.config.num_events,
            self.cbus.config.num_evs,
            self.cbus.config.num_nvs,
            1,
            0,
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

        # ** change these pins if desired to suit your hardware
        self.cbus.set_leds(21, 20)
        self.cbus.set_switch(22)

        self.cbus.set_name(self.module_name)
        self.cbus.set_params(self.module_params)
        # self.cbus.set_event_handler(self.event_handler)
        self.cbus.set_received_message_handler(self.received_message_handler)
        # self.cbus.set_sent_message_handler(self.sent_message_handler)

        if self.module_params[8] & cbusdefs.PF_COE:
            self.cbus.consume_own_messages = True

        self.cbus.begin()

        # ***
        # *** end of bare minimum init

        # ***
        # *** create Gridconnect object
        # ***

        self.svr = gcserver.gcserver(self.cbus)

        # ***
        # *** module initialisation complete

        self.logger.log(f'module: name = <{self.module_name.decode()}>, mode = {self.cbus.config.mode}, can id = {self.cbus.config.canid}, node number = {self.cbus.config.node_number}')
        self.logger.log(f'free memory = {self.cbus.config.free_memory()} bytes')

        # *** end of initialise method

    # ***
    # *** received message handler
    # *** converts to a GC string and outputs to the USB serial port
    # ***

    def received_message_handler(self, msg: canmessage.canmessage) -> None:
        gcstr = self.svr.CANtoGC(msg)
        sys.stdout.write(gcstr)

    # ***
    # *** coroutines that run in parallel
    # ***

    # *** task to blink the onboard LED
    async def blink_led_coro(self) -> None:

        try:
            led = Pin('LED', Pin.OUT)
        except TypeError:
            led = Pin(25, Pin.OUT)

        while True:
            led.value(1)
            await asyncio.sleep_ms(20)
            led.value(0)
            await asyncio.sleep_ms(980)

    #
    # *** user module application task - like Arduino loop()
    # *** reads Gridconnect strings from the USB serial port and converts to CBUS messages
    #
    
    async def module_main_loop_coro(self) -> None:
    
        s = asyncio.StreamReader(sys.stdin)
        input_string = ''
        got_som = False

        while True:
            c = await s.read(1)

            if not c.upper() in 'XSNR0123456789ABCDEF;:':      # non-GC characters ignored
                continue

            if len(input_string) > 24:     # message is too long; discard it and restart parser
                input_string = ''
                got_som = False
                ccount = 0
                continue

            if c == ':':        # colon at an time resets string
                input_string = c
                got_som = True
            else:
                if got_som:         # start-of-message has been received
                    if c == ';':    # semicolon = end of message
                        input_string += c
                        got_som = False
                        msg = self.svr.GCtoCAN(input_string)
                        if msg:
                            await self.cbus.send_cbus_message_no_header_update(msg)
                    else:           # any other valid character
                        input_string += c

    # ***
    # *** module main entry point - like Arduino setup()
    # ***

    async def run(self) -> None:
        self.logger.log('run start')

        # module has been reset - do one-time config here
        if self.cbus.config.was_reset:
            self.logger.log('module was reset')
            self.cbus.config.set_reset_flag(False)

        # start coroutines
        self.tb = asyncio.create_task(self.blink_led_coro())
        self.tm = asyncio.create_task(self.module_main_loop_coro())

        # start async REPL and wait for exit
        # repl = asyncio.create_task(aiorepl.task(globals()))

        self.logger.log('module startup complete')
        await asyncio.gather(self.tm)


# create the module object and run it
mod = mymodule()
mod.initialise()
asyncio.run(mod.run())

# the asyncio scheduler is now in control
# no code after this line is executed

print('*** application has ended ***')
