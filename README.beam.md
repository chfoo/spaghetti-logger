Fake Spaghetti Logger
=====================

Quick Start
===========

Requires

* [Python](https://www.python.org/) 3.3+
* [TornadoWeb](http://www.tornadoweb.org/) Python library version 4.3+

You can install the required Python libraries using Pip. Assuming Linux system:

        pip3 install tornado

Add the `--user` option to not use sudo.

Then run

        python3 fakespaghettilogger.py CHANNEL_ID_NUM LOGGING_DIR

* where `CHANNEL_ID_NUM` is the numeric ID of the channel (not the channel name).
* and `LOGGING_DIR` is the directory name of logs to be placed.


Operation
=========

The logger will place logs under directories for each channel and log to files named by date. It will reconnect automatically.

The chat logger will save the original WebSocket message received.

Only 1 channel is supported per instance because their stream does not include channel IDs for parts/joins.
