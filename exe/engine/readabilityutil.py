'''
Created on Sep 29, 2014

@author: mike
'''

from textstatistics.textstatistics import TextStatistics
from exe import globals as G

import os

class ReadabilityUtil(object):
    '''
    classdocs
    '''
    
    text_idevices = {"FreeTextIdevice" : ["content"]
                     }
    

    def __init__(self, params = None):
        '''
        Constructor
        '''
        pass
    
    
    def get_package_readability_info(self, package):
        text = self.node_to_text(package.root)
        result = self.make_info_arr_for_text(text)
        num_pages = self.page_count(package.root)
        
        result["words_per_page"] =  {
                 "average" : round(float(result['word_count']['max'])
                                    /float(num_pages)),
                 "label" : x_("Words Per Page")
        }
        
        return result
    
    def make_info_arr_for_text(self, text):
        ts = TextStatistics(text)
        distinct_word_count = ts.word_count_distinct()
        total_word_count = ts.word_count()
        
        result = {
            "syllables_per_word" : {
                    "max" : ts.max_syllables_per_word(),
                    "average" : round(ts.average_syllables_per_word(), 2),
                    "label" : x_("Syllables Per Word")
            },
            "word_count" : {
                "max" : total_word_count,
                "label" : x_("Word Count"),
            },
            "words_per_sentence" : {
                "average" : ts.average_words_per_sentence(),
                "max" : ts.max_words_per_sentence(),
                "label" : x_("Words Per Sentence")
            },
            "different_words_total_ratio" : {
                "average" : str(round(float(total_word_count) / 
                                        float(distinct_word_count), 2)),
                 "label" : x_("Number words total per unique word")
                                             
            },
            "num_different_words" : {
                 "max" : distinct_word_count,
                 "label" : x_("Total number of unique words")
            }
                  
        }
        
        return result
    
    def page_count(self, node):
        num_pages = 1
        for child in node.children:
            num_pages += self.page_count(child)
            
        return num_pages 

        
    def node_to_text(self, node, recursive = True):
        text = ""
        for idevice in node.idevices:
            class_name =idevice.__class__.__name__ 
            if class_name in ReadabilityUtil.text_idevices:
                txt_fields = ReadabilityUtil.text_idevices[class_name]
                for field_name in txt_fields:
                    dev_content = getattr(idevice, field_name).content
                    text += dev_content
                
        for child in node.children:
            text += self.node_to_text(child)
              
        return text
    
    def list_readability_presets(self, extension_type):
        '''
        Will list the readability presets in the directory
        extension_type - extension without prefixed .
        '''
        extension = "." + extension_type
        result_list = []
        
        for file_name in os.listdir(G.application.config.readabilityPresetsDir):
            if file_name[-4:] == extension:
                result_list.append(file_name)
                
        
        return result_list
        
    