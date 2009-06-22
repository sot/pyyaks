import logging
import types

def emit_without_newline(self, record):
    """
    This is a copy of logging.StreamHandler.emit but without the
    automatic newline.
    """
    try:
        msg = self.format(record)
        fs = "%s"
        if not hasattr(types, "UnicodeType"): #if no unicode support...
            self.stream.write(fs % msg)
        else:
            try:
                self.stream.write(fs % msg)
            except UnicodeError:
                self.stream.write(fs % msg.encode("UTF-8"))
        self.flush()
    except (KeyboardInterrupt, SystemExit):
        raise
    except:
        self.handleError(record)

def init(stdoutlevel=logging.INFO,
         filelevel=logging.INFO,
         filename=None,
         format="%(message)s"
         ):

    #create formatter
    formatter = logging.Formatter(format)

    #create console handler and set level to error
    if stdoutlevel is not None:
        ch = logging.StreamHandler()
        ch.setLevel(stdoutlevel)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    #create file handler and set level to debug
    if filename and filelevel is not None:
        fh = logging.FileHandler(filename, mode='w')
        fh.setLevel(filelevel)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

def add_autonewline(logging_output_func):
    """Wrap a logging class output function to allow for disabling
    the automatic newline that gets emitted."""
    def new_logging_output_func(msg, autonewline=True):
        if not autonewline:
            logging.StreamHandler.emit = emit_without_newline
        logging_output_func(msg)
        logging.StreamHandler.emit = emit_with_newline
    return new_logging_output_func

VERBOSE = 15
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL

# Copy the original StreamHandler emit function
emit_with_newline = logging.StreamHandler.emit

#create logger at root level
logger = logging.getLogger("")
logger.setLevel(logging.DEBUG)

# Add a VERBOSE level and define methods to use it
logging.addLevelName(15, 'VERBOSE')
logging.verbose = lambda msg: logger.log(VERBOSE, msg)
logger.verbose = logging.verbose

# Define Logging methods that allow for disabling automatic emitting of newline
debug = add_autonewline(logging.debug)
verbose = add_autonewline(logging.verbose)
info = add_autonewline(logging.info)
warning = add_autonewline(logging.warning)
error = add_autonewline(logging.error)
critical = add_autonewline(logging.critical)
