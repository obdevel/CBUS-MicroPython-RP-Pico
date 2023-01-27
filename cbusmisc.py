import uasyncio as asyncio
from micropython import const

import canmessage
import cbus
import cbusobjects
import logger

TT_ROTATE_FASTEST = const(0)
TT_ROTATE_CLOCKWISE = const(1)
TT_ROTATE_ANTICLOCKWISE = const(2)


class turntable:
    def __init__(self, name: str, cbus: cbus.cbus, position_events: tuple, stop_event: tuple = None,
                 feedback_events: tuple = None, query_message: tuple = None, init: bool = False, init_pos: int = 0):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.position_events = position_events
        self.stop_event = stop_event
        self.has_sensor = feedback_events is not None
        self.feedback_events = feedback_events
        self.query_message = query_message
        self.sensor = None
        self.current_position = 0
        self.target_position = 0
        self.evt = asyncio.Event()

        if self.has_sensor:
            self.sensor_name = 'turntable:' + self.name + ':sensor'
            self.sensor = cbusobjects.multi_sensor(self.sensor_name, cbus, self.feedback_events, self.query_message)
            self.sensor_monitor_task_handle = asyncio.create_task(self.sensor_monitor_task())

            if self.query_message is not None:
                self.sync_state()

        if init:
            self.position_to(init_pos)

    def dispose(self) -> None:
        if self.has_sensor:
            self.sensor_monitor_task_handle.cancel()
            self.sensor.dispose()

    def sync_state(self) -> None:
        msg = canmessage.message_from_tuple(self.query_message)
        self.cbus.send_cbus_message(msg)

    def sensor_monitor_task(self) -> None:
        while True:
            await self.sensor.wait()
            self.current_position = self.sensor.state

    async def position_to(self, position: int, wait: bool = False) -> bool:
        ret = False
        msg = canmessage.event_from_tuple(self.cbus, self.position_events[position])
        msg.send()

        if wait and self.has_sensor:
            self.current_position = -1
            evw = await cbusobjects.WaitAnyTimeout((self.evt,), cbusobjects.OP_TIMEOUT).wait()

            if evw is None:
                self.logger.log(f'turntable: name = {self.name}, timeout')
                ret = False
            else:
                self.current_position = self.sensor.state
                self.logger.log(f'turntable: name = {self.name}, position = {self.current_position}')
                ret = True

        return ret

    def stop(self) -> None:
        if self.stop_event:
            msg = canmessage.event_from_tuple(self.cbus, self.stop_event)
            msg.send()

    def wait(self) -> None:
        self.evt.clear()
        await self.sensor.wait()
        self.evt.set()


class uncoupler:
    def __init__(self, name: str, cbus: cbus.cbus, event: tuple, auto_off: bool = False, timeout: int = cbusobjects.RELEASE_TIMEOUT) -> None:
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.timeout = timeout
        self.event = canmessage.event_from_tuple(self.cbus, event)
        self.auto_off = auto_off

    def on(self) -> None:
        self.event.send_on()
        self.logger.log(f'uncoupler {self.name} on')

        if self.auto_off:
            _ = asyncio.create_task(self.auto_off_timer())

    def off(self):
        self.event.send_off()
        self.logger.log(f'uncoupler {self.name} off')

    async def auto_off_timer(self):
        self.logger.log(f'uncoupler {self.name} waiting for timeout')
        await asyncio.sleep_ms(self.timeout)
        self.logger.log(f'uncoupler {self.name} timed out')
        self.off()
