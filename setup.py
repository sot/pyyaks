import pyyaks

try:
    from testr.setup_helper import cmdclass
except ImportError:
    cmdclass = {}

from setuptools import setup
setup(name='pyyaks',
      url='http://cxc.harvard.edu/contrib/pyyaks',
      version=pyyaks.__version__,
      description='Pipeline processing toolkit',
      author='Tom Aldcroft',
      author_email='aldcroft@head.cfa.harvard.edu',
      packages=['pyyaks', 'pyyaks.tests'],
      tests_require=['pytest'],
      cmdclass=cmdclass,
      )
