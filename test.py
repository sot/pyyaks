import os
import re
import sys
import ContextValue
from ContextValue import render, ContextDict
import Task
from Task import task
import Shell
import Logging as Log

# Initialize output logging
loglevel = Log.VERBOSE
Log.init(stdoutlevel=loglevel, filename='test.log', filelevel=loglevel, format="%(message)s")

# Create bash wrapper around Shell.bash.  This sets up a file-like object
# to stream shell pexpect output in a way that plays well with Task output.
bash = Task.bash(loglevel)

ciaoenv = Shell.getenv('. /soft/ciao/bin/ciao.bash')

# Define src vars
src = ContextDict('src')
src['obsid'] = 123
src['ccdid'] = 2
src['srcdir'] = '{{ src.obsid }}/{{src.ccdid}}'

# Define file aliases
File = ContextDict('file', basedir='data', valuetype=ContextValue.File)
File['srcdir'] = '{{ src.srcdir }}'
File['evt2']   = '{{ src.srcdir }}/acis_evt2.fits'
File['img']    = '{{ src.srcdir }}/acis_img.fits'
File['img2']   = '{{ src.srcdir }}/acis_img2.fits'

# Define tasks (process steps)
@task(always=True,
      targets=['{{file.evt2}}'],
      dir='{{file.srcdir}}')
def make_evt2():
    bash('touch {{ file.evt2 }}')

@task(depends=['{{file.evt2}}'],
      targets=['{{file.img}}',
               '{{file.img2}}'],
      dir='{{file.srcdir}}')
def make_img():
    bash('touch {{ file.img }}')
    bash('touch {{ file.img2 }}')

@task()
def ls(dir):
    bash('ls ' + dir)

@task()
def wait(secs):
    bash("""echo 'hello'
            sleep %d
            echo 'world'""" % secs)

@task()
def plist(tool='dmlist'):
    bash('plist %s' % tool, env=ciaoenv)

@task(env=ciaoenv)
def plist2(tool='dmlist'):
    bash("""\
         plist dmlist
         plist dmcopy
         plist dmstat""")
    

@task()
def make_dir(dir):
    if not os.path.isdir(dir):
        os.makedirs(dir)
        if not os.path.isdir(dir):
            raise Task.TaskFailure, 'Failed to make directory %s' % dir
        
# os.chdir('examples')

Log.debug(src['obsid'])
Log.debug(str(File['evt2']))
Log.debug(File['evt2'].abs)
Log.debug(File['evt2'].rel)
Log.debug(File['srcdir'].abs)
Log.debug(render('{{file.evt2.abs}}'))
Log.debug(render("Working on obsid {{src.obsid}}"))

for src['obsid'] in range(1):
    Task.start(message='Processing for obsid=%s' % src['obsid'])

    make_dir(File['srcdir'].abs)
    make_evt2()
    make_img()
    plist('dmcopy')
    plist2('dmcopy')
    ls('{{ file.srcdir }}')

    Task.end(message='Processing for obsid=%s' % src['obsid'])
