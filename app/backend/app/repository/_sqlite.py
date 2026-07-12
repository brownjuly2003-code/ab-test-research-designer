"""The SQLite backend: the domain mixins composed into one class.

Nothing lives here but the composition. Each domain is defined in its own module and
every method keeps the signature it had as part of the former single-class backend.
"""

from app.backend.app.repository._api_keys import _ApiKeysMixin
from app.backend.app.repository._audit import _AuditMixin
from app.backend.app.repository._core import _BackendCore
from app.backend.app.repository._diagnostics import _DiagnosticsMixin
from app.backend.app.repository._execution import _ExecutionMixin
from app.backend.app.repository._history import _HistoryMixin
from app.backend.app.repository._projects import _ProjectsMixin
from app.backend.app.repository._slack import _SlackMixin
from app.backend.app.repository._templates import _TemplatesMixin
from app.backend.app.repository._webhooks import _WebhooksMixin
from app.backend.app.repository._workspace import _WorkspaceMixin


class SQLiteBackend(
    _ProjectsMixin,
    _HistoryMixin,
    _TemplatesMixin,
    _ApiKeysMixin,
    # _AuditMixin inherits _WebhooksMixin (transactional outbox enqueue), so the
    # subclass must precede its base here or the MRO cannot linearize.
    _AuditMixin,
    _WebhooksMixin,
    _SlackMixin,
    _WorkspaceMixin,
    _DiagnosticsMixin,
    _ExecutionMixin,
    _BackendCore,
):
    pass
