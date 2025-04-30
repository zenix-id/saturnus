# models/orbit_model_llm.py
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
from logging import getLogger
import requests  # Make sure the 'requests' library is available in your Odoo environment

_logger = getLogger(__name__)


class OrbitModelLlm(models.Model):
    _name = 'orbit.model.llm'
    _description = 'LLM Model Configuration'

    # _inherit = ['mail.thread', 'mail.alias.mixin',
    #             'mail.activity.mixin', 'rating.mixin']
    name = fields.Char(
        'Model ID / Name',
        help="The unique identifier or name of the model (e.g., 'gpt-4o', 'llama3-70b'). Can be set manually or copied from the connection test results.",
        index=True
    )
    display_name_label = fields.Char(
        'Display Name',
        compute='_compute_display_name_label',
        store=False
    )
    base_url = fields.Char('Base URL', required=True)
    api_key = fields.Char('API Key', required=True)
    provider = fields.Selection([
        ('openai', 'OpenAI'),
        ('azure', 'Azure'),
        ('google', 'Google'),
        ('other', 'Other'),
        ('orbit', 'Orbit'),
        ('anthropic', 'Anthropic'),
        ('cohere', 'Cohere'),
        ('huggingface', 'Hugging Face'),
        ('llama_index', 'Llama Index'),
        ('replicate', 'Replicate'),
        ('stability_ai', 'Stability AI'),
        ('open_router', 'Open Router'),
    ], string='Provider', default='orbit', required=True)

    @api.depends('name', 'provider')
    def _compute_display_name_label(self):
        """Computes a user-friendly display name."""
        for record in self:
            provider_label = dict(self._fields['provider'].selection).get(
                record.provider, record.provider)
            record.display_name_label = f"{provider_label}: {record.name}" if record.name else provider_label

    def name_get(self):
        """Uses the computed display name for record identification."""
        result = []
        for record in self:
            result.append((record.id, record.display_name_label))
        return result

    @api.onchange('provider')
    def _onchange_provider_set_base_url(self):
        """Suggests a default Base URL based on the selected provider."""
        provider_urls = {
            'openai': 'https://api.openai.com/v1',
            'azure': 'https://<your-resource-name>.openai.azure.com',
            'google': 'https://generativelanguage.googleapis.com',
            'anthropic': 'https://api.anthropic.com/v1',
            'cohere': 'https://api.cohere.ai/v1',
            'huggingface': 'https://api-inference.huggingface.co',
            'llama_index': 'http://localhost:8000',
            'replicate': 'https://api.replicate.com/v1',
            'stability_ai': 'https://api.stability.ai/v1',
            'open_router': 'https://openrouter.ai/api/v1',
            'orbit': 'http://localhost:1337/v1',
        }
        self.base_url = provider_urls.get(self.provider, '')

    def _process_and_select_models(self, models_data):
        """
        Processes the raw model data list, sorts it with 'free' models prioritized,
        and returns a formatted string of the top 10 models.
        """
        if not models_data:
            return "No models found."

        processed_models = []
        for model in models_data:
            # Use 'id' as the primary identifier, fallback to 'name' if 'id' is missing (unlikely but safe)
            model_id = model.get('id')
            # Use 'name' for display, fallback to 'id'
            display_name = model.get('name', model_id)

            if not model_id:
                continue  # Skip models without an ID

            # Check if 'free' exists in the ID or display name (case-insensitive)
            is_free = 'free' in str(model_id).lower(
            ) or 'free' in str(display_name).lower()
            processed_models.append(
                {'id': model_id, 'display': display_name, 'is_free': is_free})

        # Sort models: free models first, then alphabetically by display name
        # Sorting by boolean `is_free` descending (True comes first)
        processed_models.sort(key=lambda x: (
            not x['is_free'], x['display'].lower()))

        # Get top 10 models
        top_models = processed_models[:10]

        # Format the output string
        if not top_models:
            return "No models found after processing."

        # Create a list string, using the ID (which is often what users need to configure)
        model_list_str = "\n".join(
            [f"- {model['id']}" for model in top_models])
        count = len(models_data)
        message = f"Found {count} models.\nTop {len(top_models)} available models (priority to 'free'):\n{model_list_str}"
        return message

    def test_connection(self):
        """
        Tests connection, fetches models, and displays the total count
        along with a list of top 10 models (prioritizing 'free').
        """
        self.ensure_one()

        if not self.api_key or not self.base_url:
            raise UserError(
                "API Key and Base URL must be set to test the connection.")

        models_url = f"{self.base_url.rstrip('/')}/models"
        headers = {'Authorization': f'Bearer {self.api_key}'}

        _logger.info(
            f"Testing connection to {models_url} for provider {self.provider}")

        notification_params = {
            'sticky': False,  # Default to non-sticky
        }

        try:
            # Increased timeout slightly
            response = requests.get(models_url, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()

            if isinstance(data, dict) and 'data' in data and isinstance(data['data'], list):
                models_list_info = self._process_and_select_models(
                    data['data'])
                notification_params.update({
                    'title': 'Connection Successful',
                    'message': models_list_info,  # Use the processed list
                    'type': 'success',
                    'sticky': True,  # Make sticky to allow user to copy model names
                })
            else:
                _logger.warning(
                    f"Connection successful but unexpected data structure from {models_url}: {str(data)[:200]}...")
                notification_params.update({
                    'title': 'Connection Successful (Warning)',
                    'message': f"Connected, but the response format was unexpected. Expected JSON with a 'data' list. Check API documentation.",
                    'type': 'warning',
                    'sticky': True,
                })

        # Error handling remains the same as previous version
        except requests.exceptions.Timeout:
            _logger.warning(f"Timeout connecting to {models_url}")
            notification_params.update({
                'title': 'Connection Failed',
                'message': f"Connection timed out when trying to reach {models_url}. Check the Base URL and network.",
                'type': 'danger', 'sticky': True,
            })
        except requests.exceptions.HTTPError as http_err:
            error_details = f"Server returned status {http_err.response.status_code}."
            try:
                error_body = http_err.response.json()
                error_details += f"\nDetails: {str(error_body)[:200]}"
            except ValueError:
                error_details += f"\nResponse: {http_err.response.text[:200]}"
            _logger.warning(
                f"HTTP error connecting to {models_url}: {http_err} - {error_details}")
            notification_params.update({
                'title': 'Connection Failed',
                'message': f"Failed to connect. {error_details}\nCheck Base URL and API Key.",
                'type': 'danger', 'sticky': True,
            })
        except requests.exceptions.RequestException as req_err:
            _logger.error(f"Connection error for {models_url}: {req_err}")
            notification_params.update({
                'title': 'Connection Failed',
                'message': f"Could not connect to the API endpoint: {models_url}\nError: {req_err}",
                'type': 'danger', 'sticky': True,
            })
        except ValueError as json_err:
            _logger.error(
                f"Failed to decode JSON response from {models_url}: {json_err}")
            notification_params.update({
                'title': 'Connection Error',
                'message': f"Received an invalid response from the server (not valid JSON).\nCheck the Base URL.",
                'type': 'danger', 'sticky': True,
            })
        except Exception as e:
            _logger.exception(
                f"Unexpected error during connection test for {self.id}: {e}")
            notification_params.update({
                'title': 'Connection Test Error',
                'message': f'An unexpected error occurred: {e}',
                'type': 'danger', 'sticky': True,
            })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': notification_params
        }

# Ensure the button in your XML view calls this 'test_connection' method:
# <button name="test_connection" string="Test Connection" type="object" class="oe_highlight"/>
