"""Module to support executing a single task (processing step) in the pyaxx pipeline."""

import os
from stat import ST_MTIME # Really constants 7 and 8
from traceback import format_exc
from ContextValue import render
from Logging import debug, verbose, info, warning, error, critical

# Module var for maintaining status of current set of tasks
status = dict(fail = False)

class DependFileMissing(Exception):
    pass

class TaskSuccess(Exception):
    pass

class TaskFailure(Exception):
    pass

def check_depend(depends=None, targets=None):
    """Check that:
     - All 'depends' exist (if not, raise exception)
     - All 'targets' exist and are older than oldest 'depends'
     """
    # Lists of mod time for depend and target files.  Seed the list with a
    # fake very OLD and NEW file (respectively) so the final min/max comparison
    # always works.
    mtime = dict(depends = [-1e38], targets = [1e38])
    filetypes = dict(depends = depends, targets = targets)

    for filetype, files in filetypes.items():
        if files:
            debug('Checking %s files: %s' % (filetype, str(files)))
            for file_ in files:
                file_ = render(file_)
                if os.path.exists(file_):
                    mtime[filetype].append(os.stat(file_)[ST_MTIME])
                else:
                    if filetype == 'depends':
                        raise DependFileMissing, 'Depend file %s not found' % file_
                    else:
                        return False

    # Are all targets as old as all depends?  Allow for equality since target files could be
    # created within the same second (particularly for "touch" files).
    return min(mtime['targets']) >= max(mtime['depends'])

def task(depends=None, targets=None, env=None, always=None, dir=None):
    def decorate(func):
        def new_func(*args, **kwargs):
            if status['fail'] and not always:
                return

            verbose('-' * 40)
            info(' Running task: %s' % func.func_name)
            verbose('-' * 40)
            origdir = os.getcwd()
            # origenv = ...

            # Change to specified dir after caching current dir.  Allow for uncaught
            # exception here.  Change this?
            try:
                if dir:
                    try:
                        newdir = render(dir)
                        debug('Changing to directory "%s"' % newdir)
                        os.chdir(newdir)
                    except OSError, msg:
                        raise TaskFailure, msg

                if env:
                    # Set local environment
                    pass

                # Check dependencies before execution.  If met then abort with success
                if check_depend(depends, targets) and targets:
                    raise TaskSuccess

                # Actually run the function.  Catch any exceptions and re-raise as TaskFailure.
                # This ignores function return val, but task processing should not depend on
                # return vals anyway since there is no guarantee that func will get run anyway.
                try:
                    func(*args, **kwargs)
                except:
                    # Change limit based on verbosity [to do]
                    raise TaskFailure, format_exc(limit=0)

                if targets and not check_depend(depends, targets):
                    raise TaskFailure, 'Dependency not met after processing'
                
            except TaskSuccess:
                pass
            except (TaskFailure, DependFileMissing), msg:
                error('%s: %s\n\n' % (func.func_name, msg))
                status['fail'] = True

            if env:
                # Reset local environment
                pass

            # Go back to original directory
            if dir:
                os.chdir(origdir)

            return
                
        new_func.func_name = func.func_name
        return new_func
    return decorate

def start(message=None):
    status['fail'] = False
    if message is not None:
        info('*' * 60)
        info('** %-54s **' % message)
        info('*' * 60)

def end(message=None):
    if message is not None:
        info('*' * 60)
        info('** %-54s **' % (message + (status['fail'] and ' FAILED' or ' SUCCEEDED')))
        info('*' * 60)
    status['fail'] = False
        
