import contextlib
import hashlib
import imaplib
from email.parser import BytesParser
from email.policy import SMTP

import pytest

from icloud_mail.config import Config
from icloud_mail.mail import Mailbox, MailError
from test_update_draft import UIDPlusIMAP


class DeleteIMAP(UIDPlusIMAP):
    """Exercise real mailbox switching and targeted writes without any network."""

    def __init__(self, method='UIDPLUS'):
        super().__init__()
        self.capabilities = b'IMAP4rev1 UIDPLUS' + (b' MOVE' if method == 'MOVE' else b'')
        self.folder_rows = [b'(\\Drafts) "/" "Drafts"',
                            b'(\\Trash) "/" "Deleted Messages"']
        self.after_copy = None

    def list(self):
        return 'OK', self.folder_rows

    def select(self, folder, readonly=True):
        self.selected = folder.strip('"')
        if self.selected == 'Drafts':
            self.messages, self.flags = self.drafts, self.draft_flags
        else:
            assert self.selected == 'Deleted Messages' and readonly
            self.messages, self.flags = self.trash, self.trash_flags
        return 'OK', [str(len(self.messages)).encode()]

    def uid(self, operation, *args):
        if operation == 'MOVE':
            self.calls.append((operation, *args))
            assert self.selected == 'Drafts' and args == ('8', '"Deleted Messages"')
            if self.failure == 'MOVE_NO':
                return 'NO', [b'Move rejected']
            target = max(self.trash, default=100) + 1
            self.trash[target] = self.drafts.pop(8)
            self.trash_flags[target] = self.draft_flags.pop(8)
            if self.failure == 'MOVE_LOST_REPLY':
                raise imaplib.IMAP4.abort('Connection lost after move')
            return 'OK', [b'COPYUID 43 8 ' + str(target).encode()]
        result = super().uid(operation, *args)
        if operation == 'COPY' and self.after_copy:
            self.after_copy()
        return result

    def archive_externally(self):
        self.trash[101] = self.drafts.pop(8)
        self.trash_flags[101] = self.draft_flags.pop(8)


@pytest.fixture
def delete_box():
    def make(method='UIDPLUS'):
        box = Mailbox(Config(email='owner@icloud.com', app_password='test'))
        client = DeleteIMAP(method)

        @contextlib.contextmanager
        def connection():
            yield client

        box.connection = connection
        arguments = dict(folder='Drafts', uidvalidity=42, uid=8,
                         expected_message_id=BytesParser(policy=SMTP).parsebytes(client.original)['Message-ID'],
                         expected_content_sha256=hashlib.sha256(client.original).hexdigest())
        return box, client, arguments
    return make


def writes(client):
    return [call for call in client.calls if call[0] in ('MOVE', 'COPY', 'STORE', 'EXPUNGE', 'append')]


@pytest.mark.parametrize('method', ['MOVE', 'UIDPLUS'])
def test_delete_archives_exact_draft_and_preserves_unrelated_deleted_message(delete_box, method):
    box, client, arguments = delete_box(method)
    unrelated_raw = client.drafts[20]
    unrelated_flags = client.draft_flags[20].copy()

    result = box.delete_draft(**arguments)

    assert result['deleted'] and result['removed_from_drafts']
    assert not result['cleanup_pending'] and not result['permanently_deleted']
    assert result['trash'] == dict(folder='Deleted Messages', uidvalidity=43, uid=101,
                                  message_id=arguments['expected_message_id'],
                                  content_sha256=arguments['expected_content_sha256'])
    assert client.drafts == {20: unrelated_raw}
    assert client.draft_flags[20] == unrelated_flags == {b'\\Deleted'}
    assert client.trash == {101: client.original}
    if method == 'MOVE':
        assert writes(client) == [('MOVE', '8', '"Deleted Messages"')]
    else:
        assert writes(client) == [('COPY', '8', '"Deleted Messages"'),
                                  ('STORE', '8', '+FLAGS.SILENT', '(\\Deleted)'),
                                  ('EXPUNGE', '8')]

    first_writes = writes(client).copy()
    repeated = box.delete_draft(**arguments)
    assert repeated['deleted'] and repeated['reused']
    assert repeated['trash'] == result['trash']
    assert writes(client) == first_writes


