from unittest.mock import Mock
from evaluator import evaluate_policy

def test_evaluator_with_mock_rule():
    rule = Mock()
    rule.applies.return_value = True
    assert evaluate_policy({}, [rule])
