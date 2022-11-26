# cbusclocks.py
# cbus wall and fast clocks

import time

import machine
import uasyncio as asyncio
from micropython import const

import logger

WALLCLOCK = const(0)
FASTCLOCK = const(1)

default_ntp_server = const('europe.pool.ntp.org')

day_names = {
    0: const('Monday'),
    1: const('Tuesday'),
    2: const('Wednesday'),
    3: const('Thursday'),
    4: const('Friday'),
    5: const('Saturday'),
    6: const('Sunday')
}

month_names = {
    1: const('January'),
    2: const('February'),
    3: const('March'),
    4: const('April'),
    5: const('May'),
    6: const('June'),
    7: const('July'),
    8: const('August'),
    9: const('September'),
    10: const('October'),
    11: const('November'),
    12: const('December')
}


def format_datetime(t: int, terse: bool = False) -> str:
    lt = time.gmtime(t)
    if terse:
        s = f'{day_names[lt[6]][:3]} {lt[2]:02} {month_names[lt[1]][:3]} {lt[0]} {lt[3]:02}:{lt[4]:02}:{lt[5]:02}'
    else:
        s = f'{day_names[lt[6]]} {lt[2]:02} {month_names[lt[1]]} {lt[0]} {lt[3]:02}:{lt[4]:02}:{lt[5]:02}'
    return s


def time_today(hours: int, minutes: int, seconds: int) -> int:
    gm = list(time.gmtime(time.time()))
    gm[3] = hours
    gm[4] = minutes
    gm[5] = seconds
    return time.mktime(tuple(gm))


class time_subscription:
    def __init__(self, sub_time: int, evt: asyncio.Event) -> None:
        self.sub_time = sub_time
        self.evt = evt


class cbusclock:
    def __init__(self, cbus, clock_type=WALLCLOCK, init_time=0, use_ntp=False, ntp_server=None) -> None:
        self.logger = logger.logger()
        self.cbus = cbus
        self.clock_type = clock_type
        self.use_rtc = clock_type == WALLCLOCK
        self.rtc = None
        self.current_time = 0
        self.multiplier = 1
        self.clock_update_interval = 1000
        self.paused = True if self.clock_type == FASTCLOCK else False
        self.use_ntp = use_ntp and clock_type == WALLCLOCK
        self.ntp_server = ntp_server if ntp_server else default_ntp_server
        self.ntp_update_interval = 3_600_000
        self.last_ntp_update = 0
        self.tz_offset = 0
        self.dst_offset = 0
        self.send_events = False
        self.event_freq = 0
        self.event_last_sent = 0
        self.has_temp_sensor = False
        self.temp_pin = 0
        self.current_temperature = 0.0
        self.last_temp_reading = 0
        self.subscriptions = []

        self.set_multiplier(1)

        if self.use_rtc:
            self.rtc = machine.RTC()

        if use_ntp:
            self.set_time_from_ntp(ntp_server)
        else:
            self.current_time = init_time

        asyncio.create_task(self.run())

    def set_time(self, new_time) -> None:
        nt = new_time - (self.tz_offset + self.dst_offset)
        if self.clock_type == WALLCLOCK:
            lt = time.gmtime(nt)
            tt = (lt[0], lt[1], lt[2], 4, lt[3], lt[4], lt[5], lt[6])
            self.rtc.datetime(tt)
            self.current_time = time.time()
        else:
            self.current_time = nt

    def get_time(self) -> int:
        return self.current_time

    def set_time_from_ntp(self, ntp_server: str) -> None:
        import ntptime
        if ntp_server and len(ntp_server) > 0:
            ntptime.host = ntp_server
            ntp_time = ntptime.time()
            if ntp_time > 0:
                lt = time.gmtime(ntp_time)
                tt = (lt[0], lt[1], lt[2], 4, lt[3], lt[4], lt[5], lt[6])
                self.rtc.datetime(tt)
                self.current_time = time.time()
                self.last_ntp_update = time.ticks_ms()

    def set_multiplier(self, multiplier: int) -> None:
        self.multiplier = multiplier
        self.clock_update_interval = int(1000 / self.multiplier)

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def add_subscription(self, sub: time_subscription) -> None:
        if sub.sub_time <= time.time():
            sub.evt.set()
        else:
            sub.evt.clear()
            self.subscriptions.append(sub)

    def remove_subscription(self, sub: time_subscription) -> None:
        for i, s in enumerate(self.subscriptions):
            if s.time == sub.sub_time and s.evt is sub.evt:
                del self.subscriptions[i]
                break

    def read_temperature(self) -> None:
        self.last_temp_reading = time.ticks_ms()
        if self.has_temp_sensor:
            v_zero = 400
            tc = 19.53
            adc = machine.ADC(machine.Pin(self.temp_pin))
            num_adc_samples = 10
            a = 0
            for x in range(num_adc_samples):
                a += adc.read_u16()
            a /= num_adc_samples
            mv = a * (3300 / 65535)
            ta = (mv - v_zero) / tc
            self.current_temperature = ta
        else:
            self.current_temperature = 0.0

    async def run(self) -> None:
        while True:
            await asyncio.sleep_ms(self.clock_update_interval)
            now = time.ticks_ms()

            if not self.paused:
                if self.use_rtc:
                    self.current_time = time.time() + self.tz_offset + self.dst_offset
                else:
                    self.current_time += 1

                for i, s in enumerate(self.subscriptions):
                    if s.sub_time <= self.current_time:
                        s.evt.set()
                        del self.subscriptions[i]

                if self.send_events and time.ticks_diff(now, self.event_last_sent) > self.event_freq:
                    self.event_last_sent = now

                if self.has_temp_sensor and time.ticks_diff(now, self.last_temp_reading) > 10_000:
                    self.read_temperature()

            if self.use_ntp and time.ticks_diff(now, self.last_ntp_update) > self.ntp_update_interval:
                self.set_time_from_ntp(self.ntp_server)