def test_read_exposes_full_content_hash_without_marking_seen(delete_box):
    box, client, _ = delete_box()
    flags = client.draft_flags[8].copy()
    result = box.read('Drafts', 42, 8, max_chars=1)
    assert result['content_sha256'] == hashlib.sha256(client.original).hexdigest()
    assert len(result['body']) == 1
    assert client.draft_flags[8] == flags
    assert not writes(client)
    assert any(call[0] == 'FETCH' and 'BODY.PEEK[' in call[2] for call in client.calls)


@pytest.mark.parametrize('change, message', [
    ({'folder': 'INBOX'}, 'Only the configured Drafts'),
    ({'uidvalidity': 99}, 'identity changed'),
    ({'uid': 20}, 'not a draft'),
    ({'expected_message_id': '<different@example.org>'}, 'identity or content changed'),
    ({'expected_content_sha256': '0' * 64}, 'identity or content changed'),
    ({'expected_content_sha256': 'invalid'}, 'content_sha256'),
    ({'expected_message_id': 'bad\r\nSTORE 8 +FLAGS (\\Deleted)'}, 'Control'),
    ({'uid': 0}, 'positive'),
])
def test_invalid_identity_never_writes(delete_box, change, message):
    box, client, arguments = delete_box()
    with pytest.raises(MailError, match=message):
        box.delete_draft(**dict(arguments, **change))
    assert set(client.drafts) == {8, 20}
    assert not client.trash and not writes(client)


@pytest.mark.parametrize('method', ['MOVE', 'UIDPLUS'])
def test_changed_content_with_same_message_id_stops_before_writes(delete_box, method):
    box, client, arguments = delete_box(method)
    client.drafts[8] = client.original.replace(b'Original body', b'Changed draft body')
    with pytest.raises(MailError, match='identity or content changed'):
        box.delete_draft(**arguments)
    assert not writes(client) and not client.trash


@pytest.mark.parametrize('folder_rows', [
    [b'(\\Drafts) "/" "Drafts"'],
    [b'(\\Drafts) "/" "Drafts"', b'(\\Trash) "/" "Deleted Messages"',
     b'(\\Trash) "/" "Other Trash"'],
    [b'(\\Drafts \\Trash) "/" "Drafts"'],
])
def test_missing_ambiguous_or_same_trash_stops_before_writes(delete_box, folder_rows):
    box, client, arguments = delete_box()
    client.folder_rows = folder_rows
    with pytest.raises(MailError, match='Trash folder is ambiguous'):
        box.delete_draft(**arguments)
    assert not writes(client) and not client.trash


def test_no_safe_capability_stops_before_writes(delete_box):
    box, client, arguments = delete_box()
    client.capabilities = b'IMAP4rev1'
    with pytest.raises(MailError, match='requires IMAP MOVE or UIDPLUS'):
        box.delete_draft(**arguments)
    assert not writes(client)


def test_corrupt_copy_never_marks_or_removes_source(delete_box):
    box, client, arguments = delete_box()
    client.failure = 'CORRUPT_COPY'
    result = box.delete_draft(**arguments)
    assert result['cleanup_pending'] and not result['deleted']
    assert client.drafts[8] == client.original
    assert b'\\Deleted' not in client.draft_flags[8]
    assert [call[0] for call in writes(client)] == ['COPY']


@pytest.mark.parametrize('failure', ['COPY_NO', 'COPY_LOST_REPLY', 'STORE_NO',
                                     'STORE_LOST_REPLY', 'EXPUNGE_NO', 'EXPUNGE_LOST_REPLY'])
