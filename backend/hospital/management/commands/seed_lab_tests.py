from django.core.management.base import BaseCommand
from hospital.models import Branch
from hospital.lab_catalogue import seed_tests


class Command(BaseCommand):
    help = 'Add missing starter laboratory tests to active branches without changing existing entries.'

    def handle(self, *args, **options):
        for branch in Branch.objects.filter(active=True):
            seed_tests(branch)
        self.stdout.write(self.style.SUCCESS('Starter test catalogue checked. Existing tests left unchanged.'))
