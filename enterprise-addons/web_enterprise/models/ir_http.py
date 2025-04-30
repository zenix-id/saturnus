# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json

from odoo import models
from odoo.http import request


class Http(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _post_logout(cls):
        super()._post_logout()
        request.future_response.set_cookie('color_scheme', max_age=0)

    def webclient_rendering_context(self):
        """ Overrides community to prevent unnecessary load_menus request """
        return {
            'session_info': self.session_info(),
        }

    def session_info(self):
        ICP = self.env['ir.config_parameter'].sudo()

        # Original logic (dibiarkan sebagai komentar)
        # if self.env.user.has_group('base.group_system'):
        #     warn_enterprise = 'admin'
        # elif self.env.user._is_internal():
        #     warn_enterprise = 'user'
        # else:
        #     warn_enterprise = False

        # Force Enterprise always
        warn_enterprise = 'user'  # or 'admin' if you want full access feel

        result = super(Http, self).session_info()
        result['support_url'] = "https://www.zenix.id/help"
        if warn_enterprise:
            result['warning'] = warn_enterprise
            result['expiration_date'] = ICP.get_param('database.expiration_date') or '2099-12-31'
            result['expiration_reason'] = ICP.get_param('database.expiration_reason') or 'Trial'
        return result
