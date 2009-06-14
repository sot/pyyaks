"""Module to support executing a single task (processing step) in the pyaxx pipeline."""
import sys
import os
import re
import time
from stat import ST_MTIME # Really constants 7 and 8
import traceback
import ContextValue
import Logging as Log
import Shell

# Module var for maintaining status of current set of tasks
status = dict(fail = False)

class DependFileMissing(Exception):
    pass

class DependFuncFailure(Exception):
    pass

class TaskSuccess(Exception):
    pass

class TaskFailure(Exception):
    pass

def check_depend(depends=None, targets=None):
    """Check that dependencies are satisfied.

    A dependency in the ``depends`` or ``targets`` list can be either a file
    name supplied as a renderable object or a sequence with 3 elements: func,
    args, kwargs.

    A file name is treated in the usual sense of depend and target files.  A
    missing depend file raises an exception and a missing target means
    check_depend returns False.  In addition all target files must be newer
    than all depend files.

    For (func, args, kwargs) input, func(*args, **kwargs) is evaluated and is
    evaluated in boolean context.  For the ``depends`` list a func() return of
    False raises an exception indicating that the task dependencies are not
    met.  For ``targets`` a func() return of False results in check_depend
    returning False.

    :param depends: list of file or function dependencies
    :param targets: list of file or function targets

    :returns: boolean indicating that dependencies are satisfied
    """
    # This routine should be refactored into something more comprehensible
    # but for now it works.

    # Lists of mod time for depend and target files.  Seed the list with a
    # fake very OLD and NEW file (respectively) so the final min/max comparison
    # always works.
    mtime = dict(depends = [1], targets = [2**31])
    deptypes = dict(depends=depends, targets=targets)

    for deptype, deps in deptypes.items():
        if not deps:
            continue

        Log.debug('Checking %s deps' % deptype)
        for dep in deps:
            try:
                func, args, kwargs = dep
            except (TypeError, ValueError):
                filename = ContextValue.render(dep)
                if os.path.exists(filename):
                    Log.debug('%s mtime is %s' % (filename, time.ctime(os.stat(filename)[ST_MTIME])))
                    mtime[deptype].append(os.stat(filename)[ST_MTIME])
                    Log.debug('File %s exists' %  filename)
                else:
                    Log.debug('File %s does not exist' %  filename)
                    if deptype == 'depends':
                        raise DependFileMissing, 'Depend file %s not found' % filename
                    else:
                        return False
            else:
                if func(*args, **kwargs):
                    Log.debug('Func %s succeeded' % func.func_name)
                else:
                    Log.debug('Func %s failed' % func.func_name)
                    if deptype == 'depends':
                        raise DependFuncFailure, 'Depend function %s false' % func.func_name
                    else:
                        return False                

    # Are all targets as old as all depends?  Allow for equality since target files could be
    # created within the same second (particularly for "touch" files).
    min_targets = min(mtime['targets'])
    max_depends = max(mtime['depends'])
    Log.debug('min targets time=%s   max depeends time=%s'
              % (time.ctime(min_targets), time.ctime(max_depends)))
    return min_targets >= max_depends

class TaskDecor(object):
    def setup(self):
        pass

    def teardown(self):
        pass

    def __call__(self, func):
        """return function decorator"""
        def new_func(*args, **kwargs):
            try:
                self.setup()
                func(*args, **kwargs)
            except (KeyboardInterrupt, TaskSuccess):
                raise
            except:
                if status['fail'] is False:
                    Log.error('%s: %s\n\n' % (func.func_name, traceback.format_exc()))
                    status['fail'] = True
                raise
            finally:
                self.teardown()

        new_func.func_name = func.func_name
        new_func.func_doc = func.func_doc
        return new_func

class chdir(TaskDecor):
    def __init__(self, newdir):
        self.newdir = newdir
        
    def setup(self):
        self.origdir = os.getcwd()
        newdir = ContextValue.render(self.newdir)
        os.chdir(newdir)
        Log.verbose('Changed to directory "%s"' % newdir)

    def teardown(self):
        os.chdir(self.origdir)
        Log.debug('Restored directory to "%s"' % self.origdir)

class setenv(TaskDecor):
    def __init__(self, env):
        self.env = env

    def setup(self):
        self.origenv = os.environ.copy()
        os.environ.update(self.env)
        Log.debug('Updated local environment')

    def teardown(self):
        for envvar in self.env:
            del os.environ[envvar]
        os.environ.update(self.origenv)
        Log.debug('Restored local environment')

class depends(TaskDecor):
    def __init__(self, depends=None, targets=None):
        self.depends = depends
        self.targets = targets
        self.skip = False

    def setup(self):
        if check_depend(self.depends, self.targets) and self.targets:
            self.skip = True
            Log.verbose('Skipping because dependencies met')
            raise TaskSuccess

    def teardown(self):
        if (not self.skip
            and self.targets
            and not check_depend(self.depends, self.targets)):
            raise TaskFailure, 'Dependency not met after processing'

def task(always=None):
    """Function decorator to support definition of a processing task.

    :param always: Always run the task even if prior processing has failed
    :returns: Decorated function
    """

    def decorate(func):
        def new_func(*args, **kwargs):
            if status['fail'] and not always:
                return

            Log.verbose('')
            Log.verbose('-' * 60)
            Log.info(' Running task: %s at %s' % (func.func_name, time.ctime()))
            Log.verbose('-' * 60)

            try:
                func(*args, **kwargs)
            except KeyboardInterrupt:
                raise
            except TaskSuccess:
                pass
            except:
                if status['fail'] is False:
                    print 'Setting status=fail in task'
                    Log.error('%s: %s\n\n' % (func.func_name, traceback.format_exc()))
                    status['fail'] = True
                
        new_func.func_name = func.func_name
        new_func.func_doc = func.func_doc
        return new_func
    return decorate

def start(message=None):
    status['fail'] = False
    if message is not None:
        Log.info('')
        Log.info('*' * 60)
        Log.info('** %-54s **' % message)
        Log.info('*' * 60)

def end(message=None):
    if message is not None:
        Log.info('')
        Log.info('*' * 60)
        Log.info('** %-54s **' % (message + (' FAILED' if status['fail'] else ' SUCCEEDED')))
        Log.info('*' * 60)
        Log.info('')
    status['fail'] = False
        

def bash(loglevel, oneline=False):
    """Wrap Shell.bash function so input cmd is automatically rendered and
    output gets Logged if loglevel <= VERBOSE.

    :param loglevel: logging level
    :param oneline: join multiline input into a one space-separated line
    """
    class VerboseFileHandle:
        def __init__(self):
            pass
        def write(self, s):
            Log.verbose(s, autonewline=False)
        def flush(self):
            pass
        def close(self):
            pass

    def newbash(cmd, **kwargs):
        logfile = (loglevel <= Log.VERBOSE) and VerboseFileHandle() or None
        cmdlines = [x.strip() for x in cmd.splitlines()]
        sep = ' ' if oneline else os.linesep
        cmd = ContextValue.render(sep.join(cmdlines))
        return Shell.bash(cmd, logfile=logfile, **kwargs)
    return newbash

