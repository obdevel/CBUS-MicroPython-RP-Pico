
class circularQueue:

    def __init__(self, capacity):
        self.capacity = capacity
        self.queue = [None] * capacity
        self.tail = -1
        self.head = 0
        self.size = 0
        self.hwm = 0
        self.dropped = 0

    def available(self):
        return (self.size > 0)

    def enqueue(self, item):
        if self.size == self.capacity:
            print("Error: queue is full")
            self.dropped = self.dropped + 1
            return False
        else:
            self.tail = (self.tail + 1) % self.capacity
            self.queue[self.tail] = item
            self.size = self.size + 1
            self.hwm = self.hwm + 1 if self.size > self.hwm else self.hwm
            return True

    def dequeue(self):
        if self.size == 0:
            print("Error: queue is empty")
            return None
        else:
            tmp = self.queue[self.head]
            self.head = (self.head + 1) % self.capacity
            self.size = self.size - 1
            return tmp

    def peek(self):
        if self.size == 0:
            return None
        else:
            return self.queue[self.head]

    def empty(self):
        self.size = 0

    def is_full(self):
        return self.size == self.capacity

    def is_empty(self):
        return self.size == 0

    def display(self):
        index = self.head

        for i in range(self.size):
            print(self.queue[index])
            index = (index + 1) % self.capacity
