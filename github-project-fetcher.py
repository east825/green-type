from __future__ import print_function
import json
import os
import random
import subprocess
import argparse

import requests
import sys

# exclude some common libraries from samples
_excludes = ['django', 'flask', 'celery', 'web2py', 'cython', 'web']


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
                             'q': 'language:python stars:10..200',
                             'size': '<=50000',  # no larger than 50 MB
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
            desc = item['description'].lower()
            if any(word in desc for word in _excludes) \
                    or os.path.exists(os.path.join(args.dest, item['name'])):
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