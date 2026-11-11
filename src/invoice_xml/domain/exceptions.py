"""Excepciones del dominio para facturación y generación XML UBL 2.1."""


class InvoiceDomainError(ValueError):
    """Error base cuando una entidad de facturación viola invariantes de negocio."""


class XmlSchemaValidationError(Exception):
    """Error lanzado cuando el XML generado no cumple con UBL-Invoice-2.1.xsd."""

    def __init__(self, message: str, details: list[str] | None = None) -> None:
        super().__init__(message)
        self.details = details or []

