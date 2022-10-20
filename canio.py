# canio.py


class canio:

    """a base class to represent a generic CAN bus interface"""

    def __init__(self):
        print("** canio constructor")
        pass

    def begin(self):
        pass

    def send_message(self):
        pass

    def get_next_message(self):
        pass

    def available(self):
        pass

    def reset(self):
        pass
