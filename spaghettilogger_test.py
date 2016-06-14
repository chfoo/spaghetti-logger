import datetime
import glob
import io
import os
import socketserver
import tempfile
import threading
import unittest

from spaghettilogger import ChatLogger, Client


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    pass


class TestLogger(unittest.TestCase):
    def test_logger(self):
        thread_event = threading.Event()

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                nick = self.rfile.readline()
                assert nick.startswith(b'NICK'), nick

                user = self.rfile.readline()
                assert user.startswith(b'USER'), user

                self.wfile.write(
                    b':tmi.twitch.tv 001 twitch_username :Welcome, GLHF!\n'
                    b':tmi.twitch.tv 002 twitch_username :Your host is tmi.twitch.tv\n'
                    b':tmi.twitch.tv 003 twitch_username :This server is rather new\n'
                    b':tmi.twitch.tv 004 twitch_username :-\n'
                    b':tmi.twitch.tv 375 twitch_username :-\n'
                    b':tmi.twitch.tv 372 twitch_username :You are in a maze of twisty passages, all alike.\n'
                    b':tmi.twitch.tv 376 twitch_username :>\n'
                )

                for dummy in range(3):
                    caps = self.rfile.readline()
                    assert caps.startswith(b'CAP'), caps

                join = self.rfile.readline()
                assert join.startswith(b'JOIN'), join

                self.wfile.write(b':twitch_username!twitch_username@twitch_username.tmi.twitch.tv JOIN #test_channel\n')
                self.wfile.write(b':justinfan28394!justinfan28394@justinfan28394.tmi.twitch.tv JOIN #test_channel\n')
                self.wfile.write(b':twitch_username!twitch_username@twitch_username.tmi.twitch.tv PART #test_channel\n')
                self.wfile.write(b':jtv MODE #test_channel +o operator_user\n')
                self.wfile.write(b'@msg-id=slow_off :tmi.twitch.tv NOTICE #test_channel :This room is no longer in slow mode.\n')
                self.wfile.write(b'@ban-duration=600;ban-reason= :tmi.twitch.tv CLEARCHAT #test_channel :naughty_user\n')
                self.wfile.write(b':tmi.twitch.tv CLEARCHAT #test_channel\n')
                self.wfile.write('@badges=;color=;display-name=Naughty_User;emotes=;mod=0;room-id=1337;subscriber=0;turbo=1;user-id=1337;user-type= :naughty_user!naughty_user@naughty_user.tmi.twitch.tv PRIVMSG #test_channel :☺\n'.encode('utf8'))
                self.wfile.write(b'@badges=;color=;display-name=Naughty_User;emotes=;mod=0;room-id=1337;subscriber=0;turbo=1;user-id=1337;user-type= :naughty_user!naughty_user@naughty_user.tmi.twitch.tv PRIVMSG #test_channel :\x01ACTION OneHand\x01\n')
                self.wfile.write(b'@badges=global_mod/1,turbo/1;color=#0D4200;display-name=TWITCH_UserNaME;emotes=25:0-4,12-16/1902:6-10;mod=0;room-id=1337;subscriber=0;turbo=1;user-id=1337;user-type=global_mod :twitch_username!twitch_username@twitch_username.tmi.twitch.tv PRIVMSG #test_channel :Kappa Keepo Kappa\n')
                self.wfile.write(b'@badges=staff/1,broadcaster/1,turbo/1;color=#008000;display-name=TWITCH_UserName;emotes=;mod=0;msg-id=resub;msg-param-months=6;room-id=1337;subscriber=1;system-msg=TWITCH_UserName\shas\ssubscribed\sfor\s6\smonths!;login=twitch_username;turbo=1;user-id=1337;user-type=staff :tmi.twitch.tv USERNOTICE #test_channel :Great stream -- keep it up!\n')

                thread_event.set()

        server = ThreadedTCPServer(('localhost', 0), Handler)
        port = server.server_address[1]

        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = os.path.join(temp_dir, 'logs')

            os.mkdir(log_dir)

            channels_file_path = os.path.join(temp_dir, 'channels.txt')

            with open(channels_file_path, 'w') as file:
                file.write('#test_channel\n')

            chat_logger = ChatLogger(log_dir)
            client = Client(chat_logger, channels_file_path)

            client.autoconnect('localhost', port, 'justinfan28394')

            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.daemon = True
            server_thread.start()

            client_thread = threading.Thread(target=client.reactor.process_forever)
            client_thread.daemon = True
            client_thread.start()

            thread_event.wait(30)

            server.shutdown()
            server.server_close()

            client.stop()

            data = io.StringIO()
            paths = sorted(glob.glob(temp_dir + '/logs/#test_channel/*.log'))

            for path in paths:
                print('reading', path)
                with open(path) as file:
                    data.write(file.read())

            log_file_data = data.getvalue()

            print(log_file_data)

            self.assertRegex(log_file_data, r'# {}.* logstart'.format(datetime.datetime.utcnow().year))
            self.assertIn('join justinfan28394', log_file_data)
            self.assertIn('part twitch_username', log_file_data)
            self.assertIn('mode jtv +o operator_user', log_file_data)
            self.assertRegex(log_file_data, r'notice .* :This room is no longer in slow mode\.')
            self.assertIn('clearchat ban-duration=600;ban-reason= :naughty_user', log_file_data)
            self.assertIn('clearchat  :', log_file_data)
            self.assertIn('☺', log_file_data)
            self.assertIn('\x01ACTION OneHand\x01', log_file_data)
            self.assertIn('TWITCH_UserNaME', log_file_data)
            self.assertIn('Kappa Keepo', log_file_data)
            self.assertRegex(log_file_data, r'usernotice .*msg-param-months.* :Great stream')
