# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ZmsMetric(models.Model):
    _name = 'zms.metric'
    _description = 'ZmsMetric'

    value = fields.Float('Value', help="Value of the metric")
    tag_ids = fields.Many2many(
        'zms.tag',
        string='Tags',
        help="Tags associated with the metric",
    )
