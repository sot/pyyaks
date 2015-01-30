"""Utilities to run subprocesses"""

from __future__ import print_function, division, absolute_import

import re
import os
import sys
import time
import signal
import subprocess
import logging

import pyyaks.context
import pyyaks.logger
import pyyaks.pexpect as pexpect

class NullHandler(logging.Handler):
    def emit(self, record):
        pass

logger = logging.getLogger('pyyaks')
logger.addHandler(NullHandler())
logger.propagate = False

class ShellError(Exception):
    pass

# Give pexpect.spawn a new convenience method that sends a line and expects the prompt
def _sendline_expect_func(prompt):
    """Returns a convenience method to monkey-patch into pexpect.spawn.""" 
    def sendline_expect(self, cmd, quiet=False):
        """Send a command and expect the given prompt.  Return the 'before' part"""
        if quiet:
            logfile_read = self.logfile_read
            self.logfile_read = None

        self.sendline(cmd)
        self.expect(prompt)

        if prompt.search(cmd):
            self.expect(prompt)
        if quiet:
            self.logfile_read = logfile_read

        return self.before.splitlines()[1:]

    return sendline_expect

PROMPT1 = r'Bash-\t> '
PROMPT2 = r'Bash-\t- '
re_PROMPT = re.compile(r'Bash-\d\d:\d\d:\d\d([->]) ')

# See skare/install.py for the Template code that can do interpolation of all
# shell ${var} variables for debug

def _fix_paths(envs, pathvars=('PATH', 'PERLLIB', 'PERL5LIB', 'PYTHONPATH',
                              'LD_LIBRARY_PATH', 'MANPATH', 'INFOPATH')):
    """For the specified env vars that represent a search path, make sure that the
    paths are unique.  This allows the environment setting script to be lazy
    and not worry about it.  This routine gives the right-most path precedence
    and modifies C{envs} in place.

    :param envs: Dict of environment vars
    :param pathvars: List of path vars that will be fixed
    :rtype: None (envs is modified in-place)
    """

    # Process env vars that are contained in the PATH_ENVS set
    for key in set(envs.keys()) & set(pathvars):
        path_ins = envs[key].split(':')
        pathset = set()
        path_outs = []
        # Working from right to left add each path that hasn't been included yet.
        for path in reversed(path_ins):
            if path not in pathset:
                pathset.add(path)
                path_outs.append(path)
        envs[key] = ':'.join(reversed(path_outs))

def _parse_keyvals(keyvals):
    """Parse the key=val pairs from the newline-separated string.

    :param keyvals: Newline-separated string with key=val pairs
    :rtype: Dict of key=val pairs.
    """
    re_keyval = re.compile(r'([\w_]+) \s* = \s* (.*)', re.VERBOSE)
    keyvalout = {}
    for keyval in keyvals:
        m = re.search(re_keyval, keyval.strip())
        if m:
            key, val = m.groups()
            keyvalout[key] = val
    return keyvalout

