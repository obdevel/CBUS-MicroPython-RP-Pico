
## module_asyncio.py

# example CBUS module main class using asyncio library

import micropython, machine, time
import uasyncio as asyncio
import cbusmodule, cbus, mcp2515, cbusdefs, cbusconfig, canmessage, cbuslongmessage

class mymodule(cbusmodule.cbusmodule):

    def __init__(self):
        print('** module constructor')
        super().__init__()

        self.received_message_counter = 0
        self.led = machine.Pin(25, machine.Pin.OUT)

    def f1(self, a, b, c):
        print(f'f1: {a}, {b}, {c}')

    def f2(self, a, b, c):
        print(f'f2: {a}, {b}, {c}')

    def f3(self, a, b, c):
        print(f'f3: {a}, {b}, {c}')

    def event_handler(self, msg, idx):
        self.received_message_counter += 1
        print(f'-- user event handler: index = {idx}, count = {self.received_message_counter}')
        print(msg)
        ev1 = self.cbus.config.read_event_ev(idx, 1)
        print(f'ev1 = {ev1}')
        fn = self.function_tab.get(ev1)
        # print(f'f = {fn}')
        fn[0](fn[1], fn[2], fn[3])
        print()

    def initialise(self):
        print('** module initialise')

        start_time = time.ticks_ms()
        micropython.alloc_emergency_exception_buf(500)

        self.cbus = cbus.cbus(mcp2515.mcp2515(), cbusconfig.cbusconfig(storage_type=cbusconfig.CONFIG_TYPE_FILES))

        self.module_id = 103
        self.module_name = 'PYCO   '
        self.module_params = [20,
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
                         0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

        self.cbus.set_switch(22)
        self.cbus.set_leds(21, 20)
        self.cbus.set_name(self.module_name)
        self.cbus.set_params(self.module_params)
        self.cbus.set_event_handler(self.event_handler)
        self.cbus.set_frame_handler(self.frame_handler)

        self.lm = cbuslongmessage.cbuslongmessage(self.cbus, 512, 4)
        self.lm_ids = [1, 2, 3, 4, 5]
        self.lm.subscribe(self.lm_ids, self.long_message_handler)

        self.cbus.begin()

        self.msg1 = canmessage.canmessage(99, 5, [0x90, 0, 22, 0, 25])
        self.msg2 = canmessage.canmessage(99, 5, [0xe9, 1, 0, 0, 24, 0, 0, 0])
        self.msg3 = canmessage.canmessage(4, 5, [0x91, 0, 22, 0, 23, 0, 0, 0])
        self.msg4 = canmessage.canmessage(555, 0, [], True, False)
        self.msgx = canmessage.canmessage(444, 33, [], False, True)

        self.function_tab = {
            1: (self.f1, 1, 2, 3),
            2: (self.f2, 2, 4, 6),
            5: (self.f3, 5, 10, 15)
        }

        print()
        print(f'** initialise complete, time = {time.ticks_ms() - start_time} ms')
        print()
        print(f'module: name = <{self.module_name}>, mode = {self.cbus.config.mode}, can id = {self.cbus.config.canid}, node number = {self.cbus.config.node_number}')
        print(f'free memory = {self.cbus.config.free_memory()} bytes')
        print()

    async def cbus_coro(self):
        print('** cbus_coro start')

        while True:
            c = self.cbus.process()
            await asyncio.sleep(0)

    async def long_message_coro(self):
        print('** long_message_coro start')

        while True:
            self.lm.process()
            await asyncio.sleep_ms(0)

    async def blink_led_coro(self):
        print('** blink_led_coro start')

        while True:
            self.led.value(1)
            await asyncio.sleep_ms(20)
            self.led.value(0)
            await asyncio.sleep_ms(980)

    async def run(self):
        print('*** asyncio scheduler is now running the module main loop and co-routines')

        asyncio.create_task(self.cbus_coro())
        asyncio.create_task(self.long_message_coro())
        asyncio.create_task(self.blink_led_coro())

        while True:
            await asyncio.sleep(5)
            self.cbus.can.rx_queue.enqueue(self.msg3)


mod = mymodule()
mod.initialise()
asyncio.run(mod.run())

