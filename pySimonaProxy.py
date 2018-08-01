#!/usr/bin/python3

# Based on Simple socket server using threads by Silver Moon
# (https://www.binarytides.com/python-socket-server-code-example/)

import socket
import sys
import _thread
import time
import re

HOST = ''   # Symbolic name meaning all available interfaces
PORT = 4001 # Arbitrary non-privileged port

CMD_APDU = "APDU"
CMD_RESET = "RESET"
CMD_ENUM = "ENUM"
CMD_SEPARATOR = ":"
CMD_LINE_SEPARATOR = "|"
CMD_RESPONSE_END = "@@"
CMD_RESPONSE_FAIL = "FAIL"


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


# Function for pasing input request
# ><reader name>|><cmd ID>:<"APDU" / "RESET" / "ENUM">:<optional hexa string, e.g. "00A4040304">|
def parse_input_request(s):
    match = re.match(r'>(?P<readerName>.*?)\|>(?P<commandID>.*?):(?P<commandName>.*?):(?P<commandData>.*?)\|', s, re.I)
    if match:
        return InputRequestData(match.group("readerName"), match.group("commandID"),
                                match.group("commandName"),match.group("commandData"))
    else:
        return None


# Function for handling connections. This will be used to create threads
def clientthread(connection):
    # infinite loop so that function do not terminate and thread do not end.
    while True:

        # Receiving from client
        data = connection.recv(4096)

        if len(data) == 0:
            time.sleep(0.1) # sleep little before making another receive attempt
            continue

        print(data)

        value = data.decode("utf-8")
        value = value.strip()

        print('>> ' + value)

        # parse input
        input_req = parse_input_request(value)

        if not input_req:
            print('Invalid input request, skipping')
            continue

        print("Reader: '{0}', CommandID: '{1}', Command: '{2}', CommandData: '{3}'".format(input_req.reader_name,
                                                                                           input_req.command_id,
                                                                                           input_req.command_name,
                                                                                           input_req.command_data))
        response_created = False
        response_data = ""

        # SEND APDU
        if input_req.command_name.lower() == CMD_APDU.lower():
            response_data = "102030409000"   # test response, send to SIMONA instead
            response_created = True

        # RESET
        if input_req.command_name.lower() == CMD_RESET.lower():
            # test response, send to SIMONA instead
            response_data = "621A82013883023F008404524F4F5485030079AD8A0105A1038B01019000"
            response_created = True

        # No valid command found
        if not response_created:
            response_data = CMD_RESPONSE_FAIL
            response_created = True

        response = ">{0}{1}{2}{3}\n".format(input_req.command_id, CMD_SEPARATOR, input_req.command_data,
                                            CMD_RESPONSE_END)
        print(response)
        connection.sendall(response.encode("utf-8"))

    # Terminate connection for given client (if outside loop)
    connection.close()


def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print('Socket created')

    # Bind socket to local host and port
    try:
        s.bind((HOST, PORT))
    except socket.error as msg:
        print('Bind failed. Error Code : ' + str(msg[0]) + ' Message ' + msg[1])
        sys.exit()

    print('Socket bind complete')

    # Start listening on socket
    s.listen(10)
    print('Socket now listening')

    # now keep talking with the client
    while 1:
        # wait to accept a connection - blocking call
        conn, addr = s.accept()
        print('Connected with ' + addr[0] + ':' + str(addr[1]))

        # start new thread takes with arguments
        _thread.start_new_thread(clientthread,(conn,))

    s.close()

if __name__ == "__main__":
    main()

