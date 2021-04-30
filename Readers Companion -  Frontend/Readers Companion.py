from __future__ import division

import re
import sys
import csv
import time
import os
import boto3
import jsonbin
import operator
from fuzzywuzzy import fuzz
import google.cloud.speech as speech
import pyaudio
from six.moves import queue
import requests
from pydub import AudioSegment
from pydub.playback import play
import threading
import queue


# jsonbin


def synthesise(words, file="data/synthesis.mp3"):
	polly_client = boto3.Session(
				aws_access_key_id="AKIA5WPG66PZ6FRWS6LU",
		aws_secret_access_key="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",
		region_name='us-west-2').client('polly')

	response = polly_client.synthesize_speech(VoiceId='Amy',
				OutputFormat='mp3',
				Text = words)

	file = open(file, 'wb')
	file.write(response['AudioStream'].read())
	file.close()

client = jsonbin.Client('6021a91306934b65f5305bb6')


# Audio recording parameters
RATE = 16000
CHUNK = int(RATE / 10)  # 100ms

# Absolute Path
root = os.path.dirname(os.path.abspath(__file__))

class MicrophoneStream(object):
	"""Opens a recording stream as a generator yielding the audio chunks."""
	def __init__(self, rate, chunk):
		self._rate = rate
		self._chunk = chunk

		# Create a thread-safe buffer of audio data
		self._buff = queue.Queue()
		self.closed = True

	def __enter__(self):
		self._audio_interface = pyaudio.PyAudio()
		self._audio_stream = self._audio_interface.open(
			format=pyaudio.paInt16,
			# The API currently only supports 1-channel (mono) audio
			# https://goo.gl/z757pE
			channels=1, rate=self._rate,
			input=True, frames_per_buffer=self._chunk,
			# Run the audio stream asynchronously to fill the buffer object.
			# This is necessary so that the input device's buffer doesn't
			# overflow while the calling thread makes network requests, etc.
			stream_callback=self._fill_buffer,
		)

		self.closed = False
		return self

	def __exit__(self, type, value, traceback):
		self._audio_stream.stop_stream()
		self._audio_stream.close()
		self.closed = True
		# Signal the generator to terminate so that the client's
		# streaming_recognize method will not block the process termination.
		self._buff.put(None)
		self._audio_interface.terminate()

	def _fill_buffer(self, in_data, frame_count, time_info, status_flags):
		"""Continuously collect data from the audio stream, into the buffer."""
		self._buff.put(in_data)
		return None, pyaudio.paContinue

	def generator(self):
		while not self.closed:
			# Use a blocking get() to ensure there's at least one chunk of
			# data, and stop iteration if the chunk is None, indicating the
			# end of the audio stream.
			chunk = self._buff.get()
			if chunk is None:
				return
			data = [chunk]

			# Now consume whatever other data's still buffered.
			while True:
				try:
					chunk = self._buff.get(block=False)
					if chunk is None:
						return
					data.append(chunk)
				except queue.Empty:
					break

			yield b''.join(data)


class sThread (threading.Thread):
	def __init__(self, name, q, qLock, responses):
	   threading.Thread.__init__(self)
	   self.name = name
	   self.q = q
	   self.qLock = qLock
	   self.responses = responses
	def run(self):
		print ("Starting " + self.name)
		StreamToQueue(self.q, self.qLock, self.responses)
		print ("Exiting " + self.name)

def StreamToQueue(q, qLock, responses):
	for response in responses:
		if not response.results:
			continue

		# The `results` list is consecutive. For streaming, we only care about
		# the first result being considered, since once it's `is_final`, it
		# moves on to considering the next utterance.
		result = response.results[0]
		if not result.alternatives:
			continue
	
		qLock.acquire()
		q.put(result)
		qLock.release()


