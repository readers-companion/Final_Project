import boto3
import socket
import time
import sys
import os
import os.path
import jsonbin
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

# Boot Backend

client = jsonbin.Client('6021a91306934b65f5305bb6')

def json_bin(*args):
	while True:
		if len(args) == 2:
			try:
				client.store(args[0], args[1])
				break
			except:
				pass
		elif len(args) == 1:
			try:
				x = client.retrieve(args[0])
				return x
			except:
				pass
	
port_to_use = 5000		
		


while True:

	json_bin('status', "asr-novel_select") # Set mode to listen for title
	json_bin('bookname', "") # Set mode to listen for title
	json_bin('model_status', "offline") # Set mode to listen for title

	port_to_use += 3
	

	os.system(f"gnome-terminal --tab -- python3 '/home/sam/Documents/Sheffield University/PGDip/MiniProject/Readers Companion - Backend/NLP/system.py' {port_to_use}")

	listen = True

	status = ""

	while listen:
		if status == "exit":
			s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			s.connect(("localhost", port_to_use))
			s.sendall("EXIT".encode())
			s.close()
			break
			
		if status == "nlp":
			question = json_bin("text")


			# Listen socket
			x = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			x.bind(("localhost", int(port_to_use - 1)))
			x.listen(1)

			# Transmission socket
			s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			s.connect(("localhost", port_to_use))
			s.sendall(question.encode())
			s.close()

			conn, addr = x.accept()
			data = conn.recv(1024)
			conn.close()        
			answer = data.decode()
			
			json_bin('text', answer)
			json_bin('status', 'synthesis')
		status = json_bin("status")
		time.sleep(1)
