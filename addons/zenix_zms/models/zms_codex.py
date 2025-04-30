# -*- coding: utf-8 -*-
import logging
import re
import string
import secrets

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)

# Pola Regex untuk validasi Codex: Alphanumeric (a-z, A-Z, 0-9), tepat 8 karakter
CODEX_PATTERN = r'^[a-zA-Z0-9]{8}$'

class ZmsCodex(models.Model):
    _name = 'zms.codex'
    _description = 'ZMS Codex Registry'
    _order = 'id desc' # Urutkan berdasarkan ID terbaru secara default

    name = fields.Char(
        string='Codex',
        required=True,
        index=True,     # Index untuk pencarian cepat & constraint
        copy=False,     # Codex harus unik, jangan copy langsung
        size=8,         # Batasan ukuran (meski validasi lebih kuat)
        help="Unique 8-character alphanumeric code (a-z, A-Z, 0-9)."
    )
    model_id = fields.Many2one(
        'ir.model',
        string='Model',
        required=True,
        index=True,
        ondelete='cascade', # Jika definisi model dihapus, entri codex ini tidak valid lagi
        help="Model technical name this codex refers to."
    )
    # Gunakan Integer untuk res_id, karena ID Odoo adalah integer
    res_id = fields.Integer(
        string='Record ID',
        required=True,
        index=True,
        help="ID of the record in the target model."
    )
    # Field Reference untuk link langsung di UI (Opsional tapi sangat berguna)

    # --- SQL Constraints ---
    _sql_constraints = [
        # 1. Codex (name) harus unik di seluruh tabel zms.codex
        ('codex_name_uniq', 'UNIQUE(name)', 'The Codex code must be unique across all records!'),
        # 2. Kombinasi Model + Record ID harus unik (satu record hanya punya satu codex)
        ('codex_model_res_id_uniq', 'UNIQUE(model_id, res_id)', 'A Codex entry already exists for this specific record!'),
    ]

    # --- Python Constraints ---
    @api.constrains('name')
    def _check_codex_format(self):
        """Validates the Codex format: 8 alphanumeric characters."""
        for record in self:
            if record.name and not re.fullmatch(CODEX_PATTERN, record.name):
                raise ValidationError(
                    _("Invalid Codex format: '%(codex)s'. Must be 8 alphanumeric characters.", codex=record.name)
                )

    # --- Helper Methods ---
    @api.model
    def _select_codex_models(self):
        """Defines which models can have a Codex entry."""
        # Mulai dengan model 'zms.device', tambahkan model lain jika perlu
        return [('zms.device', 'ZMS Device')]


    # --- Logika Generator Kode ---
    @api.model
    def _generate_unique_codex_code(self):
        """Generates a unique 8-character alphanumeric code string."""
        alphabet = string.ascii_letters + string.digits
        codex_length = 8
        max_attempts = 100 # Safety limit

        for _attempt in range(max_attempts):
            new_codex = ''.join(secrets.choice(alphabet) for _ in range(codex_length))
            # Cek keunikan di tabel ini (zms.codex)
            if not self.search_count([('name', '=', new_codex)]):
                _logger.info("Generated unique codex code: %s", new_codex)
                return new_codex

        _logger.error("Could not generate a unique codex code after %d attempts.", max_attempts)
        raise UserError(_("System failed to generate a unique Codex code. Please try the operation again or contact support."))

    # --- Method Utama untuk Assign Codex ---
    @api.model
    def assign_codex_to_record(self, model_name, res_id):
        """
        Generates a unique codex and creates a registry entry.
        Returns the newly created zms.codex recordset.
        """
        if not model_name or not res_id:
            raise UserError(_("Model name and Record ID are required to assign a codex."))
        _logger.info("Assigning codex requested for model '%s', record ID %d", model_name, res_id)

        # Cari model ID menggunakan method _get yang lebih aman
        model_odoo = self.env['ir.model']._get(model_name)
        if not model_odoo:
             _logger.error("Could not find ir.model for technical name '%s'", model_name)
             raise UserError(_("System configuration error: Model '%s' not found. Cannot assign Codex.", model_name))

        # Cek apakah record ini sudah punya codex (untuk idempotency)
        existing_codex = self.search([
            ('model_id', '=', model_odoo.id),
            ('res_id', '=', res_id)
        ], limit=1)
        if existing_codex:
            _logger.warning("Codex assignment requested for %s,%d but codex '%s' already exists (ID: %d). Returning existing.",
                            model_name, res_id, existing_codex.name, existing_codex.id)
            return existing_codex # Kembalikan yang sudah ada

        # Generate kode unik BARU
        new_codex_code = self._generate_unique_codex_code() # Panggil method internal

        # Buat entri registry
        try:
            # Gunakan sudo() untuk memastikan bisa create dari konteks mana saja
            codex_entry = self.sudo().create({
                'name': new_codex_code,
                'model_id': model_odoo.id,
                'res_id': res_id,
            })
            _logger.info("Created ZMS Codex entry ID %d for %s,%d with code '%s'",
                         codex_entry.id, model_name, res_id, new_codex_code)
            # Kembalikan recordset yang baru dibuat
            return codex_entry
        except Exception as e:
            _logger.error(
                "Failed to create ZMS Codex registry entry for %s,%d (code '%s'). Error: %s",
                model_name, res_id, new_codex_code, e, exc_info=True
            )
            # Error saat create registry setelah kode digenerate
            raise UserError(_(
                "Failed to register Codex '%(code)s' for record %(model)s,%(id)d: %(error)s",
                code=new_codex_code, model=model_name, id=res_id, error=e
            )) from e