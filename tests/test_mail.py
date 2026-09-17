import contextlib
import base64
from email.parser import BytesParser
from email.policy import default

import pytest

from icloud_mail.config import Config
from icloud_mail.mail import Mailbox, MailError, draft_message, parse_folder, parse_message, quoted, utf7_decode, utf7_encode


def test_folders_and_injection():
    name = 'Entwürfe & Käse/日本語'
    assert utf7_decode(utf7_encode(name)) == name
    row = b'(\\HasNoChildren \\Drafts) "/" "' + utf7_encode(name).encode() + b'"'
    assert parse_folder(row) == {'name': name, 'flags':['\\HasNoChildren','\\Drafts']}
    assert parse_folder((b'(\\Drafts) "/" {6}', b'Drafts'))['name'] == 'Drafts'
    assert quoted('a"b\\c') == '"a\\"b\\\\c"'
    with pytest.raises(MailError):
        quoted('hello\r\nSTORE 1 +FLAGS (\\Deleted)')


def test_mime_and_draft_reply():
    original = {'message-id':'<original@example.org>', 'references':'<first@example.org>'}
    msg = draft_message('owner@icloud.com', ['Person <person@example.org>'], 'Re: Grüße', 'Hallo ü', [], [], 'request_0000000001', original)
    parsed = BytesParser(policy=default).parsebytes(msg.as_bytes())
    assert parsed['In-Reply-To'] == '<original@example.org>'
    assert parsed['References'] == '<first@example.org> <original@example.org>'
    assert parsed.get_content().strip() == 'Hallo ü'
    assert msg['Message-ID'] == draft_message('owner@icloud.com', [], 'x', 'y', [], [], 'request_0000000001')['Message-ID']
    with pytest.raises(MailError):
        draft_message('owner@icloud.com', ['person@example.org\r\nBcc: evil@example.org'], 'x', '', [], [], 'request_0000000001')


def test_html_and_attachment():
    from email.message import EmailMessage
    msg = EmailMessage()
    msg['Subject'] = 'Grüße'
    msg.set_content('<html><head><title>hidden</title></head><body><p>Hello</p><script>secret</script><img src="https://tracking.example/x"></body></html>', subtype='html')
    msg.add_attachment(b'PDF bytes', maintype='application', subtype='pdf', filename='../invoice.pdf')
    parsed = parse_message(msg.as_bytes())
    assert parsed['subject'] == 'Grüße'
    assert 'Hello' in parsed['body'] and 'secret' not in parsed['body'] and 'hidden' not in parsed['body']
    assert parsed['attachments'][0]['filename'] == '../invoice.pdf'  # metadata only, never written as a path
    assert parsed['attachments'][0]['size'] == 9


class FakeIMAP:
    def __init__(self):
        self.raw = b'From: p@example.org\r\nTo: owner@icloud.com\r\nSubject: Test\r\nMessage-ID: <original@example.org>\r\n\r\nBody'
        self.calls = []
        self.saved = None
    def list(self):
        return 'OK', [b'(\\Drafts) "/" "Drafts"']
    def select(self, name, readonly=True):
        self.calls.append(('select', name, readonly))
        return 'OK', [b'3']
    def response(self, key):
        return key, [b'42']
    def uid(self, operation, *args):
        self.calls.append((operation, *args))
        if operation == 'SEARCH':
            # uid() forwards its arguments verbatim; RFC 3501 requires the
            # CHARSET keyword before a supplied encoding name.
            assert args[:2] == ('CHARSET', 'UTF-8'), 'Invalid UID SEARCH charset syntax'
            if b'Message-ID' in args[-1]:
                return 'OK', [b'9' if self.saved else b'']
            return 'OK', [b'2 5 8']
        raw = self.saved if self.saved and args[0] == '9' else self.raw
        if args[1] == '(RFC822.SIZE)':
            return 'OK', [f'1 (RFC822.SIZE {len(raw)})'.encode()]
        assert 'BODY.PEEK[' in args[1]
        if 'BODY.PEEK[HEADER]' in args[1]:
            raw = raw.split(b'\r\n\r\n', 1)[0] + b'\r\n\r\n'
        return 'OK', [(b'1 (BODY[] {100}', raw), b')']
    def append(self, folder, flags, when, raw):
        self.calls.append(('append', folder, flags))
        assert flags == '(\\Draft)'
        self.saved = raw
        return 'OK', [b'APPENDUID 42 9']


@pytest.fixture
def mailbox():
    box = Mailbox(Config(email='owner@icloud.com', app_password='test'))
    client = FakeIMAP()
    @contextlib.contextmanager
    def connection():
        yield client
    box.connection = connection
    return box, client


def test_search_pagination_and_read_identity(mailbox):
    box, client = mailbox
    results = box.search(sender='some"one', since='2026-01-01', before='2027-01-01', unread=True, limit=2)
    assert [x['uid'] for x in results['messages']] == [8, 5]
    assert results['next_before_uid'] == 5
    command = next(c[-1] for c in client.calls if c[0] == 'SEARCH')
    assert b'SINCE 01-Jan-2026 BEFORE 01-Jan-2027 UNSEEN' in command
    assert b'FROM "some\\"one"' in command
    assert box.read('INBOX', 42, 8, offset=1, max_chars=2)['body'] == 'od'
    assert all(c[2] for c in client.calls if c[0] == 'select')
    assert not any(c[0] in ('STORE','EXPUNGE') for c in client.calls)
    with pytest.raises(MailError, match='identity changed'):
        box.read('INBOX', 43, 8)
    assert box.search(before_uid=1)['messages'] == []


