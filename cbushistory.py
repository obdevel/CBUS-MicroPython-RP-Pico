# CBUS event history

import time
import logger
import canmessage
import uasyncio as asyncio

POLARITY_OFF = 0
POLARITY_ON = 1
POLARITY_EITHER = 2
POLARITY_UNKNOWN = -1

ORDER_ANY = 0
ORDER_GIVEN = 1
ORDER_REVERSE = 2

ORDER_BEFORE = 3
ORDER_AFTER = 4

TIME_ANY = -1
TIMESPAN_ANY = -1

WHICH_ANY = 0
WHICH_EARLIEST = 1
WHICH_LATEST = 2


class historyitem:

    """CBUS meesage history item"""

    def __init__(self, msg):
        self.msg = msg
        self.insert_time = time.ticks_ms()


class cbushistory:

    """CBUS message history"""

#    def __new__(cls):
#        if not hasattr(cls, "instance"):
#            cls.instance = super(cbushistory, bus, max_size=64, time_to_live=10000, match_events_only=True).__new__(cls, bus, max_size=64, time_to_live=10000, match_events_only=True)
#        return cls.instance

    def __init__(self, bus, max_size=64, time_to_live=10000, match_events_only=True):
        self.logger = logger.logger()
        self.history = []
        self.max_size = max_size
        self.time_to_live = time_to_live
        self.match_events_only = match_events_only
        self.bus = bus
        self.bus.set_history(self)

    def set_ttl(self, time_to_live):
        self.time_to_live = time_to_live

    def add(self, msg):
        if self.match_events_only and not msg.data[0] in canmessage.event_opcodes:
            return

        if len(self.history) < self.max_size:
            self.history.append(historyitem(msg))

    async def reaper(self):
        while True:
            for i in range(len(self.history) - 1, -1, -1):
                if self.history[i].insert_time + self.time_to_live < time.ticks_ms():
                    del self.history[i]
            await asyncio.sleep_ms(20)

    def count(self):
        c = 0
        for i in range(len(self.history)):
            c += 1
        return c

    def clear(self):
        self.history = []

    def display(self):
        for i in range(len(self.history)):
            sc = self.history[i].msg.as_tuple()
            it = self.history[i].insert_time
            ds = f"{i} {sc} {it}"
            self.logger.log(ds)

    def event_received(self, event, within=TIME_ANY):
        for i in range(len(self.history)):
            if (self.history[i].msg.data[1] * 256) + self.history[i].msg.data[2] == event[1] and (self.history[i].msg.data[3] * 256) + self.history[i].msg.data[4] == event[2]:
                if (event[0] == POLARITY_EITHER or (event[0] == POLARITY_ON and not (self.history[i].msg.data[0] & 1)) or (event[0] == POLARITY_OFF and (self.history[i].msg.data[0] & 1))):
                    if (within == TIME_ANY or self.history[i].insert_time > (time.ticks_ms() - within)):
                        return True
        return False

    def count_of_event(self, event, within=TIME_ANY):
        count = 0
        for i in range(len(self.history)):
            if (self.history[i].msg.data[1] * 256) + self.history[i].msg.data[2] == event[1] and (self.history[i].msg.data[3] * 256) + self.history[i].msg.data[4] == event[2]:
                if (event[0] == POLARITY_EITHER or (event[0] == POLARITY_ON and not (self.history[i].msg.data[0] & 1)) or (event[0] == POLARITY_OFF and (self.history[i].msg.data[0] & 1))):
                    if (self.history[i].insert_time > (time.ticks_ms() - within) or within == TIME_ANY):
                        count += 1
        return count

    def time_received(self, event, which=WHICH_ANY):
        times = []
        for i in range(len(self.history)):
            if (self.history[i].msg.data[1] * 256) + self.history[i].msg.data[2] == event[1] and (self.history[i].msg.data[3] * 256) + self.history[i].msg.data[4] == event[2]:
                if (event[0] == POLARITY_EITHER or (event[0] == POLARITY_ON and not (self.history[i].msg.data[0] & 1)) or (event[0] == POLARITY_OFF and (self.history[i].msg.data[0] & 1))):
                    if which == WHICH_ANY:
                        return self.history[i].insert_time
                    else:
                        times.append(self.history[i].insert_time)

        if len(times) > 0:
            times.sort()
            if which == WHICH_EARLIEST:
                return times[0]
            else:
                return times[-1]

        return -1

    def received_before(self, event1, event2):
        return self.time_received(event1) < self.time_received(event2)

    def received_after(self, event1, event2):
        return self.time_received(event1) > self.time_received(event2)

    def received_in_order(self, event1, event2, order=ORDER_BEFORE):
        if order == ORDER_BEFORE:
            return self.received_before(event1, event2)
        else:
            return self.received_after(event1, event2);

    def current_event_state(self, event):
        state = POLARITY_UNKNOWN
        earliest_time = 0

        for i in range(len(self.history)):
            if (self.history[i].msg.data[1] * 256) + self.history[i].msg.data[2] == event[1] and (self.history[i].msg.data[3] * 256) + self.history[i].msg.data[4] == event[2]:
                if self.history[i].insert_time > earliest_time:
                    earliest_time = self.history[i].insert_time
                    state = (POLARITY_OFF if (self.history[i].msg.data[0] & 1) else POLARITY_ON)

        return state

    def time_of_last_message(self, polarity=POLARITY_EITHER, match_events_only=True):
        latest_time = 0

        for i in range(len(self.history)):
            match = False

            if match_events_only and self.history[i].msg.is_event():
                if polarity == POLARITY_EITHER or (polarity == POLARITY_OFF and self.history[i].msg.data[0] & 1) or (polarity == POLARITY_ON and not (self.history[i].msg.data[0] & 1)):
                    match = True
            elif not match_events_only:
                    match = True

            if match and latest_time < self.history[i].insert_time:
                latest_time = self.history[i].insert_time 

        return latest_time

    def sequence_received(self, events=[], order=ORDER_ANY, within=TIME_ANY, timespan=TIME_ANY):
        times = []
        ret = True

        if len(events) < 1:
            return False

        for event in events:
            etime = self.time_received(event)

            if etime == -1:
                ret = False
                break
            else:
                if within == TIME_ANY or (etime > time.ticks_ms() - within):
                    times.append(etime)

        if len(times) == len(events):
            if order == ORDER_GIVEN:
                for i in range(len(times) - 1):
                    if times[i] > times[i + 1]:
                        ret = False
                        break
            elif order == ORDER_REVERSE:
                for i in range(len(times) - 1):
                    if times[i] < times[i + 1]:
                        ret = False
                        break
            elif order == ORDER_ANY:
                ret = True
        else:
            ret = False

        if ret and timespan != TIMESPAN_ANY:
            times.sort()
            if times[len(times) - 1] - times[0] > timespan:
                ret = False

        return ret

