# -*- coding: utf-8 -*-
{
    'name': 'Zenix_zms',
    'version': '1.0.0',
    'summary': """ Zenix_zms Summary """,
    'author': '',
    'website': '',
    'category': '',
    'depends': ['base', 'web'],
    "data": [
        "security/ir.model.access.csv",
        "security/zenix_zms_security.xml",
        "views/zms_codex_views.xml",
        "views/zms_device_views.xml",
        "views/zms_host_views.xml",
        "views/zms_secret_vault_views.xml",
        "views/zms_secret_views.xml",
        "views/zms_menu.xml",
        
    ],
    'assets': {
              'web.assets_backend': [
                  'zenix_zms/static/src/**/*'
              ],
          },
    'application': True,
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
