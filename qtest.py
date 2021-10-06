import circularQueue as cq

q = cq.circularQueue(64)
q.enqueue(42)
q.enqueue(84)
print(q.size)
print(q.dequeue())
print(q.size)
q.dequeue()

for i in range(64):
    q.enqueue(i)

q.size
