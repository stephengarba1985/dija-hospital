from .models import LabTest

STARTER_TESTS = [
    ('fbc', 'Full blood count', 'Whole blood'),
    ('malaria', 'Malaria parasite test', 'Blood'),
    ('urinalysis', 'Urinalysis', 'Urine'),
    ('rbg', 'Random blood glucose', 'Blood'),
    ('uec', 'Urea, electrolytes & creatinine', 'Blood'),
]


def seed_tests(branch):
    for code, name, specimen in STARTER_TESTS:
        LabTest.objects.get_or_create(branch=branch, code=code, defaults={'name': name, 'specimen_type': specimen})
