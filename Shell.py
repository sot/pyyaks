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

        return os.linesep.join(self.before.splitlines()[1:])

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

def parse_keyvals(keyvalstr):
    """Parse the key=val pairs from the newline-separated string.  Return dict of key=val pairs."""
    re_keyval = re.compile(r'([\w_]+) \s* = \s* (.*)', re.VERBOSE)
    keyvals = keyvalstr.splitlines()
    keyvalout = {}
    for keyval in keyvals:
        m = re.search(re_keyval, keyval.strip())
        if m:
            key, val = m.groups()
            keyvalout[key] = val
    return keyvalout

def bash(cmdstr, logfile=sys.stdout, keep_env=None):
    """Run the command string cmdstr in a bash shell.  It can have multiple
    lines.  Each line is separately sent to the shell.  The exit status is
    checked if the shell comes back with a PS1 prompt. Bash control structures
    like if or for use prompt PS2 and in this case status is not checked.  At
    the end the 'printenv' command is issued in order to find any changes to
    the environment that occurred as a result of the commands.  If exit status
    is non-zero at any point then processing is terminated and the bad exit
    status value is returned.

    Input: command string
    Output: exit status"""

    print '\nRunning command(s):'
    print MyTemplate(cmdstr).safe_substitute(dict(os.environ)), '\n'

    os.environ['PS1'] = PROMPT1
    os.environ['PS2'] = PROMPT2
    shell = pexpect.spawn('/bin/bash --noprofile --norc --noediting', timeout=1e8)
    shell.delaybeforesend = 0.01
    shell.logfile_read=logfile
    shell.expect(r'.+')

    for line in cmdstr.splitlines():
        shell.sendline_expect(line)
        if re_PROMPT.match(shell.after).group(1) == '>':
            try:
                exitstr = shell.sendline_expect('echo $?', quiet=True).strip()
                exitstatus = int(exitstr)
            except ValueError:
                print "\n\n Shell / expect got out of sync:"
                print " Response to 'echo $?' was apparently '%s'\n\n" % exitstr
                raise
                
            if exitstatus > 0:
                raise ShellError, 'Bash command %s failed with exit status %d' % (cmdstr,
                                                                                  exitstatus)

    # Update os.environ based on changes to environment made by cmdstr
    if keep_env:
        currenv = dict(os.environ)
        newenv = parse_keyvals(shell.sendline_expect("printenv", quiet=True))
        fix_paths(newenv)
        for key in newenv.keys():
            if key not in currenv or currenv[key] != newenv[key]:
                print 'Updating os.environ[%s] = "%s"' % (key, newenv[key])
                os.environ[key] = newenv[key]

    shell.close()
    print
    return 0

