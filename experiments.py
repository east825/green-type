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
import platform
from contextlib import contextmanager

import requests


PROJECT_ROOT = os.path.dirname(__file__)
REPORTS_DIR = os.path.join(PROJECT_ROOT, 'reports')

PYTHON2_BIN, PYTHON3_BIN = 'python2', 'python3'
VENV2_BIN, VENV3_BIN = 'venv2', 'venv3'

BIN_DIR = 'Scripts' if platform.system() == 'Windows' else 'bin'

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

    # mostly text
    'CamDavidsonPilon/Probabilistic-Programming-and-Bayesian-Methods-for-Hackers',
    'karan/Projects',
    'mitsuhiko/rstblog',
    'redecentralize/alternative-internet',
    'kennethreitz/python-guide',
    'taobao/nginx-book',

    # doesn't have enough Python modules to analyze
    'mattwilliamson/arduino-sms-alarm',
    'logsol/Github-Auto-Deploy.git',
    'jokkedk/webgrind',
    'square/SocketRocket',
    'misfo/Shell-Turtlestein',
    'jreese/spotify-gnome',
    'fogleman/Minecraft',
    'paulgb/simplediff',
    'somerandomdude/Iconic',
    'gleitz/howdoi',
    'dominis/ansible-shell',

    # broken projects
    'Eichhoernchen/SiriServer',
    'Aaln/whit',
    'chen3feng/typhoon-blade',
    'numenta/nupic',  # has python template modules with $VAR placeholders
    'gregmalcolm/python_koans',  # has exercises both for Python 2 and Python 3
    'surfly/gevent',  # has Python 3 specific modules
    'faif/python-patterns',  # targeting Python 3

    # too complex project structure
    'edx/configuration',
    'deis/deis',
    'klen/python-mode',

    # pretty much useless without dependencies
    # or has too many of them
    'mitmproxy/mitmproxy',
    'shipyard/shipyard',
    'thumbor/thumbor',
    'hausdorff/snapchat-fs',
    'slacy/minimongo',
    'mongodb/mongo-python-driver',
    'nvie/rq',
    'aws/aws-cli',
    'getsentry/sentry',
    'eldarion/biblion',
    'astanway/Commit-Logs-From-Last-Night',

    # other
    'python-git/python',
    'iambus/xunlei-lixian',
])


@contextmanager
def cd(path):
    old_dir = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_dir)


def run(*args, **kwargs):
    stdout = kwargs.pop('stdout', sys.stdout)
    stderr = kwargs.pop('stderr', subprocess.STDOUT)
    ignore_errors = kwargs.pop('ignore_errors', False)
    try:
        subprocess.check_call(args, stdout=stdout, stderr=stderr, **kwargs)
    except subprocess.CalledProcessError as e:
        print(e, file=sys.stderr)
        if _failfast:
            sys.exit(1)
        if not ignore_errors:
            raise e


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

        reports_root = os.path.join(projects_directory, '.reports')
        if not os.path.exists(reports_root):
            print('Reports directory does not exists yet. '
                  'Creating one at {!r}.'.format(reports_root))
            os.makedirs(reports_root)

        venv_root = os.path.join(projects_directory, '.venv')
        if not os.path.exists(venv_root):
            print('Virtual environments directory does not exists yet. '
                  'Creating one at {!r}.'.format(venv_root))
            os.makedirs(venv_root)

        project_reports = []
        for project_name in os.listdir(projects_directory):
            project_path = os.path.join(projects_directory, project_name)
            if project_path in (venv_root, reports_root):
                continue

            if os.path.isdir(project_path):
                report_path = os.path.join(reports_root, project_name + '.json')
                if not args.force and os.path.exists(report_path):
                    print('Using existing JSON report for {}.'.format(project_name))
                else:
                    try:
                        venv_path = os.path.join(venv_root, 'env-' + project_name)
                        if not os.path.exists(venv_path):
                            print('Creating virtualenv in {!r}.'.format(venv_path))
                            run(VENV2_BIN, venv_path)

                        venv_python = os.path.join(venv_path, BIN_DIR, 'python')
                        venv_pip = os.path.join(venv_path, BIN_DIR, 'pip')

                        with cd(project_path):
                            if os.path.exists('requirements.txt'):
                                run(venv_pip, 'install', '-r', 'requirements.txt',
                                    ignore_errors=True)

                            if os.path.exists('setup.py'):
                                run(venv_python, 'setup.py', 'develop', ignore_errors=True)

                        with cd(PROJECT_ROOT):
                            run(venv_python, os.path.join(PROJECT_ROOT, 'runner.py'),
                                '--json', '--follow-imports',
                                '--output', report_path,
                                project_path)
                    except subprocess.CalledProcessError:
                        print('Unrecoverable error in {}. Skipping.'.format(project_name))
                        continue

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

            if not values:
                print('No values exist for {}.'.format(path))
                continue

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
    cmd_collect_statistics.add_argument('directory', nargs='?', default='samples/github')
    cmd_collect_statistics.add_argument('--force', action='store_true')
    cmd_collect_statistics.set_defaults(func=collect_statistics)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()