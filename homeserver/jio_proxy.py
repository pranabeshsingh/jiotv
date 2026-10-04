#!/usr/bin/env python3
"""
JioTV Outbound Proxy for Home Network Client (e.g. homeserver).
Binds outbound traffic specifically to the residential Jio network interface (192.168.130.2 / enp2s0)
to bypass datacenter IP restrictions (HTTP 450) and VPN tunnels.
"""

import socket
import select
import threading
import sys

# Tailscale interface / IP of homeserver
LISTEN_HOST = "100.107.251.122"
LISTEN_PORT = 8888

# Local physical IP on the home Jio Fiber router subnet
SOURCE_IP = "192.168.130.2"


def forward_data(src, dst):
    try:
        while True:
            data = src.recv(32768)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try:
            src.shutdown(socket.SHUT_RD)
        except Exception:
            pass
        try:
            dst.shutdown(socket.SHUT_WR)
        except Exception:
            pass


def handle_client(client_sock):
    try:
        request_line = b""
        while b"\r\n" not in request_line:
            chunk = client_sock.recv(1)
            if not chunk:
                client_sock.close()
                return
            request_line += chunk

        parts = request_line.decode("latin1").split()
        if len(parts) < 2:
            client_sock.close()
            return

        method, target = parts[0], parts[1]

        headers = b""
        while b"\r\n\r\n" not in headers:
            chunk = client_sock.recv(4096)
            if not chunk:
                break
            headers += chunk

        if method.upper() == "CONNECT":
            # HTTPS tunneling
            host, port_str = target.split(":")
            port = int(port_str)
            remote_sock = socket.create_connection(
                (host, port), source_address=(SOURCE_IP, 0), timeout=15
            )
            client_sock.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")

            t1 = threading.Thread(target=forward_data, args=(client_sock, remote_sock))
            t2 = threading.Thread(target=forward_data, args=(remote_sock, client_sock))
            t1.daemon = True
            t2.daemon = True
            t1.start()
            t2.start()
            t1.join()
            t2.join()
            client_sock.close()
            remote_sock.close()
        else:
            # Plain HTTP request
            url_part = target
            if url_part.startswith("http://"):
                url_part = url_part[7:]
            host_header = url_part.split("/")[0]
            if ":" in host_header:
                host, port_str = host_header.split(":")
                port = int(port_str)
            else:
                host = host_header
                port = 80

            remote_sock = socket.create_connection(
                (host, port), source_address=(SOURCE_IP, 0), timeout=15
            )
            path = "/" + "/".join(url_part.split("/")[1:]) if "/" in url_part else "/"
            new_req = f"{method} {path} HTTP/1.1\r\n".encode("latin1") + headers
            remote_sock.sendall(new_req)

            t1 = threading.Thread(target=forward_data, args=(client_sock, remote_sock))
            t2 = threading.Thread(target=forward_data, args=(remote_sock, client_sock))
            t1.daemon = True
            t2.daemon = True
            t1.start()
            t2.start()
            t1.join()
            t2.join()
            client_sock.close()
            remote_sock.close()
    except Exception:
        try:
            client_sock.close()
        except Exception:
            pass


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((LISTEN_HOST, LISTEN_PORT))
    server.listen(128)
    print(f"Proxy listening on {LISTEN_HOST}:{LISTEN_PORT}, outbound via {SOURCE_IP}")
    while True:
        client, addr = server.accept()
        t = threading.Thread(target=handle_client, args=(client,))
        t.daemon = True
        t.start()


if __name__ == "__main__":
    main()
