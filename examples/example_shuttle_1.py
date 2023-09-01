# example to show simple end-ti-end shuttle with and intermediate stop
# based on the standard application template
#

import uasyncio as asyncio
from machine import Pin, UART

import aiorepl
import canmessage
import cbus
import cbusconfig
import cbusdefs
import cbusmodule
import cbusobjects
import logger
import mcp2515

from primitives import WaitAny, WaitAll


class mymodule(cbusmodule.cbusmodule):
    def __init__(self):
        super().__init__()
        self.logger = logger.logger()

    def initialise(self):

        # ***
        # *** bare minimum module init
        # ***

        # ** change these pin numbers to suit your CAN interface hardware
        # ** also the switch and LED pins further down
        # ** you can also change the module name and ID if desired
        # ** and the number of events, EVs and NVs

        from machine import SPI
        bus = SPI(0, baudrate=10_000_000, polarity=0, phase=0, bits=8, firstbit=SPI.MSB, sck=Pin(2), mosi=Pin(3), miso=Pin(4))
        can = mcp2515.mcp2515(osc=16_000_000, cs_pin=5, interrupt_pin=1, bus=bus)
        config = cbusconfig.cbusconfig(storage_type=cbusconfig.CONFIG_TYPE_FILES, num_nvs=20, num_events=64, num_evs=4)
        self.cbus = cbus.cbus(can, config)

        self.module_id = 104
        self.module_name = bytes('PYSHTL1', 'ascii')
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

        # ** change these pins if desired to suit your hardware
        self.cbus.set_leds(21, 20)
        self.cbus.set_switch(22)

        self.cbus.set_name(self.module_name)
        self.cbus.set_params(self.module_params)
        self.cbus.set_event_handler(self.event_handler)
        self.cbus.set_received_message_handler(self.received_message_handler)
        self.cbus.set_sent_message_handler(self.sent_message_handler)

        self.cbus.consume_own_messages = True
        self.cbus.consume_query_type = canmessage.QUERY_ALL

        self.cbus.begin()

        # ***
        # *** end of bare minimum init

        # ***
        # *** module initialisation complete

        self.logger.log(f'module: name = <{self.module_name.decode()}>, mode = {self.cbus.config.mode}, can id = {self.cbus.config.canid}, node number = {self.cbus.config.node_number}')
        self.logger.log(f'free memory = {self.cbus.config.free_memory()} bytes')

        # *** end of initialise method

    # ***
    # *** coroutines that run in parallel
    # ***

    # *** task to blink the onboard LED
    async def blink_led_coro(self) -> None:
        self.logger.log('blink_led_coro start')
        try:
            led = Pin('LED', Pin.OUT)
        except TypeError:
            led = Pin(25, Pin.OUT)

        while True:
            led.value(1)
            await asyncio.sleep_ms(20)
            led.value(0)
            await asyncio.sleep_ms(980)

    # *** user module application task - like Arduino loop()
    async def module_main_loop_coro(self) -> None:
        self.logger.log('main loop coroutine start')

        while True:
            await asyncio.sleep_ms(25)

    # ***
    # *** automation example
    # ***

    async def shuttle(self, decoder_id: int, speed: int=10, delay: int=10000) -> None:
        self.logger.log('** shuttle example start')

        # use type 1 for DCC++ or 0 for MERG DCC
        dcc_type = 0

        # create throttle connection
        self.logger.log('** creating throttle')
        if dcc_type == 1:
            self.logger.log('** using DCC++')
            import dcc
            self.port = UART(0, baudrate=115200, tx=Pin(12), rx=Pin(13))
            self.conn = dcc.dccpp_serial_connection(self.port)
            self.throttle = dcc.dccpp(self.conn)
        else:
            self.logger.log('** using MERG DCC')
            import mergdcc
            self.throttle = mergdcc.merg_cab(self.cbus)

        # acquire loco and initialise
        self.logger.log('** acquiring loco')
        self.loco = dcc.loco(decoder_id)
        await self.throttle.acquire(self.loco)
        await self.throttle.track_power(1)
        await self.throttle.status()
        await self.throttle.set_speed(self.loco, 0)

        # create sensor objects to represent the three IR detectors
        self.sensor1 = cbusobjects.binary_sensor('start_sensor', self.cbus, ((0, 66, 1), (1, 66, 1)), (cbusdefs.OPC_AREQ, 0, 66, 0, 1))
        self.sensor2 = cbusobjects.binary_sensor('midpoint_sensor', self.cbus, ((0, 66, 2), (1, 66, 2)), (cbusdefs.OPC_AREQ, 0, 66, 0, 2))
        self.sensor3 = cbusobjects.binary_sensor('end_sensor', self.cbus, ((0, 66, 3), (1, 66, 3)), (cbusdefs.OPC_AREQ, 0, 66, 0, 3))

        try:
            self.logger.log('** waiting for loco to be positioned')

            while self.sensor1.state != cbusobjects.OBJECT_STATE_ON:
                await self.sensor1.wait()

            self.logger.log('** loco detected at start sensor')
            num_loops = 1

            while True:

                self.logger.log(f'** start of sequence: {num_loops}')

                self.logger.log('** wait')
                await asyncio.sleep_ms(delay)                                                 # wait n secs
                self.logger.log('** forward')
                await self.throttle.set_direction(self.loco, dcc.DIRECTION_FORWARD)                      # forward direction
                self.logger.log('** depart')
                await self.throttle.set_speed(self.loco, speed)                                     # move off

                self.logger.log('** waiting for midpoint sensor')
                while self.sensor2.state != cbusobjects.OBJECT_STATE_ON:
                    state = await self.sensor2.wait()                                         # wait for mid point sensor
                    self.logger.log(f'{self.sensor2.name} = {state}')

                self.logger.log('** midpoint sensor reached')
                self.logger.log('** stop')
                await self.throttle.set_speed(self.loco, 0)                                              # stop
                self.logger.log('** wait')
                await asyncio.sleep_ms(delay)                                                 # wait n secs
                self.logger.log('** depart')
                await self.throttle.set_speed(self.loco, speed)                                          # move off

                self.logger.log('** waiting for end sensor')
                while self.sensor3.state != cbusobjects.OBJECT_STATE_ON:
                    state = await self.sensor3.wait()                                         # wait for end point sensor
                    self.logger.log(f'{self.sensor3.name} = {state}')

                self.logger.log('** end sensor reached')
                self.logger.log('** stop')
                await self.throttle.set_speed(self.loco, 0)                                              # stop
                self.logger.log('** wait')
                await asyncio.sleep_ms(delay)                                                 # wait n secs
                self.logger.log('** reverse')
                await self.throttle.set_direction(self.loco, dcc.DIRECTION_REVERSE)                      # reverse direction
                self.logger.log('** depart')
                await self.throttle.set_speed(self.loco, speed)                                          # move off

                self.logger.log('** waiting for midpoint sensor')
                while self.sensor2.state != cbusobjects.OBJECT_STATE_ON:
                    state = await self.sensor2.wait()                                         # wait for midpoint sensor
                    self.logger.log(f'{self.sensor2.name} = {state}')

                self.logger.log('** midpoint sensor reached')
                self.logger.log('** stop')
                self.throttle.set_speed(self.loco, 0)                                              # stop
                self.logger.log('** wait')
                await asyncio.sleep_ms(delay)                                                 # wait n secs
                self.logger.log('** depart')
                await self.throttle.set_speed(self.loco, speed)                                          # move off

                self.logger.log('** waiting for start sensor')
                while self.sensor1.state != cbusobjects.OBJECT_STATE_ON:
                    state = await self.sensor1.wait()                                         # wait for start point sensor
                    self.logger.log(f'{self.sensor1.name} = {state}')

                self.logger.log('** start sensor reached')
                await self.throttle.set_speed(self.loco, 0)                                              # stop

                num_loops += 1

        except asyncio.CancelledError as e:
            self.logger.log(f'** task cancelled, exception = {e.__qualname__}')
            await self.throttle.track_power(0)

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
        self.ts = asyncio.create_task(self.shuttle(27, 10, 10000, 1))

        # start async REPL and wait for exit
        repl = asyncio.create_task(aiorepl.task(globals()))

        self.logger.log('module startup complete')
        await asyncio.gather(repl)


# create the module object and run it
mod = mymodule()
mod.initialise()
asyncio.run(mod.run())

# the asyncio scheduler is now in control
# no code after this line is executed

print('*** application has ended ***')
