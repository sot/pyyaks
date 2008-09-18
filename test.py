import os
import re
import sys
from ContextValue import ContextDict, render, render_func
import Task
from Task import task
from Shell import bash

# Wrap bash function so 1st arg is automatically rendered
bash = render_func(bash)

# Define src vars
src = ContextDict('src')
src['obsid'] = 123
src['ccdid'] = 2

# Define file aliases
File = ContextDict('file', basedir='data')
File['srcdir'] = '{{ src.obsid }}/{{src.ccdid}}'
File['evt2']   = '{{ file.srcdir }}/acis_evt2.fits'
File['img']    = '{{ file.srcdir }}/acis_img.fits'
File['img2']    = '{{ file.srcdir }}/acis_img2.fits'

File['srcdir'].basedir = None

# Define tasks (process steps)
@task(always=True,
      depends=['test.py'],
      dir='{{srcdir}}')
def do_something():
    print render("Working on obsid {{src.obsid}}")
    bash('echo obs{{ src.obsid }}')

@task(depends=['{{file.evt2}}'],
      targets=['{{file.img}}',
               '{{file.img2}}'],
      dir='{{srcdir}}')
def make_img():
    bash('touch {{ file.img }}')

@task()
def make_dir(dir):
    makedirs(dir)

os.chdir('examples')

print src['obsid']
print str(File['evt2'])
print File['evt2'].abs
print File['evt2'].rel
print render('{{file.evt2.abs}}')
print render("Working on obsid {{src.obsid}}")

for src['obsid'] in range(0):
    Task.start(message='Processing for obsid=%s' % src['obsid'])

    make_dir(File['srcdir'].abs)
    do_something()
    make_img()

    Task.end(message='Processing for obsid=%s' % src['obsid'])
