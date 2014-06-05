from __future__ import unicode_literals, print_function, division
import functools
import json

import os
import logging
import argparse
import textwrap
import traceback
import operator
import sys

from greentype import core
from greentype import utils
from greentype.compat import open

PROJECT_ROOT = os.path.dirname(__file__)
REPORTS_DIR = os.path.join(PROJECT_ROOT, 'reports')

file_handler = logging.FileHandler(
    os.path.join(PROJECT_ROOT, 'greentype.log'),
    mode='w'
)
file_handler.setFormatter(logging.Formatter(
    fmt='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
))
logging.getLogger('greentype.core').addHandler(file_handler)


# def analyze_project(target_path, args):
# analyzer = core.GreenTypeAnalyzer(target_path=target_path)
#     analyzer.config.update_from_object(args)
#
#     if analyzer.config['ANALYZE_BUILTINS']:
#         analyzer.index_builtins()
#
#     analyzer.index_project()
#
#     with utils.timed('Inferred types for parameters'):
#         analyzer.infer_parameter_types()
#     return analyzer.statistics_report
#
#
# def main():
#     parser = argparse.ArgumentParser()
#     parser.add_argument('--src-roots', type=lambda x: x.split(':'), default=[],
#                         dest='SOURCE_ROOTS',
#                         help='Sources roots separated by colon.')
#
#     parser.add_argument('-t', '--target', default='',
#                         dest='TARGET_NAME',
#                         help='Target qualifier to restrict output.')
#
#     parser.add_argument('-L', '--follow-imports', action='store_true',
#                         dest='FOLLOW_IMPORTS',
#                         help='Follow imports during indexing.')
#
#     parser.add_argument('-B', '--no-builtins', action='store_false',
#                         dest='ANALYZE_BUILTINS',
#                         help='Not analyze built-in modules reflectively first.')
#
#     parser.add_argument('-d', '--dump-params', action='store_true',
#                         help='Dump parameters qualified by target.')
#
#     parser.add_argument('-v', '--verbose', action='store_true',
#                         dest='VERBOSE',
#                         help='Enable DEBUG logging level.')
#
#     parser.add_argument('--json', action='store_true',
#                         help='Dump analysis results in JSON.')
#
#     parser.add_argument('--batch', action='store_true',
#                         help='Run analysis on all projects in directory.')
#
#     parser.add_argument('--force', action='store_true',
#                         help='Do not use existing statistics report.')
#
#     parser.add_argument('path',
#                         help='Path to single Python module or directory.')
#
#     args = parser.parse_args()
#
#     if args.VERBOSE:
#         logging.getLogger().setLevel(logging.DEBUG)
#
#     LOG.info('Python path: %s', sys.path)
#
#     try:
#         target_path = os.path.abspath(os.path.expanduser(args.path))
#         if args.batch:
#             print('Running analysis in batch mode. Scanning directory {!r}.'.format(target_path))
#             LOG.info('Reports directory does not exists yet. Creating one at %r.', REPORTS_DIR)
#             if not os.path.exists(REPORTS_DIR):
#                 os.makedirs(REPORTS_DIR)
#
#             project_reports = []
#             for project_name in os.listdir(target_path):
#                 project_path = os.path.join(target_path, project_name)
#                 if os.path.isdir(project_path):
#                     report_path = os.path.join(REPORTS_DIR, project_name + '.json')
#                     if not args.force and os.path.exists(report_path):
#                         print('Using existing JSON report for {}'.format(project_name))
#                         # json handles encoding by itself
#                         with open(report_path, 'rb') as f:
#                             report = json.load(f, encoding='utf-8')
#                     else:
#                         try:
#                             statistics = analyze_project(project_path, args)
#                         except SyntaxError:
#                             print('Syntax error during analysis in {}. '
#                                   'Wrong Python version? Skipping.\n{}'
#                                   .format(project_name, traceback.format_exc(1)))
#                             continue
#                         report = statistics.as_dict(with_samples=False)
#                         if report['indexed']['in_project']['parameters'] == 0:
#                             print('Nothing to analyze in {}. Skipping.'.format(project_name))
#                             continue
#                         with open(report_path, 'wb') as f:
#                             json.dump(report, f, encoding='utf-8', indent=2)
#
#                     project_reports.append(report)
#
#             if not project_reports:
#                 print('No projects found.')
#                 return
#             print('Total {:d} projects'.format(len(project_reports)))
#
#             metrics = [
#                 ('Attributeless parameters',
#                  'project_statistics.parameters.attributeless.rate'),
#                 ('Attributeless parameters passed to other function',
#                  'project_statistics.parameters.attributeless.usages.argument.rate'),
#                 ('Attributeless parameters used as operand',
#                  'project_statistics.parameters.attributeless.usages.operand.rate'),
#                 ('Attributeless parameters used as function return value',
#                  'project_statistics.parameters.attributeless.usages.returned.rate'),
#                 ('Undefined type parameters',
#                  'project_statistics.parameters.undefined_type.rate'),
#                 ('Exact type parameters', 'project_statistics.parameters.exact_type.rate'),
#                 ('Scattered type parameters',
#                  'project_statistics.parameters.scattered_type.rate'),
#                 ('Maximum number of base classes',
#                  'project_statistics.additional.max_bases.max'),
#             ]
#
#             for title, path in metrics:
#                 values, value_sources = [], {}
#                 keys = path.split('.')
#                 for report in project_reports:
#                     value = functools.reduce(operator.getitem, keys, report)
#                     values.append(value)
#                     value_sources[value] = report['project_root']
#
#                 mean = sum(values) / len(values)
#                 if len(values) > 1:
#                     variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
#                 else:
#                     variance = 0
#                 min_value = min(values)
#                 max_value = max(values)
#
#                 print(textwrap.dedent("""\
#                 {title}:
#                   mean={mean}
#                   variance={variance}
#                   max={max_value} ({max_project})
#                   min={min_value} ({min_project})
#                     """.format(title=title, mean=mean, variance=variance,
#                                max_value=max_value, max_project=value_sources[max_value],
#                                min_value=min_value, min_project=value_sources[min_value])))
#         else:
#             statistics = analyze_project(target_path, args)
#             # TODO: analyze newly found functions as well
#             statistics.dump_params = args.dump_params
#             if args.json:
#                 print(statistics.format_json(with_samples=True))
#             else:
#                 print(statistics.format_text(dump_params=args.dump_params))
#
#     except Exception:
#         traceback.print_exc()


if __name__ == '__main__':
    core.GreenTypeAnalyzer.main()
