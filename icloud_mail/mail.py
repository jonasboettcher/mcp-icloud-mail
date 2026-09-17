import base64
import binascii
import contextlib
import email.policy
import hashlib
import imaplib
import json
import re
import ssl
import threading
from datetime import date, datetime, timezone
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import format_datetime, getaddresses
from html.parser import HTMLParser
from pydantic import BaseModel, ConfigDict, Field

from .config import Config


class MailError(Exception):
    pass


MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS = 10


class DraftAttachment(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)

    filename: str = Field(min_length=1, max_length=255, description='File name only, without a directory path.')
    content_base64: str = Field(max_length=4 * ((MAX_ATTACHMENT_BYTES + 2) // 3),
                                description='Standard Base64 of the actual file bytes, without a data URL prefix.')
    content_type: str = Field(default='application/octet-stream', max_length=127,
                              description='MIME media type, for example application/pdf or image/png.')


def decode_attachments(attachments):
    if len(attachments or []) > MAX_ATTACHMENTS:
        raise MailError('At most 10 attachments per draft.')
    decoded, total = [], 0
    for value in attachments or []:
        item = DraftAttachment.model_validate(value)
        quoted(item.filename)
        if item.filename in ('.', '..') or '/' in item.filename or '\\' in item.filename:
            raise MailError('Attachment filename must be a file name without a directory path.')
        content_type = item.content_type.lower()
        if not re.fullmatch(r'[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*', content_type) or content_type.startswith(('multipart/', 'message/')):
            raise MailError('Attachment content_type must be a single non-container MIME media type.')
        try:
            data = base64.b64decode(item.content_base64, validate=True)
        except (binascii.Error, ValueError):
            raise MailError('Attachment content_base64 must contain valid standard Base64.') from None
        total += len(data)
        if total > MAX_ATTACHMENT_BYTES:
            raise MailError('Attachments exceed the combined 10 MiB limit.')
        decoded.append((item.filename, content_type, data))
    return decoded


def quoted(value: str) -> str:
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise MailError("Control characters are not permitted.")
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def utf7_encode(value: str) -> str:
    result, run = [], []
    def flush():
        if run:
            result.append('&' + base64.b64encode(''.join(run).encode('utf-16-be')).decode().rstrip('=').replace('/', ',') + '-')
            run.clear()
    for c in value:
        if 32 <= ord(c) <= 126:
            flush()
            result.append('&-' if c == '&' else c)
        else:
            run.append(c)
    flush()
    return ''.join(result)


def utf7_decode(value: str) -> str:
    def decode(match):
        text = match[1]
        return '&' if not text else base64.b64decode(text.replace(',', '/') + '=' * (-len(text) % 4)).decode('utf-16-be')
    return re.sub(r'&([^-]*)-', decode, value)


def parse_folder(row):
    raw = row[0] if isinstance(row, tuple) else row
    match = re.match(rb'^\((.*?)\) (?:"(?:\\.|[^"\\])*"|NIL) (.*)$', raw)
    if not match:
        raise MailError("Unsupported IMAP folder response.")
    name = row[1] if isinstance(row, tuple) else match[2]
    if name.startswith(b'"') and name.endswith(b'"'):
        name = re.sub(rb'\\(.)', rb'\1', name[1:-1])
    return {"name": utf7_decode(name.decode('ascii')), "flags": match[1].decode('ascii').split()}


class PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'head'):
            self.hidden += 1
        if tag in ('br', 'p', 'div', 'li', 'tr'):
            self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'head'):
            self.hidden = max(0, self.hidden - 1)
    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def parse_message(raw):
    msg = BytesParser(policy=email.policy.default).parsebytes(raw)
    result = {key: str(msg.get(key, '')) for key in ('subject', 'from', 'to', 'cc', 'date', 'message-id', 'in-reply-to', 'references', 'reply-to')}
    part = msg.get_body(preferencelist=('plain', 'html'))
    text = ''
    if part:
        try:
            text = part.get_content()
        except (LookupError, UnicodeError):
            text = (part.get_payload(decode=True) or b'').decode('utf-8', errors='replace')
        if part.get_content_type() == 'text/html':
            parser = PlainHTML()
            parser.feed(text)
            text = ''.join(parser.parts)
    result['body'] = text
    result['attachments'] = [
        {'part_index': index, 'filename': p.get_filename(), 'content_type': p.get_content_type(),
         'size': len(p.get_payload(decode=True) or b'')}
        for index, p in enumerate(msg.walk()) if not p.is_multipart() and
        (p.get_filename() or p.get_content_disposition() == 'attachment')
    ]
    return result


