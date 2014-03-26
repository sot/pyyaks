import pyyaks

from setuptools import setup
setup(name='pyyaks',
      url='http://cxc.harvard.edu/contrib/pyyaks',
      version=pyyaks.__version__,
      description='Pipeline processing toolkit',
      author='Tom Aldcroft',
      author_email='aldcroft@head.cfa.harvard.edu',
      packages=['pyyaks', 'pyyaks.tests'],
      )
