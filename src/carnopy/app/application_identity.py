from __future__ import annotations

from PySide6.QtCore import QCoreApplication

ORGANIZATION_NAME = "Carnopy"
APPLICATION_NAME = "Carnopy Desktop"


def apply_application_identity(application: QCoreApplication) -> None:
    """Apply the stable identity used by both desktop frontends."""

    application.setOrganizationName(ORGANIZATION_NAME)
    application.setApplicationName(APPLICATION_NAME)
