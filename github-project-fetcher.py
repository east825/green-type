from __future__ import print_function
import os
import random
import subprocess
import argparse
import sys

import requests


# exclude some common libraries from samples
_excluded_words = frozenset([
    'django',
    'flask',
    'webpy',
    'celery',
    'web2py',
    'cython',
    'sublime',
])

_excluded_projects = frozenset([
    # mostly pictures
    'nvkelso/natural-earth-vector',
    # mostly text
    'CamDavidsonPilon/Probabilistic-Programming-and-Bayesian-Methods-for-Hackers',
    'karan/Projects',
    'python-git/python',
    'mitsuhiko/rstblog',
    'redecentralize/alternative-internet',
    'kennethreitz/python-guide',
    # doesn't have enough Python modules do analyze
    'mattwilliamson/arduino-sms-alarm',
    'logsol/Github-Auto-Deploy.git',
    'jokkedk/webgrind',
    'square/SocketRocket',
    # broken projects
    'Eichhoernchen/SiriServer',
    'Aaln/whit',
    'chen3feng/typhoon-blade'
])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--number', type=int, default=100)
    parser.add_argument('-u', '--user', type=lambda x: tuple(x.split(':', 2)))
    parser.add_argument('dest', nargs='?', default='samples/github')

    args = parser.parse_args()

    projects = {}
    page = 0
    print('Searching for projects in Python on github.com...')
    while len(projects) < args.number:
        r = requests.get('https://api.github.com/search/repositories',
                         params={
                             # 'q': 'language:python stars:10..200',
                             'q': 'language:python size:<=30000',
                             'per_page': 100,
                             'page': page
                         },
                         auth=args.user,
                         headers={'Accept': 'application/vnd.github.preview.text-match+json'})
        r.raise_for_status()
        # print(json.dumps(r.json(), indent=2))
        items = list(r.json()['items'])
        random.shuffle(items)
        for item in items:

            if item['full_name'] in _excluded_projects:
                continue

            desc = item['description'].lower()
            name = item['name'].lower()
            if any(word in desc or word in name for word in _excluded_words):
                continue

            if os.path.exists(os.path.join(args.dest, item['name'])):
                continue

            projects[item['full_name']] = item['clone_url']
            if len(projects) >= args.number:
                break
        page += 1

    print('Projects found:\n  {}'.format('\n  '.join(projects)))

    if not os.path.exists(args.dest):
        os.makedirs(args.dest)

    print('Changing CWD to', os.path.abspath(args.dest))
    os.chdir(args.dest)
    for name, url in projects.items():
        try:
            subprocess.check_call(['git', 'clone', url],
                                  stdout=sys.stdout,
                                  stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            print('Cannot clone {}: {}'.format(name, e))


if __name__ == '__main__':
    main()