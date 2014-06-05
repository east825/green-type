from __future__ import print_function, unicode_literals, division
import functools
import json
import os
import random
import subprocess
import argparse
import sys
import operator
import textwrap
import traceback
from contextlib import contextmanager

import requests


PROJECT_ROOT = os.path.dirname(__file__)
REPORTS_DIR = os.path.join(PROJECT_ROOT, 'reports')

PYTHON2_BIN, PYTHON3_BIN = 'python2', 'python3'
VENV2_BIN, VENV3_BIN = 'venv2', 'venv3'

sys.path.insert(0, PROJECT_ROOT)

_failfast = False

_excluded_words = frozenset([
    'django',
    'flask',
    'webpy',
    'celery',
    'web2py',
    'cython',
    'sublime',
])

# exclude some common libraries from samples
_excluded_projects = frozenset([
    # mostly pictures
    'nvkelso/natural-earth-vector',
    'somerandomdude/Iconic',
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
    'chen3feng/typhoon-blade',
])


@contextmanager
def cd(path):
    old_dir = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_dir)


def run(*args):
    # parts = []
    # for arg in args:
    # parts.extend(shlex.split(arg))

    try:
        subprocess.check_call(args, stdout=sys.stdout, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        print(e, file=sys.stderr)
        if _failfast:
            sys.exit(1)


def fetch_projects(args):
    projects = {}
    page = 0
    print('Searching for projects in Python on github.com...')
    projects_directory = os.path.abspath(os.path.expanduser(args.directory))
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

            if os.path.exists(os.path.join(projects_directory, item['name'])):
                continue

            projects[item['full_name']] = item['clone_url']
            if len(projects) >= args.number:
                break
        page += 1

    print('Projects found:\n  {}'.format('\n  '.join(projects)))

    if not os.path.exists(projects_directory):
        print('Project directory does not exists. Creating one at {!r}.'.format(projects_directory))
        os.makedirs(projects_directory)

    with cd(projects_directory):
        for name, url in projects.items():
            run('git', 'clone', url)


def collect_statistics(args):
    try:
        projects_directory = os.path.abspath(os.path.expanduser(args.directory))
        print('Running analysis in batch mode. Scanning directory {!r}.'.format(projects_directory))

        if not os.path.exists(REPORTS_DIR):
            print('Reports directory does not exists yet. '
                  'Creating one at {!r}.'.format(REPORTS_DIR))
            os.makedirs(REPORTS_DIR)

        project_reports = []
        for project_name in os.listdir(projects_directory):
            project_path = os.path.join(projects_directory, project_name)
            if os.path.isdir(project_path):
                report_path = os.path.join(REPORTS_DIR, project_name + '.json')
                if not args.force and os.path.exists(report_path):
                    print('Using existing JSON report for {}.'.format(project_name))
                else:
                    with cd(project_path):
                        venv_path = os.path.join(project_path, 'env')
                        if not os.path.exists('env'):
                            print('Creating virtualenv in {!r}.'.format(venv_path))
                            run(VENV2_BIN, 'env')

                        # TODO: correct paths for Windows
                        venv_interpreter_bin = os.path.join(venv_path, 'bin/python')
                        if os.path.exists('setup.py'):
                            run(venv_interpreter_bin, 'setup.py', 'develop')

                        with cd(PROJECT_ROOT):
                            run(venv_interpreter_bin, 'setup.py', 'develop')

                        venv_greentype_bin = os.path.join(venv_path, 'bin/greentype')
                        run(venv_greentype_bin, '--quiet', '--json',
                            '--exclude', 'env',
                            '--output', report_path,
                            project_path)

                with open(report_path, 'rb') as f:
                    report = json.load(f, encoding='utf-8')
                    if report['indexed']['in_project']['parameters'] == 0:
                        print('Nothing to analyze in {}. Skipping.'.format(project_name))
                        continue

                project_reports.append(report)

        if not project_reports:
            print('No projects found.')
            return
        print('Total {:d} projects'.format(len(project_reports)))

        metrics = [
            ('Attributeless parameters',
             'project_statistics.parameters.attributeless.rate'),
            ('Attributeless parameters passed to other function',
             'project_statistics.parameters.attributeless.usages.argument.rate'),
            ('Attributeless parameters used as operand',
             'project_statistics.parameters.attributeless.usages.operand.rate'),
            ('Attributeless parameters used as function return value',
             'project_statistics.parameters.attributeless.usages.returned.rate'),
            ('Undefined type parameters',
             'project_statistics.parameters.undefined_type.rate'),
            ('Exact type parameters', 'project_statistics.parameters.exact_type.rate'),
            ('Scattered type parameters',
             'project_statistics.parameters.scattered_type.rate'),
            ('Maximum number of base classes',
             'project_statistics.additional.max_bases.max'),
        ]

        for title, path in metrics:
            values, value_sources = [], {}
            for report in project_reports:
                try:
                    value = functools.reduce(operator.getitem, path.split('.'), report)
                except KeyError:
                    continue
                values.append(value)
                value_sources[value] = report['project_root']

            mean = sum(values) / len(values)
            if len(values) > 1:
                variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
            else:
                variance = 0
            min_value = min(values)
            max_value = max(values)

            print(textwrap.dedent("""\
            {title}:
              mean={mean}
              variance={variance}
              max={max_value} ({max_project})
              min={min_value} ({min_project})
                """.format(title=title, mean=mean, variance=variance,
                           max_value=max_value, max_project=value_sources[max_value],
                           min_value=min_value, min_project=value_sources[min_value])))


    except Exception:
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers()

    cmd_fetch_projects = commands.add_parser('fetch-projects')
    cmd_fetch_projects.add_argument('-n', '--number', type=int, default=100)
    cmd_fetch_projects.add_argument('-u', '--user', type=lambda x: tuple(x.split(':', 2)))
    cmd_fetch_projects.add_argument('directory', nargs='?', default='samples/github')
    cmd_fetch_projects.set_defaults(func=fetch_projects)

    cmd_collect_statistics = commands.add_parser('collect-statistics')
    cmd_collect_statistics.add_argument('directory', default='samples/github')
    cmd_collect_statistics.add_argument('--force', action='store_true')
    cmd_collect_statistics.set_defaults(func=collect_statistics)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()