
# cantest1.py

import mcp2515, cbus, cbusdefs, cbusconfig, can_message

cbus = cbus.cbus(mcp2515.mcp2515(), cbusconfig.cbusconfig())
cbus.set_switch(22)
cbus.set_leds(21, 20)
cbus.begin()

print(f'mode = {cbus.config.mode}, can id = {cbus.config.canid}, node number = {cbus.config.node_number}')

