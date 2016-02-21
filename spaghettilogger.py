#!/usr/bin/env python3
'''Twitch.tv Chat Logger'''
# Copyright 2015 Christopher Foo. License: GPLv3

import argparse
import datetime
import logging
import os.path
import random
import sys
import signal
import time

import irc.client
import irc.ctcp
import irc.strings
import irc.message


_logger = logging.getLogger(__name__)

__version__ = '1.0.5'


class LineWriter(object):
    def __init__(self, log_dir, channel_name, encoding='latin-1',
                 encoding_errors=None):
        self._log_dir = log_dir
        self._channel_name = channel_name
        self._file = None
        self._previous_date = None
        self._encoding = encoding
        self._encoding_errors = encoding_errors

        channel_dir = os.path.join(log_dir, channel_name)

        if not os.path.exists(channel_dir):
            os.mkdir(channel_dir)

    def write_line(self, line):
        current_date = datetime.datetime.utcnow().date()

        if self._previous_date != current_date:
            if self._file:
                self._file.close()

            path = os.path.join(
                self._log_dir,
                self._channel_name,
                current_date.isoformat() + '.log'
            )

            self._file = open(path, 'a', encoding=self._encoding,
                              errors=self._encoding_errors)

        assert '\n' not in line, line
        assert '\r' not in line, line
        self._file.write(line)
        self._file.write('\n')
        self._file.flush()

    def close(self):
        if self._file:
            self._file.close()
            self._file = None


class ChatLogger(object):
    def __init__(self, log_directory):
        self._log_directory = log_directory
        self._channels = []
        self._writers = {}

    def add_channel(self, channel):
        if channel not in self._writers:
            self._writers[channel] = LineWriter(self._log_directory, channel)
            self._write_line(channel, 'logstart {}'.format(channel),
                             internal=True)

    def remove_channel(self, channel):
        if channel in self._writers:
            self._write_line(channel, 'logend {}'.format(channel),
                             internal=True)
            self._writers[channel].close()
            del self._writers[channel]

    def log_message(self, nick, channel, message, tags=None):
        self._write_line(
            channel,
            'privmsg {tags} :{nick} :{message}'.format(
                tags=tags if tags else '',
                nick=nick,
                message=message
            )
        )

    def log_mode(self, nick, channel, args):
        self._write_line(
            channel,
            'mode {} {}'.format(nick, ' '.join(args))
        )

    def log_notice(self, channel, msg, tags=None):
        self._write_line(
            channel,
            'notice {tags} :{msg}'.format(
                msg=msg,
                tags=tags if tags else ''
            )
        )

    def log_clearchat(self, channel, nick=None):
        self._write_line(
            channel,
            'clearchat {nick}'.format(
                nick=nick if nick else ''
            )
        )

    def log_join(self, channel, nick):
        self._write_line(
            channel,
            'join {}'.format(nick)
        )

    def log_part(self, channel, nick):
        self._write_line(
            channel,
            'part {}'.format(nick)
        )

    def _write_line(self, channel, text, internal=False):
        if channel not in self._writers:
            _logger.warning('Discarded message to channel %s when not joined.',
                            channel)
            return

        if internal:
            prefix = '# '
        else:
            prefix = ''

        writer = self._writers[channel]
        line = '{prefix}{date} {text}'.format(
            prefix=prefix,
            date=datetime.datetime.utcnow().isoformat(),
            text=text
        )
        writer.write_line(line)

    def stop(self):
        for channel in tuple(self._writers.keys()):
            self.remove_channel(channel)

RECONNECT_SUCCESS_THRESHOLD = 60
RECONNECT_MIN_INTERVAL = 2
RECONNECT_MAX_INTERVAL = 300
KEEP_ALIVE = 60
IRC_RATE_LIMIT = (20 - 0.5) / 30
FILE_POLL_INTERVAL = 30


class ListWrapper(list):
    __slots__ = ('raw', )


