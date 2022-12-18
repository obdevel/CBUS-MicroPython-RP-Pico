# CBUS event history

import time

import uasyncio as asyncio
from micropython import const

import canmessage
import logger

ORDER_ANY = const(0)
ORDER_GIVEN = const(1)
ORDER_REVERSE = const(2)

ORDER_BEFORE = const(3)
ORDER_AFTER = const(4)

TIME_ANY = const(-1)
WINDOW_ANY = const(-1)

WHICH_ANY = const(0)
WHICH_EARLIEST = const(1)
WHICH_LATEST = const(2)


class historyitem:
    """CBUS message history item"""

    def __init__(self, msg):
        self.msg = msg
        self.arrival_time = time.ticks_ms()


class cbushistory:
    """CBUS message history"""

    def __init__(self, bus, max_size=-1, time_to_live=10000, match_events_only=True, event=None):
        self.logger = logger.logger()
        self.history = []
        self.max_size = max_size
        self.time_to_live = time_to_live
        self.match_events_only = match_events_only
        self.bus = bus
        self.event = event
        self.last_update = 0
        self.bus.add_history(self)

        asyncio.create_task(self.reaper())

    def set_ttl(self, time_to_live) -> None:
        self.time_to_live = time_to_live

    def add(self, msg) -> None:
        if msg.dlc == 0 or (self.match_events_only and not msg.data[0] in canmessage.event_opcodes):
            return

        if self.max_size == -1 or len(self.history) < self.max_size:
            self.history.append(historyitem(msg))
            self.last_update = time.ticks_ms()
            if isinstance(self.event, asyncio.Event):
                self.event.set()

    async def reaper(self, freq=500) -> None:
        while True:
            tnow = time.ticks_ms()
            for i in range(len(self.history) - 1, -1, -1):
                if self.history[i].arrival_time + self.time_to_live < tnow:
                    del self.history[i]
            await asyncio.sleep_ms(min(freq, self.time_to_live))

    def count(self) -> int:
        return len(self.history)

    def clear(self) -> None:
        self.history = []

    def display(self) -> None:
        for i in range(len(self.history)):
            sc = tuple(self.history[i].msg)
            it = self.history[i].arrival_time
            ds = f"{i} {sc} {it}"
            self.logger.log(ds)

    def last_update_time(self) -> int:
        return self.last_update

    def event_received(self, event: tuple, within=TIME_ANY) -> bool:
        for i in range(len(self.history)):
            if self.history[i].msg.get_node_number == event[1] and self.history[i].msg.get_event_number() == event[2]:
                if event[0] == canmessage.POLARITY_EITHER or (
                        event[0] == canmessage.POLARITY_ON and not (self.history[i].msg.data[0] & 1)) or (
                        event[0] == canmessage.POLARITY_OFF and (self.history[i].msg.data[0] & 1)):
                    if within == TIME_ANY or self.history[i].arrival_time > (time.ticks_ms() - within):
                        return True
        return False

    def count_of_event(self, event: tuple, within=TIME_ANY) -> int:
        count = 0
        for i in range(len(self.history)):
            if self.history[i].msg.get_node_number() == event[1] and self.history[i].msg.get_event_number() == event[2]:
                if event[0] == canmessage.POLARITY_EITHER or (
                        event[0] == canmessage.POLARITY_ON and not (self.history[i].msg.data[0] & 1)) or (
                        event[0] == canmessage.POLARITY_OFF and (self.history[i].msg.data[0] & 1)):
                    if self.history[i].arrival_time > (time.ticks_ms() - within) or within == TIME_ANY:
                        count += 1
        return count

    def time_received(self, event: tuple, which=WHICH_ANY) -> int:
        times = []
        for i in range(len(self.history)):
            if self.history[i].msg.get_node_number() == event[1] and self.history[i].msg.get_event_number() == event[2]:
                if event[0] == canmessage.POLARITY_EITHER or (
                        event[0] == canmessage.POLARITY_ON and not (self.history[i].msg.data[0] & 1)) or (
                        event[0] == canmessage.POLARITY_OFF and (self.history[i].msg.data[0] & 1)):
                    if which == WHICH_ANY:
                        return self.history[i].arrival_time
                    else:
                        times.append(self.history[i].arrival_time)

        if len(times) > 0:
            if which == WHICH_ANY:
                return times[0]
            times.sort()
            if which == WHICH_EARLIEST:
                return times[0]
            elif which == WHICH_LATEST:
                return times[-1]

        return -1

    def received_before(self, event1: tuple, event2: tuple) -> bool:
        return self.time_received(event1) < self.time_received(event2)

    def received_after(self, event1: tuple, event2: tuple) -> bool:
        return self.time_received(event1) > self.time_received(event2)

    def received_in_order(self, event1: tuple, event2: tuple, order=ORDER_BEFORE) -> bool:
        if order == ORDER_BEFORE:
            return self.received_before(event1, event2)
        else:
            return self.received_after(event1, event2)

    def current_event_state(self, event: tuple) -> int:
        state = canmessage.POLARITY_UNKNOWN
        earliest_time = 0

        for i in range(len(self.history)):
            if self.history[i].msg.get_node_number() == event[1] and self.history[i].msg.get_event_number() == event[2]:
                if self.history[i].arrival_time > earliest_time:
                    earliest_time = self.history[i].arrival_time
                    state = (canmessage.POLARITY_OFF if (self.history[i].msg.data[0] & 1) else canmessage.POLARITY_ON)

        return state

    def time_of_last_message(self, polarity=canmessage.POLARITY_EITHER, match_events_only=True) -> int:
        latest_time = 0

        for i in range(len(self.history)):
            match = False

            if match_events_only and self.history[i].msg.is_event():
                if polarity == canmessage.POLARITY_EITHER or (
                        polarity == canmessage.POLARITY_OFF and self.history[i].msg.data[0] & 1) or (
                        polarity == canmessage.POLARITY_ON and not (self.history[i].msg.data[0] & 1)):
                    match = True
            elif not match_events_only:
                match = True

            if match and latest_time < self.history[i].arrival_time:
                latest_time = self.history[i].arrival_time

        return latest_time

    def time_diff(self, events: tuple, within=TIME_ANY, timespan=WINDOW_ANY, which=WHICH_ANY):
        atimes = []

        if len(events) != 2:
            return None

        for event in events:
            etime = self.time_received(event, which)

            if etime == -1:
                return None
            else:
                if within == TIME_ANY or (etime > time.ticks_ms() - within):
                    atimes.append(etime)

        if timespan == WINDOW_ANY or abs(atimes[1] - atimes[0]) <= timespan:
            return atimes[1] - atimes[0]
        else:
            return None

    def sequence_received(self, events: tuple, order=ORDER_ANY, within=TIME_ANY, window=TIME_ANY,
                          which=WHICH_ANY) -> bool:
        times = []
        ret = True

        if self.count() < 1:
            return False

        if len(events) < 1:
            return False

        for event in events:
            etime = self.time_received(event, which)

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

        if ret and window != WINDOW_ANY:
            times.sort()
            if times[len(times) - 1] - times[0] > window:
                ret = False

        return ret
