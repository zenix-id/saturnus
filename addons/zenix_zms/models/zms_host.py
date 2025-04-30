# -*- coding: utf-8 -*-

import logging
import re
from odoo import models, fields, api
from odoo.exceptions import ValidationError

# Menambahkan logger untuk memantau proses
_logger = logging.getLogger(__name__)

class ZmsHost(models.Model):
    _name = 'zms.host'
    _description = 'ZMS Host Configuration' # Deskripsi yang lebih informatif

    name = fields.Char(
        'Host', 
        required=True, 
        help="Enter a valid IPv4, IPv6, FQDN, or URL (e.g., 192.168.1.1, fe80::1, server.example.com, https://mydevice.com)"
    )
    type = fields.Selection([
        ('ipv4', 'IPv4 Address'),
        ('ipv6', 'IPv6 Address'),
        ('fqdn', 'FQDN'),
        ('url', 'URL')
    ], string='Host Type', readonly=True, compute='_compute_host_type', store=True, # Gunakan compute field untuk konsistensi
       help="Automatically determined based on the Host value.")
    
    device_ids = fields.One2many('zms.device', 'host_id', string='Associated Devices')
    
    # Regex Patterns (didefinisikan di level class agar lebih rapi)
    # Mengizinkan whitespace di awal/akhir untuk dicek di onchange/compute
    _ipv4_pattern = (
        r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
        r'(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    )
    
    # Pola IPv6 yang lebih fleksibel (termasuk ::) - Sesuaikan jika perlu
    _ipv6_pattern = (
        r'(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|'
        r'([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|'
        r'([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|'
        r'([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|'
        r':((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|'
        r'::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|'
        r'([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))'
    )
    # Pola FQDN yang lebih ketat (tidak mengizinkan '.' atau '-' di awal/akhir label)
    _fqdn_pattern = (
       r'^((?!-)[A-Za-z0-9-]{1,63}(?<!-)\.)+[A-Za-z]{2,63}$'
    )
    # Pola URL yang lebih baik (opsional http/https, domain)
    _url_pattern = (
        r'^(https?:\/\/)?' # Protokol opsional
        r'((([a-z\d]([a-z\d-]*[a-z\d])*)\.)+[a-z]{2,}|' # nama domain
        r'((\d{1,3}\.){3}\d{1,3}))' # ATAU ip (v4) address
        r'(\:\d+)?(\/[-a-z\d%_.~+]*)*' # port dan path opsional
        r'(\?[;&a-z\d%_.~+=-]*)?' # query string opsional
        r'(\#[-a-z\d_]*)?$' # fragment opsional
        , re.IGNORECASE) # Case insensitive
    codex_id = fields.Many2one('zms.codex', string='Codex Entry', readonly=True, index=True, ondelete='restrict', copy=False, help="Link to the unique Codex registry entry for this secret.")
    codex_code = fields.Char(related='codex_id.name', string='Codex', store=True, readonly=True, index=True, help="The unique 8-character code assigned to this secret.") # Changed help
    __sql_constraints = [
        ('codex_code_uniq', 'UNIQUE(codex_code)', 'The assigned Codex code must be unique for each Secret Vault entry!'),
        ('secret_name_uniq', 'UNIQUE(name)', 'The Login Name must be unique!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        _logger.debug("ZMS Host create called with %d vals", len(vals_list))
        processed_vals_list = []
        for vals in vals_list:
            vals.pop('codex_id', None); vals.pop('codex_code', None)
            processed_vals_list.append(vals)
        try:
            new_secrets = super(ZmsHost, self).create(processed_vals_list)
        except Exception as e:
            _logger.error("Error creating secret vault entries: %s", e, exc_info=True)
            raise
        codex_model = self.env['zms.codex']
        for secret in new_secrets:
            codex_entry_rec = None
            try:
                codex_entry_rec = codex_model.assign_codex_to_record('zms.host', secret.id)
                if not codex_entry_rec: raise UserError(_("Failed to obtain a Codex entry for the new secret vault '%s'.", secret.name))
                secret.sudo().write({'codex_id': codex_entry_rec.id})
                _logger.info("Linked codex entry ID %d (Code: %s) to new secret vault ID %d", codex_entry_rec.id, codex_entry_rec.name, secret.id)
            except Exception as e_assign:
                _logger.error("CRITICAL: Failed assigning/linking Codex to new secret vault ID %d (%s). Error: %s. Manual correction needed!", secret.id, secret.name, e_assign, exc_info=True)
                raise UserError(_("Failed assigning Codex to new secret '%(name)s': %(error)s. Creation aborted.", name=secret.name, error=e_assign)) from e_assign
        _logger.info("--- Final Check Secret Vault Create ---")
        for secret in new_secrets: _logger.info("Secret ID: %d | Name: %s | Codex ID: %s | Codex Code: %s", secret.id, secret.name, secret.codex_id.id if secret.codex_id else 'None', secret.codex_code)
        _logger.info("--- End Final Check ---")
        return new_secrets

    def unlink(self):
        if not self: return True
        secret_ids = self.ids
        _logger.info("Unlinking %d ZMS Host entries (IDs: %s)", len(secret_ids), secret_ids)
        codex_model = self.env['zms.codex']
        model_id = self.env['ir.model']._get_id('zms.host')
        codex_entries_to_delete = codex_model.sudo()
        if model_id: codex_entries_to_delete = codex_model.sudo().search([('model_id', '=', model_id), ('res_id', 'in', secret_ids)])
        else: _logger.warning("Model 'zms.host' not found. Skipping ZMS Codex cleanup.")
        result = super(ZmsHost, self).unlink()
        if result and codex_entries_to_delete:
            _logger.info("Secret vaults unlinked. Deleting %d corresponding ZMS Codex entries.", len(codex_entries_to_delete))
            try: codex_entries_to_delete.sudo().unlink()
            except Exception as e: _logger.error("Failed deleting Codex entries (IDs: %s) for unlinked secrets (IDs: %s): %s", codex_entries_to_delete.ids, secret_ids, e, exc_info=True)
        return result

    def copy(self, default=None):
        self.ensure_one()
        if default is None: default = {}
        default.pop('codex_id', None); default.pop('codex_code', None); default.pop('password', None)
        # default['name'] = f"{self.name}_Copy" # Add name handling if needed
        new_secret = super(ZmsHost, self).copy(default=default)
        codex_model = self.env['zms.codex']
        codex_entry_rec = None
        try:
            codex_entry_rec = codex_model.assign_codex_to_record('zms.host', new_secret.id)
            if not codex_entry_rec: raise UserError(_("Failed to obtain Codex entry for copied secret vault '%s'.", new_secret.name))
            new_secret.sudo().write({'codex_id': codex_entry_rec.id})
            _logger.info("Linked new codex entry ID %d (Code: %s) to copied secret vault ID %d", codex_entry_rec.id, codex_entry_rec.name, new_secret.id)
        except Exception as e_copy_assign:
            _logger.error("CRITICAL: Failed assigning/linking Codex to copied secret vault ID %d (Original ID: %d). Error: %s. Manual correction needed!", new_secret.id, self.id, e_copy_assign, exc_info=True)
            raise UserError(_("Failed assigning Codex to copied secret '%(name)s': %(error)s. Copy operation failed.", name=new_secret.name, error=e_copy_assign)) from e_copy_assign
        return new_secret

    def write(self, vals):
        return super(ZmsHost, self).write(vals)
    
    @api.depends('name')
    def _compute_host_type(self):
        """
        Menentukan tipe host berdasarkan nilai field 'name'.
        Membersihkan whitespace sebelum validasi.
        Method ini menggantikan _onchange_host_set_type untuk keandalan.
        """
        for record in self:
            host_name = record.name.strip() if record.name else ''
            record.type = False # Default jika tidak cocok atau kosong

            if not host_name:
                _logger.debug("Host name is empty for record ID %s, type set to False.", record.id or 'new')
                continue # Lanjut ke record berikutnya jika nama kosong

            _logger.info("Computing type for host: '%s' (stripped from '%s')", host_name, record.name)

            # Cek IPv4
            if re.fullmatch(self._ipv4_pattern, host_name): # Gunakan fullmatch untuk kecocokan seluruh string
                _logger.info("IPv4 match found: %s", host_name)
                record.type = 'ipv4'
            
            # Cek IPv6
            elif re.fullmatch(self._ipv6_pattern, host_name, re.IGNORECASE): # Abaikan case untuk IPv6
                _logger.info("IPv6 match found: %s", host_name)
                record.type = 'ipv6'

            # Cek FQDN (setelah IPv4/IPv6 karena IP bisa dianggap FQDN oleh pola yg kurang ketat)
            elif re.fullmatch(self._fqdn_pattern, host_name, re.IGNORECASE):
                 _logger.info("FQDN match found: %s", host_name)
                 record.type = 'fqdn'

            # Cek URL (terakhir, karena bisa mengandung IP/FQDN)
            elif re.fullmatch(self._url_pattern, host_name):
                _logger.info("URL match found: %s", host_name)
                record.type = 'url'

            # Tidak ada kecocokan
            else:
                _logger.warning("No valid host type match found for: '%s'", host_name)
                # Biarkan record.type tetap False


    @api.constrains('name', 'type') # Tambahkan type ke constraint
    def _check_valid_host(self):
        """
        Memastikan bahwa host yang disimpan memiliki tipe yang valid.
        Constraint ini berjalan setelah compute field dihitung saat save.
        """
        for record in self:
            # Log nilai yang dicek oleh constraint
            _logger.info(
                "Constraint Check: Record ID %s, Host Name='%s', Host Type='%s'",
                record.id or 'new', record.name, record.type
            )

            # Periksa apakah 'type' telah berhasil dihitung (tidak False)
            # Jika 'name' ada tapi 'type' False, berarti validasi di compute gagal.
            if record.name and not record.type:
                 # Ambil nama yang sudah dibersihkan untuk pesan error
                 host_name_stripped = record.name.strip() if record.name else ''
                 _logger.error(
                     "Invalid host detected by constraint: Name='%s' (Stripped='%s'), Type resolved to '%s'",
                     record.name, host_name_stripped, record.type
                 )
                 raise ValidationError(
                    f"Invalid host: '{host_name_stripped}'. "
                    "Must be a valid IPv4, IPv6, FQDN, or URL. "
                    "Please check the format and remove any extra characters or spaces."
                )
            elif record.type:
                _logger.info(
                    "Valid host confirmed by constraint: Record ID %s, Name='%s', Type='%s'",
                    record.id or 'new', record.name, record.type
                )
            # Jika record.name kosong, tidak perlu error, field 'name' sudah required=True