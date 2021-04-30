#import time
#import os
#from datetime import datetime
#import pandas as pd
import spacy # NOTE pip install -U spacy==2.1.0
             # python -m spacy download en
import neuralcoref  # pip install neuralcoref
import os

root = os.path.dirname(os.path.abspath(__file__))

class Coreference:

    def __init__(self):
        #self.coref_results_df = pd.DataFrame(columns = ['question', 'history', 'coreference', 
        #                                                'scores', 'resolved_question', 'answer'])
        self.conversation_history = ''
        self.question = ''
        #self.corefs = ''
        #self.str_scores = ''
        self.resolved_question = ''
        
        embeddings_dict = {}
        with open(root + "/embeddings_dict/great_exp.txt", "r") as embeddings_file:
            for line in embeddings_file:
                split_line = line.strip().split(":")
                embedding = split_line[1].strip().split()
                embeddings_dict[split_line[0]] = embedding

        self.nlp = spacy.load('en')
        neuralcoref.add_to_pipe(self.nlp, conv_dict=embeddings_dict) 

        #now = datetime.now()
        #self.path_name = os.path.join('coref_results', now.strftime("%Y-%m-%d_%H.%M.%S"))
        #if not os.path.isdir(self.path_name):
        #    os.makedirs(self.path_name)


    def resolve_question(self, question):
        self.question = question
        self.question = self.question.replace('\'s','')
        
        #print("Start history: ", self.conversation_history)

        #prepare text for coreference model

        split_history = self.conversation_history.split("?")
        if len(split_history) > 3:
            self.conversation_history = "?".join(split_history[-3:])

        self.conversation_history += self.question + " " 

        #print("End history: ", self.conversation_history)
          
        doc = self.nlp(self.conversation_history)

        #check if there is any coreference 
        #if true amend the question
        #print(doc)
        if doc._.has_coref: 
            resolved_text = doc._.coref_resolved
            try:
                self.resolved_question =  resolved_text.split("?")[-2]
                self.resolved_question = self.resolved_question + "?"
            except:
                self.resolved_question = self.question
            #print("coref resolved question ", self.resolved_question)
            #self.corefs = doc._.coref_clusters

            #coref_scores={}
            #for key in doc._.coref_scores.keys(): 
            #    if not key.text.lower() in {'she', 'he', 'it', 'they', 'his', 'her', 'him', 'hers', 'their'} :
            #        continue
            #    coref_scores.update({key.text: doc._.coref_scores[ key ]}) 

            #for k in coref_scores: 
            #    self.str_scores+=str(k) + ' ' + str(coref_scores[k]) + '\n' + '\n'
               
            #This line may need to be changed 
            self.conversation_history = resolved_text
            #print("Resolved history: ", self.conversation_history)

        else:
            self.resolved_question = self.question
            #print("no coref resolved question ", self.resolved_question)

        #print(str_scores)

        return self.resolved_question

    #def write_out_results(self, answer):
        #formatted_history = self.conversation_history.replace("?", "\n")
        #self.coref_results_df = self.coref_results_df.append({
        #                'question': self.question,
        #                'history': formatted_history,
        #                'coreference': self.corefs,
        #                'scores': self.str_scores,
        #                'resolved_question': self.resolved_question,
        #                'answer': answer}, 
        #                ignore_index = True)
        #self.coref_results_df.to_csv(os.path.join(self.path_name, 'coref_results.csv'), encoding='utf-8')
        