def listen_write_loop(qResponses, wFile, qLock):
	"""Iterates through server responses and prints them.

	The responses passed is a generator that will block until a response
	is provided by the server.

	Each response may contain multiple results, and each result may contain
	multiple alternatives; for details, see https://goo.gl/tjCPAU.  Here we
	print only the transcription for the top alternative of the top result.

	In this case, responses are provided for interim results as well. If the
	response is an interim one, print a line feed at the end of it, to allow
	the next result to overwrite it, until the response is a final one. For the
	final one, print a newline to preserve the finalized transcription.
	"""

	num_chars_printed = 0
	transcript=""
	keywordTime = 0
	listeningTime = 20
	isFinal = False
	lastResultTime = time.time()
	lastPrintTime = time.time()
	active_tone = False
	while not isFinal:

		overwrite_chars = ' ' * (num_chars_printed - len(transcript))

		qLock.acquire()
		if not qResponses.empty():
			result = qResponses.get()
			qLock.release()
			lastResultTime = time.time()
			isFinal = result.is_final			
			transcript = result.alternatives[0].transcript
			if "bookworm" in transcript.lower() and not active_tone:
				play_audio("data/notification/start_listen.mp3")
				active_tone = True
			if not isFinal:
				sys.stdout.write(transcript + overwrite_chars + '\r')
				sys.stdout.flush()
			else:
				print(transcript)
			num_chars_printed = len(transcript)
		else:
			qLock.release()
			#print(threadName, "Empty queue")
			if lastResultTime == 0:
				print(isFinal, "Ticking over")
			elif time.time() - lastResultTime > 1.5: # and time.time() - lastPrintTime > 1:
				bookworms = transcript.lower().split(" ").count("bookworm")
				if bookworms == 1:
					break
				else:
					lastResultTime = time.time()
					continue
	bookworms = transcript.lower().split(" ").count("bookworm")
	if transcript.lower().replace("bookworm","").isspace():
		return False, None
	if re.search(r'\b(Bookworm exit|Bookworm quit)\b', transcript, re.I):
		play_audio("data/notification/stop_listen.mp3")
		print('Exiting..')
		return True, "Bookworm exit"
	if "bookworm " in transcript.lower():
		play_audio("data/notification/stop_listen.mp3")
		return True, transcript
	else:
		return False, None


def main(context):
	good = False
	# See http://g.co/cloud/speech/docs/languages
	# for a list of supported languages.
	language_code = 'en-UK'  # a BCP-47 language tag

	outFile = open("data/output.csv", mode='a+')
	wFile = csv.writer(outFile)

	cli= speech.SpeechClient.from_service_account_json(root + "/data/credentials.json")


	namePhrases = context

	# Add default keyword to the context
	namePhrases.append("Bookworm")
	namePhrases.append("Hey Bookworm")
	namePhrases.append("Ok Bookworm")

	speech_context = speech.SpeechContext(phrases = namePhrases)


	config = speech.RecognitionConfig(
		encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
		sample_rate_hertz=RATE,
		language_code=language_code,
		max_alternatives = 3, 
		speech_contexts = [speech_context])
	streaming_config = speech.StreamingRecognitionConfig(
		config=config,
		interim_results=True)
		
	# Listen
	with MicrophoneStream(RATE, CHUNK) as stream:
		audio_generator = stream.generator()
		requests = (speech.StreamingRecognizeRequest(audio_content=content)
					for content in audio_generator)

		responses = cli.streaming_recognize(streaming_config, requests)

		queueLock = threading.Lock()
		workQueue = queue.Queue(100)
		streamThread = sThread("streamThread", workQueue, queueLock, responses)
		streamThread.setDaemon(True)
		streamThread.start()
		#print("Started thread")

		# Now, put the transcription responses to use.
		while good == False:
			good, utterance = listen_write_loop(workQueue, wFile, queueLock)
		if len(utterance) != 0:
			if good == True:
				utterance = utterance.replace("bookworm", "Bookworm")
				if client.retrieve("status") == "asr-novel_select":
					novel = utterance.split("Bookworm ")[-1]
					return novel
				speech_recognition_active = False
				utterance_raw = utterance
				utterance = utterance.split("Bookworm ")[-1]
				print("Output: {}".format(utterance))
				utterance_raw = "     " + utterance_raw
				check_shutdown = utterance_raw[-5:]
				if check_shutdown.lower() == " exit":
					client.store("status", "exit")
					client.store("front_end", "exit")
					play_audio("data/notification/shutdown.mp3")
					return "exit"
				else:
					client.store('status', 'nlp')
					client.store('text', utterance)
				return utterance


