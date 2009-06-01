"""Module to support executing a single task (processing step) in the pyaxx pipeline."""
from __future__ import with_statement 
import contextlib

import os
import re
from stat import ST_MTIME # Really constants 7 and 8
from traceback import format_exc
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

def preserve_cwd(function):
   def decorator(*args, **kwargs):
      cwd = os.getcwd()
      try:
          print "preserve_cwd: running function"
          return function(*args, **kwargs)
      finally:
          print "preserve_cwd: changing back to", cwd
          os.chdir(cwd)
   return decorator

@contextlib.contextmanager
def remember_cwd():
    curdir = os.getcwd()
    print "remember_cwd before:", os.getcwd()
    try:
        yield
    finally:
        os.chdir(curdir)
        print "remember_cwd after:", os.getcwd()

def with_chdir(dirname):
    try:
        with remember_cwd():
            os.chdir(dirname)
            print "with_chdir before:", os.getcwd()
    except Exception, msg:
        print msg
    print "with_chdir after:", os.getcwd()

class RevealAccess(object):
    """A data descriptor that sets and returns values
       normally and prints a message logging their access.
    """

    def __init__(self, initval=None, name='var'):
        self.val = initval
        self.name = name

    def __get__(self, obj, objtype):
        print 'Retrieving', self.name
        return self.val

    def __set__(self, obj, val):
        print 'Updating' , self.name
        self.val = val

class MyClass(object):
    x = RevealAccess(10, 'var "x"')
    y = 5


@preserve_cwd
def chdir(dirname):
    print "chdir before:", os.getcwd()
    os.chdir(dirname)
    print "chdir after:", os.getcwd()

def test_chdir(dirname):
    print "test_chdir before:", os.getcwd()
    chdir('/home/aldcroft')
    print "test_chdir after:", os.getcwd()
    
    print "test_chdir before:", os.getcwd()
    chdir('/nope/aldcroft')
    print "test_chdir before:", os.getcwd()

def test_with_chdir(dirname):
    print "test_with_chdir before:", os.getcwd()
    with_chdir('/home/aldcroft')
    print "test_with_chdir after:", os.getcwd()
    
    print "test_with_chdir before:", os.getcwd()
    with_chdir('/nope/aldcroft')
    print "test_with_chdir before:", os.getcwd()

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
    mtime = dict(depends = [-1e38], targets = [1e38])
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
                    mtime[deptype].append(os.stat(filename)[ST_MTIME])
                    Log.debug('File %s exists' %  filename)
                else:
                    Log.debug('File %s does not exist' %  filename)
                    if deptype == 'depends':
                        raise DependFileMissing, 'Depend file %s not found' % filename
                    else:
                        return False
                continue

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
    return min(mtime['targets']) >= max(mtime['depends'])

def task(depends=None, targets=None, env=None, always=None, dir=None):
    """Function decorator to support definition of a processing task.

    :param depends: List of input files that the task depends on
    :param target_funcs: List of output files that the task creates/updates
    :param funcs: List of (func, args, kwargs) tuples
    :param env: Dict of env var updates
    :param always: Always run the task even if prior processing has failed
    :param dir: Directory in which to run

    :returns: Decorated function
    """
    def decorate(func):
        def new_func(*args, **kwargs):
            if status['fail'] and not always:
                return

            Log.verbose('')
            Log.verbose('-' * 40)
            Log.info(' Running task: %s' % func.func_name)
            Log.verbose('-' * 40)
            origdir = os.getcwd()
            origenv = os.environ.copy()

            # Change to specified dir after caching current dir.  Allow for uncaught
            # exception here.  Change this?
            try:
                if dir:
                    try:
                        newdir = ContextValue.render(dir)
                        Log.debug('Changing to directory "%s"' % newdir)
                        os.chdir(newdir)
                    except OSError, msg:
                        raise TaskFailure, msg

                if env:
                    # Set local environment
                    os.environ.update(env)

                # Check dependencies before execution.  If met then abort task with success.
                # The order is important: check_depend can raise an exception if any depends files
                # are missing.  But after that if there are no 
                if check_depend(depends, targets) and targets:
                    raise TaskSuccess

                # Actually run the function.  Catch any exceptions and re-raise as TaskFailure.
                # This ignores function return val, but task processing should not depend on
                # return vals anyway since there is no guarantee that func will get run anyway.
                try:
                    Log.debug('Running func %s' % func)
                    func(*args, **kwargs)
                except:
                    # Change limit based on verbosity [to do]
                    raise TaskFailure, format_exc(limit=2)

                if targets and not check_depend(depends, targets):
                    raise TaskFailure, 'Dependency not met after processing'
                
            except TaskSuccess:
                pass
            except (TaskFailure, DependFileMissing), msg:
                Log.error('%s: %s\n\n' % (func.func_name, msg))
                status['fail'] = True

            if env:
                # Reset local environment
                for envvar in env:
                    del os.environ[envvar]
                os.environ.update(origenv)
                

            # Go back to original directory
            if dir:
                os.chdir(origdir)

            return
                
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
        Log.info('** %-54s **' % (message + (status['fail'] and ' FAILED' or ' SUCCEEDED')))
        Log.info('*' * 60)
        Log.info('')
    status['fail'] = False
        

def bash(loglevel):
    """Wrap Shell.bash function so input cmd is automatically rendered and
    output gets Logged if loglevel <= VERBOSE."""
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
        cmd = ContextValue.render(os.linesep.join(cmdlines))
        return Shell.bash(cmd, logfile=logfile, **kwargs)
    return newbash

