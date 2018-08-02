#!/usr/bin/python3

# Based on Simple socket server using threads by Silver Moon
# (https://www.binarytides.com/python-socket-server-code-example/)

import _thread
import json
import logging
import coloredlogs
import re
import requests
import socket
import sys
import time

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
    test_simulated_card = False # if true, simulated response is send back

    socket_host = ''   # Symbolic name meaning all available interfaces
    socket_port = 4001 # Arbitrary non-privileged port

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


class SimonaSocketProxy:
    # Function for pasing input request
    # ><reader name>|><cmd ID>:<"APDU" / "RESET" / "ENUM">:<optional hexa string, e.g. "00A4040304">|
    @staticmethod
    def parse_input_request(s):
        match = re.match(r'>(?P<readerName>.*?)\|>(?P<commandID>.*?):(?P<commandName>.*?):(?P<commandData>.*?)\|', s, re.I)
        if match:
            command_data = match.group("commandData")
            command_data = command_data.replace(' ', '')
            return InputRequestData(match.group("readerName"), match.group("commandID"),
                                    match.group("commandName"), command_data)
        else:
            return None

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

    # Function for handling connections. This will be used to create threads
    @staticmethod
    def client_thread(connection, ip, port, proxy_cfg):
        try:
            # infinite loop so that function do not terminate and thread do not end.
            while True:
                # Receiving from client
                data = connection.recv(4096)

                if len(data) == 0:
                    time.sleep(0.1) # sleep little before making another receive attempt
                    continue

                value = data.decode("utf-8")
                value = value.strip()

                logging.debug(">> " + value)

                # parse input
                input_req = SimonaSocketProxy.parse_input_request(value)

                if not input_req:
                    logging.error('Invalid input request, skipping')
                    continue

                logging.info("Reader:'{0}',CommandID:'{1}',Command:'{2}',Data:'{3}'".format(input_req.reader_name,
                                                                                            input_req.command_id,
                                                                                            input_req.command_name,
                                                                                            input_req.command_data))
                # for testing with local card, rename Simona readers to local one
                if proxy_cfg.gpprorest_test_with_local_reader:
                    if input_req.reader_name.find('Simona') != -1:
                        logging.debug('Changing remote reader {0} to local reader {1} for testing'
                                      .format(input_req.reader_name, proxy_cfg.gpprorest_test_local_reader))
                        input_req.reader_name = proxy_cfg.gpprorest_test_local_reader

                response_data = None

                # SEND APDU
                if input_req.command_name.lower() == CMD_APDU.lower():
                    if proxy_cfg.test_simulated_card:
                        response_data = "102030409000"
                    else:
                        payload = {'apdu': input_req.command_data, 'terminal': input_req.reader_name}
                        response_data = SimonaSocketProxy.make_request(proxy_cfg.gpprorest_proxy, payload, proxy_cfg.gpprorest_http_headers)

                # RESET
                if input_req.command_name.lower() == CMD_RESET.lower():
                    if proxy_cfg.test_simulated_card:
                        # test response, send to SIMONA instead
                        response_data = "621A82013883023F008404524F4F5485030079AD8A0105A1038B01019000"
                    else:
                        payload = {'reset': '1', 'terminal': input_req.reader_name, 'close': '1'}
                        response_data = SimonaSocketProxy.make_request(proxy_cfg.gpprorest_proxy, payload, proxy_cfg.gpprorest_http_headers)

                # No valid command found
                if not response_data:
                    response_data = CMD_RESPONSE_FAIL

                response = ">{0}{1}{2}{3}\n".format(input_req.command_id, CMD_SEPARATOR, response_data,
                                                    CMD_RESPONSE_END)
                logging.info(response)
                connection.sendall(response.encode("utf-8"))
        except:
            logging.info('Exception in serving response, ending thread')
            logging.info('\n')

        # Terminate connection for given client (if outside loop)
        connection.close()
        return

    @staticmethod
    def start_server(proxy_cfg):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as soc:
            # this is for easy starting/killing the app
            soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            logging.debug('Socket created')

            # Bind socket to local host and port
            try:
                soc.bind((proxy_cfg.socket_host, proxy_cfg.socket_port))
                logging.debug('Socket bind complete')
            except socket.error as msg:
                logging.error('Bind failed. Error Code : ' + str(msg[0]) + ' Message ' + msg[1])
                sys.exit()

            # Start listening on socket
            soc.listen(10)
            logging.info('Socket now listening')

            from threading import Thread

            # now keep talking with the client
            while True:
                # wait to accept a connection - blocking call
                conn, addr = soc.accept()
                ip, port = str(addr[0]), str(addr[1])
                logging.info('Connected with ' + ip + ':' + port)

                # start new thread takes with arguments
                Thread(target=SimonaSocketProxy.client_thread, args=(conn, ip, port, proxy_cfg)).start()

            soc.close()


def main():
    proxy_cfg = ProxyConfig()   # use default config
    SimonaSocketProxy.start_server(proxy_cfg)

if __name__ == "__main__":
    main()

