import threading
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import random
import string
import requests
import json
import threading
from datetime import datetime, timezone
import time
_logger = logging.getLogger('odoo.addons.orbit_agent')


class OrbitAgent(models.Model):
    _name = 'orbit.agent'
    _description = 'OrbitAgent'
    _inherit = [
        'portal.mixin',
        'mail.thread.cc',
        'utm.mixin',
        'rating.mixin',
        'mail.activity.mixin',
        'mail.tracking.duration.mixin',
    ]

    name = fields.Char('Name', required=True)
    role = fields.Text('Role')
    status = fields.Selection([
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ], string='Status', default='active')
    task_ids = fields.One2many('project.task', 'agent_id', string='Tasks')
    total_tasks = fields.Integer(
        compute='_compute_total_tasks', string='Total Tasks')
    project_ids = fields.Many2many('project.project', string='Projects')
    project_count = fields.Integer(
        compute='_compute_project_count', string='Project Count')
    model_id = fields.Many2one(
        'orbit.model.llm', string='Model', help="Model used by this agent.")
    company_ids = fields.Many2many('res.company', string='Companies')
    resource_ids = fields.Many2many('ir.model', string='Resources')
    user_id = fields.Many2one('res.users', string='Related User')

    @api.depends('task_ids')
    def _compute_total_tasks(self):
        for record in self:
            record.total_tasks = len(record.task_ids)

    @api.depends('project_ids')
    def _compute_project_count(self):
        for record in self:
            record.project_count = len(record.project_ids)

    def action_create_user(self):
        for agent in self:
            if agent.user_id:
                raise UserError(_("User already exists for this agent."))

            def generate_random_string(length=5):
                return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

            random_id = generate_random_string(5)
            random_name = f"agent-{random_id}"
            login_name = f"agent-{random_id}"

            def generate_unique_login():
                while True:
                    random_login = f"agent-{generate_random_string(5)}"
                    existing_user = self.env['res.users'].search(
                        [('login', '=', random_login)], limit=1)
                    if not existing_user:
                        return random_login

            login_name = generate_unique_login()

            new_user = self.env['res.users'].create({
                'name': random_name,
                'login': login_name,
                'email': f'{login_name}@example.com',
                'company_ids': [(6, 0, agent.company_ids.ids)],
                'company_id': agent.company_ids[0].id if agent.company_ids else self.env.company.id,
            })

            agent.user_id = new_user

    def get_external_reply(self, prompt, session_id=None):
        """
        Memanggil API eksternal dan mengembalikan hasil reply.
        """
        url = "http://160.22.193.35:78/webhook/46116445-3b13-48c0-9a38-cd034bee92ac"
        sessionID = f"{self._name}-{self.id}-{int(datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())}"
        payload = {
            "prompt": prompt,
            "sessionID": sessionID
        }
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json'
        }

        _logger.info("[OrbitAgent] Sending request to external API")
        _logger.info("Request URL: %s", url)
        _logger.info("Payload: %s", json.dumps(payload, indent=2))
        _logger.info("Headers: %s", headers)

        try:
            response = requests.post(
                url, headers=headers, data=json.dumps(payload), timeout=3600)
            _logger.info("API status code: %s", response.status_code)

            response.raise_for_status()
            result = response.json()

            _logger.info("API Response JSON: %s", json.dumps(result, indent=2))
            output = result.get("output", "Tidak ada respon dari server.")
            _logger.info("Extracted AI Output: %s", output)

            return output
        except Exception as e:
            _logger.error(
                "API Error (OrbitAgent.get_external_reply): %s", str(e))
            return f"[API Error] {str(e)}"


class MailMessage(models.Model):
    _inherit = 'mail.message'

    def _process_ai_reply_async(self, agent, prompt, session_id):
        try:
            _logger.info(
                "Async call for agent ID %s with prompt: %s", agent.id, prompt)
            reply_text = agent.get_external_reply(
                prompt=prompt, session_id=session_id)
            _logger.info("AI reply: %s", reply_text)

            # Buat cursor dan env baru karena threading tidak punya context env asli
            with self.pool.cursor() as new_cr:
                new_env = api.Environment(new_cr, self._uid, self._context)
                agent_rec = new_env['orbit.agent'].browse(agent.id)
                agent_rec.message_post(
                    body=reply_text,
                    message_type='comment',
                    author_id=agent_rec.user_id.partner_id.id
                )
                new_cr.commit()

        except Exception as e:
            _logger.error(
                "Error in async AI reply for agent %s: %s", agent.id, str(e))

    @api.model_create_multi
    def create(self, vals_list):
        _logger.info("Creating mail.message records: %s", vals_list)
        records = super().create(vals_list)

        for message in records:
            try:
                if message.model == 'orbit.agent' and message.message_type == 'comment':
                    agent = self.env['orbit.agent'].browse(message.res_id)
                    if not agent or not agent.user_id:
                        _logger.warning("Agent or agent user not found.")
                        continue

                    if message.author_id != agent.user_id.partner_id:
                        _logger.info(
                            "Preparing AI reply for agent %s", agent.id)

                        event = threading.Event()
                        result_holder = {}

                        # Thread untuk memanggil API
                        def request_ai_response():
                            try:
                                reply_text = agent.get_external_reply(
                                    prompt=message.body or "",
                                    session_id=str(agent.user_id.id)
                                )
                                result_holder['reply'] = reply_text
                                event.set()
                            except Exception as e:
                                _logger.error("Error calling AI: %s", e)

                        # Thread fallback jika timeout
                        def fallback_background_reply():
                            _logger.info(
                                "Fallback async AI started after 10 seconds delay...")
                            self._process_ai_reply_async(
                                agent, message.body or "", str(agent.user_id.id))

                        # Jalankan thread utama request
                        request_thread = threading.Thread(
                            target=request_ai_response, daemon=True)
                        request_thread.start()

                        # Tunggu 10 detik, kalau belum selesai -> fallback async
                        if not event.wait(timeout=60):
                            fallback_thread = threading.Thread(
                                target=fallback_background_reply, daemon=True)
                            fallback_thread.start()
                        else:
                            # Jika respon diterima tepat waktu, simpan langsung
                            reply_text = result_holder.get('reply')
                            if reply_text:
                                message.with_env(self.env).sudo().create({
                                    'model': 'orbit.agent',
                                    'res_id': agent.id,
                                    'body': reply_text,
                                    'message_type': 'comment',
                                    'author_id': agent.user_id.partner_id.id
                                })

            except Exception as err:
                _logger.error("Error processing message ID %s: %s",
                              message.id, str(err))

        return records
