import re
import os
import sys
import pexpect
from string import Template

class ShellError(Exception):
    pass

# Give pexpect.spawn a new convenience method that sends a line and expects the prompt
def sendline_expect_func(prompt):
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
pexpect.spawn.sendline_expect = sendline_expect_func(re_PROMPT)

class MyTemplate(Template):
    pattern = r"""%(delim)s(?:           # ?: is non-capturing group
              (?P<escaped>$^) |          # Escape sequence that cannot happen
              (?P<named>%(id)s)      |   # delimiter and a Python identifier
              {(?P<braced>%(id)s)}   |   # delimiter and a braced identifier
              (?P<invalid>)              # Other ill-formed delimiter exprs
              )
              """ % {'delim' : re.escape('$'),
                     'id'    : r'[_a-z][_a-z0-9]*' }

def fix_paths(envs):
    """For the specified env vars that represent a search path, make sure that the
    paths are unique.  This allows the environment setting script to be lazy
    and not worry about it.  This routine gives the right-most path precedence."""

    # Process env vars that are contained in the PATH_ENVS set
    for key in set(envs.keys()) & set(('PATH', 'PERLLIB', 'PERL5LIB', 'PYTHONPATH',
                                       'LD_LIBRARY_PATH', 'MANPATH', 'INFOPATH')):
        path_ins = envs[key].split(':')
        pathset = set()
        path_outs = []
        # Working from right to left add each path that hasn't been included yet.
        for path in reversed(path_ins):
            if path not in pathset:
                pathset.add(path)
                path_outs.append(path)
        envs[key] = ':'.join(reversed(path_outs))

def parse_keyvals(keyvals):
    """Parse the key=val pairs from the newline-separated string.  Return dict of key=val pairs."""
    re_keyval = re.compile(r'([\w_]+) \s* = \s* (.*)', re.VERBOSE)
    keyvalout = {}
    for keyval in keyvals:
        m = re.search(re_keyval, keyval.strip())
        if m:
            key, val = m.groups()
            keyvalout[key] = val
    return keyvalout

def _bash(cmdstr, logfile=None, importenv=False, getenv=False, env=None):
    """Run the command string cmdstr in a bash shell.  It can have multiple
    lines.  Each line is separately sent to the shell.  The exit status is
    checked if the shell comes back with a PS1 prompt. Bash control structures
    like if or for use prompt PS2 and in this case status is not checked.  At
    the end the 'printenv' command is issued in order to find any changes to
    the environment that occurred as a result of the commands.  If exit status
    is non-zero at any point then processing is terminated and the bad exit
    status value is returned.

    Input: command string
    Output: shell output"""

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
                raise ShellError, msg
                
            if exitstatus > 0:
                raise ShellError, 'Bash command %s failed with exit status %d' % (cmdstr,
                                                                                  exitstatus)

    # Update os.environ based on changes to environment made by cmdstr
    deltaenv = dict()
    if importenv or getenv:
        currenv = dict(os.environ)
        newenv = parse_keyvals(shell.sendline_expect("printenv", quiet=True))
        fix_paths(newenv)
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

def bash(cmdstr, logfile=None, importenv=False, env=None):
    return _bash(cmdstr, logfile=logfile, importenv=importenv, env=env)[0]

def getenv(cmdstr, importenv=False, env=None):
    return _bash(cmdstr, importenv=importenv, env=env, getenv=True)[1]

def importenv(cmdstr, env=None):
    return _bash(cmdstr, importenv=True, env=env)[1]
