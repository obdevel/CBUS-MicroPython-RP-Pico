
# cantest1.py

import time
t1 = time.ticks_ms()

import mcp2515, cbus, cbusdefs, cbusconfig, canmessage, cbuslongmessage

cbus = cbus.cbus(mcp2515.mcp2515(), cbusconfig.cbusconfig())
cbus.set_switch(22)
cbus.set_leds(21, 20)
cbus.begin()

#lmsg = cbuslongmessage.cbuslongmessage(cbus)

print(f't1 = {t1}')
print(f'startup time = {time.ticks_ms() - t1} ms')

print(f'module: mode = {cbus.config.mode}, can id = {cbus.config.canid}, node number = {cbus.config.node_number}')
print(f'free memory = {cbus.config.free_memory()}')

