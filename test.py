import os
import re
import sys
import ContextValue
from ContextValue import render, render_func, ContextDict
from Task import task, start as task_start, end as task_end
import Shell
import Logging
from Logging import debug, verbose, info, warning, error, critical

# Initialize output logging
loglevel = Logging.VERBOSE
Logging.init(stdoutlevel=loglevel, format="%(message)s")

# Wrap bash function so 1st arg is automatically rendered
def bash(cmd):
    class VerboseFileHandle:
        def __init__(self):
            self.out = ''
        def write(self, s):
            self.out += s
            if s.endswith(os.linesep):
                if len(re.sub(Shell.re_PROMPT, '', s).strip()) > 0:
                    verbose(self.out.strip())
                self.out = ''
        def flush(self):
            self.write('')
        def close(self):
            pass
    logfile = loglevel <= Logging.VERBOSE and VerboseFileHandle() or None
    cmdlines = [x.strip() for x in cmd.splitlines()]
    cmd = render(os.linesep.join(cmdlines))
    return Shell.bash(cmd, logfile=logfile)

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
    bash("""echo 'hello'
            sleep 3
            echo 'world'""")

@task()
def make_dir(dir):
    if not os.path.isdir(dir):
        os.makedirs(dir)
        if not os.path.isdir(dir):
            raise Task.TaskFailure, 'Failed to make directory %s' % dir
        
# os.chdir('examples')

debug(src['obsid'])
debug(str(File['evt2']))
debug(File['evt2'].abs)
debug(File['evt2'].rel)
debug(File['srcdir'].abs)
debug(render('{{file.evt2.abs}}'))
debug(render("Working on obsid {{src.obsid}}"))

for src['obsid'] in range(1):
    task_start(message='Processing for obsid=%s' % src['obsid'])

    make_dir(File['srcdir'].abs)
    make_evt2()
    make_img()
    ls('{{ file.srcdir }}')

    task_end(message='Processing for obsid=%s' % src['obsid'])
