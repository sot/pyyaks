import logging
import types
from logging import NOTSET, DEBUG, INFO, WARNING, CRITICAL, ERROR
import sys
import contextlib

@contextlib.contextmanager
def newlines_suppressed(logger):
    current = []
    try:
        for handler in logger.handlers:
            current.append(getattr(handler, 'suppress_newline', False))
            handler.suppress_newline = True
        yield
    finally:
        for handler, suppress_newline in zip(logger.handlers, current):
            handler.suppress_newline = suppress_newline

class NullHandler(logging.Handler):
    def emit(self, record):
        pass

# Add a verbose level
VERBOSE = 15
logging.VERBOSE = VERBOSE
logging.addLevelName(VERBOSE, 'VERBOSE')

def emit_newline_optional(handler, record):
    """Same as logging.Handler.emit but with an option to suppress the
    trailing newline if a Handler attribute suppress_newline is True. If the
    attribute is not True or does not exist then there is no change from the
    normal behavior.
    """
    try:
        msg = handler.format(record)
        fs = "%s" if getattr(handler, 'suppress_newline', None) else "%s\n"
        if not hasattr(types, "UnicodeType"): #if no unicode support...
            handler.stream.write(fs % msg)
        else:
            try:
                handler.stream.write(fs % msg)
            except UnicodeError:
                handler.stream.write(fs % msg.encode("UTF-8"))
        handler.flush()
    except (KeyboardInterrupt, SystemExit):
        raise
    except:
        handler.handleError(record)

logging.StreamHandler.emit = emit_newline_optional

def get_logger(filename=None, filemode='w', format='%(message)s',
                 datefmt=None, level=logging.INFO, stream=sys.stdout, filelevel=None,
                 name='pyyaks'):
    """
    Do basic configuration for the logging system. Similar to
    logging.basicConfig but the logger name is configurable and both a file
    output and a stream output can be created. 
    
    Returns a logger object.
    
    The default behaviour is to create a StreamHandler which writes to
    sys.stdout, set a formatter using the "%(message)s" format string, and
    add the handler to the "pyyaks" logger.

    A number of optional keyword arguments may be specified, which can alter
    the default behaviour.

    filename  Specifies that a FileHandler be created using the specified
              filename.
    filemode  Specifies the mode to open the file, if filename is specified
              (defaults to 'w').
    format    Use the specified format string for the handler.
    datefmt   Use the specified date/time format.
    level     Set the logger level to the specified level (default=INFO).
    filelevel Set the level for the file logger.  If not specified this
              defaults to ``level``.
    stream    Use the specified stream to initialize the StreamHandler.
              Defaults to sys.stdout.  Set to None to disable.
    name      Logger name

    """
    # Get a logger for the specified name and remove existing handlers
    logger = logging.getLogger(name)
    logger.setLevel(DEBUG)
    map(logger.removeHandler, logger.handlers[:])
    fmt = logging.Formatter(format, datefmt)

    # Add handlers. Add NullHandler if no file or stream output so that
    # modules don't emit a warning about no handler.
    if not (filename or stream):
        logger.addHandler(NullHandler())

    if filename:
        hdlr = logging.FileHandler(filename, filemode)
        hdlr.setLevel(level if filelevel is None else filelevel)
        hdlr.setFormatter(fmt)
        logger.addHandler(hdlr)

    if stream:
        hdlr = logging.StreamHandler(stream)
        hdlr.setLevel(level)
        hdlr.setFormatter(fmt)
        logger.addHandler(hdlr)

    # Add a VERBOSE level and define method to use it
    logger.verbose = lambda msg: logger.log(logging.VERBOSE, msg)
    
    return logger