def bash_shell(cmdstr, logfile=None, importenv=False, getenv=False, env=None):
    """Run the command string ``cmdstr`` in a bash shell.  It can have multiple
    lines.  Each line is separately sent to the shell.  The exit status is
    checked if the shell comes back with a PS1 prompt. Bash control structures
    like if or for use prompt PS2 and in this case status is not checked.  At
    the end the ``printenv`` command may be used in order to find any changes to
    the environment that occurred as a result of the commands.  If exit status
    is non-zero at any point then processing is terminated and a ``ShellError``
    exception is raise.

    :param cmdstr: command string
    :param logfile: append output to the suppplied file object
    :param importenv: import any environent changes back to python env
    :param getenv: get the environent changes after running ``cmdstr``
    :param env: set environment using ``env`` dict prior to running commands

    :returns: (outlines, deltaenv)
    """

    # Import pexpect here so that this the other (Spawn) part of this module
    # doesn't depend on pexpect (which is not in the std library)
    pexpect.spawn.sendline_expect = _sendline_expect_func(re_PROMPT)

    os.environ['PS1'] = PROMPT1
    os.environ['PS2'] = PROMPT2
    shell = pexpect.spawn('/bin/bash --noprofile --norc --noediting', timeout=1e8)
    shell.delaybeforesend = 0.01
    shell.logfile_read=logfile
    shell.expect(r'.+')

    if env:
        for key, val in env.items():
            # Would be better to properly escape any shell characters.
            # And would be good to make sure this actually worked...
            shell.sendline_expect("export %s='%s'" % (key, val), quiet=True)

    outlines = []
    for line in cmdstr.splitlines():
        outlines += shell.sendline_expect(line)

        if re_PROMPT.match(shell.after).group(1) == '>':
            try:
                exitstr = shell.sendline_expect('echo $?', quiet=True)[0].strip()
                exitstatus = int(exitstr)
            except ValueError:
                msg = ("Shell / expect got out of sync:\n" + 
                       "Response to 'echo $?' was apparently '%s'" % exitstr)
                raise ShellError(msg)
                
            if exitstatus > 0:
                raise ShellError('Bash command %s failed with exit status %d' % (cmdstr,
                                                                                  exitstatus))

    # Update os.environ based on changes to environment made by cmdstr
    deltaenv = dict()
    if importenv or getenv:
        currenv = dict(os.environ)
        newenv = _parse_keyvals(shell.sendline_expect("printenv", quiet=True))
        _fix_paths(newenv)
        for key in set(newenv) - set(('PS1', 'PS2', '_', 'SHLVL')):
            if key not in currenv or currenv[key] != newenv[key]:
                deltaenv[key] = newenv[key]
        if importenv:
            os.environ.update(deltaenv)

    shell.close()

    # expect leaves a stray prompt when logging, so send a linefeed
    if logfile:
        logfile.write('\n')

    return outlines, deltaenv

# Some convenience methods for bashing

def bash(cmdstr, importenv=False, env=None):
    """Render the input ``cmdstr`` and run in a bash shell.  Output is logged at
    the VERBOSE level.

    :param cmdstr: command string
    :param importenv: import any environent changes back to python env
    :param env: set environment using ``env`` dict prior to running commands

    :returns: bash output string
    """
    class _LogFileHandle:
        def __init__(self):
            pass
        def write(self, s):
            logger.verbose(s)
        def flush(self):
            pass
        def close(self):
            pass

    with pyyaks.logger.newlines_suppressed(logger):
        out = bash_shell(pyyaks.context.render(cmdstr),
                         logfile=_LogFileHandle(), importenv=importenv, env=env)
    return out

def getenv(cmdstr, importenv=False, env=None):
    """Run the ``cmdstr`` string in a bash shell and return the resulting
    update to the current python environment (os.environ).

    :param cmdstr: command string
    :param importenv: import any environent changes back to python env
    :param env: set environment using ``env`` dict prior to running commands

    :returns: Dict of environment vars update produced by ``cmdstr``
    """
    return bash_shell(pyyaks.context.render(cmdstr), importenv=importenv,
                      env=env, getenv=True)[1]

def importenv(cmdstr, env=None):
    """Run ``cmdstr`` in a bash shell and import the environment updates into the
    current python environment (os.environ).  

    :param cmdstr: command string
    :param env: set environment using ``env`` dict prior to running commands

    :returns: Dict of environment vars update produced by ``cmdstr``
    """
    return bash_shell(pyyaks.context.render(cmdstr), importenv=True,
                      env=env)[1]

# Null file-like object.  Needed because pyfits spews warnings to stdout
class _NullFile:
    def write(self, data): pass
    def writelines(self, lines): pass
    def flush(self): pass
    def close(self): pass

class RunTimeoutError(RuntimeError):
    pass