def download_file_from_google_drive(id, destination):
	URL = "https://docs.google.com/uc?export=download"

	session = requests.Session()

	response = session.get(URL, params = { 'id' : id }, stream = True)
	token = get_confirm_token(response)

	if token:
		params = { 'id' : id, 'confirm' : token }
		response = session.get(URL, params = params, stream = True)

	save_response_content(response, destination)

def get_confirm_token(response):
	for key, value in response.cookies.items():
		if key.startswith('download_warning'):
			return value

	return None

def save_response_content(response, destination):
	CHUNK_SIZE = 32768
	with open(destination, "wb") as f:
		for chunk in response.iter_content(CHUNK_SIZE):
			if chunk: # filter out keep-alive new chunks
				f.write(chunk)

def play_audio(filename):
	music = AudioSegment.from_mp3(filename)
	play(music)

novel_list = ["a-christmas-carol", "alices-adventures-in-wonderland", "around-the-world-in-80-days", "frankenstein", "jane-eyre", "the-tenant-of-wildfell-hall", "the-great-gatsby", "the-three-musketeers", "the-war-of-the-worlds", "war-and-peace"]

novel_list = [x.replace("-"," ") for x in novel_list]

def check_novel(text_input, novel_list):
	novel_ranked = {}
	for novel in novel_list:
		novel_ranked[novel] = int(fuzz.ratio(text_input, novel))
	novel_ranked = sorted(novel_ranked.items(),key=operator.itemgetter(1),reverse=True)
	selected_novel = novel_ranked[0][0]
	return selected_novel, novel_ranked[0][1]


	
play_audio("data/notification/initial_intro.mp3") # Play intro audio
time.sleep(1) #  Wait 1 second
play_audio("data/notification/select_novel.mp3") # Play novel select audio
client.store('status', "asr-novel_select") # Set mode to listen for title
status = "asr-novel_select" # status set to listen for title
fuzziness = 0
while fuzziness <= 70:
	novel = main(novel_list)
	novel = novel.lower()
	novel, fuzziness = check_novel(novel, novel_list)
	if fuzziness >= 70:
		break
	play_audio("data/notification/invalid_book.mp3")
client.store('text', "You have selected {}".format(novel))
client.store('status', "synthesis")
client.store('bookname', novel)
client.store("model_status", "loading")
synthesise(f"You have selected {novel}")
play_audio("data/synthesis.mp3")
os.remove("data/synthesis.mp3")
play_audio("data/notification/loading.mp3")


while client.retrieve("model_status") != "online":
	time.sleep(1)

intro = True

novel_file = "context/" + novel.replace(" ","-") + "_context.txt"

with open(novel_file, "r") as novel_txt:
	data = novel_txt.read()
	novel_context = data.split("\n")

client.store('status', "asr")

while client.retrieve("front_end") != "exit":
	status = client.retrieve("status")
	if status == "synthesis-speak":
		play_audio("data/synthesis.mp3")
		os.remove("data/synthesis.mp3")
		client.store('status', "asr")
	if status == "synthesis":
		if float(client.retrieve("NLP_Confidence")) < 0 and client.retrieve("model_status") == "online":
			play_audio("data/notification/no_good_answer.mp3")
			client.store('status', "asr")
		else:
			text = client.retrieve("text")
			synthesise(text)
			client.store('status', 'synthesis-speak')
	if status == "asr":
		if intro == True:
			play_audio("data/notification/intro_final.mp3")
			intro = False
		utterance = main(novel_context)
		if utterance != "exit":
			synthesise(f"The answer to your question {utterance} is", file="data/question.mp3")
			time.sleep(4)
			play_audio("data/question.mp3")
			os.remove("data/question.mp3")
	time.sleep(1)

client.store("front_end", "startup")



