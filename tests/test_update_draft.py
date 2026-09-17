import contextlib
import imaplib
import re
from email.parser import BytesParser
from email.policy import SMTP

import pytest

from icloud_mail.config import Config
from icloud_mail.mail import Mailbox, MailError, draft_message, parse_message
from test_mail import attachment


class UpdateIMAP:
    def __init__(self):
        msg = draft_message('owner@icloud.com', ['to@example.org'], 'Re: Grüße', 'Original body',
                            ['cc@example.org'], ['bcc@example.org'], 'original_draft_001',
                            {'message-id': '<thread@example.org>', 'references': '<first@example.org>'},
                            [attachment(b'original file', 'original.pdf')])
        self.original = msg.as_bytes()
        self.messages = {8: self.original, 20: b'Subject: Unrelated\r\n\r\nKeep me'}
        self.flags = {8: {b'\\Draft', b'\\Seen'}, 20: {b'\\Deleted'}}
        self.trash = {}
        self.calls = []
        self.capabilities = b'IMAP4rev1 UIDPLUS MOVE'
        self.fail_append = False
        self.lose_append_reply = False
        self.corrupt_append = False
        self.fail_move = False
        self.lose_move_reply = False
        self.change_original = False

    def capability(self):
        return 'OK', [self.capabilities]

    def list(self):
        return 'OK', [b'(\\Drafts) "/" "Drafts"', b'(\\Trash) "/" "Deleted Messages"']

    def select(self, folder, readonly=True):
        assert folder == '"Drafts"' and not readonly
        return 'OK', [str(len(self.messages)).encode()]

    def response(self, key):
        return key, [b'42']

    def uid(self, operation, *args):
        self.calls.append((operation, *args))
        if operation == 'SEARCH':
            assert args[:2] == ('CHARSET', 'UTF-8')
            needle = re.search(rb'HEADER Message-ID "([^"]+)"', args[-1])[1].decode()
            matches = [uid for uid, raw in self.messages.items()
                       if BytesParser(policy=SMTP).parsebytes(raw).get('Message-ID') == needle]
            return 'OK', [b' '.join(str(uid).encode() for uid in matches)]
        uid = int(args[0])
        if operation == 'MOVE':
            assert uid == 8 and args[1] == '"Deleted Messages"'
            if self.fail_move:
                return 'NO', [b'Cannot move']
            self.trash[uid] = self.messages.pop(uid)
            self.flags.pop(uid)
            if self.lose_move_reply:
                raise imaplib.IMAP4.abort('Connection lost after move')
            return 'OK', [b'Moved']
        assert operation == 'FETCH'
        if uid not in self.messages:
            return 'OK', [None]
        raw = self.messages[uid]
        if args[1] == '(UID FLAGS)':
            return 'OK', [b'1 (UID ' + str(uid).encode() + b' FLAGS (' + b' '.join(self.flags[uid]) + b'))']
        if args[1] == '(RFC822.SIZE)':
            return 'OK', [f'1 (RFC822.SIZE {len(raw)})'.encode()]
        assert 'BODY.PEEK[' in args[1]
        if 'BODY.PEEK[HEADER]' in args[1]:
            raw = raw.split(b'\r\n\r\n')[0] + b'\r\n\r\n'
        return 'OK', [(b'1 (BODY[] {100}', raw), b')']

    def append(self, folder, flags, when, raw):
        self.calls.append(('append',))
        assert folder == '"Drafts"' and flags == '(\\Draft \\Seen)'
        if self.fail_append:
            return 'NO', [b'Over quota']
        self.messages[21] = raw.replace(b'Original body', b'Corrupted body') if self.corrupt_append else raw
        self.flags[21] = {b'\\Draft', b'\\Seen'}
        if self.change_original:
            self.messages[8] = self.original.replace(b'Original body', b'Concurrent change')
        if self.lose_append_reply:
            raise imaplib.IMAP4.abort('Connection lost after append')
        return 'OK', [b'APPENDUID 42 21']


@pytest.fixture
def update_box():
    box = Mailbox(Config(email='owner@icloud.com', app_password='test'))
    client = UpdateIMAP()
    @contextlib.contextmanager
    def connection():
        yield client
    box.connection = connection
    args = dict(folder='Drafts', uidvalidity=42, uid=8,
                expected_message_id=BytesParser(policy=SMTP).parsebytes(client.original)['Message-ID'],
                request_id='update_request_001', attachments=[attachment(b'new file', 'new.pdf')])
    return box, client, args


