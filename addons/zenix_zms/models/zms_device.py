# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import subprocess # Untuk menjalankan ping
import platform   # Untuk deteksi OS
_logger = logging.getLogger(__name__)
HARDCODED_LATENCY_API_URL = "http://192.168.1.102:4000/api/latency"
from urllib.parse import urlencode
import requests # Untuk memanggil API Latency
import json     # Untuk parsing JSON response

class ZmsDevice(models.Model):
    _name = 'zms.device'
    _description = 'ZMS Network Device'
    # _rec_name = 'display_name'

    # --- Field Nama (Computed) ---
    name = fields.Char(
        'Device Identifier (System)',
        required=True,          # Keep NOT NULL constraint
        index=True,
        copy=False,             # Avoid copying the computed name directly
        readonly=True,
        compute='_compute_device_name',
        store=True,
        default='-',            # Temporary default for initial INSERT
        help=_("System-generated unique identifier: role-type-codex_code. Auto-updated after save.")
    )
    # --- Field untuk Input User (Opsional) ---
    # display_name = fields.Char('Device Name', required=True, index=True)

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
    host_id = fields.Many2one('zms.host', required=True, string='Host/IP', ondelete='restrict')
    type = fields.Selection([
        ('rtr', 'Router'), ('swch', 'Switch'), ('ont', 'ONT'), ('srv', 'Server'),
        ('fw', 'Firewall'), ('ap', 'Access Point'), ('mdm', 'Modem'),
        ('stg', 'Storage Device'), ('ups', 'UPS'), ('ws', 'Workstation'), ('otr', 'Other')
    ], string='Device Type', default='rtr', required=True, tracking=True)

    status = fields.Selection([
        ('act', 'Active'), ('inact', 'Inactive'), ('maint', 'Under Maintenance'), ('decom', 'Decommissioned')
    ], string='Status', default='act', required=True, tracking=True)

    role = fields.Selection([
        ('core', 'Core'), ('dist', 'Distribution'), ('acc', 'Access'), ('edge', 'Edge'),
        ('srv', 'Server'), ('stg', 'Storage'), ('bkp', 'Backup'), ('mon', 'Monitoring'),
        ('sec', 'Security'), ('otr', 'Other')
    ], string='Role', default='core', required=True, tracking=True)

    secret_id = fields.Many2one(
        'zms.secret', string='Secret Vault', ondelete='set null',
        help="Link to the secret vault entry for this device."
    )
    platform = fields.Selection([
        ('routeros', 'RouterOS'), ('mktk', 'MikroTik'), ('openwrt', 'OpenWRT'),
        ('vyos', 'VyOS'), ('pfsense', 'pfSense'), ('ios', 'Cisco IOS'),
        ('nxos', 'Cisco NX-OS'), ('junoss', 'Juniper JunOS'), ('linux', 'Linux'),
        ('debian', 'Debian'), ('ubuntu', 'Ubuntu'), ('centos', 'CentOS'),
        ('rhel', 'RHEL'), ('alpine', 'Alpine'), ('windows', 'Windows Server'),
        ('esxi', 'ESXi'), ('proxmox', 'Proxmox'), ('otr', 'Other')
    ], string='Platform', default='routeros', required=True)
    location = fields.Selection([
        ('dc', 'Data Center'), ('netrm', 'Network Room'), ('srvrm', 'Server Room'),
        ('telco', 'Telecom Room'), ('hq', 'Office HQ'), ('branch', 'Office Branch'),
        ('rmte', 'Remote Site'), ('cloud', 'Cloud'), ('lab', 'Lab'), ('wh', 'Warehouse'),
        ('colo', 'Colocation'), ('edge', 'Edge Site'), ('campus', 'Campus'),
        ('tower', 'Tower/BTS'), ('fact', 'Factory'), ('unk', 'Unknown')
    ], string='Location', default='dc', required=True)
    platform_version = fields.Char(string='Platform Version')
    notes = fields.Text(string='Notes')
    latency_ms = fields.Integer(
        string='Last Latency (ms)', readonly=True, copy=False,
        help="Last measured latency to this device's host in milliseconds. Updated via 'Check Latency'."
    )

    # --- SQL Constraints ---
    _sql_constraints = [
        ('name_uniq', 'UNIQUE(name)', 'The generated Device Identifier must be unique! Potential codex collision or data issue.'),
        ('codex_code_uniq', 'UNIQUE(codex_code)', 'The assigned Codex code must be unique for each device!'),
        # ('display_name_uniq', 'UNIQUE(display_name)', 'The Device Name must be unique!'),
    ]

    @api.depends('role', 'type', 'codex_code')
    def _compute_device_name(self):
        """Computes the device name based on role, type, and codex_code."""
        for device in self:
            if device.role and device.type and device.codex_code:
                device.name = f"{device.role}-{device.type}-{device.codex_code}"
            else:
                 if not device.name or device.name == '-':
                      device.name = '-'

    @api.model_create_multi
    def create(self, vals_list):
        _logger.debug("ZMS Device create called with %d vals", len(vals_list))
        processed_vals_list = []
        for i, vals in enumerate(vals_list):
            vals.pop('name', None)
            vals.pop('codex_id', None)
            vals.pop('codex_code', None)
            if not vals.get('role'): raise ValidationError(_("Device Role is required."))
            if not vals.get('type'): raise ValidationError(_("Device Type is required."))
            if not vals.get('host_id'): raise ValidationError(_("Host/IP is required."))
            processed_vals_list.append(vals)

        try:
            new_devices = super().create(processed_vals_list)
        except Exception as e:
             err_msg = str(e).lower()
             if 'name_uniq' in err_msg or 'zms_device_name_uniq' in err_msg:
                 _logger.error("Unique constraint violation during initial device creation (on default name?): %s", e, exc_info=True)
                 raise UserError(_("Failed to create device due to an unexpected naming conflict. Please try again.")) from e
             elif 'not-null constraint' in err_msg and '"name"' in err_msg:
                 _logger.error("Unexpected NotNullViolation on 'name' despite default: %s", e, exc_info=True)
                 raise UserError(_("Internal error: Failed setting initial device name. Please contact administrator.")) from e
             else:
                _logger.error("Error creating devices: %s", e, exc_info=True); raise

        codex_model = self.env['zms.codex']
        for device in new_devices:
            codex_entry_rec = None
            try:
                codex_entry_rec = codex_model.assign_codex_to_record('zms.device', device.id)
                if not codex_entry_rec:
                    _logger.error("Failed to obtain Codex entry for potentially created device ID %d.", device.id)
                    raise UserError(_("Failed to obtain Codex entry. Device creation aborted."))
                # Write codex_id. This triggers the @api.depends for _compute_device_name
                device.sudo().write({'codex_id': codex_entry_rec.id})
                _logger.info("Linked codex entry ID %d (Code: %s) to new device ID %d. Name should recompute.",
                             codex_entry_rec.id, codex_entry_rec.name, device.id)
            except Exception as e_assign:
                _logger.error("CRITICAL: Failed linking Codex to device ID %d. Error: %s.", device.id, e_assign, exc_info=True)
                raise UserError(_("Failed assigning Codex: %s. Creation aborted.", e_assign)) from e_assign

        # *** REMOVED: new_devices.refresh() ***
        # The compute mechanism should handle the update automatically before commit.

        _logger.info("--- Final Check After Create/Write (In-Memory Values) ---")
        for device in new_devices:
             # Log the name value as it is in memory right now
             _logger.info("Device ID: %d | Current In-Memory Name: %s | Role: %s | Type: %s | Codex ID: %s | Codex Code: %s",
                          device.id, device.name, device.role, device.type, device.codex_id.id, device.codex_code)
        _logger.info("--- End Final Check ---")

        return new_devices

    # --- Override Unlink --- (No changes needed)
    def unlink(self):
        if not self: return True
        device_ids = self.ids
        _logger.info("Unlinking %d ZMS Devices (IDs: %s)", len(device_ids), device_ids)
        # ... (rest of unlink logic remains the same) ...
        codex_model = self.env['zms.codex']
        model_id = self.env['ir.model']._get_id('zms.device')
        codex_entries_to_delete = codex_model.sudo()
        if model_id:
            codex_entries_to_delete = codex_model.sudo().search([
                ('model_id', '=', model_id), ('res_id', 'in', device_ids)
            ])
        else: _logger.warning("Model 'zms.device' not found. Skipping Codex cleanup.")
        result = super(ZmsDevice, self).unlink()
        if result and codex_entries_to_delete:
            codex_ids_deleted = codex_entries_to_delete.ids
            _logger.info("Attempting to delete %d related Codex entries (IDs: %s) for unlinked devices.", len(codex_entries_to_delete), codex_ids_deleted)
            try:
                codex_entries_to_delete.sudo().unlink()
                _logger.info("Successfully deleted %d Codex entries.", len(codex_ids_deleted))
            except Exception as e: _logger.error("Failed deleting Codex entries (IDs: %s) for unlinked devices: %s", codex_ids_deleted, e, exc_info=True)
        return result


    # --- Override Copy --- (Removed refresh call here too for consistency)
    def copy(self, default=None):
        self.ensure_one()
        _logger.info("Copying device ID %d (Current Name: %s)", self.id, self.name)
        if default is None: default = {}
        default.pop('name', None)
        default.pop('codex_id', None)
        default.pop('codex_code', None)
        default.pop('latency_ms', None)

        new_device = super().copy(default=default)
        _logger.info("Device copied to new ID %d (Initial Name: %s). Assigning new codex...", new_device.id, new_device.name)

        codex_model = self.env['zms.codex']
        codex_entry_rec = None
        try:
            codex_entry_rec = codex_model.assign_codex_to_record('zms.device', new_device.id)
            if not codex_entry_rec:
                 _logger.error("Failed to obtain new Codex entry for copied device ID %d.", new_device.id)
                 raise UserError(_("Failed to obtain Codex entry for the copied device. Copy aborted."))
            new_device.sudo().write({'codex_id': codex_entry_rec.id})

            # *** REMOVED: new_device.refresh() ***
            # Let compute mechanism handle the update.

            _logger.info("Linked new codex entry ID %d (Code: %s) to copied device ID %d. Final Name (in memory): %s",
                         codex_entry_rec.id, codex_entry_rec.name, new_device.id, new_device.name)
        except Exception as e_copy_assign:
             _logger.error("CRITICAL: Failed assigning/linking Codex to copied device ID %d (Original ID: %d). Error: %s.", new_device.id, self.id, e_copy_assign, exc_info=True)
             raise UserError(_("Failed assigning Codex to the copied device: %s. Copy operation failed.", e_copy_assign)) from e_copy_assign
        return new_device

    # --- Override Write --- (No changes needed)
    def write(self, vals):
        _logger.debug("ZMS Device write called for IDs %s with vals: %s", self.ids, vals)
        # ... (rest of write logic remains the same) ...
        if 'role' in vals and not vals.get('role'): raise ValidationError(_("Device Role cannot be empty."))
        if 'type' in vals and not vals.get('type'): raise ValidationError(_("Device Type cannot be empty."))
        if 'name' in vals:
            if vals['name'] == '-' and len(self) == 1 and self.name != '-':
                 _logger.warning("Attempted to write temporary default '-' to computed field 'name' for ID %s. Ignoring.", self.ids)
                 vals.pop('name')
            elif vals['name'] != '-':
                 _logger.warning("Attempted to write directly to computed field 'name' for IDs %s. Ignoring 'name' value: %s", self.ids, vals['name'])
                 vals.pop('name')
            else: vals.pop('name')
        if not vals: return True
        try:
            res = super().write(vals)
            _logger.info("Write successful for IDs %s. Name recomputation (if needed) was triggered.", self.ids)
            return res
        except Exception as e:
            err_msg = str(e).lower()
            if 'name_uniq' in err_msg or 'zms_device_name_uniq' in err_msg:
                 _logger.error("Unique constraint violation on 'name' during write for IDs %s: %s", self.ids, e)
                 raise UserError(_("Saving failed: The resulting Device Identifier ('role-type-codex') is already in use by another device.")) from e
            elif 'codex_code_uniq' in err_msg or 'zms_device_codex_code_uniq' in err_msg:
                 _logger.error("Unique constraint violation on 'codex_code' during write for IDs %s: %s", self.ids, e)
                 raise UserError(_("Codex code unique constraint failed.")) from e
            else: _logger.error("Error updating device(s) %s: %s", self.ids, e, exc_info=True); raise

    # --- Action Assign Codex --- (Removed refresh call here too)
    def action_assign_codex(self):
        _logger.info("Action 'Assign Codex' triggered for device IDs: %s", self.ids)
        codex_model = self.env['zms.codex']
        devices_updated = 0
        devices_skipped = 0
        errors = []
        devices_needing_codex = self.filtered(lambda d: not d.codex_id)
        _logger.info("%d devices out of %d selected need a codex.", len(devices_needing_codex), len(self))

        for device in devices_needing_codex:
            _logger.debug("Assigning codex for device ID %d (Current Name: %s)", device.id, device.name)
            try:
                codex_entry_rec = codex_model.assign_codex_to_record('zms.device', device.id)
                if codex_entry_rec:
                    device.sudo().write({'codex_id': codex_entry_rec.id})
                    # *** REMOVED: device.refresh() ***
                    _logger.info("Successfully assigned codex '%s' (ID: %d) to device ID %d. New Name (in memory): %s",
                                    codex_entry_rec.name, codex_entry_rec.id, device.id, device.name)
                    devices_updated += 1
                else:
                    _logger.warning("assign_codex_to_record returned None for device ID %d", device.id)
                    errors.append(f"Device ID {device.id}: Failed to obtain Codex entry.")
                    devices_skipped += 1
            except Exception as e_assign:
                _logger.error("Error assigning codex to device ID %d: %s", device.id, e_assign, exc_info=True)
                errors.append(f"Device ID {device.id} (Name: {device.name}): {e_assign}")
                devices_skipped += 1

        devices_skipped += (len(self) - len(devices_needing_codex))
        # ... (rest of action_assign_codex feedback logic remains the same) ...
        if errors:
            error_message = _("Codex assignment finished with errors:\n- %d devices updated.\n- %d devices skipped (already had codex or failed).\n\nErrors:\n%s",
                            devices_updated, devices_skipped, "\n".join(errors))
            _logger.error("Codex assignment errors occurred: %s", "\n".join(errors))
            return {
                'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('Codex Assignment Failed'), 'message': error_message, 'sticky': True, 'type': 'danger'}
            }
        elif devices_updated > 0:
            _logger.info("Successfully assigned codex to %d devices.", devices_updated)
            return {
                'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('Codex Assigned'), 'message': _('Successfully assigned codex to %d device(s).', devices_updated), 'sticky': False, 'type': 'success'}
            }
        else:
            _logger.info("No devices required codex assignment or none were selected/found needing one.")
            return {
                'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('Codex Assignment'), 'message': _('No devices required a new codex assignment.'), 'sticky': False, 'type': 'info'}
            }

    def _find_or_create_tags(self, tag_names_to_ensure):
        """
        Finds existing tags or creates new ones based on names.
        Returns a list of tag IDs.
        """
        tag_model = self.env['zms.tag']
        tag_ids_to_link = []
        valid_tag_names = list(tag_names_to_ensure) # Assume input is a list/set of valid strings
        if not valid_tag_names:
            return []

        existing_tags = tag_model.search([('name', 'in', valid_tag_names)])
        existing_tag_map = {tag.name: tag.id for tag in existing_tags}
        tag_ids_to_link.extend(existing_tags.ids)

        tags_to_create = set(valid_tag_names) - set(existing_tag_map.keys())

        newly_created_tags = []
        if tags_to_create:
            for tag_name in tags_to_create:
                try:
                    new_tag = tag_model.create({'name': tag_name})
                    newly_created_tags.append(new_tag)
                    _logger.info(f"Created new tag: '{tag_name}' (ID: {new_tag.id})")
                except Exception as tag_create_err:
                    _logger.error(f"Failed to create tag '{tag_name}': {tag_create_err}", exc_info=True)

            tag_ids_to_link.extend(tag.id for tag in newly_created_tags)
        return tag_ids_to_link
    # --- Method Cek Latency --- (No changes needed)
    def action_check_device_latency(self):
        metric_model = self.env['zms.metric']
        # --- Use Hardcoded URL ---
        api_target_url = HARDCODED_LATENCY_API_URL
        # --- End Hardcoded URL ---

        updates_to_perform = {}
        error_messages = []
        devices_to_check = self
        _logger.info("--- action_check_device_latency START ---")
        _logger.info("Total devices selected: %d (IDs: %s)", len(devices_to_check), devices_to_check.ids)

        devices_without_host = devices_to_check.filtered(lambda d: not d.host_id or not d.host_id.name)
        if devices_without_host:
            _logger.info("Devices skipped due to missing Host/IP: %d (IDs: %s)", len(devices_without_host), devices_without_host.ids)
            for dev in devices_without_host:
                _logger.warning("Skipping latency check for Device '%s' (ID: %s): Host/IP is not set.", dev.name or dev.id, dev.id)
                updates_to_perform[dev.id] = None

        valid_devices = devices_to_check - devices_without_host
        _logger.info("Number of valid devices to check: %d (IDs: %s)", len(valid_devices), valid_devices.ids)

        if not valid_devices and not devices_without_host:
             _logger.info("No devices were selected. Exiting check.")
             return { 'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': _('Latency Check'), 'message': _('No devices were selected.'), 'sticky': False, 'type': 'info'} }

        if valid_devices:
            for device in valid_devices:
                host_target = device.host_id.name.strip()
                params = {'host': host_target}
                latency_value_for_metric = None # Store float/int value for metric

                try: encoded_params = urlencode(params); full_api_url_with_params = f"{api_target_url}?{encoded_params}"
                except Exception as e_url: _logger.error("Error encoding URL params for Device ID %s, Host %s: %s", device.id, host_target, e_url); error_messages.append(f"Device {device.name or device.id} (Host: {host_target}): Error preparing API request URL."); updates_to_perform[device.id] = None; continue

                _logger.info("[Device ID: %s] Calling API: %s", device.id, full_api_url_with_params)
                try:
                    response = requests.get(full_api_url_with_params, timeout=10); _logger.info("[Device ID: %s] API Status Code: %s", device.id, response.status_code); response.raise_for_status()
                    try:
                        data = response.json(); _logger.info("[Device ID: %s] API Response: %s", device.id, data)
                        if data.get('statusCode') == 200 and 'latency' in data:
                            latency_val = data.get('latency')
                            latency_int = None
                            try:
                                latency_float = float(latency_val)
                                latency_int = int(round(latency_float))
                                updates_to_perform[device.id] = latency_int
                                latency_value_for_metric = latency_float
                                _logger.info("[Device ID: %s] Success: Latency %s ms (Rounded to %d for device field)", device.id, latency_val, latency_int)
                            except (ValueError, TypeError):
                                _logger.error("[Device ID: %s] Invalid numeric latency format '%s'. Resp: %s", device.id, latency_val, data); error_messages.append(f"Device {device.name or device.id} (Host: {host_target}): Invalid latency format ({latency_val})."); updates_to_perform[device.id] = None
                        else:
                             error_msg = data.get('message', 'Unknown API issue'); api_err = data.get('error', ''); latency_detail = data.get('latency_detail', ''); full_error = f"{error_msg}{f' ({api_err})' if api_err else ''}{f' [{latency_detail}]' if latency_detail else ''}"; _logger.warning("[Device ID: %s] API issue: %s. Resp: %s", device.id, full_error, data); error_messages.append(f"Device {device.name or device.id} (Host: {host_target}): API issue - {full_error}"); updates_to_perform[device.id] = None

                        # <<< START: METRIC & TAG HANDLING >>>
                        if latency_value_for_metric is not None:
                            tag_names_to_ensure = set()
                            if device.codex_code:
                                tag_names_to_ensure.add(f"codex:{device.codex_code}")
                            else:
                                _logger.warning(f"[Device ID: {device.id}] Skipping codex tag for metric as codex_code is missing.")
                            tag_names_to_ensure.add("metric:latency")

                            if tag_names_to_ensure:
                                metric_tag_ids = self._find_or_create_tags(tag_names_to_ensure)

                                if metric_tag_ids:
                                    metric_values = {
                                        'value': latency_value_for_metric,
                                        'tag_ids': [(6, 0, metric_tag_ids)]
                                    }
                                    try:
                                        new_metric = metric_model.create(metric_values)
                                        _logger.info(f"[Device ID: {device.id}] Created metric record ID {new_metric.id} with value {latency_value_for_metric} and tags {metric_tag_ids}")
                                    except Exception as metric_create_err:
                                        _logger.error(f"[Device ID: {device.id}] Failed to create metric record for latency {latency_value_for_metric}: {metric_create_err}", exc_info=True)
                                        error_messages.append(f"Device {device.name or device.id} (Host: {host_target}): Failed to create metric record.") # Add specific error
                                else:
                                     _logger.warning(f"[Device ID: {device.id}] Skipping metric creation as tag creation/retrieval failed.")
                            else:
                                _logger.warning(f"[Device ID: {device.id}] Skipping metric creation as no valid tags could be determined.")

                        # <<< END: METRIC & TAG HANDLING >>>

                    except json.JSONDecodeError: _logger.error("[Device ID: %s] Invalid JSON. URL: %s. Status: %s, Body: %s", device.id, full_api_url_with_params, response.status_code, response.text[:500], exc_info=True); error_messages.append(f"Device {device.name or device.id} (Host: {host_target}): Invalid JSON response from API."); updates_to_perform[device.id] = None
                except requests.exceptions.Timeout: _logger.error("[Device ID: %s] Timeout: %s", device.id, full_api_url_with_params); error_messages.append(f"Device {device.name or device.id} (Host: {host_target}): Request timed out."); updates_to_perform[device.id] = None
                except requests.exceptions.ConnectionError as conn_err: _logger.error("[Device ID: %s] Connection error: %s: %s", device.id, full_api_url_with_params, conn_err); error_messages.append(f"Device {device.name or device.id} (Host: {host_target}): Cannot connect to Latency API ({api_target_url})."); updates_to_perform[device.id] = None
                except requests.exceptions.HTTPError as http_err:
                    status_code = http_err.response.status_code if http_err.response else 'N/A'; error_text = http_err.response.text[:500] if http_err.response else 'No response text'; _logger.error("[Device ID: %s] HTTP error %s: %s. Resp: %s", device.id, status_code, full_api_url_with_params, error_text, exc_info=True); api_message = f"API ({api_target_url}) status {status_code}"
                    try:
                        if http_err.response: error_data = http_err.response.json(); api_message = error_data.get('message', api_message); api_error_detail = error_data.get('error', ''); api_message += f" ({api_error_detail})" if api_error_detail else ''; latency_detail = error_data.get('latency_detail', ''); api_message += f" [{latency_detail}]" if latency_detail else ''
                    except json.JSONDecodeError: pass
                    error_messages.append(f"Device {device.name or device.id} (Host: {host_target}): {api_message}"); updates_to_perform[device.id] = None
                except requests.exceptions.RequestException as req_err: _logger.error("[Device ID: %s] Request error: %s", device.id, req_err, exc_info=True); error_messages.append(f"Device {device.name or device.id} (Host: {host_target}): Network request failed ({req_err})."); updates_to_perform[device.id] = None
                except Exception as general_err:
                     _logger.error("[Device ID: %s] Unexpected error during latency check for host %s: %s", device.id, host_target, general_err, exc_info=True); error_messages.append(f"Device {device.name or device.id} (Host: {host_target}): Unexpected error ({type(general_err).__name__})."); updates_to_perform[device.id] = None


        _logger.info("--- Updating Device Latency Fields ---")
        updated_count = 0; failed_to_update_count = 0; null_update_count = 0
        if updates_to_perform:
            _logger.info("Writing latency updates for %d devices.", len(updates_to_perform))
            devices_to_update = self.browse(updates_to_perform.keys())
            for device in devices_to_update:
                latency_value = updates_to_perform.get(device.id); _logger.debug("[Device ID: %s] Writing latency_ms = %s", device.id, latency_value)
                try:
                    device.write({'latency_ms': latency_value})
                    if latency_value is not None: updated_count += 1
                    else: null_update_count += 1
                    _logger.debug("[Device ID: %s] Device write successful.", device.id)
                except Exception as write_err:
                    _logger.error("[Device ID: %s] Failed write latency %s: %s", device.id, latency_value, write_err, exc_info=True)
                    err_msg_key = f"Device {device.name or device.id} (ID {device.id})"
                    if not any(msg.startswith(err_msg_key) for msg in error_messages):
                         error_messages.append(f"{err_msg_key}: Failed to save latency update to device.")
                    failed_to_update_count += 1

        # --- Final Logging & Notification ---
        total_processed = len(valid_devices)
        error_count = len(error_messages)
        reset_count = null_update_count + len(devices_without_host) # includes skipped devices

        _logger.info("Latency check finished. Attempted: %d. Success (value): %d. Resets/Skipped: %d. Failed device writes: %d. API/Network/Metric Errors: %d",
                     total_processed, updated_count, reset_count, failed_to_update_count, error_count - failed_to_update_count)
        _logger.info("--- action_check_device_latency END ---")

        final_message = ""; final_notif_type = 'info';
        success_count = updated_count

        if error_count > 0:
             error_summary = "\n- ".join(error_messages[:5])
             if error_count > 5: error_summary += f"\n- ... ({error_count - 5} more issues, check logs)"
             final_message = _(
                 'Latency check completed with issues (%d).\n' # Simpler message header
                 'Successful device updates: %d.\n'
                 'Resets/Skipped: %d.\n\n'
                 'Issues found:\n- %s',
                 error_count, success_count, reset_count, error_summary
             )
             final_notif_type = 'warning'
        elif success_count > 0:
            final_message = _('Successfully updated latency for %d device(s).', success_count)
            if reset_count > 0:
                 final_message += _(' (%d devices were skipped or had latency reset).', reset_count)
            final_notif_type = 'success'
        elif reset_count > 0:
             final_message = _('Latency check completed. %d devices were skipped or had latency reset (e.g., missing host, check failures).', reset_count)
             final_notif_type = 'info'
        elif not devices_to_check:
            final_message = _('No devices were selected for latency check.')
            final_notif_type = 'info'
        else: # Should not happen if valid_devices > 0 unless all API calls fail without errors added?
            final_message = _('Latency check ran, but no updates or errors occurred (check logs).')
            final_notif_type = 'info'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Latency Check Result'),
                'message': final_message,
                'sticky': (final_notif_type != 'success'),
                'type': final_notif_type,
            }
        }