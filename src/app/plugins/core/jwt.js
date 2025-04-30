import jwt from '@fastify/jwt';

async function fp(fastify, opts) {
    const secret = '210491210491210491';  // Secret key to sign the JWT token
    fastify.register(jwt, { secret });
}

export default fp;
