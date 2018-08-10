#!/usr/bin/python3

# File name: pySimonaProxy.py
# Author: Petr Svenda, Dan Cvrcek
# Date created: 7/11/2018
# Python Version: 3.x
# MIT license
#
# Based on Simple socket server using threads by Silver Moon
# (https://www.binarytides.com/python-socket-server-code-example/)

import json
import logging
import coloredlogs
import re
import requests
import socket
import sys
import time
import threading

logger = logging.getLogger(__name__)
coloredlogs.install(level='DEBUG')
# coloredlogs.install(level='DEBUG', logger=logger) # to suppress logs from libs

logging.basicConfig(level=logging.DEBUG)

CMD_APDU = "APDU"
CMD_RESET = "RESET"
CMD_ENUM = "ENUM"
CMD_SEPARATOR = ":"
CMD_LINE_SEPARATOR = "|"
CMD_RESPONSE_END = "@@"
CMD_RESPONSE_FAIL = "FAIL"


class ProxyConfig:
    test_simulated_card = False # if true, completely simulated response is send back

    socket_host = ''    # Symbolic name meaning all available interfaces
    socket_port = 4001  # Arbitrary non-privileged port

    gpprorest_proxy = 'http://127.0.0.1:8081/api/v1/basic'  # rest proxy for simona boards, use basicj for more info
    gpprorest_http_headers = {'X-Auth-Token': 'b'}

    gpprorest_test_with_local_reader = True # if true, name of local reader will be used instead of supplied remote one
    # gpprorest_test_local_reader = 'Generic EMV Smartcard Reader 0'
    gpprorest_test_local_reader = 'OMNIKEY CardMan 6121 0'


class InputRequestData:
    reader_name = ""
    command_id = ""
    command_name = ""
    command_data = ""

    def __init__(self, reader_name, command_id, command_name, command_data):
        self.reader_name = reader_name
        self.command_id = command_id
        self.command_name = command_name
        self.command_data = command_data


class ClientThread(threading.Thread):
    """
    Function for handling connections. This will be used to create threads
    """

    def __init__(self, connection, ip, port, proxy_cfg):
        threading.Thread.__init__(self)
        self.connection = connection
        self.ip = ip
        self.port = port
        self.proxy_cfg = proxy_cfg

    def run(self):
        try:
            # infinite loop so that function do not terminate and thread do not end.
            while True:
                # first we read all the commands
                data = self.connection.recv(4096)
                if len(data) == 0:  # connection was closed
                    break

                reader, commands = SimonaSocketProxy.parse_input_request(data)

                if len(commands) == 0:
                    logging.error("No commands to process")
                    time.sleep(0.1)  # sleep little before making another receive attempt
                    continue

                for command in commands:
                    if len(command) == 2:
                        input_req = InputRequestData(reader, command['id'], command['name'], "")
                    else:
                        input_req = InputRequestData(reader, command['id'], command['name'], command['bytes'])

                    logging.info("Reader:'{0}',CommandID:'{1}',Command:'{2}',Data:'{3}'".format(input_req.reader_name,
                                                                                                input_req.command_id,
                                                                                                input_req.command_name,
                                                                                                input_req.command_data))
                    # for testing with local card, rename Simona readers to local one
                    if self.proxy_cfg.gpprorest_test_with_local_reader:
                        if input_req.reader_name.find('Simona') != -1:
                            logging.debug('Changing remote reader {0} to local reader {1} for testing'
                                          .format(input_req.reader_name, self.proxy_cfg.gpprorest_test_local_reader))
                            input_req.reader_name = self.proxy_cfg.gpprorest_test_local_reader

                    response_data = None

                    # SEND APDU
                    if input_req.command_name.lower() == CMD_APDU.lower():
                        if self.proxy_cfg.test_simulated_card:
                            # test response
                            response_data = "102030409000"
                        else:
                            payload = {'apdu': input_req.command_data, 'terminal': input_req.reader_name}
                            response_data = SimonaSocketProxy.make_request(
                                self.proxy_cfg.gpprorest_proxy, payload,
                                self.proxy_cfg.gpprorest_http_headers)

                    # RESET
                    if input_req.command_name.lower() == CMD_RESET.lower():
                        if self.proxy_cfg.test_simulated_card:
                            # test response
                            response_data = "621A82013883023F008404524F4F5485030079AD8A0105A1038B01019000"
                        else:
                            payload = {'reset': '1', 'terminal': input_req.reader_name, 'close': '1'}
                            response_data = SimonaSocketProxy.make_request(
                                self.proxy_cfg.gpprorest_proxy, payload,
                                self.proxy_cfg.gpprorest_http_headers)

                    # No valid command found
                    if not response_data:
                        response_data = CMD_RESPONSE_FAIL

                    response = ">{0}{1}{2}{3}\n".format(input_req.command_id, CMD_SEPARATOR, response_data,
                                                        CMD_RESPONSE_END)
                    logging.info(response)
                self.connection.sendall(response.encode("utf-8"))
        except Exception as ex:
            logging.info('Exception in serving response, ending thread %s' % ex)
            logging.info('\n')

        # Terminate connection for given client (if outside loop)
        self.connection.close()
        return


