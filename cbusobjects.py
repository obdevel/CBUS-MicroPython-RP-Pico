# cbussensor.py
# a CBUS sensor implementation

import cbusdefs
import canmessage
import cbuspubsub
import logger
import uasyncio as asyncio

SENSOR_STATE_UNKNOWN = -1
SENSOR_STATE_OFF = 0
SENSOR_STATE_ON = 1

sensor_states = {
    SENSOR_STATE_UNKNOWN: "Unknown",
    SENSOR_STATE_OFF: "Off",
    SENSOR_STATE_ON: "On"
}

sensors = {}

TURNOUT_STATE_UNKNOWN = -1
TURNOUT_STATE_CLOSED = 0
TURNOUT_STATE_THROWN = 1

turnout_states = {
    TURNOUT_STATE_UNKNOWN: "Unknown",
    TURNOUT_STATE_CLOSED: "Closed",
    TURNOUT_STATE_THROWN: "Thrown"
}

turnouts = {}


class sensor:
    def __init__(self, name, cbus, query, event=None, default=SENSOR_STATE_UNKNOWN):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.query = query
        self.event = event
        self.sub = cbuspubsub.subscription(self.cbus, query, canmessage.QUERY_TUPLE)
        sensors[name] = self

        if isinstance(self.event, asyncio.Event):
            self.event.clear()

    def __del__(self):
        self.sub.unsubscribe(self.req)
        del sensor[self.name]

    def run(self):
        pass


class binarysensor(sensor):
    def __init__(self, name, cbus, query, event=None, default=SENSOR_STATE_UNKNOWN):
        super().__init__(name, cbus, query, event, default)
        self.state = default
        asyncio.create_task(self.run())

    async def run(self):
        while True:
            msg = await self.sub.wait()
            if msg.len > 0:
                new_state = SENSOR_STATE_OFF if msg.data[0] & 1 else SENSOR_STATE_ON
                if self.state != new_state:
                    self.state = new_state
                    if isinstance(self.event, asyncio.Event):
                        self.event.set()


class valuesensor(sensor):
    def __init__(self, name, cbus, query, event=None, default=-1):
        super().__init__(name, cbus, query, event, default)
        asyncio.create_task(self.run())
        self.value = default

    async def run(self):
        while True:
            msg = await self.sub.wait()
            if msg.len > 0:
                self.value = 99
                if isinstance(self.event, asyncio.Event):
                    self.event.set()


class turnout:
    def __init__(self, name, cbus, turnout_events, initial_state=TURNOUT_STATE_CLOSED, create_sensor=False, sensor_events=None, init=False):
        self.logger = logger.logger()
        turnouts[name] = self
        self.name = name
        self.cbus = cbus
        self.turnout_events = turnout_events
        self.state = initial_state
        self.create_sensor = create_sensor
        self.sensor_events = sensor_events
        self.sensor = None
        self.event = None
        self.task = None

        if init:
            if initial_state == TURNOUT_STATE_CLOSED:
                self.close()
            else:
                self.throw()

        if create_sensor:
            self.event = asyncio.Event()
            self.sensor = binarysensor(name + ":sensor", self.cbus, self.sensor_events, self.event)
            self.task = asyncio.create_task(self.run())

    def __del__(self):
        if self.task is not None:
            self.task.cancel()
            del self.sensor
        del turnouts[self.name]

    def getstate(self):
        return self.state

    def is_closed(self):
        return self.state == TURNOUT_STATE_CLOSED

    def is_thrown(self):
        return not self.is_closed()

    def throw(self):
        opc = self.turnout_events[0][0]
        nn = self.turnout_events[0][1]
        en = self.turnout_events[0][2]
        msg = canmessage.cbusevent(self.cbus, True, nn, en, canmessage.EVENT_ON)
        msg.send_on()
        self.state = TURNOUT_STATE_UNKNOWN if self.create_sensor else TURNOUT_STATE_THROWN

    def close(self):
        opc = self.turnout_events[1][0]
        nn = self.turnout_events[1][1]
        en = self.turnout_events[1][2]
        msg = canmessage.cbusevent(self.cbus, True, nn, en, canmessage.EVENT_ON)
        msg.send_off()
        self.state = TURNOUT_STATE_UNKNOWN if self.create_sensor else TURNOUT_STATE_CLOSED

    async def run(self):
        while True:
            await self.event.wait()
            self.event.clear()
            self.state = self.sensor.state
            self.logger.log(f"turnout sensor {self.sensor.name} trigged, state = {self.sensor.state}")


class turnoutgroup:
    def __init__(self, turnouts):
        self.logger = logger.logger()
        self.turnouts = turnouts

    def set(self, state):
        for t in self.turnouts:
            pass


class signal:
    def __init__(self):
        self.logger = logger.logger()


class semaphore_signal(signal):
    def __init__(self):
        super().__init__()


class colour_signal_two(signal):
    def __init__(self):
        super().__init__()


class colour_signal_three(signal):
    def __init__(self):
        super().__init__()


class colour_signal_four(signal):
    def __init__(self):
        super().__init__()

