import uasyncio as asyncio

import canmessage
import cbus
import cbushistory
import cbusroutes
import logger


class entry_exit:

    def __init__(self, name: str, cbus: cbus.cbus, nxroute: cbusroutes.route, switch_events: tuple, producer_events: tuple) -> None:
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.switch_events = switch_events
        self.nxroute = nxroute
        self.producer_events = producer_events

        self.switch_history = cbushistory.cbushistory(self.cbus, time_to_live=5_000, query_type=canmessage.QUERY_UDF,
                                                      query=self.udf)
        self.nx_run_task_handle = asyncio.create_task(self.nx_run_task())

    def dispose(self):
        self.switch_history.remove()
        self.nx_run_task_handle.cancel()
        self.nxroute.dispose()

    def udf(self, msg):
        if tuple(msg) in self.switch_events:
            return True

    async def nx_run_task(self):
        while True:
            await self.switch_history.add_evt.wait()
            self.switch_history.add_evt.clear()

            if self.nxroute.state == cbusroutes.ROUTE_STATE_UNSET:
                if self.switch_history.sequence_received(self.switch_events):
                    self.logger.log(f'nxroute:{self.name}: received sequence')
                    b = await self.nxroute.acquire()
                    self.logger.log(f'nxroute:{self.name}: acquire returns {b}')
                    if b:
                        await self.nxroute.set()
                        self.logger.log(f'nxroute:{self.name}: route set')
                    if len(self.producer_events) > 0 and len(self.producer_events[0] == 3):
                        msg = canmessage.event_from_tuple(self.cbus, self.producer_events[0])
                        msg.polarity = int(b)
                        msg.send()
                else:
                    self.logger.log(f'nxroute:{self.name}: received one event')
                    if len(self.producer_events) > 1 and len(self.producer_events[1] == 3):
                        msg = canmessage.event_from_tuple(self.cbus, self.producer_events[1])
                        msg.send()
            else:
                if self.switch_history.any_received(self.switch_events):
                    self.logger.log(f'nxroute:{self.name}: releasing route')
                    self.nxroute.release()
                    self.nxroute.release_timeout_task_handle.cancel()
                    if len(self.producer_events) > 2 and len(self.producer_events[2] == 3):
                        msg = canmessage.event_from_tuple(self.cbus, self.producer_events[2])
                        msg.send()
