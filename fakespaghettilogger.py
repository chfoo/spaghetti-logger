# This is free and unencumbered software released into the public domain.

# Anyone is free to copy, modify, publish, use, compile, sell, or
# distribute this software, either in source code form or as a compiled
# binary, for any purpose, commercial or non-commercial, and by any
# means.

# In jurisdictions that recognize copyright laws, the author or authors
# of this software dedicate any and all copyright interest in the
# software to the public domain. We make this dedication for the benefit
# of the public at large and to the detriment of our heirs and
# successors. We intend this dedication to be an overt act of
# relinquishment in perpetuity of all present and future rights to this
# software under copyright law.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.

# For more information, please refer to <http://unlicense.org>

import argparse
import datetime
import json
import logging
import os
import sys

import time
import tornado.gen
import tornado.websocket
import tornado.ioloop

from spaghettilogger import LineWriter, RECONNECT_MIN_INTERVAL, \
    RECONNECT_SUCCESS_THRESHOLD, RECONNECT_MAX_INTERVAL

_logger = logging.getLogger(__name__)

__version__ = '1.0.1'


class Client(object):
    def __init__(self, url, channel_id, log_dir):
        self._writer = LineWriter(log_dir, str(channel_id), encoding='utf-8',
                                  encoding_errors='replace')
        self._url = url
        self._channel_id = channel_id

    def run(self):
        tornado.ioloop.IOLoop.current().run_sync(self._run)

    @tornado.gen.coroutine
    def _run(self):
        sleep_time = RECONNECT_MIN_INTERVAL

        while True:
            start_time = time.time()
            try:
                yield self._run_session()
            except tornado.websocket.WebSocketError:
                _logger.exception('Websocket error')

            end_time = time.time()

            if end_time - start_time < RECONNECT_SUCCESS_THRESHOLD:
                sleep_time *= 2
                sleep_time = min(sleep_time, RECONNECT_MAX_INTERVAL)
            else:
                sleep_time = RECONNECT_MIN_INTERVAL

            _logger.info("Sleeping for %s seconds", sleep_time)

            yield tornado.gen.sleep(sleep_time)

    @tornado.gen.coroutine
    def _run_session(self):
        conn = yield tornado.websocket.websocket_connect(self._url)

        _logger.info("Join channel %s", self._channel_id)

        self._write_line('logstart {}'.format(self._channel_id),
                         internal=True)

        conn.write_message(json.dumps({
            "type": "method",
            "method": "auth",
            "arguments": [self._channel_id],
            "id": 1
        }))

        while True:
            msg = yield conn.read_message()

            if msg is None:
                break

            self._write_line(msg)

    def _write_line(self, msg, internal=False):
        if internal:
            prefix = '# '
        else:
            prefix = ''

        writer = self._writer
        line = '{prefix}{date} {text}'.format(
            prefix=prefix,
            date=datetime.datetime.utcnow().isoformat(),
            text=msg
        )
        writer.write_line(line)


def main():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('channel_id', type=int)
    arg_parser.add_argument('log_dir')
    arg_parser.add_argument('--url', default='wss://chat2-dal07.beam.pro:443')

    args = arg_parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if not os.path.isdir(args.log_dir):
        sys.exit('log dir provided is not a directory.')

    _logger.info('Starting websocket client.')

    channel_ids = []

    client = Client(args.url, args.channel_id, args.log_dir)
    client.run()

    _logger.info('Stopped websocket client.')

if __name__ == '__main__':
    main()
