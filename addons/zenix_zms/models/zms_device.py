# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from ..utils import device_name_sanitizer # Sesuaikan path jika perlu
import subprocess # Untuk menjalankan ping
import platform   # Untuk deteksi OS
_logger = logging.getLogger(__name__)

class ZmsDevice(models.Model):
    _name = 'zms.device'
    _description = 'ZMS Network Device'

    # ... (definisi field name, codex_id, codex_code, host_id, dll tetap sama) ...
    # --- Field Nama ---
    name = fields.Char(
        'Device Name', required=True, index=True, copy=False,
        help=_("Unique identifier for the device. Formatting rules might apply.")
    )
    # --- Relasi ke Codex ---
    codex_id = fields.Many2one(
        'zms.codex', string='Codex Entry', readonly=True, index=True,
        ondelete='restrict', copy=False,
        help="Link to the unique Codex registry entry for this device."
    )
    # --- Field Related ---
    codex_code = fields.Char(
        related='codex_id.name', string='Codex', store=True, readonly=True, index=True,
        help="The unique 8-character code assigned to this device."
    )
    # --- Field Lainnya ---
    host_id = fields.Many2one('zms.host', string='Host/IP', ondelete='restrict')
    device_type = fields.Selection([
        ('router', 'Router'), ('switch', 'Switch'), ('ont', 'ONT'),
        ('server', 'Server'), ('firewall', 'Firewall'), ('other', 'Other')
    ], string='Device Type', required=True)
    status = fields.Selection([
        ('active', 'Active'), ('inactive', 'Inactive'), ('maintenance', 'Under Maintenance')
    ], string='Status', default='active', required=True)
    
    secret_id = fields.Many2one(
        'zms.secret', string='Secret Vault', ondelete='set null',
        help="Link to the secret vault entry for this device."
    )
    platform = fields.Selection([('routeros', 'RouterOS'), ('linux', 'Linux'), ('windows', 'Windows')], string='Platform', required=True,default='routeros')
    # --- SQL Constraints ---
    _sql_constraints = [
        ('name_uniq', 'UNIQUE(name)', 'The Device Name must be unique!'),
        ('codex_code_uniq', 'UNIQUE(codex_code)', 'The assigned Codex code must be unique for each device!'),
    ]


    @api.model_create_multi
    def create(self, vals_list):
        """Create device first, then request/assign codex entry and link it."""
        _logger.debug("ZMS Device create called with %d vals", len(vals_list))

        # 1. Hapus field codex dari vals & proses Nama
        processed_vals_list = []
        original_names = {}
        for i, vals in enumerate(vals_list):
            vals.pop('codex_id', None); vals.pop('codex_code', None)
            if 'name' in vals and vals.get('name'):
                original_name = vals['name']
                try:
                    name_rule = device_name_sanitizer.determine_rule(original_name)
                    processed_name = device_name_sanitizer.apply_rule(original_name, name_rule)
                    if not processed_name: raise ValidationError(_("Device Name '%s' is empty.", original_name))
                    if processed_name != original_name.strip(): _logger.info("Device name processed: '%s' -> '%s'", original_name, processed_name)
                    vals['name'] = processed_name
                    original_names[i] = original_name
                except ValidationError as e: raise ValidationError(_("Invalid Device Name '%(name)s': %(error)s", name=original_name, error=e.args[0])) from e
                except Exception as e_name: raise UserError(_("Error processing name '%(name)s': %(err)s", name=original_name, err=e_name)) from e_name
            processed_vals_list.append(vals)

        # 2. Buat record device DULU
        try:
            new_devices = super(ZmsDevice, self).create(processed_vals_list)
        except Exception as e:
            # (Error handling name_uniq sama seperti sebelumnya)
            err_msg = str(e).lower()
            if 'name_uniq' in err_msg or ('unique constraint' in err_msg and 'zms_device_name_uniq' in err_msg):
                 p_name = processed_vals_list[0].get('name', 'Unknown') if processed_vals_list else 'Unknown'
                 o_name = original_names.get(0, p_name)
                 raise UserError(_("Device Name '%(name)s' (from '%(orig)s') is already in use.", name=p_name, orig=o_name)) from e
            else: _logger.error("Error creating devices: %s", e, exc_info=True); raise


        # 3. Setelah device dibuat, minta codex entry dan link-kan
        codex_model = self.env['zms.codex']
        for device in new_devices:
            codex_entry_rec = None
            try:
                codex_entry_rec = codex_model.assign_codex_to_record('zms.device', device.id)
                if not codex_entry_rec: raise UserError(_("Failed to obtain Codex entry for '%s'.", device.name))
                device.sudo().write({'codex_id': codex_entry_rec.id})
                _logger.info("Linked codex entry ID %d (Code: %s) to new device ID %d", codex_entry_rec.id, codex_entry_rec.name, device.id)
            except Exception as e_assign:
                _logger.error("CRITICAL: Failed linking Codex to device ID %d (%s). Error: %s.", device.id, device.name, e_assign, exc_info=True)
                raise UserError(_("Failed assigning Codex to '%(name)s': %(error)s. Creation aborted.", name=device.name, error=e_assign)) from e_assign

        # --- HAPUS .refresh() ---
        # new_devices.refresh() # <-- BARIS INI DIHAPUS/DIKOMENTARI

        # --- Logging (Coba akses langsung setelah write) ---
        _logger.info("--- Final Check After Create/Write (No Refresh) ---")
        for device in new_devices:
             # Akses langsung field setelah write, cache Odoo seharusnya sudah update
             codex_id_val = device.codex_id.id if device.codex_id else 'None'
             codex_code_val = device.codex_code # Coba baca related field
             _logger.info("Device ID: %d | Name: %s | Codex ID: %s | Codex Code (Related): %s",
                          device.id, device.name, codex_id_val, codex_code_val)
        _logger.info("--- End Final Check ---")
        # --------------------------------------------------

        return new_devices # Kembalikan recordset

    # ... (Method unlink, copy, write tetap sama seperti sebelumnya) ...
    # --- Override Unlink ---
    def unlink(self):
        if not self: return True
        device_ids = self.ids
        _logger.info("Unlinking %d ZMS Devices (IDs: %s)", len(device_ids), device_ids)
        codex_model = self.env['zms.codex']
        model_id = self.env['ir.model']._get_id('zms.device')
        codex_entries_to_delete = codex_model.sudo()
        if model_id: codex_entries_to_delete = codex_model.sudo().search([('model_id', '=', model_id), ('res_id', 'in', device_ids)])
        else: _logger.warning("Model 'zms.device' not found. Skipping Codex cleanup.")
        result = super(ZmsDevice, self).unlink()
        if result and codex_entries_to_delete:
            _logger.info("Deleting %d related Codex entries.", len(codex_entries_to_delete))
            try: codex_entries_to_delete.sudo().unlink()
            except Exception as e: _logger.error("Failed deleting Codex entries (IDs: %s) for unlinked devices (IDs: %s): %s", codex_entries_to_delete.ids, device_ids, e, exc_info=True)
        return result

    # --- Override Copy ---
        # --- Override Copy ---
    def copy(self, default=None):
        """Copy device first, then request/assign a NEW codex entry and link it."""
        self.ensure_one()
        if default is None: default = {}

        # Pastikan link codex tidak tercopy
        default.pop('codex_id', None)
        default.pop('codex_code', None)

        # --- Proses Nama untuk Salinan (gunakan logic dari create/utils) ---
        copied_name_base = f"{self.name}_Copy" # Basis nama awal
        try:
            # Tentukan aturan untuk nama asli (Asumsi utils masih ada)
            name_rule = device_name_sanitizer.determine_rule(self.name)
            # Terapkan aturan ke nama asli untuk dapat basis yg bersih
            clean_base = device_name_sanitizer.apply_rule(self.name, name_rule)
            copied_name_base = f"{clean_base}_Copy"
        except Exception as e_name_copy:
            _logger.warning("Could not apply name sanitization during copy prep for ID %d: %s. Using basic copy name.", self.id, e_name_copy)

        # Cari nama unik untuk salinan
        new_name = copied_name_base
        count = 1
        while self.search_count([('name', '=', new_name)]) > 0:
            count += 1
            new_name = f"{copied_name_base}{count}" # Atau basis bersih + Copy + count
            if count > 100: # Safety break
                 raise UserError(_("Could not generate a unique name for the copied device."))
        default['name'] = new_name
        _logger.info("Prepared unique name for copy: '%s'", new_name)
        # ----------------------------------------------------------

        # 1. Buat salinan device DULU dengan nama unik yg sudah disiapkan
        #    Gunakan sintaks super yang BENAR:
        new_device = super(ZmsDevice, self).copy(default=default)

        # 2. Minta codex entry BARU untuk device salinan
        codex_model = self.env['zms.codex']
        codex_entry_rec = None
        try:
            codex_entry_rec = codex_model.assign_codex_to_record('zms.device', new_device.id)
            if not codex_entry_rec:
                 raise UserError(_("Failed to obtain Codex entry for copied device '%s'.", new_device.name))

            # 3. Tulis link codex_id ke device salinan (pakai sudo jika perlu)
            new_device.sudo().write({'codex_id': codex_entry_rec.id})
            _logger.info("Linked new codex entry ID %d (Code: %s) to copied device ID %d",
                         codex_entry_rec.id, codex_entry_rec.name, new_device.id)

        except Exception as e_copy_assign:
            _logger.error(
                "CRITICAL: Failed to assign/link Codex to copied device ID %d (Original ID: %d). Error: %s. Manual correction needed!",
                new_device.id, self.id, e_copy_assign, exc_info=True
            )
            # Gagalkan proses copy agar konsisten
            raise UserError(_(
                "Failed to assign a Codex to the copied device '%(name)s': %(error)s. Copy operation failed.",
                name=new_device.name, error=e_copy_assign
            )) from e_copy_assign

        return new_device

    # --- Override Write ---
        # --- Override Write ---
    # Hapus pemeriksaan codex_id/codex_code di sini
    def action_assign_codex(self):
        """Assigns Codex to selected devices that don't have one yet."""
        _logger.info("Action 'Assign Codex' triggered for device IDs: %s", self.ids)
        codex_model = self.env['zms.codex']
        devices_updated = 0
        devices_skipped = 0
        errors = []

        # Loop melalui device yang dipilih (self adalah recordset)
        for device in self:
            # Hanya proses jika belum punya codex_id
            if not device.codex_id:
                _logger.debug("Assigning codex for device ID %d (Name: %s)", device.id, device.name)
                try:
                    # Panggil method assign dari zms.codex
                    # Method ini sudah handle cek existing dan create jika perlu
                    codex_entry_rec = codex_model.assign_codex_to_record('zms.device', device.id)
                    if codex_entry_rec:
                        # Tulis link ke device (pakai sudo jika perlu)
                        device.sudo().write({'codex_id': codex_entry_rec.id})
                        _logger.info("Successfully assigned codex '%s' (ID: %d) to device ID %d",
                                        codex_entry_rec.name, codex_entry_rec.id, device.id)
                        devices_updated += 1
                    else:
                        # Seharusnya assign_codex_to_record raise error jika gagal
                            _logger.warning("assign_codex_to_record returned None for device ID %d", device.id)
                            errors.append(f"Device ID {device.id}: Failed to obtain Codex entry.")
                            devices_skipped += 1

                except Exception as e_assign:
                    _logger.error("Error assigning codex to device ID %d: %s", device.id, e_assign, exc_info=True)
                    errors.append(f"Device ID {device.id} (Name: {device.name}): {e_assign}")
                    devices_skipped += 1
            else:
                _logger.debug("Skipping device ID %d (Name: %s), already has codex_id %d",
                                device.id, device.name, device.codex_id.id)
                devices_skipped += 1

            # Berikan feedback ke user (opsional)
            if errors:
                error_message = _("Codex assignment partially failed:\n- %d devices updated.\n- %d devices skipped (already had codex or failed).\n\nErrors:\n%s",
                                devices_updated, devices_skipped, "\n".join(errors))
                # Bisa raise warning atau hanya log, tergantung preferensi
                # raise UserError(error_message)
                _logger.error("Codex assignment errors occurred: %s", "\n".join(errors))
                # Mungkin return action untuk refresh view?
            elif devices_updated > 0:
                _logger.info("Successfully assigned codex to %d devices.", devices_updated)
                # Beri notifikasi sukses jika perlu
            else:
                _logger.info("No devices required codex assignment or none were selected.")

            # Return action untuk refresh view (opsional)
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }
    def write(self, vals):
        """Override write to handle name changes, ignore codex changes."""
        # 1. HAPUS/KOMENTARI pemeriksaan codex di awal write
        # if 'codex_id' in vals:
        #     _logger.warning("Ignoring attempt to write readonly field 'codex_id' for device(s) %s.", self.ids)
        #     vals.pop('codex_id')
        # if 'codex_code' in vals:
        #      _logger.warning("Ignoring attempt to write related field 'codex_code' for device(s) %s.", self.ids)
        #      vals.pop('codex_code')

        # 2. Proses perubahan Nama (jika ada dan utils dipakai)
        #    Logika ini tetap sama
        if 'name' in vals and vals.get('name') and len(self) == 1:
            original_name = vals['name']; current_name = self.name
            try:
                name_rule = device_name_sanitizer.determine_rule(original_name)
                processed_name = device_name_sanitizer.apply_rule(original_name, name_rule)
                if not processed_name: raise ValidationError(_("Device Name '%s' is empty.", original_name))
                if processed_name != current_name:
                    if processed_name != original_name.strip(): _logger.info("Device name processed for ID %d: '%s' -> '%s'", self.id, original_name, processed_name)
                    vals['name'] = processed_name
                else:
                    if 'name' in vals: del vals['name']
            except ValidationError as e: raise ValidationError(_("Invalid Device Name '%(name)s': %(error)s", name=original_name, error=e.args[0])) from e
            except Exception as e_name: raise UserError(_("Error processing name '%(name)s': %(err)s", name=original_name, err=e_name)) from e_name
        elif 'name' in vals and len(self) > 1: _logger.warning("Mass name update detected. Sanitization skipped.")

        # Jika vals menjadi kosong setelah proses nama (dan penghapusan codex dihilangkan)
        if not vals:
            return True # Tidak ada yang perlu di-write

        # 3. Panggil super.write dengan vals yang sudah bersih (tanpa codex dihapus paksa)
        try:
            return super(ZmsDevice, self).write(vals)
        except Exception as e:
            # Error handling tetap sama
            err_msg = str(e).lower()
            if 'name_uniq' in err_msg or 'zms_device_name_uniq' in err_msg: raise UserError(_("Device Name '%s' is already in use.", vals.get('name', ''))) from e
            # Cek codex_code_uniq sebagai pengaman tambahan
            elif 'codex_code_uniq' in err_msg or 'zms_device_codex_code_uniq' in err_msg: raise UserError(_("Codex code unique constraint failed. This indicates a potential issue in codex generation or assignment.")) from e
            else: _logger.error("Error updating device(s) %s: %s", self.ids, e, exc_info=True); raise