# -*- coding: utf-8 -*-
import logging
from datetime import date, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class OrbitSecretVault(models.Model):
    _name = 'orbit.secret.vault'
    _description = 'Orbit Secret Vault'
    _inherit = ['mail.thread']
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True, tracking=True)
    secret_type = fields.Selection([
        ('api_key', 'API Key'),
        ('password', 'Password'),
        ('token', 'Token'),
        ('other', 'Other'),
    ], string='Secret Type', required=True, tracking=True,
        help="Jenis rahasia yang disimpan seperti API Key, password, token, atau lainnya.")
    url = fields.Char(string='URL', tracking=True)
    access = fields.Char(string='Username / Login', tracking=True)
    secret_value = fields.Text(
        string='Secret Value', required=True, tracking=True)
    description = fields.Text(string='Description')
    owner_id = fields.Many2one(
        'res.users', string='Owner', default=lambda self: self.env.user, readonly=True)
    expiration_date = fields.Date(string='Expiration Date', tracking=True)
    is_expired = fields.Boolean(
        string='Expired', compute='_compute_is_expired', store=True)

    _sql_constraints = [
        ('unique_name', 'unique(name)', 'The vault entry name must be unique!'),
    ]

    @api.depends('expiration_date')
    def _compute_is_expired(self):
        today = date.today()
        for record in self:
            record.is_expired = bool(
                record.expiration_date and record.expiration_date < today)

    @api.model
    def _notify_expiring_secrets(self):
        threshold = date.today() + timedelta(days=5)
        soon_expiring = self.search([
            ('expiration_date', '<=', threshold),
            ('expiration_date', '>=', date.today())
        ])
        for secret in soon_expiring:
            _logger.info("Secret '%s' will expire soon (on %s)",
                         secret.name, secret.expiration_date)
            secret.message_post(
                body=_(
                    "Reminder: This secret will expire on <b>%s</b>.") % secret.expiration_date,
                subject="Secret Expiration Notice",
                message_type="notification"
            )
    # Schedule this method to run daily using Odoo's automated actions or cron jobs
    # to ensure users are notified about expiring secrets.
    # You can also create a scheduled action in Odoo to call this method daily.
    # This can be done in the Odoo UI under Settings > Technical > Automation > Scheduled Actions.
    # Example of a scheduled action:
    # {
    #     'name': 'Notify Expiring Secrets',
    #     'model_id': model_id,  # Replace with the actual model ID     