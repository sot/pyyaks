#!/usr/bin/env python
import os
import re
import sys
import cPickle as pickle
import tempfile
import math
import shutil
import time
import multiprocessing

import Ska.Shell
import Ska.File
import numpy as np

import pyyaks.task
import pyyaks.logger
import pyyaks.context
from pyyaks.task import task, chdir, setenv, depends, make_dir
from pyyaks.context import render, ContextDict, render_args

prog_dir = os.path.dirname(__file__)

# Initialize output logging
loglevel = pyyaks.logger.INFO
logger = pyyaks.logger.get_logger(level=loglevel, format='%(process)d: %(message)s')

# Define src vars
SRC = pyyaks.context.ContextDict('src')
SRC['ra'].format = '%.4f'
SRC['dec'].format = '%.4f'
Src = SRC.accessor()

# Define file aliases
FILE = pyyaks.context.ContextDict('file', basedir='testmulti')
FILE.update(dict(
    resources_dir = 'resources/',
    index_template ='resources/index_template',
    pyaxx =         'resources/pyaxx',
    obs_dir =       'obs{{src.obsid}}/',
    obs_asol =      'obs{{src.obsid}}/asol',
    ccd_dir =       'obs{{src.obsid}}/ccd{{src.ccdid}}/',
    ccd_evt =       'obs{{src.obsid}}/ccd{{src.ccdid}}/acis_evt2',
    ccd_expmap =    'obs{{src.obsid}}/ccd{{src.ccdid}}/expmap',
    info =          'obs{{src.obsid}}/ccd{{src.ccdid}}/info'))
File = FILE.accessor()

srcs = ((0., 20., 100, 2),
        (1., 21., 101, 2),
        (2., 22., 102, 2),
        (13., 23., 103, 2),
        (4., 24., 104, 2),
        (5., 25., 105, 2),
        (6., 26., 106, 2),
        (17., 27., 107, 2),
        (18., 28., 108, 2),
        )

#####################################################################################
# Task definitions
#####################################################################################
@task()
@depends(targets=[FILE['ccd_dir']])
def make_xdat_and_src_dirs():
    make_dir(File['ccd_dir'])
    time.sleep(5)
    # time.sleep(Src.ra)

###################################################################################
@task()
def restore_src(filename):
    if os.path.exists(filename):
        logger.verbose('Restoring from %s' % filename)
        time.sleep(3)
        # time.sleep(np.random.uniform(3, 5.))
        SRC.update(pickle.load(open(filename, 'r')))
        
###################################################################################
@task()
def store_src(filename):
    logger.verbose('Storing to %s' % filename)
    time.sleep(3)
    # time.sleep(np.random.uniform(3, 5.))
    pickle.dump(SRC, open(filename, 'w'))

###################################################################################
@task()
@depends(depends=[os.path.join(prog_dir, 'pyaxx.css'),
                  os.path.join(prog_dir, 'index_template.html')],
         targets=[FILE['pyaxx.css'],
                  FILE['index_template.html']])
def copy_resources():
    time.sleep(1)
    make_dir(File['resources_dir'])
    for name in ('pyaxx.css', 'index_template.html'):
        logger.verbose('Copying %s to resources' % name)
        shutil.copy(os.path.join(prog_dir, name), File[name])

###################################################################################
@task()
@depends(depends=[SRC['ra'],
                  SRC['dec']],
         targets=[SRC[x] for x in ('x', 'y')])
# @setenv(ciaoenv)
def set_coords():
    Src.x = Src.ra / 10.
    Src.y = Src.dec/ 20.


#####################################################################################
# Main pipeline function
#####################################################################################
def pipeline(src):
    # Clear the SRC contextdict and then populate from objlist table rows
    SRC.clear()
    SRC['ra'], SRC['dec'], SRC['obsid'], SRC['ccdid'] = src
    SRC['xdat_id'] = '%s_%s' % (Src.ra, Src.dec)

    pyyaks.task.start(message='Processing for %s obsid=%d ccdid=%d' % (Src['xdat_id'], Src['obsid'], Src['ccdid']))

    restore_src(File['info.pickle'])
    make_xdat_and_src_dirs()
    copy_resources()
    store_src(File['info.pickle'])
    
    pyyaks.task.end(message='Processing for %s obsid=%d ccdid=%d' % (Src['xdat_id'], Src['obsid'], Src['ccdid']))
    
#####################################################################################
# Main processing loop
#####################################################################################

pool = multiprocessing.Pool()              # start 4 worker processes
pool.map(pipeline, srcs)

