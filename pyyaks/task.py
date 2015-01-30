"""Module to support executing a single task (processing step) in the pyaxx pipeline."""

from __future__ import print_function, division, absolute_import

import pdb
import sys
import os
import re
import time
import traceback
import logging

import pyyaks.context
import pyyaks.logger
import pyyaks.shell
import collections

class NullHandler(logging.Handler):
    def emit(self, record):
        pass

logger = logging.getLogger('pyyaks')
logger.addHandler(NullHandler())
logger.propagate = False

# Module var for maintaining status of current set of tasks
status = dict(fail=False,
              context_file=None)

class DependMissing(Exception):
    pass

class DependFuncFailure(Exception):
    pass

class TaskSkip(Exception):
    pass

class TaskFailure(Exception):
    pass

def func_depend(func, *args, **kwargs):
    """
    For (func, args, kwargs) input, func(*args, **kwargs) is evaluated and is
    evaluated in boolean context.  For the ``depends`` list a func() return of
    False raises an exception indicating that the task dependencies are not
    met.  For ``targets`` a func() return of False results in check_depend
    returning False.
    """
    if isinstance(dep, (list, tuple)):
        func, args, kwargs = dep
        if func(*args, **kwargs):
            logger.debug('Func %s succeeded' % func.__name__)
        else:
            logger.debug('Func %s failed' % func.__name__)
            if deptype == 'depends':
                raise DependFuncFailure('Depend function %s false' % func.__name__)
            else:
                return False                

def check_depend(depends=None, targets=None):
    """Check that dependencies are satisfied.

    A dependency in the ``depends`` or ``targets`` list can be either a file
    name as a string or a renderable object (file or value) with an mtime
    attribute.

    A file name is treated in the usual sense of depend and target files.  A
    missing depend file raises an exception and a missing target means
    check_depend returns False.  In addition all targets must be newer
    than all depends.

    :param depends: list of file or value dependencies
    :param targets: list of file or value targets

    :returns: dependencies_satisfied, info_message
    """
    # Lists of mod time for depend and target files.  Seed the list with a
    # fake very OLD and NEW file (respectively) so the final min/max comparison
    # always works.
    mtimes = dict(depends = [1],
                  targets = [2**31])
    deptypes = dict(depends=depends,
                    targets=targets)
    statuses = {}

    # Step through all depends and targets and determine existence and mod. time.
    # Collect this status and informational messages in statuses[deptype]
    for deptype in ('depends', 'targets'):
        statuses[deptype] = []
        deps = deptypes[deptype]
        if not deps:
            continue

        for dep in deps:
            # Check if dep is not a ContextValue.  If so interpret as a filename
            if not hasattr(dep, 'mtime'):
                dep = pyyaks.context.ContextValue(val=dep, name=dep,
                                                  parent=pyyaks.context.ContextDict(basedir='.'))
                
            mtime = dep.mtime                
            info = '%s %s %s = %s' % (deptype.title()[:-1], dep.type, dep.fullname, dep.abs)
            if mtime is None:
                statuses[deptype].append((False, info + ' does not exist'))
            else:
                statuses[deptype].append((True, info + ' (%s)' % time.ctime(mtime)))
                mtimes[deptype].append(mtime)

    # Do all depends exist?  If not raise an exception which will trigger task failure
    if not all(x[0] for x in statuses['depends']):
        msg = 'Dependencies missing:\n' + '\n'.join(x[1] for x in statuses['depends'])
        logger.debug(msg)
        raise DependMissing(msg)

    # Do all targets exist?  If not return False.  This is a normal situation
    # before the task is run but will raise an exception after the task is run.
    if not all(x[0] for x in statuses['targets']):
        msg = 'Targets missing:\n' + '\n'.join(x[1] for x in statuses['targets'])
        logger.debug(msg)
        return False, msg

    # Are all targets as old as all depends?  Allow for equality since target files could be
    # created within the same second (particularly for "touch" files).
    min_targets = min(mtimes['targets'])
    max_depends = max(mtimes['depends'])
    ok = min_targets >= max_depends
    msg = 'Depends and targets info:\n' if ok else 'Depend(s) are newer than target(s):\n'
    msg += '\n'.join(x[1] for x in (statuses['depends'] + statuses['targets']))
    logger.debug(msg)
    return ok, msg

class TaskDecor(object):
    """Base class for generating task decorators."""

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
            except (KeyboardInterrupt, TaskSkip):
                raise
            except:
                if status['fail'] is False:
                    logger.error('%s: %s\n\n' % (func.__name__, traceback.format_exc()))
                    status['fail'] = True
                raise
            finally:
                self.teardown()

        new_func.__name__ = func.__name__
        new_func.__doc__ = func.__doc__
        return new_func

