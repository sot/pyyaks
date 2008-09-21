import logging

VERBOSE = 15
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL

def init(stdoutlevel=logging.INFO,
         filelevel=logging.INFO,
         filename=None,
         # format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
         # format="%(levelname)s - %(message)s"
         format="%(message)s"
         ):

    #create logger at root level
    logger = logging.getLogger("")
    logger.setLevel(logging.DEBUG)

    # Add a VERBOSE level and define methods to use it
    logging.addLevelName(15, 'VERBOSE')
    logging.verbose = lambda msg: logger.log(VERBOSE, msg)
    logger.verbose = logging.verbose

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
        fh = logging.FileHandler(filename)
        fh.setLevel(filelevel)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

# Define convenience methods that apps may import
debug = lambda msg: logging.debug(msg)
verbose = lambda msg: logging.verbose(msg)
info = lambda msg: logging.info(msg)
warning = lambda msg: logging.warning(msg)
error = lambda msg: logging.error(msg)
critical = lambda msg: logging.critical(msg)
