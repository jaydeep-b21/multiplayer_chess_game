import socket
import struct
import time

def make_packet(_id, payload):
    b = bytes([_id]) + payload

    return struct.pack("I", len(b)) + b

B_EMPTY = b""
PACKET_PING = 0
PACKET_HANG = 1

CLIENT_CLIENT = "client"
CLIENT_SERVERCLIENT = "server_client"

class Client:
    def __init__(self, socket, _kind=CLIENT_CLIENT):
        self._kind = _kind
        
        self.socket = socket
        self.connected = True

        self.socket.settimeout(0.0)
        
        self.last_ping_sent = 0
        self.last_ping_received = time.time()

        self.buf = b""

    ## API use
    @staticmethod
    def new_connection(addr):
        sock = socket.socket()
        sock.connect(addr)

        return Client(sock)

    ## internal use
    def read_packets(self):
        ## is an index present?
        if len(self.buf) >= 4:
            packet_length = struct.unpack("I", self.buf[:4])[0]

            ## whole packet is present
            if len(self.buf) >= packet_length+4:
                packet_buf = self.buf[:4+packet_length]

                ## read the packet: id, payload
                packet = (packet_buf[4], packet_buf[5:])
                print(packet)

            ## move the buffer
            self.buf = self.buf[4+packet_length:]

            return [packet, *self.read_packets()]
        
        else:
            return []

    ## API use
    def send(self, buf):
        if not self.connected:
            raise Exception("Client not connected!")

        self._send(buf)

    ## for internal use
    def _send(self, buf):
        if not self.connected:
            return
        
        try:
            self.socket.sendall(buf)
        except:
            print(self._kind, "sending error, disconnecting")
            self.connected = False

    def ping(self):
        self._send(make_packet(PACKET_PING, B_EMPTY))
        self.last_ping_sent = time.time()

    ## API use
    def disconnect(self):
        if not self.connected:
            raise Exception("Client not connected!")

        self._disconnect()

    ## internal use
    def _disconnect(self):
        if not self.connected:
            return
        
        ## hack to make sure hang packet gets through
        self.socket.settimeout(20)
        self._send(make_packet(PACKET_HANG, B_EMPTY))
        self.connected = False

    ## update, handles internal stuff and is for API use
    def update(self):
        if not self.connected:
            return None
        
        try:
            data = self.socket.recv(1024)
            if data:
                self.buf += data
                
        except socket.error:
            pass

        ## some internal packets get handled internally
        ## all get returned
        packets = list(self.read_packets())

        ## internal handling
        ## sending ping
        if (time.time() - self.last_ping_sent) > 5:
            ##print(self._kind, "pinging")
            self.ping()

        ## iterate packets (only internal packets are handled)
        for p_id, payload in packets:

            ## received ping
            if p_id == PACKET_PING:
                ##print(self._kind, "ping received", self.last_ping_received)
                self.last_ping_received = time.time()

            ## received hang
            if p_id == PACKET_HANG:
                print(self._kind, "hang")
                self.socket.close()
                self.connected = False
                return

        ## check when last received ping
        if (time.time() - self.last_ping_received) > 10:
            ## server not responding, goodbye
            print(self._kind, "not responding")
            self._disconnect()
            

        return packets

class Server:
    def __init__(self, addr):
        self.socket = socket.socket()
        self.socket.bind(addr)
        self.socket.listen()
        
        self.running = True

        self.socket.settimeout(0.0)

        self.clients = {}
        self.new_clients = []

        self.cl_idx = 0

    def broadcast(self, buf):
        for cl_idx,cl in self.clients.items():
            cl._send(buf)

    def get_clients(self):
        return list([(k, v) for k,v in self.clients.items()])

    def get_new_clients(self):
        tmp = self.new_clients
        self.new_clients = []
        return tmp

    def get_num_clients(self):
        return len(self.clients.items())

    def get_client(self, i):
        return self.clients[i]
        
    def stop(self):
        print("stopping server")
        self.running = False
        self.socket.close()

    def update(self):
        if not self.running:
            return
    
        try:
            conn,addr = self.socket.accept()

            print(f"server: client id {self.cl_idx} connected")

            self.clients[self.cl_idx] = Client(conn, _kind=CLIENT_SERVERCLIENT)
            self.new_clients.append(self.cl_idx)
            self.cl_idx += 1
        except BlockingIOError:
            pass

        ## remove clients that are not connected
        rm = []
        for cl_id in list(self.clients.keys()):
            if not self.clients[cl_id].connected:
                self.clients.pop(cl_id)

                ## make sure it's no longer a new client
                if cl_id in self.new_clients:
                    self.new_clients.remove(cl_id)

                print(f"server: client id {cl_id} disconnected")

        ## return client updates as a dict
        d_updates = {}
        for i in self.clients:
            update = self.clients[i].update()
            if not update is None:
                d_updates[i] = update

        return d_updates

##s = Server(("127.0.0.1", 1337))
##c = Client.new_connection(("127.0.0.1", 1337))

##while len(s.clients) == 0:
##    s.update()
