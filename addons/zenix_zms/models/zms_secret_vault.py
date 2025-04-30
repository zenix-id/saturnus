import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class ZmsSecretVault(models.Model):
    _name = 'zms.secret.vault'
    _description = 'ZMS Secret Vault'

    name = fields.Char('Login Name', required=True, help="Enter the login name or identifier for this secret.")
    user_id = fields.Many2one('res.users', string='Odoo User Ref', ondelete='set null', help="Optional: Link this secret to a specific Odoo user.")
    password = fields.Char('Password', required=True, copy=False, help="The secret password. Restricted access.")

    codex_id = fields.Many2one('zms.codex', string='Codex Entry', readonly=True, index=True, ondelete='restrict', copy=False, help="Link to the unique Codex registry entry for this secret.")
    codex_code = fields.Char(related='codex_id.name', string='Codex', store=True, readonly=True, index=True, help="The unique 8-character code assigned to this secret.") # Changed help

    _sql_constraints = [
        ('codex_code_uniq', 'UNIQUE(codex_code)', 'The assigned Codex code must be unique for each Secret Vault entry!'),
        # ('secret_name_uniq', 'UNIQUE(name)', 'The Login Name must be unique!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        _logger.debug("ZMS Secret Vault create called with %d vals", len(vals_list))
        processed_vals_list = []
        for vals in vals_list:
            vals.pop('codex_id', None); vals.pop('codex_code', None)
            processed_vals_list.append(vals)
        try:
            new_secrets = super(ZmsSecretVault, self).create(processed_vals_list)
        except Exception as e:
            _logger.error("Error creating secret vault entries: %s", e, exc_info=True)
            raise
        codex_model = self.env['zms.codex']
        for secret in new_secrets:
            codex_entry_rec = None
            try:
                codex_entry_rec = codex_model.assign_codex_to_record('zms.secret.vault', secret.id)
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
        _logger.info("Unlinking %d ZMS Secret Vault entries (IDs: %s)", len(secret_ids), secret_ids)
        codex_model = self.env['zms.codex']
        model_id = self.env['ir.model']._get_id('zms.secret.vault')
        codex_entries_to_delete = codex_model.sudo()
        if model_id: codex_entries_to_delete = codex_model.sudo().search([('model_id', '=', model_id), ('res_id', 'in', secret_ids)])
        else: _logger.warning("Model 'zms.secret.vault' not found. Skipping ZMS Codex cleanup.")
        result = super(ZmsSecretVault, self).unlink()
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
        new_secret = super(ZmsSecretVault, self).copy(default=default)
        codex_model = self.env['zms.codex']
        codex_entry_rec = None
        try:
            codex_entry_rec = codex_model.assign_codex_to_record('zms.secret.vault', new_secret.id)
            if not codex_entry_rec: raise UserError(_("Failed to obtain Codex entry for copied secret vault '%s'.", new_secret.name))
            new_secret.sudo().write({'codex_id': codex_entry_rec.id})
            _logger.info("Linked new codex entry ID %d (Code: %s) to copied secret vault ID %d", codex_entry_rec.id, codex_entry_rec.name, new_secret.id)
        except Exception as e_copy_assign:
            _logger.error("CRITICAL: Failed assigning/linking Codex to copied secret vault ID %d (Original ID: %d). Error: %s. Manual correction needed!", new_secret.id, self.id, e_copy_assign, exc_info=True)
            raise UserError(_("Failed assigning Codex to copied secret '%(name)s': %(error)s. Copy operation failed.", name=new_secret.name, error=e_copy_assign)) from e_copy_assign
        return new_secret

    def write(self, vals):
        return super(ZmsSecretVault, self).write(vals)