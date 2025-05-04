// src\index.js
import { HOST, PORT, SECRET } from './config/server.js';
import logger from './config/logger.js';
import buildServer from './app/server.js';
import routeNofavicon from 'fastify-no-icon';
import jwt from '@fastify/jwt';
import conbackend from './app/backend.js'; // Corrected import name if needed
import fpcookie from '@fastify/cookie';
import auth from './app/routes/auth.js'
import oauth from './app/routes/oauth.js'
import latency from './app/routes/tools/latency.js';
import fastifySensible from '@fastify/sensible'; // <-- Import fastify-sensible
const start = async () => {
  const fastify = buildServer(logger);
  try {
    console.log('SECRET:', SECRET); // Good practice to label console logs

    // --- Register Plugins ---
    await fastify.register(routeNofavicon);
    await fastify.register(jwt, {
      secret: SECRET,
      cookie: {
        cookieName: 'refreshToken',
        sign: {
          expiresIn: '30d', // Corrected: expiresIn should be inside sign options for cookie
        },
      },
    });
    await fastify.register(fpcookie);
    await fastify.register(fastifySensible)
    await fastify.register(conbackend); // Register your backend plugin
    await fastify.register(auth)
    await fastify.register(oauth)
    await fastify.register(latency)
    await fastify.get('/token', async (request, reply) => {
      const token = fastify.jwt.sign({ name: 'exatel' /* or user details */ }, { expiresIn: '30d' });

      return { token };
    });
    // fastify.addHook('onRequest', (request) => request.jwtVerify({onlyCookie: true}))
    // --- Wait for Plugins to be Ready ---
    // Crucial step: Ensures all plugins, including conbackend and its decorators, are loaded.
    await fastify.ready();
    fastify.log.info('Fastify plugins registered and ready.');

    // await fastify.addHook('onRequest', (request) => request.jwtVerify({onlyCookie: true}))
    
    // --- Start Listening ---
    await fastify.listen({ port: PORT, host: HOST });
    // Removed the log here as buildServer already logs it on successful listen
    // fastify.log.info(`Server listening on ${HOST}:${PORT}`); // Already logged by buildServer usually

  } catch (err) {
    // Enhanced logging to capture the error details
    fastify.log.error(`Error starting server: ${err.message}`);
    fastify.log.error(err); // Log the full error object
    process.exit(1); // Exit with failure
  }
};

start();