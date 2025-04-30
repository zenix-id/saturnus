# -*- coding: utf-8 -*-
import logging
import re

# Impor _ untuk terjemahan pesan error di dalam utilitas ini
from odoo.tools.translate import _
# Impor ValidationError agar bisa di-raise dari sini jika aturan strict gagal
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# --- Konstanta untuk Pola Karakter ---
# Karakter dasar yang pasti diizinkan dalam format strict atau setelah sanitasi (tanpa spasi)
_VALID_CHARS_BASE = r'a-zA-Z0-9_'
_VALID_CHARS_HYPHEN = r'a-zA-Z0-9_-' # Termasuk hyphen
# Pola untuk mendeteksi karakter yang *memaksa* sanitasi
_INVALID_CHARS_PATTERN = re.compile(r'[^a-zA-Z0-9_\-\s]') # Apapun yg bukan huruf, angka, _, -, spasi

# --- Definisi Aturan dan Fungsi Aplikasi ---

def apply_rule(raw_name, rule):
    """
    Applies the specified sanitization/validation rule to the raw name.

    :param raw_name: The original string input.
    :param rule: The string identifier of the rule to apply
                 (e.g., 'strict_no_space_lower', 'sanitize_lower_underscore').
    :return: The processed string name.
    :raises: ValidationError if a 'strict' rule is violated.
    """
    if not raw_name:
        return raw_name # Return empty/None as is

    name = str(raw_name).strip() # Work with stripped string copy
    original_name = raw_name # Keep original for logging/messages in case of error

    _logger.debug("Applying rule '%s' to name '%s' (original: '%s')", rule, name, original_name)

    if rule == 'strict_no_space_lower':
        pattern = r'^[a-z0-9_]+$'
        if not re.fullmatch(pattern, name):
             # Gunakan _() untuk terjemahan pesan error
             raise ValidationError(
                _("Device Name '%(name)s' must contain only lowercase letters (a-z), numbers (0-9), and underscores (_).") % {'name': original_name}
             )
        return name

    elif rule == 'strict_no_space_anycase':
        pattern = r'^[a-zA-Z0-9_]+$'
        if not re.fullmatch(pattern, name):
            raise ValidationError(
                _("Device Name '%(name)s' must contain only letters (a-z, A-Z), numbers (0-9), and underscores (_).") % {'name': original_name}
            )
        return name

    elif rule == 'sanitize_lower_hyphen':
        name = name.lower()
        name = re.sub(r'[\s_]+', '-', name)        # Spaces/underscores to hyphens
        name = re.sub(r'[^a-z0-9-]+', '', name)   # Remove non-alphanumeric or hyphen
        name = name.strip('-')                    # Trim leading/trailing hyphens
        name = re.sub(r'-{2,}', '-', name)        # Prevent double hyphens
        return name

    elif rule == 'sanitize_lower_underscore':
        name = name.lower()
        name = re.sub(r'[\s-]+', '_', name)        # Spaces/hyphens to underscores
        name = re.sub(r'[^a-z0-9_]+', '', name)   # Remove non-alphanumeric or underscore
        name = name.strip('_')                    # Trim leading/trailing underscores
        name = re.sub(r'_{2,}', '_', name)        # Prevent double underscores
        return name

    elif rule == 'allow_any_keep_case':
        # Action utama (stripping) sudah dilakukan di awal
        return name

    # Fallback jika rule tidak dikenal
    _logger.warning("Unknown device name rule '%s' encountered in apply_rule. Applying default sanitization (lowercase, underscore).", rule)
    name = name.lower()
    name = re.sub(r'[\s-]+', '_', name)
    name = re.sub(r'[^a-z0-9_]+', '', name)
    name = name.strip('_')
    name = re.sub(r'_{2,}', '_', name)
    # Pastikan tidak kosong setelah fallback sanitization
    if not name:
         _logger.error("Fallback sanitization for '%s' resulted in an empty string.", original_name)
         # Mungkin lebih baik raise error di sini daripada mengembalikan string kosong
         raise ValidationError(_("Processing name '%s' resulted in an empty string after fallback sanitization.", original_name))
    return name

# --- Fungsi Heuristik untuk Menentukan Aturan ---

def determine_rule(name_to_check):
    """
    Analyzes the input name and suggests the most appropriate rule identifier string.

    :param name_to_check: The original string input to analyze.
    :return: String identifier of the suggested rule.
    """
    if not name_to_check:
        return 'allow_any_keep_case' # Aturan tidak relevan untuk string kosong

    name = str(name_to_check).strip()

    # 1. Check for definitely invalid characters -> Force sanitization (default: underscore)
    if _INVALID_CHARS_PATTERN.search(name):
        _logger.debug("Rule detection for '%s': Invalid characters found -> sanitize_lower_underscore", name_to_check)
        return 'sanitize_lower_underscore'

    # 2. Check for spaces -> Force sanitization (default: underscore)
    if ' ' in name:
        _logger.debug("Rule detection for '%s': Spaces found -> sanitize_lower_underscore", name_to_check)
        return 'sanitize_lower_underscore'

    # 3. Check if already conforms to a strict (or common clean) format -> Keep/validate it
    # Prioritaskan yang lebih ketat (lowercase) dulu
    if re.fullmatch(r'^[a-z0-9_]+$', name):
        _logger.debug("Rule detection for '%s': Matches strict_no_space_lower -> strict_no_space_lower", name_to_check)
        return 'strict_no_space_lower'

    if re.fullmatch(r'^[a-zA-Z0-9_]+$', name):
        _logger.debug("Rule detection for '%s': Matches strict_no_space_anycase -> strict_no_space_anycase", name_to_check)
        return 'strict_no_space_anycase'

    # Check for clean hyphenated formats (allow these without forcing change)
    if re.fullmatch(r'^[a-z0-9-]+$', name):
         _logger.debug("Rule detection for '%s': Matches clean lowercase hyphen -> allow_any_keep_case", name_to_check)
         return 'allow_any_keep_case'
    if re.fullmatch(r'^[a-zA-Z0-9-]+$', name):
         _logger.debug("Rule detection for '%s': Matches clean anycase hyphen -> allow_any_keep_case", name_to_check)
         return 'allow_any_keep_case'

    # 4. If no spaces, no invalid chars, but doesn't fit strict/clean patterns (e.g., CamelCase) -> Allow it
    _logger.debug("Rule detection for '%s': No invalid chars/spaces, doesn't fit known clean patterns -> allow_any_keep_case", name_to_check)
    return 'allow_any_keep_case'