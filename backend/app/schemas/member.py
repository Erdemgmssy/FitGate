import re
from datetime import date
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator
from app.core.time import localdate


def normalize_phone(value):
    if not isinstance(value, str) or not re.fullmatch(r'\+?[0-9 ()\-.]+', value.strip()):
        raise ValueError('Telefon biçimi geçersiz.')
    digits = re.sub(r'\D', '', value)
    if value.strip().startswith('00'):
        digits = digits[2:]
    if not 10 <= len(digits) <= 15 or len(set(digits)) == 1:
        raise ValueError('Telefon 10–15 rakam içermeli.')
    if len(digits) == 12 and digits.startswith('90'):
        digits = '0' + digits[2:]
    elif len(digits) == 10 and not value.strip().startswith('+'):
        digits = '0' + digits
    return digits


def normalize_email(value):
    value = value.strip().lower()
    if not value:
        return ''
    local, separator, domain = value.rpartition('@')
    try:
        domain = domain.encode('idna').decode('ascii')
    except UnicodeError:
        raise ValueError('E-posta biçimi geçersiz.') from None
    atom = r"[a-z0-9!#$%&'*+/=?^_`{|}~-]+"
    label = r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'
    if not separator or len(local) > 64 or not re.fullmatch(atom+r'(?:\.'+atom+r')*', local) or not re.fullmatch(label+r'(?:\.'+label+r')+', domain) or len(local+'@'+domain)>254:
        raise ValueError('E-posta biçimi geçersiz.')
    return local+'@'+domain


class MemberDetails(BaseModel):
    model_config = ConfigDict(extra='ignore')
    name: StrictStr = Field(min_length=1, max_length=120)
    phone: StrictStr = Field(min_length=1, max_length=30)
    email: StrictStr = Field(default='', max_length=254)
    birthDate: date | None = None
    emergency: StrictStr = Field(default='', max_length=200)
    emergencyPhone: StrictStr = Field(default='', max_length=30)
    trainer: StrictStr = Field(default='', max_length=120)
    address: StrictStr = Field(default='', max_length=400)
    note: StrictStr = Field(default='', max_length=4000)

    @field_validator('name', 'emergency', 'trainer', 'address', 'note')
    @classmethod
    def trimmed(cls, value, info):
        value = value.strip()
        if info.field_name == 'name' and not value:
            raise ValueError('Ad soyad gerekli.')
        return value

    @field_validator('phone')
    @classmethod
    def phone_valid(cls, value):
        normalize_phone(value)
        return value.strip()

    @field_validator('emergencyPhone')
    @classmethod
    def emergency_phone_valid(cls, value):
        if value.strip():
            normalize_phone(value)
        return value.strip()

    @field_validator('email')
    @classmethod
    def email_valid(cls, value):
        return normalize_email(value)

    @field_validator('birthDate', mode='before')
    @classmethod
    def blank_birth_date(cls, value):
        if value in ('', None): return None
        if not isinstance(value, (str, date)):
            raise ValueError('Doğum tarihi geçersiz.')
        return value

    @field_validator('birthDate')
    @classmethod
    def birth_date_valid(cls, value):
        if value and value > localdate():
            raise ValueError('Doğum tarihi gelecekte olamaz.')
        return value
