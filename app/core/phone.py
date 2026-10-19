from typing import Optional, Tuple
import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat


def normalize_phone(raw: str, country: Optional[str] = None) -> Tuple[str, str]:
    """Validate a phone number and return (E.164, ISO region).

    `raw` may be international (+351...) or national when `country` (ISO 3166-1
    alpha-2) is given. Raises ValueError for invalid numbers.
    """
    region = country.upper() if country else None
    try:
        number = phonenumbers.parse(raw.strip(), None if raw.strip().startswith("+") else region)
    except NumberParseException:
        raise ValueError("Número de telefone inválido.")
    if not phonenumbers.is_valid_number(number):
        raise ValueError("Número de telefone inválido.")
    iso = phonenumbers.region_code_for_number(number) or region
    if region and iso and region != iso and not raw.strip().startswith("+"):
        raise ValueError("Número de telefone inválido para o país selecionado.")
    return phonenumbers.format_number(number, PhoneNumberFormat.E164), iso or ""
