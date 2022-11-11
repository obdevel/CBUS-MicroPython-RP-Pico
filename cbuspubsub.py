# cbuspubsub.py
# publish/subscribe pattern from coroutines

import canmessage
import cbus
import logger
import uasyncio as asyncio
import primitives
import random
import re


class subscription:
    def __init__(self, name, cbus, query, query_type):
        self.logger = logger.logger()
        self.name = name
        self.cbus = cbus
        self.id = random.randint(0, 65535)
        self.query = query
        self.query_type = query_type
        self.regex = None
        self.queue = primitives.Queue()
        if type == canmessage.QUERY_REGEX:
            self.regex = re.compile(query)
        self.subscribe()

    def subscribe(self):
        self.cbus.add_subscription(self)

    def unsubscribe(self, request):
        self.logger.log("unsubscribe")
        self.cbus.remove_subscription(request)

    async def publish(self, msg):
        if msg.matches(self.query, self.query_type):
            self.queue.put_nowait(msg)

    async def wait(self):
        return await self.queue.get()