def test_update_preserves_fields_and_files_and_moves_only_original(update_box):
    box, client, args = update_box
    result = box.update_draft(**args)
    assert result['updated'] and result['previous_draft_removed'] and not result['cleanup_pending']
    assert result['previous_draft_moved_to'] == 'Deleted Messages'
    assert result['uid'] == 21 and result['uidvalidity'] == 42
    assert set(client.messages) == {20, 21} and client.trash[8] == client.original
    original = BytesParser(policy=SMTP).parsebytes(client.original)
    saved = BytesParser(policy=SMTP).parsebytes(client.messages[21])
    for key in ('From', 'To', 'Cc', 'Bcc', 'Subject', 'In-Reply-To', 'References'):
        assert saved[key] == original[key]
    assert saved.get_body().get_content() == original.get_body().get_content()
    assert [p.get_payload(decode=True) for p in saved.iter_attachments()] == [b'original file', b'new file']
    assert box.update_draft(**args)['reused']
    assert sum(c[0] == 'append' for c in client.calls) == 1
    assert sum(c[0] == 'MOVE' for c in client.calls) == 1
    assert not any(c[0] in ('STORE', 'EXPUNGE') for c in client.calls)
    with pytest.raises(MailError, match='different content'):
        box.update_draft(**dict(args, subject='changed'))


def test_update_body_and_recipients_preserves_existing_attachments(update_box):
    box, client, args = update_box
    box.update_draft(**dict(args, to=['new@example.org'], cc=[], bcc=[], subject='New subject', body='Neuer Text', attachments=None))
    saved = BytesParser(policy=SMTP).parsebytes(client.messages[21])
    assert saved.get_body().get_content().strip() == 'Neuer Text'
    assert saved['To'] == 'new@example.org' and not saved['Cc'] and not saved['Bcc']
    assert saved['Subject'] == 'New subject'
    assert saved['In-Reply-To'] == '<thread@example.org>'
    assert [p.get_payload(decode=True) for p in saved.iter_attachments()] == [b'original file']


@pytest.mark.parametrize('change,match', [
    ({'folder': 'INBOX'}, 'Only the configured'),
    ({'uidvalidity': 99}, 'identity changed'),
    ({'uid': 20}, 'not an active draft'),
    ({'uid': 999}, 'not an active draft'),
    ({'expected_message_id': '<wrong@example.org>'}, 'Message-ID changed'),
])
def test_wrong_target_never_written(update_box, change, match):
    box, client, args = update_box
    with pytest.raises(MailError, match=match):
        box.update_draft(**dict(args, **change))
    assert set(client.messages) == {8, 20} and not client.trash
    assert not any(c[0] in ('append', 'MOVE') for c in client.calls)


def test_move_required_before_writing(update_box):
    box, client, args = update_box
    client.capabilities = b'IMAP4rev1'
    with pytest.raises(MailError, match='require IMAP MOVE'):
        box.update_draft(**args)
    assert set(client.messages) == {8, 20}


@pytest.mark.parametrize('failure,match', [('fail_append', 'save was not confirmed'),
                                         ('corrupt_append', 'verification failed'),
                                         ('change_original', 'content changed')])
def test_failures_keep_original(update_box, failure, match):
    box, client, args = update_box
    setattr(client, failure, True)
    with pytest.raises(MailError, match=match):
        box.update_draft(**args)
    assert 8 in client.messages and not client.trash
    assert not any(c[0] == 'MOVE' for c in client.calls)


def test_retry_after_lost_append_response(update_box):
    box, client, args = update_box
    client.lose_append_reply = True
    with pytest.raises(imaplib.IMAP4.abort):
        box.update_draft(**args)
    assert set(client.messages) == {8, 20, 21}
    result = box.update_draft(**args)
    assert result['updated'] and result['reused']
    assert set(client.messages) == {20, 21}
    assert sum(c[0] == 'append' for c in client.calls) == 1


@pytest.mark.parametrize('failure', ['fail_move', 'lose_move_reply'])
def test_move_failure_returns_saved_draft_and_retry_completes(update_box, failure):
    box, client, args = update_box
    setattr(client, failure, True)
    first = box.update_draft(**args)
    assert first['saved'] and first['cleanup_pending'] and not first['updated']
    setattr(client, failure, False)
    second = box.update_draft(**args)
    assert second['updated'] and second['reused'] and not second['cleanup_pending']
    assert set(client.messages) == {20, 21}
    assert sum(c[0] == 'append' for c in client.calls) == 1


def test_modified_replacement_cannot_trigger_cleanup(update_box):
    box, client, args = update_box
    client.fail_move = True
    box.update_draft(**args)
    client.messages[21] = client.messages[21].replace(b'Original body', b'Edited externally')
    client.fail_move = False
    with pytest.raises(MailError, match='verification failed'):
        box.update_draft(**args)
    assert 8 in client.messages and not client.trash


def test_html_and_inline_image_preserved_when_adding_files(update_box):
    box, client, args = update_box
    msg = BytesParser(policy=SMTP).parsebytes(client.original)
    body = msg.get_body()
    body.add_alternative('<p>Hello<img src="cid:picture"></p>', subtype='html')
    html = body.get_body(preferencelist=('html',))
    html.add_related(b'picture data', maintype='image', subtype='png', cid='<picture>')
    client.original = client.messages[8] = msg.as_bytes()
    box.update_draft(**args)
    saved = BytesParser(policy=SMTP).parsebytes(client.messages[21])
    original = BytesParser(policy=SMTP).parsebytes(client.original)
    assert saved.get_body(preferencelist=('html',)).get_content() == original.get_body(preferencelist=('html',)).get_content()
    assert next(p for p in saved.walk() if p.get('Content-ID') == '<picture>').get_payload(decode=True) == b'picture data'
    assert len(parse_message(client.messages[21])['attachments']) == 2


