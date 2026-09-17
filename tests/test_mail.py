import contextlib
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
