import os
import re
import glob

fulltext_dir='/Users/yiweiluo/scientific-debates/data_scraping/fulltexts/'
fulltext_dir_2='/Users/yiweiluo/scientific-debates/data_scraping/cc_fulltexts/'
fnames = set(os.listdir(fulltext_dir)) | set(os.listdir(fulltext_dir_2))

def fulltext_exists(url,fulltext_dir=fulltext_dir):
    fname = url.replace('/','[SEP]')
    return fname+'.txt' in fnames or fname[:90]+'.txt' in fnames

def get_fname(url,fulltext_dir=fulltext_dir):
    fname = url.replace('/','[SEP]')
    if fname+'.txt' in fnames:
        return fname
    else:
        return fname[:90]

def get_fulltext(url,fulltext_dir=fulltext_dir):
    fname = url.replace('/','[SEP]')
    if fname+'.txt' in fnames or fname[:90]+'.txt' in fnames:
        try:
            with open(fulltext_dir+fname+'.txt','r') as f:
                lines = f.readlines()
        except OSError:
            with open(fulltext_dir+fname[:90]+'.txt','r') as f:
                lines = f.readlines()
                
        return lines
    return ""
