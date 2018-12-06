Spaghetti Logger
================

Spaghetti Logger is a Twitch.tv chat logger.

Fake Spaghetti Logger is a Beam.pro chat logger. See README.beam.md for instructions for Beam.


Quick Start
===========

Requires

* [Python](https://www.python.org/) 3.3+
* [irc](https://pypi.python.org/pypi/irc) Python library version 15+

You can install the required Python libraries using Pip. Assuming Linux system:

        pip3 install irc

Add the `--user` option to not use sudo.

Then run

        python3 spaghettilogger.py CHANNELS_FILE LOGGING_DIR

* where `CHANNELS_FILE` is the filename of a text file containing IRC channel names one per line (include the `#` symbol)
* and `LOGGING_DIR` is the directory name of logs to be placed.


Operation
=========

The logger will place logs under directories for each channel and log to files named by date. It will reconnect automatically.

The logger will check the channels file for modification every 30 seconds. It will join and part the channels as needed.

The logger will log the following

* PRIVMSG with tags
* NOTICE
* JOIN
* PART
* MOD
* CLEARCHAT
* USERNOTICE


For group chats, the logger needs to be logged in. Check https://chatdepot.twitch.tv/room_memberships?oauth_token=OAUTH_TOKEN_HERE for IP addresses and channel name. Use `--nickname` and `--oauth-path OAUTH_FILENAME` where `OAUTH_FILENAME` is a text file containing your oauth token.

For details of the IRC protocol, see https://dev.twitch.tv/docs/v5/guides/irc/ .

In the event the IRC address changes, use `--host` option when running the logger.


Credits
=======

Copyright 2015-2018 Christopher Foo. License: GPLv3
