import json
import os
import secrets
from pathlib import Path
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = 'Create a development administrator and save generated credentials to a private local file.'

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('This command is only available in local development. Use createsuperuser for deployment.')
        path = Path(settings.BASE_DIR).parent / '.local' / 'admin-login.json'
        if User.objects.filter(username='dija-admin').exists():
            self.stdout.write('Local administrator already exists. Password was not changed.')
            return
        if path.exists():
            raise CommandError('A credentials file already exists. Preserve it and use createsuperuser instead.')
        password = secrets.token_urlsafe(24)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with transaction.atomic():
            User.objects.create_superuser(username='dija-admin', password=password, first_name='Dija', last_name='Administrator')
            with open(path, 'x', opener=lambda filename, flags: os.open(filename, flags, 0o600)) as file:
                json.dump({'username': 'dija-admin', 'password': password}, file)
        self.stdout.write(f'Local administrator created. Credentials saved privately at {path}. No password was printed.')