def test_uidplus_partial_failure_retry_finishes_without_duplicate_copy(delete_box, failure):
    box, client, arguments = delete_box()
    client.failure = failure
    first = box.delete_draft(**arguments)
    assert first['cleanup_pending'] and not first['deleted']
    assert 20 in client.drafts and client.draft_flags[20] == {b'\\Deleted'}

    client.failure = None
    second = box.delete_draft(**arguments)
    assert second['deleted'] and not second['cleanup_pending']
    assert set(client.drafts) == {20}
    assert client.trash == {101: client.original}
    successful_copies = sum(call[0] == 'COPY' for call in writes(client))
    assert successful_copies == (2 if failure == 'COPY_NO' else 1)
    assert all(call[1] == '8' for call in writes(client))


@pytest.mark.parametrize('failure', ['MOVE_NO', 'MOVE_LOST_REPLY'])
def test_move_partial_failure_retry_only_moves_target_once(delete_box, failure):
    box, client, arguments = delete_box('MOVE')
    client.failure = failure
    first = box.delete_draft(**arguments)
    assert first['cleanup_pending'] and not first['deleted']

    client.failure = None
    second = box.delete_draft(**arguments)
    assert second['deleted']
    assert set(client.drafts) == {20} and client.trash == {101: client.original}
    assert sum(call[0] == 'MOVE' for call in writes(client)) == (2 if failure == 'MOVE_NO' else 1)
    assert not any(call[0] in ('STORE', 'EXPUNGE') for call in writes(client))


def test_missing_source_is_success_only_with_exact_recoverable_trash_copy(delete_box):
    box, client, arguments = delete_box()
    client.archive_externally()
    result = box.delete_draft(**arguments)
    assert result['deleted'] and result['reused'] and result['trash']['uid'] == 101
    assert not writes(client)


@pytest.mark.parametrize('trash_condition', ['absent', 'different_content', 'deleted'])
def test_missing_source_without_verified_recoverable_copy_is_not_success(delete_box, trash_condition):
    box, client, arguments = delete_box()
    client.archive_externally()
    if trash_condition == 'absent':
        client.trash.clear()
        client.trash_flags.clear()
    elif trash_condition == 'different_content':
        client.trash[101] = client.original.replace(b'Original body', b'Different body')
    else:
        client.trash_flags[101].add(b'\\Deleted')
    with pytest.raises(MailError, match='missing and no matching recoverable Trash copy'):
        box.delete_draft(**arguments)
    assert not writes(client)


def test_unverified_deleted_source_is_not_expunged(delete_box):
    box, client, arguments = delete_box()
    client.draft_flags[8].add(b'\\Deleted')
    with pytest.raises(MailError, match='marked deleted without a safe verified cleanup path'):
        box.delete_draft(**arguments)
    assert not writes(client) and client.drafts[8] == client.original


def test_source_changed_after_copy_is_retained(delete_box):
    box, client, arguments = delete_box()
    client.after_copy = lambda: client.drafts.__setitem__(8, client.original.replace(b'Original body', b'Concurrent edit'))
    result = box.delete_draft(**arguments)
    assert result['cleanup_pending'] and not result['deleted']
    assert b'\\Deleted' not in client.draft_flags[8]
    assert [call[0] for call in writes(client)] == ['COPY']


def test_existing_verified_copy_allows_uidplus_resume_without_another_copy(delete_box):
    box, client, arguments = delete_box()
    client.trash[101] = client.original
    client.trash_flags[101] = client.draft_flags[8].copy()
    client.draft_flags[8].add(b'\\Deleted')
    result = box.delete_draft(**arguments)
    assert result['deleted'] and result['reused']
    assert writes(client) == [('STORE', '8', '+FLAGS.SILENT', '(\\Deleted)'), ('EXPUNGE', '8')]
    assert client.trash == {101: client.original}
