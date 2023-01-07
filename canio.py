# canio.py
import canmessage
import logger


class canio:
    """a base class to represent a generic CAN bus interface"""

    def __init__(self):
        self.logger = logger.logger()
        # self.logger.log("canio constructor")
        self.rx_queue = None
        self.tx_queue = None

    def begin(self) -> None:
        pass

    def send_message(self, msg) -> int:
        pass

    def get_next_message(self) -> canmessage.canmessage:
        pass

    def poll_for_messages(self) -> None:
        pass

    def available(self) -> bool:
        pass

    def reset(self) -> None:
        pass
