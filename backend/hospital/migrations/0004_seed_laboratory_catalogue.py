from django.db import migrations


def seed_catalogue(apps, schema_editor):
    Branch = apps.get_model('hospital', 'Branch')
    LabTest = apps.get_model('hospital', 'LabTest')
    alias = schema_editor.connection.alias
    tests = [
        ('fbc', 'Full blood count', 'Whole blood'),
        ('malaria', 'Malaria parasite test', 'Blood'),
        ('urinalysis', 'Urinalysis', 'Urine'),
        ('rbg', 'Random blood glucose', 'Blood'),
        ('uec', 'Urea, electrolytes & creatinine', 'Blood'),
    ]
    for branch in Branch.objects.using(alias).all():
        for code, name, specimen in tests:
            LabTest.objects.using(alias).get_or_create(branch=branch, code=code,
                defaults={'name': name, 'specimen_type': specimen})


class Migration(migrations.Migration):
    dependencies = [('hospital', '0003_laborder_labreport_labreportaddendum_labtest_and_more')]
    operations = [migrations.RunPython(seed_catalogue, migrations.RunPython.noop)]