class UIDPlusIMAP(UpdateIMAP):
    def __init__(self):
        super().__init__()
        self.capabilities = b'IMAP4rev1 UIDPLUS'
        self.drafts = self.messages
        self.draft_flags = self.flags
        self.trash_flags = {}
        self.selected = 'Drafts'
        self.failure = None

    def select(self, folder, readonly=True):
        self.selected = folder.strip('"')
        if self.selected == 'Drafts':
            self.messages, self.flags = self.drafts, self.draft_flags
            assert not readonly
        else:
            assert self.selected == 'Deleted Messages' and readonly
            self.messages, self.flags = self.trash, self.trash_flags
        return 'OK', [str(len(self.messages)).encode()]

    def response(self, key):
        return key, [b'42' if self.selected == 'Drafts' else b'43']

    def uid(self, operation, *args):
        if operation not in ('COPY', 'STORE', 'EXPUNGE'):
            return super().uid(operation, *args)
        self.calls.append((operation, *args))
        assert self.selected == 'Drafts' and args[0] == '8'
        if self.failure == operation + '_NO':
            return 'NO', [b'Failure']
        if operation == 'COPY':
            assert args[1] == '"Deleted Messages"'
            target = max(self.trash, default=100) + 1
            self.trash[target] = self.drafts[8]
            self.trash_flags[target] = self.draft_flags[8].copy()
            if self.failure == 'CORRUPT_COPY':
                self.trash[target] = self.trash[target].replace(b'Original body', b'Corrupted copy')
        elif operation == 'STORE':
            assert args[1:] == ('+FLAGS.SILENT', '(\\Deleted)')
            self.draft_flags[8].add(b'\\Deleted')
        else:
            assert len(args) == 1 and b'\\Deleted' in self.draft_flags[8]
            self.drafts.pop(8)
            self.draft_flags.pop(8)
        if self.failure == operation + '_LOST_REPLY':
            raise imaplib.IMAP4.abort('Connection lost after command')
        return 'OK', [b'Done']


@pytest.fixture
def uidplus_box(update_box):
    box, _, args = update_box
    client = UIDPlusIMAP()
    @contextlib.contextmanager
    def connection():
        yield client
    box.connection = connection
    return box, client, args


def test_uidplus_archives_verified_copy_and_only_removes_target(uidplus_box):
    box, client, args = uidplus_box
    result = box.update_draft(**args)
    assert result['updated'] and result['previous_draft_moved_to'] == 'Deleted Messages'
    assert set(client.drafts) == {20, 21}
    assert list(client.trash.values()) == [client.original]
    assert client.draft_flags[20] == {b'\\Deleted'}
    assert ('EXPUNGE', '8') in client.calls
    assert box.update_draft(**args)['reused']
    assert sum(c[0] == 'COPY' for c in client.calls) == 1
    assert sum(c[0] == 'append' for c in client.calls) == 1


@pytest.mark.parametrize('failure', ['COPY_NO', 'COPY_LOST_REPLY', 'STORE_NO',
                                     'STORE_LOST_REPLY', 'EXPUNGE_NO', 'EXPUNGE_LOST_REPLY'])
def test_uidplus_partial_failures_resume_without_duplicate_replacements(uidplus_box, failure):
    box, client, args = uidplus_box
    client.failure = failure
    first = box.update_draft(**args)
    assert first['saved'] and first['cleanup_pending'] and not first['updated']
    assert 21 in client.drafts and 20 in client.drafts
    client.failure = None
    second = box.update_draft(**args)
    assert second['updated'] and second['reused']
    assert set(client.drafts) == {20, 21}
    assert list(client.trash.values()) == [client.original]
    assert sum(c[0] == 'append' for c in client.calls) == 1


def test_uidplus_bad_trash_copy_never_marks_or_removes_original(uidplus_box):
    box, client, args = uidplus_box
    client.failure = 'CORRUPT_COPY'
    result = box.update_draft(**args)
    assert result['cleanup_pending'] and 8 in client.drafts
    assert b'\\Deleted' not in client.draft_flags[8]
    assert not any(c[0] in ('STORE', 'EXPUNGE') for c in client.calls)


def test_uidplus_rechecks_new_draft_after_copy(uidplus_box):
    box, client, args = uidplus_box
    original_uid = client.uid
    def uid(operation, *values):
        result = original_uid(operation, *values)
        if operation == 'COPY':
            client.drafts[21] = client.drafts[21].replace(b'Original body', b'Changed replacement')
        return result
    client.uid = uid
    result = box.update_draft(**args)
    assert result['cleanup_pending'] and 8 in client.drafts
    assert not any(c[0] in ('STORE', 'EXPUNGE') for c in client.calls)
