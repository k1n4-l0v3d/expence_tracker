import re
from app import generate_captcha


def test_returns_question_string_and_int_answer():
    question, answer = generate_captcha()
    assert isinstance(question, str)
    assert isinstance(answer, int)


def test_question_matches_expected_format():
    for _ in range(30):
        question, _ = generate_captcha()
        assert re.match(r'^\d+\s*[+\-×]\s*\d+$', question), f"Bad format: {question}"


def test_math_answer_is_correct():
    for _ in range(50):
        question, answer = generate_captcha()
        match = re.match(r'^(\d+)\s*([+\-×])\s*(\d+)$', question)
        assert match, f"Could not parse: {question}"
        a, op, b = int(match.group(1)), match.group(2), int(match.group(3))
        if op == '+':
            assert answer == a + b
        elif op == '-':
            assert answer == a - b
        elif op == '×':
            assert answer == a * b


def test_answer_is_non_negative():
    for _ in range(50):
        _, answer = generate_captcha()
        assert answer >= 0
