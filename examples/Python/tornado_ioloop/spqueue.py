#!/usr/bin/env python

"""
synopsis:
    Simple Pirate queue
    This is identical to the LRU pattern, with no reliability mechanisms
    at all. It depends on the client for recovery. Runs forever.
    Original author: Daniel Lundin <dln(at)eintr(dot)org>
    Modified for async/ioloop: Dave Kuhlman <dkuhlman(at)davekuhlman(dot)org>
usage:
    python spqueue.py
notes:
    To test this use, the lazy pirate client.  To run this, start any number of
    spworker.py processes, one instance of an spqueue.py process, and any
    number lpclient.py processes, in any order.
"""

import sys
from functools import partial
import zmq
from zmq.eventloop.future import Context, Poller
from zmq.eventloop.ioloop import IOLoop
from tornado import gen

LRU_READY = "\x01"


@gen.coroutine
def run_queue():
    context = Context(1)

    frontend = context.socket(zmq.ROUTER)    # ROUTER
    backend = context.socket(zmq.ROUTER)     # ROUTER
    frontend.bind("tcp://*:5555")            # For clients
    backend.bind("tcp://*:5556")             # For workers

    poll_workers = Poller()
    poll_workers.register(backend, zmq.POLLIN)

    poll_both = Poller()
    poll_both.register(frontend, zmq.POLLIN)
    poll_both.register(backend, zmq.POLLIN)

    workers = []

    while True:
        if workers:
            socks = yield poll_both.poll()
        else:
            socks = yield poll_workers.poll()
        socks = dict(socks)

        # Handle worker activity on backend
        if socks.get(backend) == zmq.POLLIN:
            # Use worker address for LRU routing
            msg = yield backend.recv_multipart()
            if not msg:
                break
            print('I: received msg: {}'.format(msg))
            address = msg[0]
            workers.append(address)

            # Everything after the second (delimiter) frame is reply
            reply = msg[2:]

            # Forward message to client if it's not a READY
            if reply[0] != LRU_READY:
                print('I: sending -- reply: {}'.format(reply))
                yield frontend.send_multipart(reply)
            else:
                print('I: received ready -- address: {}'.format(address))

        if socks.get(frontend) == zmq.POLLIN:
            #  Get client request, route to first available worker
            msg = yield frontend.recv_multipart()
            worker = workers.pop(0)
            request = [worker, b''] + msg
            print('I: sending -- worker: {}  msg: {}'.format(worker, msg))
            yield backend.send_multipart(request)


@gen.coroutine
def run(loop):
    while True:
        yield run_queue()


def main():
    args = sys.argv[1:]
    if len(args) != 0:
        sys.exit(__doc__)
    try:
        loop = IOLoop.current()
        loop.run_sync(partial(run, loop))
    except KeyboardInterrupt:
        print('\nFinished (interrupted)')


if __name__ == '__main__':
    main()
