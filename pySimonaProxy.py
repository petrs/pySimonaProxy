#!/usr/bin/python3

# Based on Simple socket server using threads by Silver Moon
# (https://www.binarytides.com/python-socket-server-code-example/)

import socket
import sys
import _thread
import time
 
HOST = ''   # Symbolic name meaning all available interfaces
PORT = 4001 # Arbitrary non-privileged port

CMD_APDU = "APDU"
CMD_RESET = "RESET"
CMD_ENUM = "ENUM"
CMD_SEPARATOR = ":"
CMD_LINE_SEPARATOR = "|"
CMD_RESPONSE_END = "@@"
CMD_RESPONSE_FAIL = "FAIL"

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

        # Process line by line(separate by CMD_LINE_SEPARATOR)
        # 1st line == reader name with format: '><reader name>@'
        if value[0] != '>' :
            print('> was expected at begin')

        pos = value.find(CMD_LINE_SEPARATOR)
        if pos != -1:
            readerName = value[1 : pos - 1]
            pos += 1
        else:
            print("Missing line separator " + CMD_LINE_SEPARATOR)
            continue

        # 2nd line == command with format:
        # '><cmd ID>:<"APDU" / "RESET" / "ENUM">:<optional hexa string, e.g. "00A4040304">@'
        if value[pos] != '>':
            print("'>'was expected at begin")

        pos += 1

        pos2 = value.find(CMD_SEPARATOR, pos)
        uniqueCmdID = value[pos : pos2]
        pos = pos2 + 1

        pos2 = value.find(CMD_SEPARATOR, pos)
        command = value[pos : pos2]
        pos = pos2 + 1

        pos2 = value.find(CMD_LINE_SEPARATOR, pos)
        commandData = value[pos : pos2]
        pos = pos2 + 1

        # The rest of input is ignored

        print("Reader: '{0}', CommandID: '{1}', Command: '{2}', CommandData: '{3}'".format(readerName, uniqueCmdID, command, commandData))

        bReponseCreated = False
        responseData = ""

        # SEND APDU
        if command.lower() == CMD_APDU.lower():
            responseData = "102030409000"   # test response, send to SIMONA instead
            bReponseCreated = True

        # RESET
        if command.lower() == CMD_RESET.lower():
            # test response, send to SIMONA instead
            responseData = "621A82013883023F008404524F4F5485030079AD8A0105A1038B01019000"
            bReponseCreated = True

        # No valid command found
        if not bReponseCreated:
            responseData = CMD_RESPONSE_FAIL
            bReponseCreated = True

        response = ">{0}{1}{2}{3}\n".format(uniqueCmdID, CMD_SEPARATOR, responseData, CMD_RESPONSE_END)
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