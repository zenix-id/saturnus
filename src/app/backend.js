import Odoo from 'odoo-await';
import dotenv from 'dotenv';
import fpPlugin from 'fastify-plugin'; // <-- Import fastify-plugin

dotenv.config();

async function conBackendPlugin(fastify, opts) {
  fastify.log.info('Registering conBackend plugin...'); // Add log

  const backendUrl = `${process.env.BASE_URL}:${process.env.BACKEND_ODOO_PORT}`;

  // Check if required environment variables are present
  if (!process.env.BASE_URL || !process.env.BACKEND_ODOO_PORT || !process.env.BACKEND_DB) {
    fastify.log.error('Missing required Odoo environment variables (BASE_URL, BACKEND_ODOO_PORT, BACKEND_DB)! Ensure .env file is loaded correctly.');
    // Using fastify-sensible to throw error as JSON response
    const errorMessage = 'Missing required Odoo environment variables.';
    const errorDetails = 'Ensure .env file is loaded correctly.';
    throw fastify.httpErrors.internalServerError(`${errorMessage} Details: ${errorDetails}`);
  } else {
    fastify.log.info(`Odoo Backend URL: ${backendUrl}, DB: ${process.env.BACKEND_DB}`);
  }

  // Decorate fastify with method `auth`
  fastify.decorate('auth', async (username, password) => {
    fastify.log.info(`Attempting Odoo connection via decorator for user: ${username}`); // Add log

    const backend = new Odoo({
      baseUrl: backendUrl,
      db: process.env.BACKEND_DB,
      username: username,
      password: password
    });

    try {
      await backend.connect();
      fastify.log.info(`Successfully connected to Odoo backend as ${username}`);
      return backend; // Return instance so it can be used in other plugins
    } catch (error) {
      fastify.log.error(error);

      throw error
    }
  });

  fastify.log.info('Successfully decorated fastify with "auth" method.'); // Add log
}

// Wrap the plugin function with fastify-plugin
// This tells Fastify not to encapsulate this plugin, making the 'auth' decorator global.
export default fpPlugin(conBackendPlugin, {
  name: 'conbackend', // Optional: A name for the plugin (good practice)
});