class Spawn(object):
    """
    Provide methods to run subprocesses in a controlled and simple way.  Features:
     - Uses the subprocess.Popen() class
     - Send stdout and/or stderr output to a file
     - Specify a job timeout
     - Catch exceptions and log warnings

    Example usage:

      >>> from pyyaks.shell import Spawn, bash, getenv, importenv
      >>> 
      >>> spawn = Spawn()
      >>> status = spawn.run(['echo', 'hello'])
      hello
      >>> status
      0
      >>> 
      >>> try:
      ...     spawn.run(['bad', 'command'])
      ... except Exception, error:
      ...     error
      ... 
      OSError(2, 'No such file or directory')
      >>> spawn.run(['bad', 'command'], catch=True)
      Warning - OSError: [Errno 2] No such file or directory
      >>> print spawn.exitstatus
      None
      >>> print spawn.outlines
      ['Warning - OSError: [Errno 2] No such file or directory\\n']
      >>> 
      >>> spawn = Spawn(stdout=None, shell=True)
      >>> spawn.run('echo hello')
      0
      >>> spawn.run('fail fail fail')
      127
      >>> 
      >>> spawn = Spawn(stdout=None, shell=True, stderr=None)
      >>> spawn.run('fail fail fail')
      127
      >>> print spawn.outlines
      []

    Additional object attributes:
     - openfiles: List of file objects created during init corresponding
                  to filenames supplied in ``outputs`` list
    """
    def _open_for_write(self, f):
        """Return a file object for writing for ``f``, which may be nothing, a file
        name, or a file-like object."""
        if not f:
            return _NullFile()
        # Else see if it is a single file-like object
        elif hasattr(f, 'write') and hasattr(f, 'close'):
            return f
        else:
            openfile = open(f, 'w', 1)  # raises TypeError if f is not suitable
            self.openfiles.append(openfile)  # Store open file objects created by this object
            return openfile
        
    @staticmethod
    def _timeout_handler(pid, timeout):
        def handler(signum, frame):
            raise RunTimeoutError('Process pid=%d timed out after %d secs' % (pid, timeout))
        return handler

    def __init__(self, stdout=sys.stdout, timeout=None, catch=False,
                 stderr=subprocess.STDOUT, shell=False):
        """Create a Spawn object to run shell processes in a controlled way.

        :param stdout: destination(s) for process stdout.  Can be None, a file name,
             a file object, or a list of these.
        :param timeout: command timeout (default: no timeout)
        :param catch: catch exceptions and just log a warning message
        :param stderr: destination for process stderr.  Can be None, a file object,
             or subprocess.STDOUT (default).  The latter merges stderr into stdout.
        :param shell: send run() cmd to shell (subprocess Popen shell parameter)
        
        :rtype: Spawn object
        """
        self.stdout = stdout
        self.timeout = timeout or 0
        self.catch = catch
        self.stderr = stderr
        self.shell = shell
        self.openfiles = []             # Newly opened file objects for stdout
        
        # stdout can be None, <file>, 'filename', or sequence(..) of these
        try:
            self.outfiles = [self._open_for_write(self.stdout)]
        except TypeError:
            self.outfiles = [self._open_for_write(f) for f in self.stdout]

    def _write(self, line):
        for f in self.outfiles:
            f.write(line)
        self.outlines.append(line)

    def run(self, cmd, timeout=None, catch=None, shell=None):
        """Run the command ``cmd`` and abort if timeout is exceeded.

        Attributes after run():
         - outlines: list of output lines from process
         - exitstatus: process exit status or None if an exception occurred

        :param cmd: list of strings or a string(see Popen docs)
        :param timeout: command timeout (default: ``self.timeout``)
        :param catch: catch exceptions (default: ``self.catch``)
        :param shell: run cmd in shell (default: ``self.shell``)

        :rtype: process exit value
        """

        # Use object defaults if params not supplied
        if timeout is None:
            timeout = self.timeout
        if catch is None:
            catch = self.catch
        if shell is None:
            shell = self.shell

        # stderr = None is taken to imply catching stderr, done with PIPE
        stderr = self.stderr or subprocess.PIPE

        self.outlines = []
        self.exitstatus = None

        try:
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=stderr, shell=shell)

            prev_alarm_handler = signal.signal(signal.SIGALRM,
                                               Spawn._timeout_handler(self.process.pid, timeout))
            signal.alarm(self.timeout)
            for line in self.process.stdout:
                self._write(line)
            self.exitstatus = self.process.wait()
            signal.alarm(0)

            signal.signal(signal.SIGALRM, prev_alarm_handler)

        except RunTimeoutError as e:
            if catch:
                self._write('Warning - RunTimeoutError: %s\n' % e)
            else:
                raise

        except OSError as e:
            if catch:
                self._write('Warning - OSError: %s\n' % e)
            else:
                raise

        return self.exitstatus

def run_tool(cmd=None, punlearn=False, split_char='\n'):
    spawn = Spawn(stdout=None)
    cmds = [pyyaks.context.render(x).strip() for x in cmd.split(split_char)]
    if punlearn:
        spawn.run(['punlearn', cmds[0]])
    logger.verbose('Running ' + ' '.join(cmds))
    exitstatus = spawn.run(cmds)
    logger.verbose(''.join(spawn.outlines))
    if exitstatus:
        raise ValueError('Command failed with exit status = {0}'.format(exitstatus))
    return spawn.outlines
