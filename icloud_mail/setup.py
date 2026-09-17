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
        print(f'IMAP connection successful. Found {len(folders)} folders.')
        for folder in folders:
            if '\\Drafts' in folder['flags']:
                print('Drafts folder:', folder['name'])
        return
    if path.exists():
        raise SystemExit(f'Configuration already exists: {path}. It has not been overwritten.')
    address = input('Your full iCloud email address: ').strip()
    password = getpass.getpass('Apple app-specific password (hidden): ').strip()
    url = input('Public HTTPS origin without /mcp (leave blank for local testing): ').strip() or 'http://localhost:8000'
    key = secrets.token_urlsafe(32)
    state = Path('/state') if args.docker else path.parent / 'state'
    config = Config(email=address, app_password=password, public_url=url, login_key_hash=digest(key), state_dir=state)
    # Validate the credentials and discover the drafts folder BEFORE persisting.
    folders = Mailbox(config).folders()['folders']
    drafts = [f['name'] for f in folders if '\\Drafts' in f['flags']]
    if len(drafts) == 1:
        config.drafts_folder = drafts[0]
    else:
        print('Available folders:', ', '.join(f['name'] for f in folders))
        chosen = input('Exact name of the Drafts folder: ')
        if chosen not in [f['name'] for f in folders]:
            raise SystemExit('Unknown folder; nothing saved.')
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
    print('iCloud connection verified. Configuration saved:', path)
    print('Connector key (save it in your password manager now):', key)
    print('MCP URL:', config.public_url + '/mcp')
    print('Use the connector key on the login page; the Apple password stays on the server.')


if __name__ == '__main__':
    main()
