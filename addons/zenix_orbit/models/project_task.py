# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ProjectTask(models.Model):
    _inherit = 'project.task'

    agent_id = fields.Many2one(
        'orbit.agent',
        string='Agent',
        domain="[('status', '=', 'active')]",
        help="Agent responsible for this task.",
    )
