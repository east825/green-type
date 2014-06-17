from __future__ import division
from greentype.compat import PY2

TEST_DATA_DIR = 'statistics'


def test_usages(analyzer):
    module = analyzer.index_module('usages.py')
    assert module is not None

    params = analyzer.indexes['PARAMETER_INDEX']

    x1 = params['usages.func1.x']
    assert x1.used == 5
    assert x1.used_as_argument == 0
    assert x1.used_as_operand == 1
    assert x1.returned == 2

    x2 = params['usages.func2.x']
    assert x2.used == 6
    assert x2.used_as_argument == 0
    assert x2.used_as_operand == 4
    assert x2.returned == 0

    x3 = params['usages.func3.x']
    assert x3.used == 5
    assert x3.used_as_argument == 2
    assert x3.used_as_operand == 1
    assert x3.returned == 0


# @pytest.mark.xfail(reason='New statistics collected.')
def test_dict_report_format(analyzer):
    analyzer.config['PROJECT_NAME'] = 'report.py'
    analyzer.index_module('report.py')
    analyzer.infer_parameter_types()
    report = analyzer.statistics_report().as_dict(with_samples=False)

    assert report["project_root"] == analyzer.project_root
    assert report["project_name"] == "report.py"

    assert report["indexed"] == {
        "total": {
            "functions": 2,
            "classes": 3 if PY2 else 2, # + PY2_FAKE_OBJECT
            "modules": 1,
            "parameters": 5
        },
        "in_project": {
            "functions": 2,
            "classes": 2,
            "modules": 1,
            "parameters": 5
        }
    }
    assert report["project_statistics"]['parameters'] == {
        "attributeless": {
            "rate": 4 / 5,
            "total": 4,
            "usages": {
                "operand": {
                    "rate": 1 / 4,
                    "total": 1
                },
                "unused": {
                    "rate": 1 / 4,
                    "total": 1
                },
                "argument": {
                    "rate": 1 / 4,
                    "total": 1
                },
                "returned": {
                    "rate": 1 / 4,
                    "total": 1
                }
            }
        },
        "accessed_attributes": {"max": 2},
        "scattered_type": {"rate": 0, "total": 0},
        "exact_type": {"rate": 1 / 5, "total": 1},
        "undefined_type": {"rate": 0, "total": 0}
    }