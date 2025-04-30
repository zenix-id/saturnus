# -*- coding: utf-8 -*-
{
    'name': 'Zenix_orbit',
    'version': '1.0.0',
    'summary': """ Zenix_orbit Summary """,
    'author': '',
    'website': '',
    'category': '',
    'depends': ['base', 'web', 'project',],
    "data": [
        "data/cron.xml",
        "security/ir.model.access.csv",
        "security/zenix_orbit_security.xml",
        "views/orbit_agent_views.xml",
        "views/orbit_model_llm_views.xml",
        "views/orbit_secret_vault_views.xml",
        "views/zenix_zms_device_views.xml"
    ],
    'assets': {
        'web.assets_backend': [
            'zenix_orbit/static/src/**/*'
        ],
    },
    'application': True,
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