def addresses(values):
    if len(values) > 50:
        raise MailError("At most 50 recipients per field.")
    for value in values:
        quoted(value)
        parsed = getaddresses([value])
        if len(parsed) != 1 or parsed[0][1].count('@') != 1 or not all(parsed[0][1].split('@')):
            raise MailError("Each recipient must be one complete email address.")
        try:
            parsed[0][1].encode('ascii')
        except UnicodeError:
            raise MailError("Internationalized addresses require an ASCII mailbox address.") from None
    return ', '.join(values)


def draft_message(sender, to, subject, body, cc, bcc, request_id, reply_headers=None, attachments=None):
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', request_id):
        raise MailError("request_id must contain 16–128 letters, digits, underscores or hyphens.")
    if len(body.encode('utf-8')) > 500_000 or len(subject) > 998:
        raise MailError("Draft too large.")
    quoted(subject)
    msg = EmailMessage(policy=email.policy.SMTP)
    msg['From'] = sender
    for key, value in [('To', to), ('Cc', cc), ('Bcc', bcc)]:
        if value:
            msg[key] = addresses(value)
    msg['Subject'] = subject
    digest = hashlib.sha256((sender + '\0' + request_id).encode()).hexdigest()
    msg['Message-ID'] = f'<{digest}@icloud-mail-mcp.local>'
    msg['Date'] = format_datetime(datetime.now(timezone.utc))
    if reply_headers:
        ids = re.findall(r'<[^<>\s]+>', reply_headers.get('message-id', ''))
        if len(ids) != 1:
            raise MailError("Original message has no unambiguous Message-ID.")
        msg['In-Reply-To'] = ids[0]
        refs = re.findall(r'<[^<>\s]+>', reply_headers.get('references', ''))
        msg['References'] = ' '.join((refs + ids)[-30:])
    msg.set_content(body)
    # Bind retry keys to semantic content; Date is deliberately excluded.
    material = '\0'.join(str(msg.get(k, '')) for k in ('From', 'To', 'Cc', 'Bcc', 'Subject', 'In-Reply-To', 'References')) + '\0' + body
    attachment_fingerprints = []
    for filename, content_type, data in decode_attachments(attachments):
        maintype, subtype = content_type.split('/')
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
        attachment_fingerprints.append([filename, content_type, hashlib.sha256(data).hexdigest()])
    if attachment_fingerprints:
        # Preserve fingerprints of existing attachment-free drafts across upgrades.
        material += '\0attachments\0' + json.dumps(attachment_fingerprints, ensure_ascii=True, separators=(',', ':'))
    msg['X-ICloud-MCP-Content-SHA256'] = hashlib.sha256(material.encode()).hexdigest()
    return msg