class Client(irc.client.SimpleIRCClient):
    def __init__(self, chat_logger, channels_file):
        super().__init__()
        self._chat_logger = chat_logger
        self._channels_file = channels_file
        self._channels_file_timestamp = 0
        self._channels = []
        self._joined_channels = set()
        self._running = True
        self._reconnect_time = RECONNECT_MIN_INTERVAL
        self._last_connect = 0

        irc.client.ServerConnection.buffer_class.encoding = 'latin-1'
        self.connection.set_rate_limit(IRC_RATE_LIMIT)

        self.reactor.execute_every(FILE_POLL_INTERVAL, self._load_channels)
        self.reactor.execute_every(KEEP_ALIVE, self._keep_alive)

        # Monkey patch to include raw tags so we don't have to serialize it
        # again
        original_from_group = irc.message.Tag.from_group

        def new_from_group(text):
            result = original_from_group(text)
            if result:
                result = ListWrapper(result)
                result.raw = text
            return result

        irc.message.Tag.from_group = new_from_group

        # Monkey patch to preserve messages such as /me
        # Fortunately, Twitch does not require CTCP replies
        irc.ctcp.dequote = lambda msg: [msg]

    def autoconnect(self, *args, **kwargs):
        try:
            if args:
                self.connect(*args, **kwargs)
            else:
                self.connection.reconnect()
        except irc.client.ServerConnectionError:
            _logger.exception('Connect failed.')
            self._schedule_reconnect()

    def _schedule_reconnect(self):
        time_now = time.time()

        if time_now - self._last_connect > RECONNECT_SUCCESS_THRESHOLD:
            self._reconnect_time *= 2
            self._reconnect_time = min(RECONNECT_MAX_INTERVAL,
                                       self._reconnect_time)
        else:
            self._reconnect_time = RECONNECT_MIN_INTERVAL

        _logger.info('Reconnecting in %s seconds.', self._reconnect_time)
        self.reactor.execute_delayed(self._reconnect_time,
                                     self.autoconnect)

    def stop(self):
        self._running = False
        self.reactor.disconnect_all()
        self._chat_logger.stop()

    def on_welcome(self, connection, event):
        _logger.info('Logged in to server.')
        self.connection.cap('REQ', 'twitch.tv/membership')
        self.connection.cap('REQ', 'twitch.tv/commands')
        self.connection.cap('REQ', 'twitch.tv/tags')
        self._load_channels(force_reload=True)
        self._last_connect = time.time()

    def on_disconnect(self, connection, event):
        _logger.info('Disconnected!')
        self._chat_logger.stop()

        if self._running:
            self._joined_channels.clear()
            self._schedule_reconnect()

    def on_join(self, connection, event):
        client_nick = self.connection.get_nickname()
        nick = irc.strings.lower(event.source.nick)
        channel = irc.strings.lower(event.target)

        if nick == client_nick:
            _logger.info('Joined %s', channel)
            self._joined_channels.add(event.target)

        self._chat_logger.log_join(channel, nick)

    def on_part(self, connection, event):
        client_nick = self.connection.get_nickname()
        nick = irc.strings.lower(event.source.nick)
        channel = irc.strings.lower(event.target)

        if nick == client_nick and channel in self._joined_channels:
            _logger.info('Parted %s', channel)
            self._joined_channels.remove(channel)

        self._chat_logger.log_part(channel, nick)

    def on_pubmsg(self, connection, event):
        channel = irc.strings.lower(event.target)

        if hasattr(event.source, 'nick'):
            nick = irc.strings.lower(event.source.nick)

            self._chat_logger.log_message(
                nick,
                channel,
                event.arguments[0],
                event.tags.raw if event.tags else None)

    def on_mode(self, connection, event):
        nick = irc.strings.lower(event.source.nick)
        channel = irc.strings.lower(event.target)

        self._chat_logger.log_mode(nick, channel, event.arguments)

    def on_pubnotice(self, connection, event):
        channel = irc.strings.lower(event.target)

        self._chat_logger.log_notice(
            channel,
            event.arguments[0],
            event.tags.raw if event.tags else None
        )

    def on_clearchat(self, connection, event):
        channel = irc.strings.lower(event.target)
        nick = event.arguments[0] if event.arguments else None

        self._chat_logger.log_clearchat(channel, nick)

    def _join_new_channels(self):
        new_channels = frozenset(self._channels) - self._joined_channels

        for channel in new_channels:
            _logger.info('Joining %s', channel)
            self._chat_logger.add_channel(channel)
            self.connection.join(channel)

    def _part_old_channels(self):
        old_channels = self._joined_channels - frozenset(self._channels)

        for channel in old_channels:
            _logger.info('Parting %s', channel)
            self.connection.part(channel)
            self._chat_logger.remove_channel(channel)

    def _load_channels(self, force_reload=False):
        new_time = os.path.getmtime(self._channels_file)

        if not force_reload and new_time == self._channels_file_timestamp:
            return

        self._channels_file_timestamp = new_time

        self._channels = []

        with open(self._channels_file, 'r') as file:
            for channel in file:
                channel = channel.strip()

                if not channel:
                    continue

                channel = irc.strings.lower(channel)
                self._channels.append(channel)

        if self.connection.is_connected():
            self._join_new_channels()
            self._part_old_channels()

    def _keep_alive(self):
        if self.connection.is_connected():
            self.connection.ping('keep-alive')


def main():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('channels_file')
    arg_parser.add_argument('log_dir')
    arg_parser.add_argument('--host', default='irc.twitch.tv')
    arg_parser.add_argument('--port', type=int, default=6667)
    arg_parser.add_argument('--nickname')
    arg_parser.add_argument('--oauth-file')

    args = arg_parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if not os.path.isfile(args.channels_file):
        sys.exit('channels file provided is not a file.')

    if not os.path.isdir(args.log_dir):
        sys.exit('log dir provided is not a directory.')

    if args.oauth_file:
        with open(args.oauth_file, 'r') as file:
            password = 'oauth:' + file.read().strip()
    else:
        password = None

    _logger.info('Starting IRC client.')

    chat_logger = ChatLogger(args.log_dir)
    client = Client(chat_logger, args.channels_file)
    running = True
    nickname = args.nickname or 'justinfan{}'.format(random.randint(0, 9000000))

    def stop(dummy1, dummy2):
        nonlocal running
        running = False
        client.stop()

    client.autoconnect(args.host, args.port, nickname, password=password)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    while running:
        client.reactor.process_once(0.2)

    _logger.info('Stopped IRC client.')

if __name__ == '__main__':
    main()