def test_search_utf8_criteria(mailbox):
    box, client = mailbox
    result = box.search(subject='Grüße', limit=1)
    assert len(result['messages']) == 1
    command = next(c for c in client.calls if c[0] == 'SEARCH')
    assert command == ('SEARCH', 'CHARSET', 'UTF-8', 'ALL SUBJECT "Grüße"'.encode('utf-8'))


def test_draft_idempotency_and_reply(mailbox):
    box, client = mailbox
    args = dict(to=['p@example.org'], subject='Re: Test', body='Antwort', request_id='unique_request_001', reply_folder='INBOX', reply_uidvalidity=42, reply_uid=8)
    first = box.create_draft(**args)
    second = box.create_draft(**args)
    assert first['saved'] and not first['reused'] and second['reused']
    assert first['uid'] == 9
    assert sum(c[0] == 'append' for c in client.calls) == 1
    assert BytesParser(policy=default).parsebytes(client.saved)['In-Reply-To'] == '<original@example.org>'
    with pytest.raises(MailError, match='different content'):
        box.create_draft(**dict(args, body='Changed'))


def test_size_limit_and_recipient_validation(mailbox):
    box, client = mailbox
    box.config.max_message_bytes = 4
    with pytest.raises(MailError, match='download limit'):
        box.read('INBOX', 42, 8)
    with pytest.raises(MailError):
        draft_message('owner@icloud.com', ['a@example.org, b@example.org'], 's', '', [], [], 'unique_request_001')


def attachment(data=b'\x00\xffPDF bytes', filename='Prüfung 日本語.pdf', content_type='application/pdf'):
    return dict(filename=filename, content_type=content_type, content_base64=base64.b64encode(data).decode())


def test_attachment_draft_roundtrip_and_retries(mailbox):
    box, client = mailbox
    files = [attachment(), attachment(b'Hello', 'notes.txt', 'text/plain')]
    args = dict(to=['p@example.org'], cc=['cc@example.org'], bcc=['bcc@example.org'], subject='Re: Test',
                body='Grüße', request_id='attachment_request_001', attachments=files,
                reply_folder='INBOX', reply_uidvalidity=42, reply_uid=8)
    result = box.create_draft(**args)
    parsed = BytesParser(policy=default).parsebytes(client.saved)
    assert parsed.get_body().get_content().strip() == 'Grüße'
    assert parsed['Cc'] == 'cc@example.org' and parsed['Bcc'] == 'bcc@example.org'
    assert parsed['In-Reply-To'] == '<original@example.org>'
    for part, item, metadata in zip(parsed.iter_attachments(), files, result['attachments'], strict=True):
        assert part.get_content_disposition() == 'attachment'
        assert part.get_filename() == metadata['filename'] == item['filename']
        assert part.get_content_type() == metadata['content_type'] == item['content_type']
        assert part.get_payload(decode=True) == base64.b64decode(item['content_base64'])
        assert metadata['size'] == len(part.get_payload(decode=True))
    assert box.create_draft(**args)['reused']
    for changed in ([attachment(b'changed'), files[1]], [attachment(filename='other.pdf'), files[1]],
                    [attachment(content_type='application/octet-stream'), files[1]], files[::-1], []):
        with pytest.raises(MailError, match='different content'):
            box.create_draft(**dict(args, attachments=changed))
    assert sum(c[0] == 'append' for c in client.calls) == 1


@pytest.mark.parametrize('changed', [
    {'content_base64': 'invalid!'}, {'content_base64': '日本語'}, {'filename': '../file.pdf'},
    {'filename': 'C:\\file.pdf'}, {'filename': 'file\r\nX: injected'},
    {'content_type': 'text/plain; charset=utf-8'}, {'content_type': 'multipart/mixed'},
    {'content_type': 'message/rfc822'}, {'content_type': 'text/plain\r\nX: injected'},
])
def test_invalid_attachment_is_not_saved(mailbox, changed):
    box, client = mailbox
    with pytest.raises(MailError):
        box.create_draft([], 'Test', 'Body', 'attachment_request_001', attachments=[dict(attachment(), **changed)])
    assert client.saved is None


def test_attachment_limits(mailbox):
    box, client = mailbox
    args = dict(to=[], subject='Test', body='Body', request_id='attachment_request_001')
    with pytest.raises(MailError, match='At most 10'):
        box.create_draft(**args, attachments=[attachment()] * 11)
    with pytest.raises(MailError, match='combined 10 MiB'):
        box.create_draft(**args, attachments=[attachment(b'x'*(5*1024*1024+1))] * 2)
    box.config.max_message_bytes = 1000
    with pytest.raises(MailError, match='after MIME encoding'):
        box.create_draft(**args, attachments=[attachment(b'x'*1000)])
    assert client.saved is None


def test_empty_attachment_list_preserves_retry_identity():
    args = ('owner@icloud.com', [], 'Test', 'Body', [], [], 'attachment_request_001')
    original = draft_message(*args)
    empty = draft_message(*args, attachments=[])
    assert original['X-ICloud-MCP-Content-SHA256'] == empty['X-ICloud-MCP-Content-SHA256']
    assert not empty.is_multipart()
