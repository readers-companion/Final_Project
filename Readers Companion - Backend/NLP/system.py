import sys
import os
from subprocess import Popen, PIPE, STDOUT
import wikipedia
import shutil
import time
from datetime import datetime
from haystack import Finder
from haystack.preprocessor.cleaning import clean_wiki_text
from haystack.preprocessor.utils import convert_files_to_dicts
from haystack.preprocessor.preprocessor import PreProcessor
from haystack.file_converter.txt import TextConverter
from haystack.retriever.sparse import ElasticsearchRetriever
from haystack.retriever.sparse import TfidfRetriever
from haystack.reader.farm import FARMReader
from haystack.reader.transformers import TransformersReader
from haystack.utils import print_answers
import certifi
from haystack.document_store.elasticsearch import ElasticsearchDocumentStore
from haystack.document_store.memory import InMemoryDocumentStore
import json
import socket
import jsonbin

import spacy # NOTE pip install -U spacy==2.1.0
			 # python -m spacy download en
import neuralcoref # pip install neuralcoref
sys.path.append( '.' ) 
from coref import Coreference

client = jsonbin.Client('###')


arguments = sys.argv
port_to_use = int(arguments[1])


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
			

root = os.path.dirname(os.path.abspath(__file__))

# Get the title of the book from the json file

def initiate():
	while True:
		status = json_bin("model_status")
		if status == "loading":
			return json_bin("bookname")
		

book_title = initiate()

def top_50_wiki_results_2(book_title):
	# Function to fetch relevant documents given a book title

	if os.path.isdir(root + "/documents"):
		shutil.rmtree(root + '/documents')
	os.mkdir(root + '/documents')

	page_counter = 1

	titles = []
	titles.append(wikipedia.search(book_title, results=5))
	titles.append(wikipedia.search(book_title + ' character', results=5))

	res = []
	[res.append(x) for x in titles if x not in res]
	titles = res[-1]

	title_exclusions = ("film)", "disambiguation)", "actor)", "actress)",
		"album)", "soundtrack)", "TV series)", "board game)", "video game)",
		"episode)", "illusionist)", "musical)", "TV serial)",
		"magician)", "comedian)", "magic trick)", "filmmaker)", "illusion)",
		"manga)", "play)", "song)", "opera)", "film series)", "miniseries)")

	first_sent_exclusions = ("actor", "actress")

	for title in titles:
		if not any(x in title for x in title_exclusions):
			try:
				page = wikipedia.page(title, auto_suggest=False)
				first_sentence = page.summary.split('.')[0]
				if not any(x in first_sentence for x in first_sent_exclusions):
					content = page.content
					path = os.path.join(root + '/documents', str(page_counter)+'.txt')
					f = open(path, 'w', encoding='utf-8')
					f.write(content)
					f.close()
					print('Created document number ' + str(page_counter)
						+ ' from page ' + title)
					page_counter += 1

			except:
				pass

	return page_counter

if __name__ == "__main__":
	reader_name = "deepset/roberta-base-squad2"
	top_k_retriever = 7
	top_k_reader = 1
	conversational = 'True'

	# Use transfromer reader
	reader = FARMReader(model_name_or_path=reader_name,
		use_gpu=True)

	print('Fetching documents for book ' + book_title)
	document_fetcher_func = top_50_wiki_results_2
	num_docs = document_fetcher_func(book_title)

	print('Fetched ' + str(num_docs) + ' documents for book ' + book_title)

	document_store = ElasticsearchDocumentStore(host="localhost", username="", password="", index="default")
	document_store.delete_all_documents(index="default")
	#document_store = InMemoryDocumentStore()

	doc_dir = root + "/documents"
	dicts = convert_files_to_dicts(dir_path=doc_dir,
		clean_func=clean_wiki_text, split_paragraphs=True)

	# Add documents to the document store
	document_store.write_documents(dicts)

	# Use ElasticsearchRetriever
	retriever = ElasticsearchRetriever(document_store=document_store)
	#retriever = TfidfRetriever(document_store=document_store)

	finder = Finder(reader, retriever)
	top_k_reader = 1

	if conversational == "True":
		coref_model = Coreference()
	
	json_bin("model_status", "online")

	while True:
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM,)
		s.bind(("localhost", int(port_to_use)))
		s.listen(1)
		conn, addr = s.accept()
		data = conn.recv(1024)
		conn.close()
		question = data.decode()
		if question == "EXIT":
			json_bin("model_status", "offline")
			sys.exit()
		print("Initial question ", question)

		if conversational == "True":
			question = coref_model.resolve_question(question)

		print("Input question ", question)

		begin = time.time()
		prediction = finder.get_answers(question=question,
			top_k_retriever=top_k_retriever,
			top_k_reader=top_k_reader)

		j = prediction

		try:
			if j['answers'][0]['answer']:
				answer = j['answers'][0]['answer']
				probability = j['answers'][0]['probability']
				score = j['answers'][0]['score']
			else:
				answer="I don't know the answer unfortunately"
				probability=0
				score=-1
		except:
			answer="I don't know the answer unfortunately"
			probability=0
			score=-1
		
		end = time.time()
		
		json_bin("duration", end)
		json_bin("NLP_Confidence", score)


		print("Answer: " + answer)
		print("Score: " + str(score))
		print("Time taken: " + str(end-begin))

		# Transmit Answer
		x = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		x.connect(("localhost", int(port_to_use - 1)))
		x.sendall(answer.encode())
		x.close()


	# Clean up document store
	document_store.delete_all_documents(doc_id)
	es.indices.delete(index=doc_id)
	if os.path.isdir(root + "/documents"):
		shutil.rmtree(root + '/documents')


