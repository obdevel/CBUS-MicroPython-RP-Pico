## module.py
# example CBUS module main program

import micropython, time
import mcp2515, cbus, cbusdefs, cbusconfig, canmessage, cbuslongmessage


def f1(a, b, c):
    print(f"f1: {a}, {b}, {c}")


def f2(a, b, c):
    print(f"f2: {a}, {b}, {c}")


def f3(a, b, c):
    print(f"f3: {a}, {b}, {c}")


ftab = {1: (f1, 1, 2, 3), 2: (f2, 2, 4, 6), 5: (f3, 5, 10, 15)}


def run_cbus_loop():
    while True:
        c = cbus.process()


def event_handler(msg, idx):
    print(f"user event handler: index = {idx}")
    print(msg)
    ev1 = cbus.config.read_event_ev(idx, 1)
    print(f"ev1 = {ev1}")
    fn = ftab.get(ev1)
    print(f"f = {fn}")
    fn[0](fn[1], fn[2], fn[3])
    print()


def frame_handler(msg):
    print("user frame handler:")
    print(msg)


def long_message_handler(message, streamid, status):
    print(f"user long message handler: status = {status}")
    print()


def flim():
    cbus.config.set_mode(1)
    cbus.config.set_canid(5)
    cbus.config.set_node_number(333)
    cbus.config.reboot()


# execution starts here
#

start_time = time.ticks_ms()
print("** module starting")

micropython.alloc_emergency_exception_buf(500)

cbus = cbus.cbus(
    mcp2515.mcp2515(), cbusconfig.cbusconfig(storage_type=cbusconfig.CONFIG_TYPE_FILES)
)

MODULE_ID = 103
module_name = "PYCO   "
module_params = [
    20,
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

cbus.set_switch(22)
cbus.set_leds(21, 20)
cbus.set_name(module_name)
cbus.set_params(module_params)
cbus.set_event_handler(event_handler)
cbus.set_frame_handler(frame_handler)

cbus.begin()

msg1 = canmessage.canmessage(99, 5, [0x90, 0, 22, 0, 25])
msg2 = canmessage.canmessage(cbus.config.canid, 5, [0xE9, 1, 0, 0, 24, 0, 0, 0])
msg3 = canmessage.canmessage(4, 5, [0x91, 0, 22, 0, 23, 0, 0, 0])
msg4 = canmessage.canmessage(555, 0, [], True, False)

lm = cbuslongmessage.cbuslongmessage(cbus, 512, 4)
lm.subscribe([1, 2, 3, 4, 5], long_message_handler)

print()
print(f"** startup time = {time.ticks_ms() - start_time} ms")
print(
    f"module: name = |{module_name}|, mode = {cbus.config.mode}, can id = {cbus.config.canid}, node number = {cbus.config.node_number}"
)
print(f"free memory = {cbus.config.free_memory()} bytes")
print()

# if __name__ == '__main__':
#    run_cbus_loop()