class SimonaSocketProxy:
    # Function for parsing input request
    # ><reader name>|><cmd ID>:<"APDU" / "RESET" / "ENUM">:<optional hexa string, e.g. "00A4040304">|
    @staticmethod
    def parse_input_request_regex(s):
        match = re.match(r'>(?P<readerName>.*?)\|>(?P<commandID>.*?):(?P<commandName>.*?):(?P<commandData>.*?)\|', s, re.I)
        if match:
            command_data = match.group("commandData")
            command_data = command_data.replace(' ', '')
            return InputRequestData(match.group("readerName"), match.group("commandID"),
                                    match.group("commandName"), command_data)
        else:
            return None

    # Function for parsing input request - assumes every line starting with > to be on separate line
    @staticmethod
    def parse_input_request(data):
        # Receiving from client
        reader = None
        commands = []

        buffer_list = []
        try:
            buffer_list.append(data.decode('utf-8'))
        except TypeError:
            logging.error("Received data can't be converted to text")
            pass
        data = ''.join(buffer_list)

        lines = data.splitlines()
        for line in lines:
            if line[0] == '#':
                # this may be in internal info
                pass
            elif line[0] != '>':
                # we will ignore this line
                continue
            line = line[1:].strip()  # ignore the '>' and strip whitespaces
            if line.rfind('|') < 0:
                logging.error("Possibly missing | at the end of the line %s " % line)
            if not reader:
                reader = line[:line.rfind("|")]  # if '|' is not in string, it will take the whole line
            else:
                cmd_parts = line[:line.rfind("|")].split(':')
                if len(cmd_parts) < 2 or len(cmd_parts) > 3:
                    logging.error('Invalid line %s - ignoring it' % line)
                    continue

                item = {'id': cmd_parts[0], 'name': cmd_parts[1]}
                if len(cmd_parts) == 3:
                    item['bytes'] = cmd_parts[2].replace(' ', '')
                commands.append(item)

        return reader, commands

    @staticmethod
    def make_request(proxy, payload, headers):
        response_data = None
        try:
            logging.debug('Going to to send REST request to GPProREST proxy...')
            r = requests.get(proxy, params=payload, headers=headers)
        except ConnectionError as e:
            logging.error('Problem with connection' + e)
        except:
            logging.error('Problem with connection')
        else:
            # process response
            logging.debug('Response received: ' + r.content.decode())
            for line in r.content.decode().splitlines():
                if line != 'null' and len(line) > 0:
                    response_data = line
                    break
            r.close()

        return response_data

    @staticmethod
    def start_server(proxy_cfg):

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as soc:
            logging.debug('Socket created')

            try:
                soc.bind((proxy_cfg.socket_host, proxy_cfg.socket_port))
                logging.debug(
                    'Socket bind complete. host:{0}, port:{1}'.format(proxy_cfg.socket_host, proxy_cfg.socket_port))
            except socket.error as msg:
                logging.error('Bind failed. Error Code : ' + str(msg[0]) + ' Message ' + msg[1])
                sys.exit()

            # Start listening on socket
            soc.listen(10)
            logging.info('Socket now listening')

            # now keep talking with the client
            while True:
                # wait to accept a connection - blocking call
                conn, addr = soc.accept()
                ip, port = str(addr[0]), str(addr[1])
                logging.info('Connected with ' + ip + ':' + port)

                # start new thread takes with arguments
                new_client = ClientThread(conn, ip, port, proxy_cfg)

                new_client.start()
                new_client.join()

            soc.close()


def main():
    proxy_cfg = ProxyConfig()   # use default config
    SimonaSocketProxy.start_server(proxy_cfg)


if __name__ == "__main__":
    main()