class chdir(TaskDecor):
    """Run task within a specified directory.

    :param newdir: directory
    """
    
    def __init__(self, newdir):
        self.newdir = newdir
        
    def setup(self):
        self.origdir = os.getcwd()
        newdir = pyyaks.context.render(self.newdir)
        os.chdir(newdir)
        logger.verbose('Changed to directory "%s"' % newdir)

    def teardown(self):
        os.chdir(self.origdir)
        logger.debug('Restored directory to "%s"' % self.origdir)

class setenv(TaskDecor):
    """Run task within specfied runtime environment.

    :param env: dict of environment values
    """
    
    def __init__(self, env):
        self.env = env

    def setup(self):
        self.origenv = os.environ.copy()
        os.environ.update(self.env)
        logger.debug('Updated local environment')

    def teardown(self):
        for envvar in self.env:
            del os.environ[envvar]
        os.environ.update(self.origenv)
        logger.debug('Restored local environment')

class depends(TaskDecor):
    """Check that dependencies are met:
    - ``depends`` files or values exist
    - ``targets`` files or values exist and are all newer than every ``depends``.

    :param depends: sequence of context values that must exist on task entrance.
    :param targets: sequence of context values that must exist on task exit and be newer than
                    all ``depends`` (if supplied).
    """

    def __init__(self, depends=None, targets=None):
        self.depends = depends
        self.targets = targets

    def setup(self):
        self.skip = False
        depends_ok, msg = check_depend(self.depends, self.targets)
        if depends_ok and self.targets:
            self.skip = True
            logger.verbose('Skipping because dependencies met')
            raise TaskSkip

    def teardown(self):
        if not self.skip and self.targets:
            depends_ok, msg = check_depend(self.depends, self.targets)
            if not depends_ok:
                raise TaskFailure('Dependency not met after processing:\n' + msg)

def task(run=None):
    """Function decorator to support definition of a processing task.
    
    The ``run`` parameter value controls whether the task is run.

    - function: if ``run`` is a callable function then call the function
        with the task name as its argument and use the return value 
        for the following rules.
    - ``True``: Always run even if a previous task has already failed
    - ``False``: Never run
    - ``None``: Run if no previous pipeline tasks have failed (default).

    :param run: control running of task
    :returns: Decorated function
    """

    def decorate(func):
        def new_func(*args, **kwargs):
            runval = run(func.__name__) if isinstance(run, collections.Callable) else run
            if runval is False:
                return
            elif runval is True:
                pass
            elif runval is None:
                if status['fail']:
                    return
            else:
                raise ValueError('run value = %s but must be True, False, or None' % runval)

            logger.verbose('')
            logger.verbose('-' * 60)
            logger.info(' Running task: %s at %s' % (func.__name__, time.ctime()))
            logger.verbose('-' * 60)

            try:
                func(*args, **kwargs)
                pyyaks.context.store_context(status.get('context_file'))
            except KeyboardInterrupt:
                raise
            except TaskSkip:
                pass
            except:
                if status['fail'] is False:
                    logger.error('%s: %s\n\n' % (func.__name__, traceback.format_exc()))
                    status['fail'] = True
                
        new_func.__name__ = func.__name__
        new_func.__doc__ = func.__doc__
        return new_func
    return decorate

@task()
def update_context(filename, keys):
    """Run pyyaks.context.update_context as a task to catch exceptions"""
    pyyaks.context.update_context(filename, keys)

@task()
def store_context(filename, keys):
    """Run pyyaks.context.store_context as a task to catch exceptions"""
    pyyaks.context.store_context(filename, keys)

@pyyaks.context.render_args()
def start(message=None, context_file=None, context_keys=None):
    """Start a pipeline sequence."""
    
    status['fail'] = False
    status['context_file'] = context_file
    if context_file is not None and os.path.exists(context_file):
        update_context(context_file, context_keys)

    if message is not None:
        logger.info('')
        logger.info('*' * 60)
        logger.info('** %-54s **' % pyyaks.context.render(message))
        logger.info('*' * 60)

def end(message=None, context_file=None, context_keys=None):
    """End a pipeline sequence."""
    
    if context_file is not None:
        store_context(context_file, context_keys)

    if message is not None:
        logger.info('')
        logger.info('*' * 60)
        logger.info('** %-54s **' % (pyyaks.context.render(message)
                                     + (' FAILED' if status['fail'] else ' SUCCEEDED')))
        logger.info('*' * 60)
        logger.info('')
    status['fail'] = False

@pyyaks.context.render_args(1)
def make_dir(dir_):
    """Make a directory if it doesn't exist."""
    if not os.path.isdir(dir_):
        os.makedirs(dir_)
        if not os.path.isdir(dir_):
            raise pyyaks.task.TaskFailure('Failed to make directory %s' % dir_)
        logger.verbose('Made directory ' + dir_)
        

