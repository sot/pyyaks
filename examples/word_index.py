#!/usr/bin/env python

import glob
import sys, os

import pyyaks.task
import pyyaks.logger
import pyyaks.context
from pyyaks.task import task, chdir, setenv, depends
from pyyaks.context import render, ContextDict, render_args

logger = pyyaks.logger.get_logger()

# Create a context dictionary to store attributes of the input file
# that is being processed
INPUT = ContextDict('input')
Input = INPUT.accessor()

# Create a context dictionary to store file name definitions
FILE = ContextDict('file', basedir='word_index')
FILE.update({'out_dir':     '{{input.filebase}}',
             'file_link':   '{{input.filebase}}/{{input.filename}}',
             'word_alpha':  '{{input.filebase}}/word_alpha',
             'word_freq':   '{{input.filebase}}/word_freq',
             'index':       '{{input.filebase}}/index',
             })
File = FILE.accessor()


######################################################################################
@task()
@depends(targets=[FILE['out_dir']])
def make_out_dir():
    """Make the output directory where output created by the processing for
    this input file"""
    make_dir(File['out_dir'])

######################################################################################
@task()
@depends(depends=[FILE['input_file']],
         targets=[FILE['file_link']])
def make_file_link():
    """Make a link in the output directory to the original input file"""
    pyyaks.fileutil.make_local_copy(File['input_file'], File['file_link'])

######################################################################################
@task()
@depends(depends=[FILE['file_link']],
         targets=[INPUT['word_count']])
def calc_word_count():
    """Calculate the frequency of words in file"""
    word_count = {}
    text = open(File['file_link']).read()
    for word in re.findall(r'\w+', text):
        word_count.setdefault(word, 0) += 1
    Input.word_count = word_count
    print word_count

filenames = glob.glob('*.py')
for filename in filenames:
    FILE['input_file'] = os.path.abspath(filename)

    INPUT.clear()
    Input['filepath'], Input['filename'] = os.path.split(FILE['input_file'].abs)
    Input['filebase'], Input['fileext'] = os.path.splitext(Input['filename'])
    
    pyyaks.task.start(message='Processing file {{file.input_file}}')

    make_out_dir()                      # Make output directory for this filename
    make_file_link()                    # Make a local link to input file

    pyyaks.task.end(message='Processing file {{file.input_file}}')



