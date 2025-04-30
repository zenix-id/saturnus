import Fastify from 'fastify';
import cuid from 'cuid';
import path from 'path';


// Function to build the Fastify server
const buildServer = (logger) => {
  const fastify = Fastify({
    genReqId: () => cuid(),
    logger: logger,
  });

  

  fastify.get('/', async (request, reply) => {
    fastify.log.info('Hello endpoint accessed');
    return { hello: 'world' };
  });

  return fastify;
};

export default buildServer;
