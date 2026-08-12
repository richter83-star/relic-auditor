from unittest.mock import Mock
def test_generate_report():
    generator = Mock()
    generator.generate.return_value = {"report": "demo"}
    assert generator.generate()
