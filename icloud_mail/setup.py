"""Run interactively in the owner's private terminal; no credentials through chat."""
import argparse
import getpass
import json
import os
import secrets
from pathlib import Path

from .auth import digest
from .config import Config, config_path
from .mail import Mailbox


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--docker', action='store_true', help='Create secrets/config.json and state/ in this directory')
    parser.add_argument('--check', action='store_true', help='Check existing configuration against iCloud')
    args = parser.parse_args()
    path = Path('secrets/config.json').resolve() if args.docker else config_path()
    if args.check:
        config = Config.model_validate_json(path.read_text())
        folders = Mailbox(config).folders()['folders']
        print(f'IMAP-Verbindung erfolgreich. {len(folders)} Ordner gefunden.')
        for folder in folders:
            if '\\Drafts' in folder['flags']:
                print('Entwurfsordner:', folder['name'])
        return
    if path.exists():
        raise SystemExit(f'Konfiguration besteht bereits: {path}. Sie wurde nicht überschrieben.')
    address = input('Deine vollständige iCloud-Mail-Adresse: ').strip()
    password = getpass.getpass('App-spezifisches Apple-Passwort (verdeckt): ').strip()
    url = input('Öffentliche HTTPS-Adresse ohne /mcp (leer = lokaler Test): ').strip() or 'http://localhost:8000'
    key = secrets.token_urlsafe(32)
    state = Path('/state') if args.docker else path.parent / 'state'
    config = Config(email=address, app_password=password, public_url=url, login_key_hash=digest(key), state_dir=state)
    # Validate the credentials and discover the drafts folder BEFORE persisting.
    folders = Mailbox(config).folders()['folders']
    drafts = [f['name'] for f in folders if '\\Drafts' in f['flags']]
    if len(drafts) == 1:
        config.drafts_folder = drafts[0]
    else:
        print('Verfügbare Ordner:', ', '.join(f['name'] for f in folders))
        chosen = input('Exakter Name des Entwurfsordners: ')
        if chosen not in [f['name'] for f in folders]:
            raise SystemExit('Unbekannter Ordner; nichts gespeichert.')
        config.drafts_folder = chosen
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = config.model_dump(mode='json')
    data['app_password'] = password
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as file:
        json.dump(data, file, indent=2)
    if args.docker:
        Path('state').mkdir(exist_ok=True, mode=0o700)
        env = Path('.env')
        if not env.exists():
            env.write_text(f'ICLOUD_UID={os.getuid()}\nICLOUD_GID={os.getgid()}\nICLOUD_DOMAIN={url.split("://",1)[1]}\n')
    print('iCloud-Verbindung geprüft. Konfiguration gespeichert:', path)
    print('Connector-Schlüssel (jetzt im Passwortmanager speichern):', key)
    print('MCP-Adresse:', config.public_url + '/mcp')
    print('Der Connector-Schlüssel ist für die Anmeldeseite, das Apple-Passwort bleibt auf dem Server.')


if __name__ == '__main__':
    main()