class Mailbox:
    def __init__(self, config: Config):
        self.config = config
        self.write_lock = threading.Lock()

    @contextlib.contextmanager
    def connection(self):
        client = None
        try:
            client = imaplib.IMAP4_SSL('imap.mail.me.com', 993, ssl_context=ssl.create_default_context(), timeout=30)
            client.login(self.config.email, self.config.app_password.get_secret_value())
            yield client
        except (imaplib.IMAP4.error, OSError, UnicodeError):
            raise MailError("iCloud IMAP request failed. Check the app password, network and folder; no write was retried automatically.") from None
        finally:
            if client:
                with contextlib.suppress(Exception):
                    client.logout()

    def _folders(self, client):
        status, rows = client.list()
        if status != 'OK':
            raise MailError("Cannot list folders.")
        return [parse_folder(row) for row in rows if row and row != b')']

    def folders(self):
        with self.connection() as client:
            return {'folders': self._folders(client)}

    def _select(self, client, folder, expected=None, readonly=True):
        status, _ = client.select(quoted(utf7_encode(folder)), readonly=readonly)
        if status != 'OK':
            raise MailError("Folder cannot be opened.")
        _, values = client.response('UIDVALIDITY')
        if not values or not values[0]:
            raise MailError("Missing UIDVALIDITY; message identity cannot be verified.")
        validity = int(values[0])
        if expected is not None and validity != expected:
            raise MailError("Folder identity changed. Search again before reading this UID.")
        return validity

    def _search(self, client, criteria):
        # Unlike search(), uid() does not insert the CHARSET keyword.
        status, rows = client.uid('SEARCH', 'CHARSET', 'UTF-8', ' '.join(criteria).encode('utf-8'))
        if status != 'OK':
            raise MailError("Search failed; iCloud did not accept the search criteria.")
        return [int(x) for x in (rows[0] or b'').split()]

    def _fetch(self, client, uid, headers=False):
        if uid < 1:
            raise MailError("UID must be positive.")
        status, rows = client.uid('FETCH', str(uid), '(RFC822.SIZE)')
        size = re.search(rb'RFC822.SIZE (\d+)', b' '.join(x for x in rows if isinstance(x, bytes)))
        if status != 'OK' or not size:
            raise MailError("Message no longer exists.")
        if not headers and int(size[1]) > self.config.max_message_bytes:
            raise MailError("Message exceeds the configured download limit.")
        section = 'HEADER' if headers else ''
        # Hard cap even if an untrusted server misreports RFC822.SIZE.
        limit = 131072 if headers else self.config.max_message_bytes + 1
        status, rows = client.uid('FETCH', str(uid), f'(BODY.PEEK[{section}]<0.{limit}>)')
        literals = [r[1] for r in rows if isinstance(r, tuple)]
        if status != 'OK' or len(literals) != 1:
            raise MailError("Message could not be read.")
        if len(literals[0]) >= limit:
            raise MailError("Message data exceeds the download limit.")
        return literals[0]

    def search(self, folder='INBOX', text='', sender='', recipient='', subject='', since=None, before=None, unread=False, limit=20, before_uid=None):
        if not 1 <= limit <= 100 or (before_uid is not None and before_uid < 1):
            raise MailError("Invalid page size or UID cursor.")
        criteria = ['ALL']
        for key, value in [('TEXT', text), ('FROM', sender), ('TO', recipient), ('SUBJECT', subject)]:
            if value:
                if len(value) > 1000:
                    raise MailError("Search field is too long.")
                criteria.extend([key, quoted(value)])
        for key, value in [('SINCE', since), ('BEFORE', before)]:
            if value:
                d = date.fromisoformat(value)
                month = ('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec')[d.month-1]
                criteria.extend([key, f'{d.day:02}-{month}-{d.year}'])
        if unread:
            criteria.append('UNSEEN')
        with self.connection() as client:
            validity = self._select(client, folder)
            if before_uid == 1:
                return {'messages': [], 'next_before_uid': None, 'uidvalidity': validity, 'folder': folder}
            if before_uid:
                criteria.extend(['UID', f'1:{before_uid-1}'])
            uids = sorted(set(self._search(client, criteria)), reverse=True)
            messages = []
            for uid in uids[:limit]:
                msg = parse_message(self._fetch(client, uid, headers=True))
                msg.pop('body'); msg.pop('attachments')
                messages.append({'uid': uid, **msg})
            return {'folder': folder, 'uidvalidity': validity, 'messages': messages,
                    'next_before_uid': uids[limit-1] if len(uids) > limit else None,
                    'order': 'UID descending (arrival order)'}

    def read(self, folder, uidvalidity, uid, offset=0, max_chars=30000):
        if offset < 0 or not 1 <= max_chars <= 100000:
            raise MailError("Invalid body range.")
        with self.connection() as client:
            self._select(client, folder, uidvalidity)
            result = parse_message(self._fetch(client, uid))
        body = result['body']
        result.update(folder=folder, uidvalidity=uidvalidity, uid=uid, body=body[offset:offset+max_chars],
                      body_total_chars=len(body), next_offset=offset+max_chars if offset+max_chars < len(body) else None,
                      mailbox_url='https://www.icloud.com/mail/')
        return result

    def attachment(self, folder, uidvalidity, uid, part_index, offset=0, length=65536):
        if offset < 0 or not 1 <= length <= 262144:
            raise MailError("Invalid attachment range.")
        with self.connection() as client:
            self._select(client, folder, uidvalidity)
            msg = BytesParser(policy=email.policy.default).parsebytes(self._fetch(client, uid))
        parts = list(msg.walk())
        if not 0 <= part_index < len(parts):
            raise MailError("Attachment part does not exist.")
        part = parts[part_index]
        if part.is_multipart() or not (part.get_filename() or part.get_content_disposition() == 'attachment'):
            raise MailError("The part is not an attachment.")
        data = part.get_payload(decode=True) or b''
        return {'filename': part.get_filename(), 'content_type': part.get_content_type(), 'total_bytes': len(data),
                'offset': offset, 'base64': base64.b64encode(data[offset:offset+length]).decode(),
                'next_offset': offset+length if offset+length < len(data) else None}

    def create_draft(self, to, subject, body, request_id, cc=None, bcc=None, reply_folder=None, reply_uidvalidity=None, reply_uid=None, attachments=None):
        reply = (reply_folder, reply_uidvalidity, reply_uid)
        if any(x is not None for x in reply) and not all(x is not None for x in reply):
            raise MailError("Reply requires folder, UIDVALIDITY and UID together.")
        with self.write_lock, self.connection() as client:
            original = None
            if reply_uid is not None:
                self._select(client, reply_folder, reply_uidvalidity)
                original = parse_message(self._fetch(client, reply_uid, headers=True))
            msg = draft_message(self.config.email, to, subject, body, cc or [], bcc or [], request_id, original, attachments)
            raw = msg.as_bytes()
            if len(raw) > self.config.max_message_bytes:
                raise MailError('Draft exceeds the configured message size limit after MIME encoding.')
            folder = self.config.drafts_folder
            if not folder:
                drafts = [f['name'] for f in self._folders(client) if '\\Drafts' in f['flags']]
                if len(drafts) != 1:
                    raise MailError("Drafts folder is ambiguous. Set drafts_folder in configuration.")
                folder = drafts[0]
            validity = self._select(client, folder, readonly=False)
            existing = self._search(client, ['HEADER', 'Message-ID', quoted(str(msg['Message-ID']))])
            reused = bool(existing)
            if existing:
                saved = BytesParser(policy=email.policy.default).parsebytes(self._fetch(client, existing[-1], headers=True))
                if saved.get('X-ICloud-MCP-Content-SHA256') != msg['X-ICloud-MCP-Content-SHA256']:
                    raise MailError("request_id was already used for different content. Use a new request_id.")
            else:
                status, _ = client.append(quoted(utf7_encode(folder)), '(\\Draft)', None, raw)
                if status != 'OK':
                    raise MailError("iCloud did not confirm saving the draft.")
                existing = self._search(client, ['HEADER', 'Message-ID', quoted(str(msg['Message-ID']))])
            return {'saved': True, 'reused': reused, 'folder': folder, 'uidvalidity': validity,
                    'uid': existing[-1] if existing else None, 'message_id': str(msg['Message-ID']),
                    'attachments': [{'filename': p.get_filename(), 'content_type': p.get_content_type(),
                                     'size': len(p.get_payload(decode=True) or b'')} for p in msg.iter_attachments()],
                    'mailbox_url': 'https://www.icloud.com/mail/',
                    'link_note': 'Opens iCloud Mail; a stable direct draft URL is not provided by IMAP.'}
