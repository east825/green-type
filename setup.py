from setuptools import setup
from setuptools.command.test import test as TestCommand
import sys
import greentype


# Taken directly from py.test documentation
class PyTest(TestCommand):
    user_options = [('pytest-args=', 'a', "Arguments to pass to py.test")]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.pytest_args = None

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        # import here, cause outside the eggs aren't loaded
        import pytest

        errno = pytest.main(self.pytest_args)
        sys.exit(errno)


setup(
    name='greentype',
    version=greentype.__version__,
    py_modules=['runner'],
    packages=['greentype'],
    # package_data={'': ['README.rst', 'LICENSE']},
    # correct way to include LICENSE and README.rst to installation
    # data_files=[('', ['LICENSE', 'README.rst'])],
    include_package_data=True,
    install_requires=[],
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'greentype = runner:main',
        ],
    },
    url='https://github.com/east825/green-type',
    license='MIT',
    author='Mikhail Golubev',
    author_email='qsolo825@gmail.com',
    description='Fast and precise Python static analyzer (but still slow and very imprecise)',
    long_description=open('README.rst').read(),
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development',
    ],
    cmdclass={'test': PyTest},
)

