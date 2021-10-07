
## cantest1.py

import time
import mcp2515, cbus, cbusdefs, cbusconfig, canmessage, cbuslongmessage

def event_handler(msg, idx):
    print(f'event handler, index = {idx}')
    msg.print()

def frame_handler(msg):
    print('frame handler')
    msg.print()

def run():
    while 1:
        cbus.process()
        time.sleep_ms(5)

def flim():
    cbus.config.set_mode(1)
    cbus.config.set_canid(5)
    cbus.config.set_node_number(333)
    cbus.config.reboot()

MODULE_ID = 103

module_name = 'PYCO   '
module_params = [20,
                 cbusdefs.MANU_MERG,
                 0,
                 MODULE_ID,
                 cbus.config.num_events,
                 cbus.config.num_evs,
                 cbus.config.num_nvs,
                 1,
                 7,
                 0,
                 cbusdefs.PB_CAN,
                 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

cbus = cbus.cbus(mcp2515.mcp2515(), cbusconfig.cbusconfig())

cbus.set_switch(22)
cbus.set_leds(21, 20)
cbus.set_name(module_name)
cbus.set_params(module_params)
cbus.set_event_handler(event_handler)
cbus.set_frame_handler(frame_handler)

cbus.begin()

print(f'module: mode = {cbus.config.mode}, can id = {cbus.config.canid}, node number = {cbus.config.node_number}')
print(f'free memory = {cbus.config.free_memory()}')


