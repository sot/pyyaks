# Licensed under a 3-clause BSD style license - see LICENSE.rst

try:
    from testr.setup_helper import cmdclass
except ImportError:
    cmdclass = {}

from setuptools import setup
setup(name='pyyaks',
      url='http://cxc.harvard.edu/contrib/pyyaks',
      use_scm_version=True,
      setup_requires=['setuptools_scm', 'setuptools_scm_git_archive'],
      description='Pipeline processing toolkit',
      author='Tom Aldcroft',
      author_email='aldcroft@head.cfa.harvard.edu',
      packages=['pyyaks', 'pyyaks.tests'],
      tests_require=['pytest'],
      cmdclass=cmdclass,
      )
