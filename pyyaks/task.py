"""Module to support executing a single task (processing step) in the pyaxx pipeline."""
from __future__ import with_statement

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

logger = logging.getLogger('pyyaks.task')

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
            logger.debug('Func %s succeeded' % func.func_name)
        else:
            logger.debug('Func %s failed' % func.func_name)
            if deptype == 'depends':
                raise DependFuncFailure, 'Depend function %s false' % func.func_name
            else:
                return False                

def check_depend(depends=None, targets=None):
    """Check that dependencies are satisfied.

    A dependency in the ``depends`` or ``targets`` list can be either a file
    name as a string or a renderable object with an mtime attribute.

    A file name is treated in the usual sense of depend and target files.  A
    missing depend file raises an exception and a missing target means
    check_depend returns False.  In addition all target files must be newer
    than all depend files.

    :param depends: list of file or function dependencies
    :param targets: list of file or function targets

    :returns: boolean indicating that dependencies are satisfied
    """
    # Lists of mod time for depend and target files.  Seed the list with a
    # fake very OLD and NEW file (respectively) so the final min/max comparison
    # always works.
    mtimes = dict(depends = [1],
                  targets = [2**31])
    deptypes = dict(depends=depends,
                    targets=targets)

    for deptype, deps in deptypes.items():
        if not deps:
            continue

        logger.debug('Checking %s deps' % deptype)
        for dep in deps:
            if not hasattr(dep, 'mtime'):
                dep = pyyaks.context.ContextValue(val=dep, name=dep, basedir='.')
                
            mtime = dep.mtime                
            if mtime is None:
                print dep.name, repr(dep)
                logger.debug('File/value %s does not exist' %  dep.name)
                if deptype == 'depends':
                    raise DependFileMissing('Depend file/value %s not found' % dep.name)
                else:
                    return False
            else:
                logger.debug('File/value %s=%s has mtime: %s' % (dep.name, dep, time.ctime(mtime)))
                mtimes[deptype].append(mtime)

    # Are all targets as old as all depends?  Allow for equality since target files could be
    # created within the same second (particularly for "touch" files).
    min_targets = min(mtimes['targets'])
    max_depends = max(mtimes['depends'])
    logger.debug('min targets time=%s   max depeends time=%s'
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
                    logger.error('%s: %s\n\n' % (func.func_name, traceback.format_exc()))
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
        newdir = pyyaks.context.render(self.newdir)
        os.chdir(newdir)
        logger.verbose('Changed to directory "%s"' % newdir)

    def teardown(self):
        os.chdir(self.origdir)
        logger.debug('Restored directory to "%s"' % self.origdir)

class setenv(TaskDecor):
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
    def __init__(self, depends=None, targets=None):
        self.depends = depends
        self.targets = targets
        self.skip = False

    def setup(self):
        if check_depend(self.depends, self.targets) and self.targets:
            self.skip = True
            logger.verbose('Skipping because dependencies met')
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

            logger.verbose('')
            logger.verbose('-' * 60)
            logger.info(' Running task: %s at %s' % (func.func_name, time.ctime()))
            logger.verbose('-' * 60)

            try:
                func(*args, **kwargs)
            except KeyboardInterrupt:
                raise
            except TaskSuccess:
                pass
            except:
                if status['fail'] is False:
                    print 'Setting status=fail in task'
                    logger.error('%s: %s\n\n' % (func.func_name, traceback.format_exc()))
                    status['fail'] = True
                
        new_func.func_name = func.func_name
        new_func.func_doc = func.func_doc
        return new_func
    return decorate

def start(message=None):
    status['fail'] = False
    if message is not None:
        logger.info('')
        logger.info('*' * 60)
        logger.info('** %-54s **' % message)
        logger.info('*' * 60)

def end(message=None):
    if message is not None:
        logger.info('')
        logger.info('*' * 60)
        logger.info('** %-54s **' % (message + (' FAILED' if status['fail'] else ' SUCCEEDED')))
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
        

