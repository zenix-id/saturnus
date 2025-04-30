# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ZenixZmsDevice(models.Model):
    _name = 'zenix.zms.device'
    _description = 'ZenixZmsDevice'

    name = fields.Char('Name')
