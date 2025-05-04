# -*- coding: utf-8 -*-
import logging
import random
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ZmsTag(models.Model):
    _name = 'zms.tag'
    _description = 'ZmsTag'

    name = fields.Char('Name')
    color = fields.Integer('Color Index', default=lambda self: random.randint(0, 11), help="Color for the tag (Index)")
    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Tag name must be unique!")
    ]