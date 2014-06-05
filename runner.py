from __future__ import unicode_literals, print_function, division

import os
import logging

from greentype import core


PROJECT_ROOT = os.path.dirname(__file__)

file_handler = logging.FileHandler(
    os.path.join(PROJECT_ROOT, 'greentype.log'),
    mode='w'
)
file_handler.setFormatter(logging.Formatter(
    fmt='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
))
logging.getLogger('greentype.core').addHandler(file_handler)

# it's needed for setuptools console script
main = core.GreenTypeAnalyzer.main

if __name__ == '__main__':
    main()
